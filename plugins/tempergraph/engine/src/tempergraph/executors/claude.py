"""The `claude` executor: one headless Claude Code session per step attempt or judge run (ECC).

Argv is built from the constants of ECC §2.3 and §2.4 and values from the binding table or engine-checked
numbers (ECC-AC-1, SEC-B1). The prompt goes on stdin (EXI-B2). The stream is mapped by ECC §2.5 and
failures are classified by ECC §2.6 from structured facts and one exact text match (ECC-B5).
"""

from __future__ import annotations

import functools
import json
import os
import re
import shutil
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from tempergraph.contracts import (
    Capabilities,
    ErrorKind,
    Event,
    EventSink,
    InfraCause,
    ProbeReport,
    SessionRequest,
    SessionResult,
    Usage,
    ViewSet,
)
from tempergraph.executors import binding as binding_mod
from tempergraph.executors.capabilities import CLAUDE, tool_names
from tempergraph.executors.launcher import LaunchSpec, RawOutcome, StopRequest, launch, run_probe
from tempergraph.executors.session import Summary, build_result, killed_by_os, process_cause, summarize
from tempergraph.executors.summary import capability_of, input_summary
from tempergraph.security.scrub import clip, scrub

NAME = "claude"
BINARY = "claude"
BASE_ARGV = ("-p", "--output-format", "stream-json", "--verbose")
ALWAYS_DISALLOWED = "EnterWorktree,ExitWorktree"
JUDGE_TOOLS = ("Read", "Grep", "Glob")
REQUEST_TIMED_OUT = "Request timed out"  # ECC §2.6: exact equality only
THROTTLE_CATEGORIES = frozenset({"rate_limit", "overloaded"})
CONNECTION_CATEGORIES = frozenset({"connection_error", "network_error"})
AUTH_CATEGORY = "authentication_failed"
BUDGET_SUBTYPE = "error_max_budget_usd"  # shape to be confirmed by P-CC-3
GATEWAY_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK",
                "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY")
PROBED_FLAGS = ("--permission-prompts", "--bare", "--tools", "--setting-sources", "--max-budget-usd",
                "--fallback-model", "--effort", "--plugin-dir", "--strict-mcp-config")
_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+)")
_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})


# ---------------------------------------------------------------------------------------------
# Argv (ECC §2.3, §2.4)


SELF_CHECK = "tempergraph self-check "


def allow_rules(tools: tuple[str, ...], commands: tuple[str, ...], in_engine_worktree: bool) -> list[str]:
    """ECC §2.2 allow rules for the declared capabilities; never an absolute path (ECC-B1)."""
    rules: list[str] = []
    for cap in tools:
        if cap in ("edit", "write"):
            if in_engine_worktree:
                rules.append(("Edit" if cap == "edit" else "Write") + "(./**)")
        elif cap == "shell":
            rules.extend(f"Bash({c} *)" for c in commands)
        elif cap == "subagent":
            rules.append("Agent")
        else:
            rules.extend(tool_names(CLAUDE, cap))
    # the check preview is granted as one exact command even when the step declares no shell (CHK §2.5)
    rules.extend(f"Bash({c})" for c in commands if c.startswith(SELF_CHECK))
    return list(dict.fromkeys(rules))


def builtin_tools(tools: tuple[str, ...]) -> list[str]:
    names: list[str] = []
    for cap in tools:
        if cap.startswith("mcp:"):
            continue
        names.extend(tool_names(CLAUDE, cap)[:1])
    return list(dict.fromkeys(names))


def _with_preview(names: list[str], commands: tuple[str, ...]) -> list[str]:
    """Under `--tools`, the check preview needs the shell tool itself; the allow rule keeps it to one command."""
    return list(dict.fromkeys([*names, "Bash"])) if any(c.startswith(SELF_CHECK) for c in commands) else names


