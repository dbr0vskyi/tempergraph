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
from tempergraph.durability.status import classify
from tempergraph.executors.standins import ScriptedExecutor, standin
from tempergraph.run.runner import RunSettings, resume, start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.workflows import two_step
from .test_run import DRAFT, REVIEW, judge, registry

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
