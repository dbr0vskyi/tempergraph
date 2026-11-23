"""Item pauses of a concurrent map: each item has its own retry budget, a spent item pauses addressed by unit and item
while the others keep their results, and a resume names the item it answers (MAP-AC6, MAP-AC7, MAP-B6, MAP-B10, HUM-B3)."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode
from tempergraph.contracts import WorkflowSpec
from tempergraph.durability import engine_file
from tempergraph.durability.checkpoint import observer_graph, open_readonly, snapshot
from tempergraph.durability.status import row
from tempergraph.run.runner import resume
from tempergraph.store.layout import state_root_path

from .test_map import FAIL, NO_SLEEP
from .test_map_concurrent import ByItem, concurrent, go
from .test_run import registry

FIVE = [{"id": f"p{n}", "text": f"Phase {n}"} for n in range(1, 6)]
BOTH_FAIL = {"phase.p2": [FAIL, FAIL], "phase.p5": [FAIL, FAIL]}  # every attempt of p2 and p5 is judged unmet


def paused(repo: Path) -> tuple[WorkflowSpec, ByItem, Any]:
    spec = concurrent(concurrency=3, retry_budget=1)
    ex = ByItem(FIVE, judges={k: list(v) for k, v in BOTH_FAIL.items()})
    return spec, ex, go(repo, spec, ex)


def gates(repo: Path, spec: WorkflowSpec) -> list[dict[str, Any]]:
    return row(state_root_path(repo), spec, "demo/M-1")["pending_gates"]


def answer_item(repo: Path, spec: WorkflowSpec, ex: ByItem, unit: str | None, decision: str) -> Any:
    settings = dataclasses.replace(NO_SLEEP, unit=unit) if unit else NO_SLEEP
    return resume(spec, "M-1", repo, registry(ex), decision=decision, settings=settings)


def test_a_spent_item_pauses_by_unit_and_item_while_the_others_keep_their_results(repo: Path) -> None:  # MAP-AC6 (MAP-B10)
    spec, ex, out = paused(repo)
    assert out.exit_code is ExitCode.PAUSED, out.message
    assert out.payload["kind"] == "budget" and out.payload["unit"] == "phase" and out.payload["item"] in ("p2", "p5")
    assert sorted((g["unit"], g["item"], g["kind"]) for g in gates(repo, spec)) == [
        ("phase.p2", "p2", "budget"), ("phase.p5", "p5", "budget")]  # addressed by unit and item
    assert [ex.steps(i) for i in ("p1", "p2", "p3", "p4", "p5")] == [1, 2, 1, 1, 2]  # each failing item ran one retry
    before = dict(ex.sessions)
    # the person passes p2 and retries p5: p1, p3 and p4 start no session, whatever else runs
    assert answer_item(repo, spec, ex, "phase.p5", "retry").exit_code is ExitCode.PAUSED  # p2 is still pending
    done = answer_item(repo, spec, ex, "phase.p2", "proceed")
    assert done.exit_code is ExitCode.FINISHED, done.message
    for item in ("p1", "p3", "p4"):  # they kept their results: no session after the pauses
        assert ex.sessions[f"phase.{item}"] == before[f"phase.{item}"], item
    assert ex.steps("p2") == 2 and ex.steps("p5") == 3  # p2 was passed by a person; only p5 ran again


def test_items_keep_separate_retry_counters(repo: Path) -> None:  # MAP-AC6 (MAP-B6, MAP-B10)
    spec = concurrent(concurrency=3, retry_budget=1)
    ex = ByItem(FIVE[:3], judges={"phase.p1": [FAIL], "phase.p2": [FAIL, FAIL]})  # p1 retries once and passes; p2 is spent
    out = go(repo, spec, ex)
    assert out.exit_code is ExitCode.PAUSED, out.message
    assert out.payload["item"] == "p2"
    assert [ex.steps(i) for i in ("p1", "p2", "p3")] == [2, 2, 1]  # p1's retry did not spend p2's or p3's budget
    assert "--unit phase.p2 --decision <proceed|retry|stop>" in out.payload["resume"]  # the exact command
    (left,) = gates(repo, spec)
    assert left["unit"] == "phase.p2" and "--unit phase.p2" in left["resume"]


def test_a_resume_without_an_item_is_refused_with_every_command(repo: Path) -> None:  # MAP-AC7 (MAP-B6, HUM-B3)
    spec, ex, out = paused(repo)
    assert out.exit_code is ExitCode.PAUSED, out.message
    ids = interrupt_ids(spec, repo)
    assert sorted(ids.values()) == ["phase.p2", "phase.p5"]  # the two pending interrupts, by slot
    neither = answer_item(repo, spec, ex, None, "retry")
    assert neither.exit_code is ExitCode.USAGE and neither.reason == "unit_missing"
    assert len(neither.refusals) == 2 and all("--unit phase." in line for line in neither.refusals)
    assert {u for line in neither.refusals for u in ("phase.p2", "phase.p5") if u in line} == {"phase.p2", "phase.p5"}
    unknown = answer_item(repo, spec, ex, "phase.p3", "retry")  # a name that is no pending item
    assert unknown.exit_code is ExitCode.USAGE and unknown.reason == "unit_unknown"


def test_retry_of_one_item_reruns_only_that_item(repo: Path) -> None:  # MAP-AC7 (MAP-B6), MAP-AC3
    spec, ex, out = paused(repo)
    assert out.exit_code is ExitCode.PAUSED, out.message
    before = dict(ex.sessions)
    one = answer_item(repo, spec, ex, "phase.p5", "retry")
    assert one.exit_code is ExitCode.PAUSED, one.message
    (left,) = gates(repo, spec)
    assert left["unit"] == "phase.p2"  # the other pause is still pending
    done = answer_item(repo, spec, ex, "phase.p2", "stop")  # `stop` on the other ends the map
    assert done.exit_code is ExitCode.STOPPED, done.message
    assert ex.sessions["phase.p5"] == before["phase.p5"] + 2  # p5 alone ran again: its step and its judge
    for item in ("p1", "p2", "p3", "p4"):
        assert ex.sessions[f"phase.{item}"] == before[f"phase.{item}"], item
    assert "join" not in [u for _, u, _ in ex.calls]


def interrupt_ids(spec: WorkflowSpec, repo: Path) -> dict[str, str]:
    """The pending interrupts of the thread, each to the unit a resume names it by."""
    with open_readonly(engine_file.checkpoint_of(state_root_path(repo), spec.name, "M-1")) as saver:
        assert saver is not None
        return snapshot(observer_graph(spec, saver), "demo/M-1").interrupt_ids
