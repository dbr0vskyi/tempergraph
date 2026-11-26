"""A thread stopped by request resumes with no decision (RCT-B11, RCT-AC11, RCT-AC3; DUR-B9, DUR-B15)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionRequest, SessionResult, ThreadState, Usage
from tempergraph.durability.control import request_stop, stop_file
from tempergraph.durability.lock import RunLock
from tempergraph.durability.status import classify, status
from tempergraph.executors.standins import ScriptedExecutor, standin
from tempergraph.run.runner import RunSettings, resume, start
from tempergraph.store.layout import lock_path, run_dir, state_root_path

from .conftest import hash_tree
from .fixtures.workflows import two_step
from .test_run import DRAFT, REVIEW, judge, registry, verdict_block

NO_SLEEP = RunSettings(sleep=lambda s: None)


def records(repo: Path) -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", "T-1") / "run.jsonl"
    return [json.loads(ln) for ln in p.read_text().splitlines()]


def stopper(root: Path, mode: str, then: SessionResult) -> Any:
    """A scripted reply that writes a stop request while the run holds its lock, then answers with `then`."""
    def reply(req: SessionRequest) -> SessionResult:
        request_stop(root, "demo", "T-1", mode)  # type: ignore[arg-type]
        return then

    return reply


def ended_by_stop() -> SessionResult:
    return SessionResult(ok=False, partial=True, usage=Usage())


def spec_with_retry(budget: int) -> Any:
    spec = two_step()
    units = dict(spec.units)
    units["draft"] = dataclasses.replace(units["draft"], gate=dataclasses.replace(units["draft"].gate,
                                                                                  retry_budget=budget))
    return dataclasses.replace(spec, units=units)


def stopped_run(repo: Path, mode: str, spec: Any = None) -> tuple[Any, ScriptedExecutor]:
    root = state_root_path(repo)
    if mode == "drain":  # written during draft: the run stops at the boundary before review
        steps = [stopper(root, "drain", DRAFT)]
        judges = [judge()]
    else:  # written during draft's session, which the stop ends
        steps = [stopper(root, "now", ended_by_stop())]
        judges = []
    ex = standin("claude", steps=steps, judges=judges)
    out = start(spec or two_step(), "T-1", {"request": "x"}, repo, registry(ex), NO_SLEEP)
    return out, ex


@pytest.mark.parametrize("mode", ["drain", "now"])
def test_a_thread_stopped_by_request_resumes_with_no_decision(repo: Path, mode: str) -> None:  # RCT-AC11 (RCT-B11)
    out, ex = stopped_run(repo, mode)
    root = state_root_path(repo)
    assert out.exit_code is ExitCode.STOPPED and out.reason == "stopped_by_request", out.message
    assert not stop_file(root, "demo", "T-1").exists()
    assert classify(root, two_step(), "T-1") is ThreadState.UNFINISHED
    ex.steps, ex.judges = ([REVIEW], [judge()]) if mode == "drain" else ([DRAFT, REVIEW], [judge(), judge()])
    back = resume(two_step(), "T-1", repo, registry(ex), settings=NO_SLEEP)
    assert back.exit_code is ExitCode.FINISHED, back.message
    assert "None" not in back.message
    assert not stop_file(root, "demo", "T-1").exists()
    assert classify(root, two_step(), "T-1") is ThreadState.FINISHED
    exits = [r for r in records(repo) if r["kind"] == "run_exit"]
    assert exits[0]["reason"] == "stopped_by_request" and all(r.get("reason") != "attempt_cap" for r in exits)


def starts(repo: Path) -> list[str]:
    return [r["session_key"] for r in records(repo) if r["kind"] == "attempt_start"
            and r["session_key"].split(".")[-1] in ("step", "retry")]


def test_a_now_stop_spends_no_retry_and_the_interrupted_attempt_runs_again(repo: Path) -> None:  # RCT-AC3 (RCT-B11)
    spec = spec_with_retry(1)
    out, ex = stopped_run(repo, "now", spec)
    assert out.reason == "stopped_by_request", out.message
    assert not [r for r in records(repo) if r["kind"] == "gate"]  # no judgement, so no retry charged
    ex.steps, ex.judges = [DRAFT, REVIEW], [judge(), judge()]
    back = resume(spec, "T-1", repo, registry(ex), settings=NO_SLEEP)
    assert back.exit_code is ExitCode.FINISHED, back.message
    assert starts(repo) == ["draft.1.step", "draft.1.step", "review.1.step"]  # no draft.2.retry
    assert [r["attempts_counted"] for r in records(repo) if r["kind"] == "run_exit" and "attempts_counted" in r] == []


def test_a_drain_stop_starts_the_attempt_due_next_as_attempt_one(repo: Path) -> None:  # RCT-AC3 (RCT-B11)
    spec = spec_with_retry(1)
    out, ex = stopped_run(repo, "drain", spec)
    assert out.reason == "stopped_by_request", out.message
    ex.steps, ex.judges = [REVIEW], [judge()]
    back = resume(spec, "T-1", repo, registry(ex), settings=NO_SLEEP)
    assert back.exit_code is ExitCode.FINISHED, back.message
    assert starts(repo) == ["draft.1.step", "review.1.step"]
    assert not [r for r in records(repo) if r["kind"] == "gate" and r.get("token") == "RETRY"]


def person_stopped(repo: Path) -> Any:
    """A thread a person stopped at an escalation pause of `draft`."""
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    assert start(two_step(), "T-1", {"request": "x"}, repo, registry(ex), NO_SLEEP).exit_code is ExitCode.PAUSED
    out = resume(two_step(), "T-1", repo, registry(ex), decision="stop", settings=NO_SLEEP)
    assert out.reason == "person", out.message
    return ex


def budget_stopped(repo: Path) -> tuple[Any, Any]:
    spec = two_step()
    units = dict(spec.units)
    units["draft"] = dataclasses.replace(units["draft"], gate=dataclasses.replace(units["draft"].gate,
                                                                                  on_budget_spent="stop"))
    spec = dataclasses.replace(spec, units=units)
    fail = verdict_block("UNMET")
    ex = standin("claude", steps=[DRAFT] * 3, judges=[judge(fail)] * 3)
    out = start(spec, "T-2", {"request": "x"}, repo, registry(ex), NO_SLEEP)
    assert out.reason == "budget", out.message
    return spec, ex


def test_a_refused_reopen_names_the_unit_and_the_reason(repo: Path) -> None:  # DUR-AC12 (DUR-B14)
    root = state_root_path(repo)
    ex = person_stopped(repo)
    before = hash_tree(root)
    out = resume(two_step(), "T-1", repo, registry(ex), settings=NO_SLEEP)
    assert out.exit_code is ExitCode.USAGE and "draft" in out.message and "person" in out.message, out.message
    assert hash_tree(root) == before
    ex.steps, ex.judges = [DRAFT, REVIEW], [judge(), judge()]
    assert resume(two_step(), "T-1", repo, registry(ex), decision="retry",
                  settings=NO_SLEEP).exit_code is ExitCode.FINISHED

    spec, ex2 = budget_stopped(repo)
    before = hash_tree(root)
    for decision in (None, "proceed"):
        out = resume(spec, "T-2", repo, registry(ex2), decision=decision, settings=NO_SLEEP)
        assert out.exit_code is ExitCode.USAGE and "draft" in out.message and "budget" in out.message, out.message
        assert hash_tree(root) == before
    ex2.steps, ex2.judges = [DRAFT, REVIEW], [judge(), judge()]
    assert resume(spec, "T-2", repo, registry(ex2), decision="retry",
                  settings=NO_SLEEP).exit_code is ExitCode.FINISHED


def test_status_gives_an_unfinished_thread_the_plain_resume_command(repo: Path) -> None:  # DUR-AC13 (DUR-B15)
    root = state_root_path(repo)
    out, ex = stopped_run(repo, "drain")
    assert out.reason == "stopped_by_request"
    r = status(root, {"demo": two_step()})["threads"][0]
    assert r["state"] == "unfinished" and r["exit_reason"] == "stopped_by_request"
    assert r["resume"] == "tempergraph resume demo T-1" and "--decision" not in r["resume"]
    ex.steps, ex.judges = [REVIEW], [judge()]
    assert resume(two_step(), "T-1", repo, registry(ex), settings=NO_SLEEP).exit_code is ExitCode.FINISHED

    # a thread paused at a gate has its gates' commands and no `resume` key
    ex2 = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    assert start(two_step(), "T-2", {"request": "x"}, repo, registry(ex2), NO_SLEEP).exit_code is ExitCode.PAUSED
    rows = {t["thread_id"]: t for t in status(root, {"demo": two_step()})["threads"]}
    assert rows["demo/T-2"]["state"] == "paused" and "resume" not in rows["demo/T-2"]

    with RunLock(lock_path(root, "demo", "T-2")):  # a thread whose lock is held is running
        held = {t["thread_id"]: t for t in status(root, {"demo": two_step()})["threads"]}["demo/T-2"]
        assert held["state"] == "running" and "resume" not in held


def test_a_stale_request_is_cleared_and_a_stronger_mode_stays(repo: Path) -> None:  # RCT-AC8 (RCT-B8, RCT-B9)
    root = state_root_path(repo)
    out, ex = stopped_run(repo, "drain")
    assert out.reason == "stopped_by_request"
    path = stop_file(root, "demo", "T-1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "mode": "now", "caller": {}}), encoding="utf-8")
    ex.steps, ex.judges = [REVIEW], [judge()]
    back = resume(two_step(), "T-1", repo, registry(ex), settings=NO_SLEEP)
    assert "stale_stop_request_removed" in back.warnings and back.exit_code is ExitCode.FINISHED, back.message
    assert not path.exists()

    with RunLock(lock_path(root, "demo", "T-1")):  # a second request keeps the stronger mode
        assert request_stop(root, "demo", "T-1", "now") == "now"
        assert request_stop(root, "demo", "T-1", "drain") == "now"
        assert json.loads(path.read_text(encoding="utf-8"))["mode"] == "now"
