"""The session record a check reads (CHK-B24, CHK-B25, CHK-B9; CHK-AC14 to CHK-AC18, CHK-AC3).

Every fixture here is an engine fixture: a one-step workflow whose gate check writes what it received to a file
the test names (the check runs in the worker process), and an executor that pushes the tool events a real
session would. No workflow package is named.
"""

from __future__ import annotations

import io
import json
import os
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import CheckFinding, CheckResult, Gate, Judge, Routing, Step, Value, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import Event, SessionRequest, SessionResult
from tempergraph.executors.standins import answer, standin
from tempergraph.run import selfcheck
from tempergraph.run.checks import CheckContext
from tempergraph.run.commands import resolve_command
from tempergraph.run.runner import RunSettings, start
from tempergraph.store.layout import state_root_path

from .fixtures.workflows import crit, named
from .test_run import MET, registry, verdict_block

NO_SLEEP = RunSettings(sleep=lambda s: None)
SRC = Path(__file__).resolve().parents[1] / "src" / "tempergraph"
OUT_VAR = "I129_CHECK_SEEN"
FAIL_FIRST_VAR = "I129_CHECK_FAIL_FIRST"

Call = tuple[str, str | None, str | None, bool]  # name, capability, target, ok


def seen_check(ctx: Any) -> CheckResult:
    """Writes the context it received (the session included) as one JSON line, passes."""
    out = os.environ.get(OUT_VAR)
    if out:
        doc = {
            "session": None if ctx.session is None else [dict(c) for c in ctx.session],
            "visit_session": None if ctx.visit_session is None else [dict(c) for c in ctx.visit_session],
            "preview": ctx.preview,
            "attempt": ctx.attempt, "visit": ctx.visit, "unit": ctx.unit, "item": ctx.item,
            "workdir_name": ctx.workdir.name, "artifacts": ctx.artifacts, "values": ctx.values,
            "settings": ctx.settings, "criteria": list(ctx.criteria), "allow": list(ctx.allow),
            "changed_paths": list(ctx.changed_paths), "runs": len(ctx.runs),
            "git_clean": None if ctx.git is None else ctx.git.clean,
        }
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, default=str) + "\n")
    fail = os.environ.get(FAIL_FIRST_VAR) == "1" and ctx.attempt == 1 and not ctx.preview
    return CheckResult(result="FAIL" if fail else "PASS", evidence="seen",
                       findings=[CheckFinding(status="fail" if fail else "pass", criterion="c1", place="x",
                                              message="first attempt fails" if fail else "fine",
                                              fix="try again" if fail else "")])


def wf(self_check: bool = False, executor: str | None = None) -> Any:
    st = Step(prompt="Expand the plan for {request}", tools=["read", "write"], self_check=self_check,
              gate=Gate(check=seen_check, judge=Judge(stance="V."), criteria=[crit("c1")]),
              **({"executor": executor} if executor else {}))
    return named(Workflow(order=["expand"], units={"expand": st}, issue_repository="acme/x",
                          routing=Routing(description="Expand a plan")))


def push_calls(sink: Any, calls: Sequence[Call], first: int = 0, finish: bool = True) -> None:
    for i, (name, cap, target, ok) in enumerate(calls, start=first):
        sink.push(Event(kind="tool_started", data={"name": name, "call_id": f"c{i}", "capability": cap,
                                                   "input_summary": target}))
        if finish:
            sink.push(Event(kind="tool_finished", data={"call_id": f"c{i}", "ok": ok}))


def started(sink: Any) -> None:
    sink.push(Event(kind="session_started", data={"session_id": "s", "model": None, "tools": []}))


def script(calls: Sequence[Call], finish: bool = True) -> Callable[[SessionRequest, Any], SessionResult]:
    def run(req: SessionRequest, sink: Any) -> SessionResult:
        started(sink)
        push_calls(sink, calls, finish=finish)
        return answer("Expanded.", session_id="s")
    return run


class Scripted:
    """A `claude`-shaped executor whose step sessions push the events a script names."""

    def __init__(self, scripts: Sequence[Callable[[SessionRequest, Any], SessionResult]], name: str = "claude") -> None:
        self.inner = standin(name)
        self.name = self.inner.name
        self.scripts = list(scripts)
        self.n = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        run = self.scripts[min(self.n, len(self.scripts) - 1)]
        self.n += 1
        return run(req, sink)

    def run_judge(self, req: SessionRequest, views: Any, sink: Any) -> SessionResult:
        return answer(MET, tools=("Read",), session_id="j")


@pytest.fixture
def seen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "seen.jsonl"
    monkeypatch.setenv(OUT_VAR, str(out))
    return out


def lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text().splitlines()] if path.exists() else []