def step_argv(req: SessionRequest, model: str | None, fallback: str | None, flags: frozenset[str],
              mcp_config: Path | None = None) -> tuple[list[str], tuple[str, ...]]:
    argv = [BINARY, *BASE_ARGV, "--permission-mode", "acceptEdits" if req.in_engine_worktree else "default"]
    if "--permission-prompts" in flags:
        argv += ["--permission-prompts", "none"]
    if model is not None:
        argv += ["--model", model]
    rules = allow_rules(req.tools, req.commands, req.in_engine_worktree)
    if rules:
        argv += ["--allowedTools", ",".join(rules)]
    if req.enforce_tools:
        argv += ["--tools", ",".join(_with_preview(builtin_tools(req.tools), req.commands))]
    argv += ["--disallowedTools", ALWAYS_DISALLOWED]
    if req.enforce_tools and mcp_config is not None and any(t.startswith("mcp:") for t in req.tools):
        argv += ["--strict-mcp-config", "--mcp-config", str(mcp_config)]
    applied: list[str] = []
    o = req.options
    if o.effort in _EFFORTS:
        argv += ["--effort", o.effort]
        applied.append("effort")
    if o.cost_cap_usd is not None:
        argv += ["--max-budget-usd", _money(o.cost_cap_usd)]
        applied.append("cost_cap_usd")
    if fallback is not None:
        argv += ["--fallback-model", fallback]
        applied.append("fallback_alias")
    if o.turn_cap is not None:
        argv += ["--max-turns", str(int(o.turn_cap))]
        applied.append("turn_cap")
    if req.plugin_dir is not None:
        argv += ["--plugin-dir", str(req.plugin_dir)]
    return argv, tuple(applied)


def judge_argv(views: ViewSet, model: str | None, *, isolated: bool) -> list[str]:
    argv = [BINARY, *BASE_ARGV]
    argv += ["--bare"] if isolated else ["--setting-sources", ""]
    if model is not None:
        argv += ["--model", model]
    if views.tool_less:  # SRV §2.6, SRV-AC-6: the session reviewer gets no tool and no MCP server
        return argv + ["--tools", "", "--strict-mcp-config", "--disallowedTools", "mcp__*",
                       "--permission-mode", "dontAsk"]
    tools = [t for t in views.tools if not t.startswith("mcp__")] or list(JUDGE_TOOLS)
    argv += ["--tools", ",".join(tools), "--disallowedTools", "mcp__*", "--permission-mode", "dontAsk",
             "--allowedTools", ",".join(tools)]
    return argv


def _money(v: float) -> str:
    return f"{float(v):.2f}"


def step_env(model: str | None, host: Mapping[str, str] | None = None) -> dict[str, str]:
    host = os.environ if host is None else host
    env: dict[str, str] = {}
    if "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR" not in host:
        env["CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR"] = "1"
    if model is not None:
        env["CLAUDE_CODE_SUBAGENT_MODEL"] = model
    return env


# ---------------------------------------------------------------------------------------------
# Stream mapping (ECC §2.5)


def _usage(result: Mapping[str, Any]) -> Usage:
    u = result.get("usage") or {}
    by_model = {}
    for name, mu in (result.get("modelUsage") or {}).items():
        if isinstance(mu, dict):
            by_model[str(name)] = {"input_tokens": mu.get("inputTokens"), "output_tokens": mu.get("outputTokens"),
                                   "cache_read_tokens": mu.get("cacheReadInputTokens"),
                                   "cache_write_tokens": mu.get("cacheCreationInputTokens"),
                                   "reported_cost_usd": mu.get("costUSD")}
    cost = result.get("total_cost_usd")
    return Usage(input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"),
                 cache_read_tokens=u.get("cache_read_input_tokens"),
                 cache_write_tokens=u.get("cache_creation_input_tokens"),
                 reported_cost_usd=float(cost) if isinstance(cost, int | float) else None,
                 by_model=by_model, turns=result.get("num_turns"))


