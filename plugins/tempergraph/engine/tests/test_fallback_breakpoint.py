"""A gate's fallback target and operator breakpoints (FLX-B9, FLX-B10, FLX-B11)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from tempergraph.api import Gate, Judge, Routing, Step, Workflow
from tempergraph.constants import ExitCode
from tempergraph.durability.status import row
from tempergraph.executors.standins import answer, standin
from tempergraph.model.validate import errors, validate
from tempergraph.run.runner import RunSettings, ledger_rows, resume, start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.workflows import crit, named
from .test_run import MET, registry, verdict_block

NO_SLEEP = RunSettings(sleep=lambda s: None)
CAPS = {"claude": standin("claude").capabilities()}
WORK = answer("Done.", session_id="s")
PASS = answer(MET, tools=("Read",), session_id="j")
FAIL = answer(verdict_block("UNMET"), tools=("Read",), session_id="j")


def step(prompt: str = "Work on {request}", **gate: Any) -> Any:
    return Step(prompt=prompt, tools=["read"], gate=Gate(judge=Judge(stance="V."), criteria=[crit("c1")], **gate))


def wf(**gate: Any) -> Any:
    units = {"plan": step(**gate), "build": step("Build {request}"), "manual_brief": step("Brief {request}")}
    return named(Workflow(order=["plan", "build", "manual_brief"], units=units, issue_repository="acme/x",
                          routing=Routing(description="Plan, build, or write a manual brief")))


def recs(repo: Path, kind: str, task: str = "F-1") -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", task) / "run.jsonl"
    return [r for r in map(json.loads, p.read_text().splitlines()) if r["kind"] == kind]


def entered(repo: Path, task: str = "F-1") -> list[str]:
    return [r["unit"] for r in recs(repo, "unit_entered", task)]


def go(repo: Path, spec: Any, ex: Any, task: str = "F-1", **kw: Any) -> Any:
    return start(spec, task, {"request": "x"}, repo, registry(ex), dataclasses.replace(NO_SLEEP, **kw))


# -- fallback -------------------------------------------------------------------------------------------


def test_a_spent_budget_takes_the_fallback_and_the_run_is_degraded(repo: Path) -> None:  # FLX-B4, FLX-AC4
    spec = wf(retry_budget=2, on_budget_spent="fallback", fallback="manual_brief")
    ex = standin("claude", steps=[WORK] * 4, judges=[FAIL, FAIL, FAIL, PASS])
    out = go(repo, spec, ex)
    assert out.exit_code is ExitCode.FINISHED and out.degraded, out.message
    assert entered(repo) == ["plan", "manual_brief"]  # `build` is skipped
    brief = [c for c in ex.calls if c.kind == "step"][-1]
    assert "`plan` did not pass (retry_budget)" in brief.request.prompt
    (exit_rec,) = recs(repo, "run_exit")
    assert exit_rec["degraded"] is True and exit_rec["degraded_unit"] == "plan"
    r = row(state_root_path(repo), spec, "demo/F-1")
    assert r["state"] == "finished" and r["degraded"] is True and r["degraded_unit"] == "plan"
    seg = [x for x in ledger_rows(state_root_path(repo)) if x.get("kind") == "run_segment"][-1]
    assert seg["degraded"] is True
    gate = [g for g in recs(repo, "gate") if g["unit"] == "plan"][-1]
    assert gate["token"] == "FALLBACK" and gate["route_target"] == "manual_brief.step"


def test_a_hard_failure_takes_the_fallback_without_a_retry(repo: Path) -> None:
    spec = wf(on_fail="fallback", fallback="manual_brief")
    ex = standin("claude", steps=[WORK, WORK], judges=[FAIL, PASS])
    out = go(repo, spec, ex)
    assert out.exit_code is ExitCode.FINISHED and out.degraded, out.message
    assert [c.kind for c in ex.calls] == ["step", "judge", "step", "judge"]


def test_a_passing_run_is_not_degraded(repo: Path) -> None:
    spec = wf(on_budget_spent="fallback", fallback="manual_brief")
    ex = standin("claude", steps=[WORK] * 3, judges=[PASS] * 3)
    out = go(repo, spec, ex)
    assert out.exit_code is ExitCode.FINISHED and not out.degraded
    assert "degraded" not in recs(repo, "run_exit")[0]
    assert "degraded" not in row(state_root_path(repo), spec, "demo/F-1")


def test_on_fail_stop_stops_at_the_first_failure(repo: Path) -> None:
    ex = standin("claude", steps=[WORK], judges=[FAIL])
    out = go(repo, wf(on_fail="stop"), ex)
    assert out.exit_code is ExitCode.STOPPED and out.reason == "failed"
    assert [c.kind for c in ex.calls] == ["step", "judge"]


def test_the_fallback_refusals(repo: Path) -> None:  # FLX-B11, FLX-AC1
    def codes(**gate: Any) -> set[str]:
        return {f.code for f in errors(validate(wf(**gate), CAPS))}

    assert "fallback-missing" in codes(on_budget_spent="fallback")
    assert "fallback-missing" in codes(on_fail="fallback")
    assert "fallback-not-forward" in codes(on_fail="fallback", fallback="plan")
    assert "fallback-not-forward" in codes(on_fail="fallback", fallback="nowhere")
    assert not codes(on_fail="fallback", fallback="finalizer")
    assert not codes(on_budget_spent="fallback", fallback="build")


# -- breakpoints ----------------------------------------------------------------------------------------


def test_a_breakpoint_pauses_before_a_unit_with_no_session(repo: Path) -> None:  # FLX-B5, FLX-AC3
    spec = wf()
    ex = standin("claude", steps=[WORK] * 3, judges=[PASS] * 3)
    out = go(repo, spec, ex, pause_before=("build",))
    assert out.exit_code is ExitCode.PAUSED and out.reason == "breakpoint", out.message
    assert out.payload["unit"] == "build" and out.payload["decisions"] == ["proceed", "stop"]
    assert [c.kind for c in ex.calls] == ["step", "judge"] and entered(repo) == ["plan"]
    r = row(state_root_path(repo), spec, "demo/F-1")
    assert r["state"] == "paused" and r["pending_gates"][0]["kind"] == "breakpoint"
    none = resume(spec, "F-1", repo, registry(ex), settings=NO_SLEEP)
    assert none.exit_code is ExitCode.USAGE
    bad = resume(spec, "F-1", repo, registry(ex), decision="retry", settings=NO_SLEEP)
    assert bad.exit_code is ExitCode.USAGE and len(ex.calls) == 2
    done = resume(spec, "F-1", repo, registry(ex), decision="proceed", settings=NO_SLEEP)
    assert done.exit_code is ExitCode.FINISHED, done.message
    assert entered(repo) == ["plan", "build", "manual_brief"]
    rows = [x for x in ledger_rows(state_root_path(repo)) if x.get("kind") == "intervention"]
    assert rows[-1]["pause_kind"] == "breakpoint" and rows[-1]["touches"] == [{"class": "steer",
                                                                              "action": "breakpoint"}]


def test_a_breakpoint_before_the_first_unit_and_a_stop(repo: Path) -> None:  # SIL-AC18
    spec = wf()
    ex = standin("claude", steps=[WORK] * 3, judges=[PASS] * 3)
    out = go(repo, spec, ex, pause_before=("plan",))
    assert out.exit_code is ExitCode.PAUSED and ex.calls == [] and recs(repo, "attempt") == []
    segments = [x for x in ledger_rows(state_root_path(repo)) if x.get("kind") == "run_segment"]
    recorded = len(recs(repo, "finding_recorded"))
    stop = resume(spec, "F-1", repo, registry(ex), decision="stop", settings=NO_SLEEP)
    assert stop.exit_code is ExitCode.STOPPED and ex.calls == []
    assert stop.message == "demo/F-1 stopped before plan; resume continues it"
    added = [x for x in ledger_rows(state_root_path(repo)) if x.get("kind") == "run_segment"][len(segments):]
    assert [(x["thread_id"], x["exit_code"], x["reason"]) for x in added] == [("demo/F-1", 4, "person")]
    assert len(recs(repo, "finding_recorded")) == recorded + 1
    assert row(state_root_path(repo), spec, "demo/F-1")["state"] == "unfinished"
    done = resume(spec, "F-1", repo, registry(ex), settings=NO_SLEEP)  # a later resume continues it
    assert done.exit_code is ExitCode.FINISHED, done.message


def test_two_breakpoints_and_one_on_a_resume(repo: Path) -> None:
    spec = wf()
    ex = standin("claude", steps=[WORK] * 3, judges=[PASS] * 3)
    go(repo, spec, ex, pause_before=("plan",))
    again = resume(spec, "F-1", repo, registry(ex), decision="proceed",
                   settings=dataclasses.replace(NO_SLEEP, pause_before=("plan", "manual_brief")))
    assert again.exit_code is ExitCode.PAUSED and again.payload["unit"] == "manual_brief"
    assert entered(repo) == ["plan", "build"]


def test_a_breakpoint_on_an_unknown_unit_is_refused_before_spend(repo: Path) -> None:  # FLX-B11
    ex = standin("claude", steps=[WORK], judges=[PASS])
    out = go(repo, wf(), ex, pause_before=("nowhere",))
    assert out.exit_code is ExitCode.USAGE and out.reason == "breakpoint_unknown" and ex.calls == []
    assert not state_root_path(repo).exists() or not (run_dir(state_root_path(repo), "demo", "F-1")).exists()