def go(repo: Path, ex: Any, spec: Any = None, task: str = "S-1") -> Any:
    return start(spec or wf(), task, {"request": "x"}, repo, registry(ex), NO_SLEEP)


READ, SEARCH, EDIT, WRITE = "read", "search", "edit", "write"


def test_the_check_gets_the_calls_of_the_session_in_order(repo: Path, seen: Path) -> None:
    # CHK-AC14, CHK-B24, CHK-B10, AC 5
    ex = Scripted([script([("Read", READ, "docs/a.md", True), ("Grep", SEARCH, "plan", True),
                           ("Edit", EDIT, "src/b.py", True), ("Write", WRITE, "tests/c.py", True)])])
    out = go(repo, ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    (got,) = lines(seen)
    assert got["session"] == [
        {"name": "Read", "capability": "read", "target": "docs/a.md", "ok": True},
        {"name": "Grep", "capability": "search", "target": "plan", "ok": True},
        {"name": "Edit", "capability": "edit", "target": "src/b.py", "ok": True},
        {"name": "Write", "capability": "write", "target": "tests/c.py", "ok": True}]


def test_ok_false_the_retry_attempt_a_restart_and_an_unfinished_call(
        repo: Path, seen: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # CHK-AC15, CHK-B24, AC 5
    monkeypatch.setenv(FAIL_FIRST_VAR, "1")

    def restarted(req: SessionRequest, sink: Any) -> SessionResult:
        started(sink)
        push_calls(sink, [("Read", READ, "docs/old.md", True)])
        started(sink)  # an infra try that started again: only what follows counts
        push_calls(sink, [("Read", READ, "docs/new.md", True)], first=1)
        push_calls(sink, [("Read", READ, "docs/open.md", True)], first=2, finish=False)
        return answer("Expanded.", session_id="s")

    ex = Scripted([script([("Read", READ, "docs/a.md", False)]), restarted])
    out = go(repo, ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    first, second = lines(seen)
    assert first["attempt"] == 1 and first["session"] == [
        {"name": "Read", "capability": "read", "target": "docs/a.md", "ok": False}]  # an error is ok false
    assert second["attempt"] == 2 and second["session"] == [  # the retry's own record, not the first attempt's
        {"name": "Read", "capability": "read", "target": "docs/new.md", "ok": True},
        {"name": "Read", "capability": "read", "target": "docs/open.md", "ok": False}]  # no finish: ok false


def _scan(root: Path, planted: str) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and planted.encode() in p.read_bytes()}


def test_tool_inputs_off_and_outside_workspace_and_where_the_record_goes(
        repo: Path, seen: Path, tmp_path: Path) -> None:
    # CHK-AC16, CHK-B24, SEC-B2, AC 5
    planted = "PLANTED-TARGET-4471"
    ex = Scripted([script([("Read", READ, f"docs/{planted}.md", True), ("Read", READ, "<outside workspace>", True)])])
    assert go(repo, ex).exit_code is ExitCode.FINISHED
    (got,) = lines(seen)
    assert [c["target"] for c in got["session"]] == [f"docs/{planted}.md", "<outside workspace>"]
    root = state_root_path(repo)
    assert not seen.resolve().is_relative_to(root.resolve())  # the check's own copy is outside the state root
    holders = _scan(root, planted)
    assert holders and all(re.fullmatch(r"runs/demo/S-1/sessions/[^/]+/(activity\.jsonl|live\.json)", h)
                           for h in holders), holders  # never the run log, ledger, stats, exports, checkpoint


def test_with_tool_inputs_off_every_target_is_null(repo: Path, seen: Path) -> None:  # CHK-AC16, CHK-B24, AC 5
    cfg = Path(os.environ["TEMPERGRAPH_HOME"]) / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "settings.json").write_text(json.dumps({"schema_version": 1, "observe": {"tool_inputs": "off"}}))
    ex = Scripted([script([("Read", READ, "docs/secret.md", True), ("Edit", EDIT, "src/b.py", True)])])
    assert go(repo, ex).exit_code is ExitCode.FINISHED
    (got,) = lines(seen)
    assert got["session"] == [{"name": "Read", "capability": "read", "target": None, "ok": True},
                              {"name": "Edit", "capability": "edit", "target": None, "ok": True}]
    assert not _scan(state_root_path(repo), "secret.md")


def _none_case(repo: Path, seen: Path, ex: Any, spec: Any = None) -> list[dict[str, Any]]:
    out = go(repo, ex, spec)
    assert out.exit_code is ExitCode.FINISHED, out.message
    return lines(seen)


def test_no_record_is_none_never_an_empty_list(repo: Path, seen: Path) -> None:  # CHK-AC17, CHK-B25, AC 5
    # a stand-in that reports tool names only: no capability on any call
    names_only = standin("claude", steps=[answer("x", tools=("Read",), session_id="s")],
                         judges=[answer(MET, tools=("Read",), session_id="j")])
    names_only_run = _none_case(repo, seen, names_only)
    assert [g["session"] for g in names_only_run] == [None]


def test_a_session_with_no_call_has_no_record(repo: Path, seen: Path) -> None:  # CHK-AC17, CHK-B25, AC 5
    assert [g["session"] for g in _none_case(repo, seen, Scripted([script([])]))] == [None]


def test_a_journal_that_dropped_a_tool_line_has_no_record(repo: Path, seen: Path) -> None:
    # CHK-AC17, CHK-B25, AC 5: a journal capped small, so a `truncated` line names a dropped `tool_started`
    def capped(req: SessionRequest, sink: Any) -> SessionResult:
        started(sink)
        sink.max_lines = 4
        push_calls(sink, [("Read", READ, f"docs/{i}.md", True) for i in range(4)])
        return answer("Expanded.", session_id="s")

    assert [g["session"] for g in _none_case(repo, seen, Scripted([capped]))] == [None]
    journals = list((state_root_path(repo) / "runs" / "demo" / "S-1" / "sessions").glob("*/activity.jsonl"))
    assert any('"truncated"' in j.read_text() and "tool_started" in j.read_text().splitlines()[-1] for j in journals)


def test_the_preview_has_no_record_and_the_gates_own_check_has(repo: Path, seen: Path) -> None:
    # CHK-AC17, CHK-B25, AC 5
    def previewing(req: SessionRequest, sink: Any) -> SessionResult:
        (ticket,) = set(re.findall(r"tempergraph self-check ([0-9a-f]{32})", req.prompt))
        started(sink)
        push_calls(sink, [("Read", READ, "docs/a.md", True)])
        assert selfcheck.run(state_root_path(repo), ticket, io.StringIO()) == 0
        return answer("Expanded.", session_id="s")

    got = _none_case(repo, seen, Scripted([previewing]), wf(self_check=True))
    assert [(g["preview"], g["session"] is None) for g in got] == [(True, True), (False, False)]
    assert got[1]["session"] == [{"name": "Read", "capability": "read", "target": "docs/a.md", "ok": True}]


def test_a_check_that_ignores_the_record_gets_the_same_context_on_every_executor(
        repo: Path, seen: Path) -> None:
    # CHK-AC18, CHK-B9, AC 5
    claude = Scripted([script([("Read", READ, "docs/a.md", True)])])
    assert go(repo, claude, wf()).exit_code is ExitCode.FINISHED
    other = Scripted([script([("Read", READ, "docs/a.md", True)])], name="antigravity")
    reg = registry(claude)
    reg.register(other)
    out = start(wf(executor="antigravity"), "S-2", {"request": "x"}, repo, reg, NO_SLEEP)
    assert out.exit_code is ExitCode.FINISHED, out.message
    first, second = lines(seen)
    assert (first["workdir_name"], second["workdir_name"]) == ("demo--S-1", "demo--S-2")  # named by the task
    for doc in (first, second):
        doc.pop("session")
        doc.pop("visit_session")  # VSR-B1 differs by executor as `session` does
        doc.pop("workdir_name")
    assert first == second  # unit, item, visit, attempt, workdir, artifacts, values, settings, criteria, runs, git
    assert first["runs"] == 0 and first["unit"] == "expand" and first["attempt"] == 1


def _call(target: str) -> dict[str, Any]:
    return {"name": "Read", "capability": "read", "target": target, "ok": True}


def test_a_retry_check_sees_the_calls_of_the_whole_visit(
        repo: Path, seen: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AC 7, VSR-AC1
    monkeypatch.setenv(FAIL_FIRST_VAR, "1")
    ex = Scripted([script([("Read", READ, "docs/a.md", True)]), script([("Read", READ, "docs/b.md", True)])])
    assert go(repo, ex).exit_code is ExitCode.FINISHED
    first, second = lines(seen)
    assert first["session"] == [_call("docs/a.md")] and first["visit_session"] == [_call("docs/a.md")]
    assert second["session"] == [_call("docs/b.md")]  # the retry's own calls only
    assert second["visit_session"] == [_call("docs/a.md"), _call("docs/b.md")]  # first attempt, then the retry


def test_a_visit_started_by_a_trip_back_holds_no_call_of_an_earlier_visit(repo: Path, seen: Path) -> None:
    # AC 7, VSR-AC1
    review = Step(prompt="Review {request}", tools=["read"],
                  gate=Gate(judge=Judge(stance="V."), criteria=[crit("c2")], back_targets=["expand"]))
    expand = Step(prompt="Expand the plan for {request}", tools=["read", "write"],
                  produces={"notes": Value(choices=["a", "b"])},
                  gate=Gate(check=seen_check, judge=Judge(stance="V."), criteria=[crit("c1")]))
    spec = named(Workflow(order=["expand", "review"], units={"expand": expand, "review": review},
                          issue_repository="acme/x", routing=Routing(description="Expand a plan")))

    def scripted(target: str, art: str) -> Callable[[SessionRequest, Any], SessionResult]:
        def run(req: SessionRequest, sink: Any) -> SessionResult:
            started(sink)
            push_calls(sink, [("Read", READ, target, True)])
            return answer(f"Done.\nARTIFACT notes: {art}" if art else "Done.", session_id="s")
        return run

    ex = Scripted([scripted("docs/a.md", "a"), scripted("docs/r.md", ""),
                   scripted("docs/b.md", "b"), scripted("docs/r.md", "")])
    judges = [MET, verdict_block("UNMET", defect_in="notes"), MET, MET]
    ex.run_judge = lambda req, views, sink: answer(judges.pop(0), tools=("Read",), session_id="j")  # type: ignore[method-assign]
    assert go(repo, ex, spec).exit_code is ExitCode.FINISHED
    first, second = lines(seen)
    assert (first["visit"], second["visit"]) == (1, 2)
    assert first["visit_session"] == [_call("docs/a.md")]
    assert second["visit_session"] == [_call("docs/b.md")]  # nothing of the first visit


def test_visit_session_is_none_for_a_stand_in_that_reports_tool_names_only(repo: Path, seen: Path) -> None:
    # AC 7, VSR-AC2
    names_only = standin("claude", steps=[answer("x", tools=("Read",), session_id="s")],
                         judges=[answer(MET, tools=("Read",), session_id="j")])
    assert [g["visit_session"] for g in _none_case(repo, seen, names_only)] == [None]


def test_visit_session_is_none_when_the_retrys_own_record_is_none(
        repo: Path, seen: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AC 7, VSR-AC2
    monkeypatch.setenv(FAIL_FIRST_VAR, "1")
    ex = Scripted([script([("Read", READ, "docs/a.md", True)]), script([])])  # the retry has no record
    got = _none_case(repo, seen, ex)
    assert got[1]["session"] is None and got[1]["visit_session"] is None  # although the first attempt has a record


def test_a_retry_after_an_attempt_with_no_record_holds_its_own_calls_alone(
        repo: Path, seen: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AC 7, VSR-AC2
    monkeypatch.setenv(FAIL_FIRST_VAR, "1")
    ex = Scripted([script([]), script([("Read", READ, "docs/b.md", True)])])
    first, second = _none_case(repo, seen, ex)
    assert first["visit_session"] is None
    assert second["visit_session"] == [_call("docs/b.md")]


def test_the_preview_has_no_visit_session(repo: Path, seen: Path) -> None:
    # AC 7, VSR-AC2
    def previewing(req: SessionRequest, sink: Any) -> SessionResult:
        (ticket,) = set(re.findall(r"tempergraph self-check ([0-9a-f]{32})", req.prompt))
        started(sink)
        push_calls(sink, [("Read", READ, "docs/a.md", True)])
        assert selfcheck.run(state_root_path(repo), ticket, io.StringIO()) == 0
        return answer("Expanded.", session_id="s")

    got = _none_case(repo, seen, Scripted([previewing]), wf(self_check=True))
    assert [(g["preview"], g["visit_session"] is None) for g in got] == [(True, True), (False, False)]


def test_one_resolver_serves_every_executor_and_every_caller() -> None:  # CHK-AC3, CHK-B11, CHK-B9, AC 5
    defs = [p.name for p in SRC.rglob("*.py") if re.search(r"^def resolve_command\(", p.read_text(), re.M)]
    assert defs == ["commands.py"]
    for module in ("checks.py", "finalize.py"):
        assert "return resolve_command(self.allow, text, self.workdir)" in (SRC / "run" / module).read_text()
    others = [p.name for p in (SRC / "run").glob("*.py") if p.name != "commands.py"
              and re.search(r"^\s*def \w*resolve\w*command\w*\(", p.read_text(), re.M)]
    assert others == []
    allow = ("pytest", "git status")
    workdir = Path("/tmp/nowhere")
    ctx = CheckContext(unit="u", workdir=workdir, request={}, allow=allow)
    for text in ("pytest tests/a.py", "git status", "git push", "rm -rf x", "pytest ../x", "pytest | cat", ""):
        assert ctx.resolve(text) == resolve_command(allow, text, workdir)
