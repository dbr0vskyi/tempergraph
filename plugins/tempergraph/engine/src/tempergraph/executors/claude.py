"""The `claude` executor: one headless Claude Code session per step attempt or judge run (ECC).

Argv is built from the constants of ECC-B8, ECC-B9, ECC-B10, ECC-B18 (every launch is strict about MCP servers) and
ECC-B20 (the account's connectors are switched off in the environment) and values from the binding table or engine-checked
numbers (ECC-AC1, SEC-B1). The prompt goes on stdin (EXI-B2). The stream is mapped by ECC-B11 and
failures are classified by ECC-B12 from structured facts and one exact text match (ECC-B5).
"""

from __future__ import annotations

import functools
import json
import os
import re
import shutil
from collections.abc import Mapping, Sequence
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
from tempergraph.executors import mcpconfig
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
REQUEST_TIMED_OUT = "Request timed out"  # ECC-B12: exact equality only
THROTTLE_CATEGORIES = frozenset({"rate_limit", "overloaded"})
CONNECTION_CATEGORIES = frozenset({"connection_error", "network_error"})
AUTH_CATEGORY = "authentication_failed"
BUDGET_SUBTYPE = "error_max_budget_usd"  # shape to be confirmed by P-CC-3
GATEWAY_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK",
                "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY")
# ECC-B14: inside a host Claude Code session, every step, retry and judge launch leaves out the host's own names
HOST_DROP_PREFIXES = ("CLAUDECODE", "CLAUDE_")
HOST_KEEP = ("CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
             "CLAUDE_CODE_USE_FOUNDRY",
             # the operator's own sign-in and config folder: a pipeline signs `claude` in with these
             "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR")
PROBED_FLAGS = ("--permission-prompts", "--bare", "--tools", "--setting-sources", "--max-budget-usd",
                "--fallback-model", "--effort", "--plugin-dir", "--strict-mcp-config")
MCP_CONNECTORS_VAR = "ENABLE_CLAUDEAI_MCP_SERVERS"  # ECC-B20: set to `false` on every step, retry and judge launch
MCP_CONNECTORS_OFF = "false"
_VERSION_RE =re.compile(r"(\d+\.\d+\.\d+)")
_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})


# ---------------------------------------------------------------------------------------------
# Argv (ECC-B8, ECC-B9, ECC-B10)


SELF_CHECK = "tempergraph self-check "


def allow_rules(tools: tuple[str, ...], commands: tuple[str, ...], in_engine_worktree: bool) -> list[str]:
    """ECC-B7 allow rules for the declared capabilities; no absolute path (ECC-B1)."""
    rules: list[str] = []
    for cap in tools:
        if cap in ("edit", "write"):
            if in_engine_worktree:
                rules.append(("Edit" if cap == "edit" else "Write") + "(./**)")
        elif cap == "shell":
            rules.extend(f"Bash({c} *)" for c in commands)
        elif cap == "subagent":
            rules.append("Agent")
        elif cap == "read":
            rules.append("Read(./**)")  # ECC-B7: a bare `Read` rule would admit any path on the machine (P-CC-10)
        elif cap in ("search", "list"):
            continue  # ECC-B7: no rule; the CLI admits them inside the workspace and refuses them outside
        else:
            rules.extend(tool_names(CLAUDE, cap))
    # the check preview is granted as one exact command even when the step declares no shell (CHK-B17)
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
    plugins = plugin_dirs(Path(req.plugin_dir)) if req.plugin_dir is not None else []
    if "read" in req.tools:
        # ECC-B7: the workflow plugin's own files, and its dependencies', stay readable; `//` marks an absolute path
        rules += [f"Read(/{d.resolve().as_posix()}/**)" for d in plugins]
    if rules:
        argv += ["--allowedTools", ",".join(rules)]
    # ECC-B8, ECC-B14: every step launch names its built-in tools, so a host's tools are never offered
    argv += ["--tools", ",".join(_with_preview(builtin_tools(req.tools), req.commands))]
    argv += ["--disallowedTools", ALWAYS_DISALLOWED]
    # ECC-B18: every step launch is strict, so no MCP server of the account, the user or the repository is offered;
    # ECC-B8: a config is named only when the step declares an MCP tool
    argv += ["--strict-mcp-config"]
    if mcp_config is not None and any(t.startswith("mcp:") for t in req.tools):
        argv += ["--mcp-config", str(mcp_config)]
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
    # ECC-B16: no user-scope plugin, skill, hook or setting reaches a step; only the repository's settings load, and
    # the workflow plugin comes in by path with the plugins it depends on (they would come from user scope otherwise)
    argv += ["--setting-sources", STEP_SETTING_SOURCES]
    for d in plugins:
        argv += ["--plugin-dir", str(d)]
    return argv, tuple(applied)


