"""The `claude` executor (ECC-B1 to B5, ECC-AC1 to AC-4; SEC-B1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tempergraph.contracts import EventSink, InfraCause, SessionOptions, SessionRequest, ViewSet
from tempergraph.executors.binding import Binding, BindingError, BindingTable, load
from tempergraph.executors.claude import (
    ClaudeExecutor,
    classify,
    judge_argv,
    parse_line,
    step_argv,
    step_env,
)
from tempergraph.executors.launcher import RawOutcome
from tempergraph.executors.session import summarize

from .fixtures import streams as S

FLAGS = frozenset({"--permission-prompts"})


def req(tmp_path: Path, **kw: object) -> SessionRequest:
    fields: dict[str, object] = {"kind": "step", "prompt": "Write notes.", "workdir": tmp_path, "alias": "medium",
                                 "session_key": "draft.1.step"}
    fields.update(kw)
    return SessionRequest(**fields)  # type: ignore[arg-type]


def flag(argv: list[str], name: str) -> str | None:
    return argv[argv.index(name) + 1] if name in argv else None


# -- argv (ECC-B8, ECC-B9, ECC-B10) ----------------------------------------------------------------------


def test_declared_shell_in_engine_worktree(tmp_path: Path) -> None:
    r = req(tmp_path, tools=("read", "edit", "shell"), commands=("pytest", "git status"), in_engine_worktree=True)
    argv, _ = step_argv(r, "sonnet", None, FLAGS)
    assert flag(argv, "--permission-mode") == "acceptEdits"
    rules = flag(argv, "--allowedTools")
    assert rules == "Read,Edit(./**),Bash(pytest *),Bash(git status *)"  # ECC-B1
    assert "/" not in rules.replace("./**", "")
    assert flag(argv, "--disallowedTools") == "EnterWorktree,ExitWorktree"
    assert flag(argv, "--permission-prompts") == "none"
    assert argv[:5] == ["claude", "-p", "--output-format", "stream-json", "--verbose"]


def test_in_place_has_default_mode_and_no_write_rules(tmp_path: Path) -> None:
    argv, _ = step_argv(req(tmp_path, tools=("read", "write")), "sonnet", None, frozenset())
    assert flag(argv, "--permission-mode") == "default"
    assert flag(argv, "--allowedTools") == "Read"
    assert "--permission-prompts" not in argv  # only when the probe saw the flag


def test_tool_names_and_rules_stay_apart(tmp_path: Path) -> None:
    r = req(tmp_path, tools=("read", "shell", "mcp:tracker/get_issue"), commands=("pytest",), enforce_tools=True)
    argv, _ = step_argv(r, "sonnet", None, FLAGS)
    assert flag(argv, "--tools") == "Read,Bash"  # names only (ECC-B2)
    assert "(" not in flag(argv, "--tools")
    assert flag(argv, "--allowedTools") == "Read,Bash(pytest *),mcp__tracker__get_issue"


def test_options_and_inherit(tmp_path: Path) -> None:
    o = SessionOptions(effort="high", cost_cap_usd=2.5, fallback_alias="small", turn_cap=30)
    argv, applied = step_argv(req(tmp_path, alias="inherit", options=o), None, "haiku", FLAGS)
    assert "--model" not in argv
    assert (flag(argv, "--effort"), flag(argv, "--max-budget-usd"), flag(argv, "--fallback-model"),
            flag(argv, "--max-turns")) == ("high", "2.50", "haiku", "30")
    assert applied == ("effort", "cost_cap_usd", "fallback_alias", "turn_cap")


def test_judge_launch_is_read_only(tmp_path: Path) -> None:
    argv = judge_argv(ViewSet(tools=("Read", "Grep", "Glob")), "opus", isolated=False)
    assert flag(argv, "--tools") == "Read,Grep,Glob"
    assert flag(argv, "--permission-mode") == "dontAsk"
    assert flag(argv, "--disallowedTools") == "mcp__*"
    assert flag(argv, "--setting-sources") == ""
    for bad in ("Write", "Edit", "Bash", "--fallback-model", "--resume", "--continue", "acceptEdits"):
        assert all(bad not in a for a in argv)  # ECC-AC4
    assert "--bare" in judge_argv(ViewSet(), None, isolated=True)


def test_step_env() -> None:
    assert step_env("sonnet", host={}) == {"CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": "1",
                                           "CLAUDE_CODE_SUBAGENT_MODEL": "sonnet"}
    assert step_env(None, host={"CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": "0"}) == {}


# -- binding table (SEC-B1) ---------------------------------------------------------------------


def test_typed_alias_selects_an_entry() -> None:
    b = Binding(executor="claude", tiers={"large": "opus"}, aliases={"review": "claude-opus-4-8"})
    assert b.model("large") == "opus"
    assert b.model("claude:review") == "claude-opus-4-8"
    assert b.model("inherit") is None
    with pytest.raises(BindingError):
        b.model("--dangerously-skip-permissions")
    with pytest.raises(BindingError):
        Binding(executor="claude", tiers={"large": "opus; rm -rf"}).model("large")


def test_binding_file(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "bindings.json").write_text(json.dumps({"schema_version": 1, "bindings": [
        {"executor": "claude", "tiers": {"small": "claude-haiku-x"}, "aliases": {"deep": "opus"}, "x": 1}]}))
    t = load(tmp_path)
    c = t.for_executor("claude")
    assert c.model("small") == "claude-haiku-x" and c.model("medium") == "sonnet"
    assert c.qualified() == frozenset({"claude:deep"})
    assert BindingTable().for_executor("claude").model("large") == "opus"


# -- stream mapping (ECC-B11, ECC-AC2) --------------------------------------------------------


def events_of(*msgs: dict) -> list:
    out = []
    for line in S.lines(*msgs):
        out.extend(parse_line(line))
    return out


def test_stream_rows() -> None:
    evs = events_of(
        S.init(mcp_servers=[{"name": "t", "status": "failed"}], plugin_errors=["p"]),
        S.tool_use("Read", "t1", inp={"file_path": "a.md"}),
        S.tool_use("Grep", "t2", parent="t0"),
        S.tool_result("t1"), S.tool_result("t2", is_error=True),
        S.delta("hello"), S.text("thinking\nlast line here"), S.retry("rate_limit"), S.denied("Bash"),
        S.result(cost=1.73), {"type": "something_new"})
    kinds = [e.kind for e in evs]
    assert kinds == ["session_started", "tool_started", "tool_started", "tool_finished", "tool_finished",
                     "model_delta", "text", "retrying", "denied", "result"]
    started = evs[0].data
    assert started["mcp_server_errors"] == 1 and started["plugin_errors"] == 1
    assert started["cli_version"] == "2.1.329"
    assert evs[1].data["subagent"] is False and evs[2].data["subagent"] is True
    assert evs[4].data["ok"] is False
    assert evs[5].data == {"chars": 5}
    assert evs[6].data["last_line"] == "last line here"
    assert evs[7].data["category"] == "rate_limit"
    usage = evs[-1].data["usage"]
    assert usage.reported_cost_usd == 1.73  # ECC-B4
    assert usage.estimated_cost_usd is None
    assert usage.turns == 3 and usage.cache_read_tokens == 800
    assert usage.by_model["claude-sonnet"]["input_tokens"] == 1200


def test_unknown_cost_is_none_not_zero() -> None:
    evs = events_of(S.result(cost=None))
    assert evs[-1].data["usage"].reported_cost_usd is None


def test_result_permission_denials() -> None:
    evs = events_of(S.result(permission_denials=[{"tool_name": "Write"}]))
    assert [(e.kind, e.data.get("name")) for e in evs] == [("denied", "Write"), ("result", None)]


# -- failure classification (ECC-B12, ECC-AC3) ------------------------------------------------


def raw_of(*msgs: dict, **kw: object) -> tuple[RawOutcome, object]:
    evs = events_of(*msgs)
    raw = RawOutcome(lines=len(msgs), events=evs, prompt_delivered=True, exit_code=0, duration_s=1.0)
    for k, v in kw.items():
        setattr(raw, k, v)
    return raw, summarize(evs, 1.0)


@pytest.mark.parametrize(("msgs", "raw_fields", "expected"), [
    ((), {"spawn_error": OSError(11, "again")}, (InfraCause.SPAWN_FAILED, None)),
    ((), {"broken_pipe": True}, (InfraCause.BROKEN_PIPE, None)),
    ((), {"prompt_timeout": True, "stop_reason": "stop"}, (InfraCause.PROMPT_NOT_DELIVERED, None)),
    ((), {}, (InfraCause.NO_OUTPUT, None)),
    ((S.init(),), {}, (InfraCause.NO_RESULT, None)),
    ((S.init(), S.result("Request timed out", subtype="error_during_execution", is_error=True)), {},
     (InfraCause.REQUEST_TIMED_OUT, None)),
    ((S.init(), S.retry("overloaded")), {}, (InfraCause.THROTTLED, None)),
    ((S.init(), S.retry("connection_error")), {}, (InfraCause.CONNECTION, None)),
    ((S.init(),), {"exit_code": -9}, (InfraCause.OUT_OF_MEMORY, None)),
    ((S.init(), S.result("", subtype="error_max_turns", is_error=True)), {}, (None, "turn_cap")),
    ((S.init(), S.result("", subtype="error_max_budget_usd", is_error=True)), {}, (None, "cap_reached")),
    ((S.init(), S.retry("authentication_failed")), {}, (None, "auth")),
    ((S.init(), S.result("oops", is_error=True)), {}, (None, "model")),
    ((S.init(), S.result()), {}, (None, None)),
])
def test_classification(msgs: tuple, raw_fields: dict, expected: tuple) -> None:
    raw, s = raw_of(*msgs, **raw_fields)
    if not msgs:
        raw.lines = 0
    assert classify(raw, s) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize(("text", "expected"), [
    ("Request timed out", (InfraCause.REQUEST_TIMED_OUT, None)),
    ("Request timed out.", (None, "model")),
    ("The request timed out", (None, "model")),
])
def test_exact_timeout_text(text: str, expected: tuple) -> None:
    raw, s = raw_of(S.init(), S.result(text, subtype="error_during_execution", is_error=True))
    assert classify(raw, s) == expected  # type: ignore[arg-type]  # ECC-B5


# -- probe and end-to-end through the launcher ---------------------------------------------------


def test_probe_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    p = ClaudeExecutor(bindings=BindingTable()).probe()
    assert not p.ok and p.reason == "missing"


def test_probe_signed_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    S.fake_claude(tmp_path, monkeypatch, {"logged_in": False})
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
              "CLAUDE_CODE_USE_FOUNDRY"):
        monkeypatch.delenv(v, raising=False)
    p = ClaudeExecutor(bindings=BindingTable()).probe()
    assert not p.ok and p.reason == "signed_out" and p.version == "2.1.329"


def test_run_step_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rec = tmp_path / "rec.json"
    S.fake_claude(tmp_path, monkeypatch, {"record": str(rec), "lines": [
        S.init(), S.tool_use("Read", "t1"), S.tool_result("t1"), S.text("done"), S.result()]})
    ex = ClaudeExecutor(bindings=BindingTable())
    assert ex.probe().ok and "--permission-prompts" in ex.probe().facts["flags"]
    sink = EventSink()
    res = ex.run_step(req(tmp_path, tools=("read",), session_dir=tmp_path / "s"), sink)
    assert res.ok and res.text.endswith("ARTIFACT notes: notes.md")
    assert res.session_id == "s-1" and res.cli_version == "2.1.329"
    assert [c.name for c in res.tool_calls] == ["Read"] and res.tool_calls[0].ok
    assert res.usage.reported_cost_usd == 0.12
    seen = json.loads(rec.read_text())
    assert seen["prompt"] == "Write notes."
    assert seen["argv"] == list(res.argv[1:])
    assert seen["env"]["CLAUDE_CODE_SUBAGENT_MODEL"] == "sonnet"
    assert (tmp_path / "s" / "raw.jsonl").exists()


def test_run_judge_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rec = tmp_path / "rec.json"
    S.fake_claude(tmp_path, monkeypatch, {"record": str(rec), "lines": [S.init(session_id="j-1"),
                                                                        S.result("```json\n{}\n```", session_id="j-1")]})
    home = tmp_path / "home"
    (home / "config" / "credentials").mkdir(parents=True)
    (home / "config" / "credentials" / "judge").write_text("JUDGE_ONLY_TOKEN=abc\n# note\n")
    ex = ClaudeExecutor(bindings=BindingTable(), home=home)
    res = ex.run_judge(req(tmp_path, kind="judge", alias="large", credentials_profile="judge"),
                       ViewSet(tools=("Read", "Grep", "Glob")), EventSink())
    seen = json.loads(rec.read_text())
    assert res.ok and res.session_id == "j-1"
    assert seen["env"]["JUDGE_ONLY_TOKEN"] == "abc"
    assert "dontAsk" in seen["argv"] and "opus" in seen["argv"]


def test_unbound_alias_returns_a_result(tmp_path: Path) -> None:
    res = ClaudeExecutor(bindings=BindingTable()).run_step(req(tmp_path, alias="claude:none"), EventSink())
    assert not res.ok and res.error_kind == "unknown"
