"""Live probes against a signed-in `claude` (ECC §2.7, WTR §5, SRV; live-checks plan L-1 to L-12).

Skipped unless TEMPERGRAPH_LIVE=1. Each test launches `claude -p` with the argv the engine itself builds, so a
pass confirms the engine's launch, not a hand-written one. Each session is capped with `--max-budget-usd`; the
whole file costs well under one US dollar on the `haiku` alias. Run from `plugins/tempergraph/engine/`:

    TEMPERGRAPH_LIVE=1 python -m pytest tests/live -v -rA -o addopts=""

and paste the summary into the plan's results table. A failure is a finding about the engine or the CLI
version: it is recorded as it is, never edited to pass.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tempergraph.contracts import SessionOptions, SessionRequest, ViewSet
from tempergraph.executors.claude import BUDGET_SUBTYPE, judge_argv, step_argv

pytestmark = pytest.mark.live
MODEL = os.environ.get("TEMPERGRAPH_LIVE_MODEL", "haiku")
CAP = ["--max-budget-usd", "0.20"]


def _claude(argv: list[str], prompt: str, cwd: Path, timeout: float = 240) -> list[dict[str, Any]]:
    assert shutil.which("claude"), "claude is not on PATH"
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDECODE")}
    out = subprocess.run(argv, input=prompt, capture_output=True, text=True, cwd=cwd, timeout=timeout, env=env,
                         check=False)
    events = []
    for ln in out.stdout.splitlines():
        try:
            events.append(json.loads(ln))
        except ValueError:
            continue
    assert events, f"no stream-json output; stderr: {out.stderr[-800:]}"
    return events


def _init(events: list[dict[str, Any]]) -> dict[str, Any]:
    return next(e for e in events if e.get("type") == "system" and e.get("subtype") == "init")


def _result(events: list[dict[str, Any]]) -> dict[str, Any]:
    return next(e for e in reversed(events) if e.get("type") == "result")


def _step(tmp: Path, **kw: Any) -> SessionRequest:
    return SessionRequest(kind="step", prompt="", workdir=tmp, alias=MODEL, session_key="probe.1.step",
                          timeout_s=240, session_dir=tmp / "s", options=SessionOptions(), **kw)


def test_version() -> None:
    v = subprocess.run(["claude", "--version"], capture_output=True, text=True, check=True).stdout.strip()
    print(f"claude --version: {v}")
    assert v


def test_p_cc_1_bare_isolates_user_config(tmp_path: Path) -> None:  # P-CC-1
    argv = judge_argv(ViewSet(tools=("Read",)), MODEL, isolated=True) + CAP
    ev = _claude(argv, "Reply with the word ready.", tmp_path)
    init = _init(ev)
    print("init tools:", init.get("tools"), "mcp:", init.get("mcp_servers"), "plugins:", init.get("plugins"))
    assert _result(ev).get("subtype") == "success", "credentials did not work under --bare"
    assert not init.get("mcp_servers") and not init.get("plugins")


def test_p_cc_2_judge_tools_are_exact(tmp_path: Path) -> None:  # P-CC-2
    argv = judge_argv(ViewSet(tools=("Read", "Grep", "Glob")), MODEL, isolated=False) + CAP
    init = _init(_claude(argv, "Reply with the word ready.", tmp_path))
    assert sorted(init.get("tools") or []) == ["Glob", "Grep", "Read"], init.get("tools")


def test_p_cc_3_budget_end_shape(tmp_path: Path) -> None:  # P-CC-3
    argv = judge_argv(ViewSet(tools=("Read",)), MODEL, isolated=False) + ["--max-budget-usd", "0.0001"]
    res = _result(_claude(argv, "Write a 2000 word essay about rivers.", tmp_path))
    print("result at budget:", {k: res.get(k) for k in ("subtype", "is_error", "total_cost_usd")})
    assert res.get("subtype") == BUDGET_SUBTYPE


def test_p_cc_5_prompt_on_stdin(tmp_path: Path) -> None:  # P-CC-5
    argv, _ = step_argv(_step(tmp_path, tools=("read",)), MODEL, None, frozenset())
    res = _result(_claude(argv + CAP, "Reply with exactly: stdin-ok", tmp_path))
    assert res.get("subtype") == "success" and "stdin-ok" in str(res.get("result"))


def test_p_cc_6_dont_ask_refuses(tmp_path: Path) -> None:  # P-CC-6
    argv = judge_argv(ViewSet(tools=("Read",)), MODEL, isolated=False) + CAP
    ev = _claude(argv, "Run the shell command `echo probe > out.txt` with the Bash tool, then say done.", tmp_path,
                 timeout=180)
    assert not (tmp_path / "out.txt").exists()
    denied = [e for e in ev if "permission" in json.dumps(e).lower() and "denied" in json.dumps(e).lower()]
    print("denial events:", len(denied))
    assert _result(ev) is not None  # it ended without waiting on a prompt


def test_p_cc_7_transcript_location(tmp_path: Path) -> None:  # P-CC-7
    argv = judge_argv(ViewSet(tools=("Read",)), MODEL, isolated=False) + CAP
    sid = _result(_claude(argv, "Reply with the word ready.", tmp_path)).get("session_id")
    found = list((Path.home() / ".claude" / "projects").glob(f"*/{sid}.jsonl")) if sid else []
    print("transcript:", found[0] if found else "none kept")  # either answer is a result; record it


def _probe_plugin(root: Path) -> Path:
    p = root / "tgprobe"
    (p / ".claude-plugin").mkdir(parents=True)
    (p / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "tgprobe", "version": "0.0.1"}))
    (p / "skills" / "hello").mkdir(parents=True)
    (p / "skills" / "hello" / "SKILL.md").write_text(
        "---\nname: hello\ndescription: Say the probe word. Use when asked for the probe word.\n---\n\n"
        "Reply with exactly: skill-ok\n")
    (p / "agents").mkdir()
    (p / "agents" / "helper.md").write_text("---\nname: helper\ndescription: A probe agent.\n---\n\nSay hi.\n")
    return p


def test_p_cc_8_and_9_plugin_dir_skill(tmp_path: Path) -> None:  # P-CC-8, P-CC-9
    plugin = _probe_plugin(tmp_path)
    req = _step(tmp_path, tools=("read", "skill:tgprobe:hello"), plugin_dir=plugin)
    argv, _ = step_argv(req, MODEL, None, frozenset({"--permission-prompts"}))
    ev = _claude(argv + CAP, "Use the hello skill and reply with what it says.", tmp_path)
    init = json.dumps(_init(ev))
    print("init names hello:", "hello" in init, "helper:", "helper" in init)
    assert "hello" in init and "helper" in init  # P-CC-9
    calls = [b for e in ev if e.get("type") == "assistant" for b in (e.get("message") or {}).get("content") or []
             if isinstance(b, dict) and b.get("type") == "tool_use"]
    print("tool calls:", [(c.get("name"), c.get("input")) for c in calls])
    assert any(c.get("name") == "Skill" for c in calls)  # P-CC-8: the record names the skill


def test_p_wtr_1_no_worktree_tools(tmp_path: Path) -> None:  # P-WTR-1
    argv, _ = step_argv(_step(tmp_path, tools=("read",)), MODEL, None, frozenset())
    tools = _init(_claude(argv + CAP, "Reply with the word ready.", tmp_path)).get("tools") or []
    assert "EnterWorktree" not in tools and "ExitWorktree" not in tools


def test_srv_reviewer_has_no_tools(tmp_path: Path) -> None:  # SRV-AC-6 live
    argv = judge_argv(ViewSet(tool_less=True), MODEL, isolated=False) + CAP
    ev = _claude(argv, "Reply with the word ready.", tmp_path)
    assert (_init(ev).get("tools") or []) == [] and _result(ev).get("subtype") == "success"