STEP_SETTING_SOURCES = "project"


def plugin_dirs(root: Path) -> list[Path]:
    """ECC-B16: the workflow plugin's root, then each plugin its `.claude-plugin/plugin.json` names under
    `dependencies` that is found beside it: a sibling folder of that name (a marketplace checkout) or, in Claude Code's
    plugin cache, the newest version folder of that name. A dependency found nowhere is left out."""
    out = [root]
    try:
        deps = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")).get("dependencies")
    except (OSError, ValueError, AttributeError):
        return out
    for dep in deps if isinstance(deps, list) else []:
        name = (dep.get("name") if isinstance(dep, dict) else dep) or ""
        name = str(name).split("@", 1)[0]
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", name):
            continue
        found = _plugin_named(root.parent / name, name) or _newest_version(root.parent.parent / name, name)
        if found is not None and found.resolve() not in {d.resolve() for d in out}:
            out.append(found)
    return out


def _plugin_named(folder: Path, name: str) -> Path | None:
    try:
        held = json.loads((folder / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return folder if isinstance(held, dict) and held.get("name") == name else None


def _newest_version(folder: Path, name: str) -> Path | None:
    try:
        kids = sorted((k for k in folder.iterdir() if k.is_dir()), key=lambda k: k.stat().st_mtime, reverse=True)
    except OSError:
        return None
    return next((k for k in kids if _plugin_named(k, name) is not None), None)


def judge_argv(views: ViewSet, model: str | None, *, isolated: bool, mcp_config: Path | None = None) -> list[str]:
    """ECC-B10. With MCP views and a private config (ECC-B3), `--tools` still holds the built-in views only and the
    MCP views are admitted by name from the strict config; without a config the judge gets no MCP tool at all."""
    argv = [BINARY, *BASE_ARGV]
    argv += ["--bare"] if isolated else ["--setting-sources", ""]
    if model is not None:
        argv += ["--model", model]
    if views.tool_less:  # SRV-B18, SRV-B19, SRV-B20, SRV-AC6: the session reviewer gets no tool and no MCP server
        return argv + ["--tools", "", "--strict-mcp-config", "--disallowedTools", "mcp__*",
                       "--permission-mode", "dontAsk"]
    tools = [t for t in views.tools if not t.startswith("mcp__")] or list(JUDGE_TOOLS)
    mcp = [t for t in views.tools if t.startswith("mcp__")]
    if mcp_config is not None and mcp:
        return argv + ["--tools", ",".join(tools), "--strict-mcp-config", "--mcp-config", str(mcp_config),
                       "--permission-mode", "dontAsk", "--allowedTools", ",".join([*tools, *mcp])]
    argv += ["--tools", ",".join(tools), "--strict-mcp-config", "--disallowedTools", "mcp__*",
             "--permission-mode", "dontAsk",
             "--allowedTools", ",".join(tools)]
    return argv


def _money(v: float) -> str:
    return f"{float(v):.2f}"


def step_env(model: str | None, host: Mapping[str, str] | None = None) -> dict[str, str]:
    host = os.environ if host is None else host
    env: dict[str, str] = {MCP_CONNECTORS_VAR: MCP_CONNECTORS_OFF}  # ECC-B20: no claude.ai connector, whatever the host
    if "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR" not in host:
        env["CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR"] = "1"
    if model is not None:
        env["CLAUDE_CODE_SUBAGENT_MODEL"] = model
    return env


# ---------------------------------------------------------------------------------------------
# Stream mapping (ECC-B11)


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
    """Map one stream-json line to normalized events; unknown types map to nothing (ECC-B13, ECC-B11).

    `tool_started` carries the tool's capability and its one-line `input_summary` (EVT-B21), with paths
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
# Failure classification (ECC-B12)


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
    """Judge-only credentials: name=value lines laid over the judge's environment (SEC-B12, SEC-B13)."""
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


def _mask_private(res: SessionResult) -> SessionResult:
    """The path of a private configuration is in no record the engine keeps (SEC-B12)."""
    res.argv = tuple("<private>" if i and res.argv[i - 1] == "--mcp-config" else a for i, a in enumerate(res.argv))
    return res


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
        if "--strict-mcp-config" not in flags:
            self._probe = ProbeReport(ok=False, reason="probe_failed", version=m.group(1), path=path,
                                      facts={"flags": flags, "missing_flags": ["--strict-mcp-config"]})
            return self._probe
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
        declared = mcpconfig.declared_servers(req.tools)
        if not declared or self.mcp_config is not None:
            argv, applied = step_argv(req, model, fallback, self._flags(), self.mcp_config)
            return self._run(req, argv, applied, step_env(model), sink, idle_s=req.idle_s)
        servers = mcpconfig.operator_servers(req.workdir)
        undefined = [s for s in declared if s not in servers]
        base = mcpconfig.scratch_base(req.session_dir)
        if undefined or base is None:  # a declared server is never dropped silently (ECC-B23)
            why = ("MCP server not defined in the operator's configuration: " + ", ".join(undefined)
                   if undefined else "no scratch folder for the private MCP config; declared servers: "
                   + ", ".join(declared))
            return SessionResult(ok=False, error_kind="refused", text=why)
        with mcpconfig.private_config(declared, servers, base, direct=True) as cfg:  # removed on every exit path
            argv, applied = step_argv(req, model, fallback, self._flags(), cfg)
            res = self._run(req, argv, applied, step_env(model), sink, idle_s=req.idle_s)
        return _mask_private(res)

    def run_judge(self, req: SessionRequest, views: ViewSet, sink: EventSink) -> SessionResult:
        try:
            model = self.binding.model(req.alias)
        except binding_mod.BindingError:
            return SessionResult(ok=False, error_kind="unknown")
        env = {**_credentials(req.credentials_profile, self._home), MCP_CONNECTORS_VAR: MCP_CONNECTORS_OFF}  # ECC-B20
        viewed = mcpconfig.viewed_servers(views.tools)
        servers = mcpconfig.operator_servers(req.workdir) if viewed else {}
        usable = {s: t for s, t in viewed.items() if mcpconfig.classify(s, servers) == "proxiable"}
        base = mcpconfig.scratch_base(req.session_dir) if usable else None
        if not usable or base is None:  # no proxy can be given: the launch is the read-only one, with no MCP tool
            argv = judge_argv(views, model, isolated=CLAUDE.isolates_user_config)
            return self._run(req, argv, (), env, sink, idle_s=None)  # judges never get an idle limit (EXI-B4)
        offered = [t for t in views.tools if not t.startswith("mcp__")]
        offered += [f"mcp__{s}__{t}" for s, tools in usable.items() for t in tools]
        with mcpconfig.private_config(usable, servers, base) as cfg:  # removed on every exit path (SEC-B12)
            argv = judge_argv(replace(views, tools=tuple(offered)), model, isolated=CLAUDE.isolates_user_config,
                              mcp_config=cfg)
            res = self._run(req, argv, (), env, sink, idle_s=None)
        return _mask_private(res)

    def undefined_mcp_servers(self, tools: Sequence[str], workdir: Path | None = None) -> list[str]:
        """ECC-B22: each declared MCP server the operator's own configuration does not define, in first-seen order;
        an unreadable configuration defines none."""
        defined = mcpconfig.operator_servers(workdir if workdir is not None else Path.cwd())
        return [s for s in mcpconfig.declared_servers(tools) if s not in defined]

    def unreachable_views(self, views: ViewSet, workdir: Path) -> dict[str, str]:
        """ECC-B15: each viewed MCP server with no working proxy, with its reason; checked before the judge prompt."""
        return mcpconfig.unreachable(views.tools, workdir)

    def _run(self, req: SessionRequest, argv: list[str], applied: tuple[str, ...], env: dict[str, str],
             sink: EventSink, *, idle_s: int | None) -> SessionResult:
        path = self._probe.path if self._probe and self._probe.path else shutil.which(BINARY)
        argv = [path or BINARY, *argv[1:]]
        spec = LaunchSpec(argv=argv, stdin_payload=req.prompt.encode("utf-8"), workdir=req.workdir,
                          timeout_s=req.timeout_s, idle_s=idle_s, session_key=req.session_key,
                          env_overlay=env, env_drop=HOST_DROP_PREFIXES, env_keep=HOST_KEEP,
                          session_dir=req.session_dir, grace_s=self.grace_s)
        # ECC-B17: the last `rate_limit_event` is kept beside the mapping, which still gives it no event (SSN-B7)
        last_limit: dict[str, Any] = {}
        mapper = functools.partial(parse_line, workdir=req.workdir)

        def keep_limit(line: bytes) -> list[Event]:
            try:
                msg = json.loads(line)
            except ValueError:
                msg = None
            if isinstance(msg, dict) and msg.get("type") == "rate_limit_event":
                info = msg.get("rate_limit_info")
                last_limit.clear()
                last_limit.update(info if isinstance(info, dict) else {})
            return mapper(line)

        raw = launch(spec, keep_limit, sink, stop=self.stop)
        s = summarize(raw.events, raw.duration_s)
        infra, kind = classify(raw, s)
        spent, resets_at = _spent_allowance(last_limit)
        version = self._probe.version if self._probe else ""
        for ev in raw.events:
            if ev.kind == "session_started" and ev.data.get("cli_version"):
                version = str(ev.data["cli_version"])
        return build_result(raw, s, cli_version=version, argv=argv, applied=applied, infra=infra,
                            error_kind=kind, ok=s.result is not None and bool(s.result.get("ok")),
                            usage_limit=spent, usage_limit_resets_at=resets_at)


def _spent_allowance(info: Mapping[str, Any]) -> tuple[bool, float | None]:
    """ECC-B17: a last `rate_limit_event` of status `rejected` says the allowance is spent; `resetsAt` is read as epoch
    seconds (open question of the spec on the unit), null when absent, not a number or `credits_required`."""
    if info.get("status") != "rejected":
        return False, None
    at = info.get("resetsAt")
    if info.get("errorCode") == "credits_required" or isinstance(at, bool) or not isinstance(at, int | float):
        return True, None
    return True, float(at)


# Live probe facts of ECC-B13 and their recorded state: P-CC-13 was run by the operator on 2026-11-25 (live row L-43);
# P-CC-1 to P-CC-12 have not been run on a signed-in host yet.
LIVE_FACTS: dict[str, str] = {**{f"P-CC-{i}": "not run" for i in range(1, 13)}, "P-CC-13": "confirmed"}
ClaudeExecutor.live_facts = LIVE_FACTS  # type: ignore[attr-defined]  # read by `executors` (CLI-B3)