def parse_line(line: bytes, workdir: Path | None = None) -> list[Event]:
    """Map one stream-json line to normalized events; unknown types map to nothing (ECC §4).

    `tool_started` carries the tool's capability and its one-line `input_summary` (EVT §2.5), with paths
    relative to `workdir`.
    """
    msg = json.loads(line)
    if not isinstance(msg, dict):
        return []
    kind, sub = msg.get("type"), msg.get("subtype")
    if kind == "system" and sub == "init":
        servers = msg.get("mcp_servers") or []
        return [Event(kind="session_started", data={
            "session_id": msg.get("session_id"), "model": msg.get("model"), "tools": list(msg.get("tools") or []),
            "cli_version": msg.get("claude_code_version", ""),
            "mcp_server_errors": sum(1 for s in servers if isinstance(s, dict) and s.get("status") != "connected"),
            "plugin_errors": len(msg.get("plugin_errors") or [])})]
    if kind == "system" and sub == "api_retry":
        return [Event(kind="retrying", data={"category": msg.get("error")})]
    if kind == "system" and sub == "permission_denied":
        return [Event(kind="denied", data={"name": msg.get("tool_name", "")})]
    if kind == "assistant":
        out = []
        for block in (msg.get("message") or {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                name = str(block.get("name", ""))
                cap = capability_of(CLAUDE, name)
                out.append(Event(kind="tool_started", data={
                    "name": name, "call_id": block.get("id", ""), "capability": cap,
                    "subagent": msg.get("parent_tool_use_id") is not None,
                    "input_summary": input_summary(cap, name, block.get("input"), workdir)}))
            elif block.get("type") == "text":
                last = (str(block.get("text") or "").strip().splitlines() or [""])[-1]
                out.append(Event(kind="text", data={"last_line": clip(scrub(last), 200)}))
        return out
    if kind == "user":
        out = []
        content = (msg.get("message") or {}).get("content") or []
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                out.append(Event(kind="tool_finished", data={"call_id": block.get("tool_use_id", ""),
                                                             "ok": not block.get("is_error", False)}))
        return out
    if kind == "stream_event":
        delta = ((msg.get("event") or {}).get("delta") or {})
        if delta.get("type") == "text_delta":
            return [Event(kind="model_delta", data={"chars": len(delta.get("text") or "")})]
        return []
    if kind == "result":
        events = [Event(kind="denied", data={"name": d.get("tool_name", "")})
                  for d in msg.get("permission_denials") or [] if isinstance(d, dict)]
        events.append(Event(kind="result", data={
            "ok": msg.get("subtype") == "success" and not msg.get("is_error", False),
            "usage": _usage(msg), "text": msg.get("result") or "", "subtype": msg.get("subtype"),
            "is_error": bool(msg.get("is_error", False)), "session_id": msg.get("session_id")}))
        return events
    return []


# ---------------------------------------------------------------------------------------------
# Failure classification (ECC §2.6)


def classify(raw: RawOutcome, s: Summary) -> tuple[InfraCause | None, ErrorKind | None]:
    cause = process_cause(raw)
    if cause is not None:
        return cause, None
    if raw.stop_reason is not None:
        return None, None  # timed_out, stalled or partial carry it
    last_retry = s.retry_categories[-1] if s.retry_categories else None
    if s.result is None:
        if AUTH_CATEGORY in s.retry_categories:
            return None, "auth"
        if last_retry in THROTTLE_CATEGORIES:
            return InfraCause.THROTTLED, None
        if last_retry in CONNECTION_CATEGORIES:
            return InfraCause.CONNECTION, None
        if killed_by_os(raw):
            return InfraCause.OUT_OF_MEMORY, None
        return InfraCause.NO_RESULT, None
    r = s.result
    subtype, text = r.get("subtype"), r.get("text")
    if subtype != "success" and text == REQUEST_TIMED_OUT:
        return InfraCause.REQUEST_TIMED_OUT, None
    if subtype == "error_max_turns":
        return None, "turn_cap"
    if subtype == BUDGET_SUBTYPE:
        return None, "cap_reached"
    if AUTH_CATEGORY in s.retry_categories and (r.get("is_error") or subtype != "success"):
        return None, "auth"
    if r.get("is_error") or subtype != "success":
        return None, "model"
    return None, None


# ---------------------------------------------------------------------------------------------
# The executor


def _credentials(profile: str | None, home: Path | None) -> dict[str, str]:
    """Judge-only credentials: name=value lines laid over the judge's environment (SEC §2.4)."""
    if not profile or not re.fullmatch(r"[A-Za-z0-9_.-]+", profile):
        return {}
    path = (home or binding_mod.home_path()) / "config" / "credentials" / profile
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                if re.fullmatch(r"[A-Z_][A-Z0-9_]*", k.strip()):
                    env[k.strip()] = v.strip()
    return env


class ClaudeExecutor:
    name = NAME

    def __init__(self, *, bindings: binding_mod.BindingTable | None = None, home: Path | None = None,
                 mcp_config: Path | None = None, stop: StopRequest | None = None, grace_s: float = 10.0) -> None:
        self._bindings = bindings
        self._home = home
        self._probe: ProbeReport | None = None
        self.mcp_config = mcp_config
        self.stop = stop
        self.grace_s = grace_s

    # -- declarations ---------------------------------------------------------------------------

    @property
    def binding(self) -> binding_mod.Binding:
        if self._bindings is None:
            self._bindings = binding_mod.load(self._home)
        return self._bindings.for_executor(NAME)

    def capabilities(self) -> Capabilities:
        version = self._probe.version if self._probe else ""
        return replace(CLAUDE, binds_aliases=CLAUDE.binds_aliases | self.binding.qualified(), version=version)

    def probe(self) -> ProbeReport:
        path = shutil.which(BINARY)
        if path is None:
            self._probe = ProbeReport(ok=False, reason="missing")
            return self._probe
        ver = run_probe([path, "--version"])
        m = _VERSION_RE.search(ver.stdout)
        if ver.exit_code != 0 or m is None:
            self._probe = ProbeReport(ok=False, reason="version_unreadable", path=path)
            return self._probe
        helptext = run_probe([path, "--help"]).stdout
        flags = sorted(f for f in PROBED_FLAGS if f in helptext)
        auth = run_probe([path, "auth", "status"])
        logged_in = False
        try:
            logged_in = bool(json.loads(auth.stdout).get("loggedIn"))
        except (ValueError, AttributeError):
            logged_in = auth.exit_code == 0
        gateway = [v for v in GATEWAY_VARS if os.environ.get(v)]
        facts = {"flags": flags, "logged_in": logged_in, "gateway_vars": gateway}
        if not logged_in and not gateway:
            self._probe = ProbeReport(ok=False, reason="signed_out", version=m.group(1), path=path, facts=facts)
        else:
            self._probe = ProbeReport(ok=True, version=m.group(1), path=path, facts=facts)
        return self._probe

    def _flags(self) -> frozenset[str]:
        if self._probe is None:
            self.probe()
        assert self._probe is not None
        return frozenset(self._probe.facts.get("flags", ()))

    # -- runs -----------------------------------------------------------------------------------

    def run_step(self, req: SessionRequest, sink: EventSink) -> SessionResult:
        try:
            model = self.binding.model(req.alias)
            fb = req.options.fallback_alias
            fallback = self.binding.model(fb) if fb else None
        except binding_mod.BindingError:
            return SessionResult(ok=False, error_kind="unknown")
        argv, applied = step_argv(req, model, fallback, self._flags(), self.mcp_config)
        return self._run(req, argv, applied, step_env(model), sink, idle_s=req.idle_s)

    def run_judge(self, req: SessionRequest, views: ViewSet, sink: EventSink) -> SessionResult:
        try:
            model = self.binding.model(req.alias)
        except binding_mod.BindingError:
            return SessionResult(ok=False, error_kind="unknown")
        argv = judge_argv(views, model, isolated=CLAUDE.isolates_user_config)
        env = _credentials(req.credentials_profile, self._home)
        return self._run(req, argv, (), env, sink, idle_s=None)  # judges never get an idle limit (EXI-B4)

    def _run(self, req: SessionRequest, argv: list[str], applied: tuple[str, ...], env: dict[str, str],
             sink: EventSink, *, idle_s: int | None) -> SessionResult:
        path = self._probe.path if self._probe and self._probe.path else shutil.which(BINARY)
        argv = [path or BINARY, *argv[1:]]
        spec = LaunchSpec(argv=argv, stdin_payload=req.prompt.encode("utf-8"), workdir=req.workdir,
                          timeout_s=req.timeout_s, idle_s=idle_s, session_key=req.session_key,
                          env_overlay=env, session_dir=req.session_dir, grace_s=self.grace_s)
        raw = launch(spec, functools.partial(parse_line, workdir=req.workdir), sink, stop=self.stop)
        s = summarize(raw.events, raw.duration_s)
        infra, kind = classify(raw, s)
        version = self._probe.version if self._probe else ""
        for ev in raw.events:
            if ev.kind == "session_started" and ev.data.get("cli_version"):
                version = str(ev.data["cli_version"])
        return build_result(raw, s, cli_version=version, argv=argv, applied=applied, infra=infra,
                            error_kind=kind, ok=s.result is not None and bool(s.result.get("ok")))


# Live probe facts of ECC §2.7 and their recorded state; none has run on a signed-in host yet (T0.1).
LIVE_FACTS: dict[str, str] = {f"P-CC-{i}": "not run" for i in range(1, 10)}
ClaudeExecutor.live_facts = LIVE_FACTS  # type: ignore[attr-defined]  # read by `executors` (CLI-B3)
