"""The concurrent map: items at once, each with its own state; read-only items fail when they change the run's worktree
(MAP-AC5, CMP-AC9, WSP-AC18)."""

from __future__ import annotations

import dataclasses
import json
import threading
import time
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from tempergraph.compiler import compile_workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionRequest, SessionResult, WorkflowSpec
from tempergraph.executors.standins import answer, standin
from tempergraph.run.runner import start

from .test_map import NO_SLEEP, THREE, mapped, p2_fails_once, recs
from .test_run import MET, registry

FOUR = [{"id": f"p{n}", "text": f"Phase {n}"} for n in range(1, 5)]


class ByItem:
    """A stand-in that answers by unit and item (concurrent items run in any order), counts the sessions open at once
    and can hold each session for a moment so that sessions overlap."""

    def __init__(self, items: list[dict[str, str]] = THREE, *, hold_s: float = 0.0,
                 judges: dict[str, list[str]] | None = None, touch: dict[str, str] | None = None) -> None:
        self.inner = standin("claude")
        self.name = self.inner.name
        self.items = items
        self.hold_s = hold_s
        self.judges = {k: list(v) for k, v in (judges or {}).items()}  # `phase.p2` -> verdict blocks, first one first
        self.touch = touch or {}  # `phase.p2` -> a file the item's first step writes in its working directory
        self.lock = threading.Lock()
        self.open = 0
        self.peak = 0
        self.calls: list[tuple[str, str, str | None]] = []  # (kind, unit, item)
        self.requests: list[SessionRequest] = []
        self.sessions: dict[str, int] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    @staticmethod
    def whose(req: SessionRequest) -> tuple[str, str | None]:
        parts = req.session_key.split(".")
        return parts[0], (parts[1] if parts[0] == "phase" else None)

    def _enter(self, kind: str, req: SessionRequest) -> tuple[str, str | None]:
        unit, item = self.whose(req)
        with self.lock:
            self.open += 1
            self.peak = max(self.peak, self.open)
            self.calls.append((kind, unit, item))
            self.requests.append(req)
            self.sessions[f"{unit}.{item}"] = self.sessions.get(f"{unit}.{item}", 0) + 1
        return unit, item

    def _leave(self) -> None:
        with self.lock:
            self.open -= 1

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        unit, item = self._enter("step", req)
        try:
            if self.hold_s:
                time.sleep(self.hold_s)
            workdir = Path(req.workdir)
            if unit == "plan":
                (workdir / "phases.json").write_text(json.dumps(self.items))
                return answer("Planned.\nARTIFACT phases: phases.json", session_id="plan")
            if unit == "phase":
                name = self.touch.get(f"phase.{item}")
                if name and req.session_key.split(".")[2] == "1":
                    (workdir / name).write_text(f"written by {item}\n")
                return answer(f"Did {item}.\nARTIFACT note: {item}-done", session_id=f"s-{item}")
            return answer("Joined.", session_id="join")
        finally:
            self._leave()

    def run_judge(self, req: SessionRequest, views: Any, sink: Any) -> SessionResult:
        unit, item = self._enter("judge", req)
        try:
            if self.hold_s:
                time.sleep(self.hold_s)
            with self.lock:
                queue = self.judges.get(f"{unit}.{item}") or []
                verdict = queue.pop(0) if queue else MET
            return answer(verdict, tools=("Read",), session_id=f"j-{item}")
        finally:
            self._leave()

    def steps(self, item: str) -> int:
        return len([1 for k, u, i in self.calls if (k, u, i) == ("step", "phase", item)])


def concurrent(*, tools: tuple[str, ...] = ("read",), concurrency: int = 2, workspace: str = "auto",
               **fields: Any) -> WorkflowSpec:
    """A concurrent map whose item step declares `tools` (read-only by default)."""
    spec = mapped(mode="concurrent", concurrency=concurrency, **fields)
    m = spec.units["phase"]
    assert m.step is not None
    changed = dataclasses.replace(m, step=dataclasses.replace(m.step, tools=tuple(tools)))
    return dataclasses.replace(spec, units={**spec.units, "phase": changed}, workspace=workspace)  # type: ignore[arg-type]


def go(repo: Path, spec: WorkflowSpec, ex: Any, task: str = "M-1", **kw: Any) -> Any:
    return start(spec, task, {"request": "x"}, repo, registry(ex), dataclasses.replace(NO_SLEEP, **kw))


def test_a_concurrent_map_runs_two_items_at_once_and_never_a_third(repo: Path) -> None:  # MAP-AC5 (MAP-B9)
    ex = ByItem(FOUR, hold_s=0.15)
    out = go(repo, concurrent(concurrency=2), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert {i for k, u, i in ex.calls if (k, u) == ("step", "phase")} == {"p1", "p2", "p3", "p4"}  # every item runs
    assert ex.peak == 2, ex.peak  # two sessions open at once, never a third
    (items,) = recs(repo, "map_items")
    assert (items["count"], items["ids"]) == (4, ["p1", "p2", "p3", "p4"])


def test_concurrency_above_the_list_runs_the_whole_list_at_once(repo: Path) -> None:  # MAP-AC5 (MAP-B7)
    ex = ByItem(THREE[:2], hold_s=0.15)
    out = go(repo, concurrent(concurrency=3), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert ex.peak == 2 and ex.steps("p1") == 1 and ex.steps("p2") == 1


def test_a_concurrency_of_one_runs_the_items_one_at_a_time(repo: Path) -> None:  # MAP-AC5 (MAP-B7)
    ex = ByItem(THREE, hold_s=0.05)
    out = go(repo, concurrent(concurrency=1), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert ex.peak == 1 and [i for k, u, i in ex.calls if (k, u) == ("step", "phase")] == ["p1", "p2", "p3"]


def test_every_item_keeps_its_own_attempt_feedback_and_result(repo: Path) -> None:  # CMP-AC9 (CMP-B14), MAP-AC5
    ex = ByItem(THREE[:2], hold_s=0.05)
    out = go(repo, concurrent(concurrency=2, check=p2_fails_once), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert ex.steps("p1") == 1 and ex.steps("p2") == 2  # p2 failed its check once and retried; p1 was not touched
    retry = next(r for r in ex.requests if r.session_key == "phase.p2.2.retry")
    assert "not there" in retry.prompt and "Did p2." in retry.prompt  # its own blockers and its own previous report
    assert "Did p1." not in retry.prompt and "Phase 1" not in retry.prompt  # nothing of its sibling
    checks = recs(repo, "check")
    assert sorted((c["item"], c["result"]) for c in checks if c["unit"] == "phase") == [
        ("p1", "PASS"), ("p2", "FAIL"), ("p2", "PASS")]
    gates = [(g["item"] or "-", g["token"]) for g in recs(repo, "gate") if g["unit"] == "phase"]
    assert sorted(gates) == [("-", "PROCEED"), ("p1", "NEXT"), ("p2", "NEXT"), ("p2", "RETRY")]  # `-`: the map's own
    join = next(r for r in ex.requests if r.session_key == "join.1.step")
    assert join.session_key == "join.1.step"  # the join starts once, after both items passed
    assert ex.calls[-2:] == [("step", "join", None), ("judge", "join", None)]


def test_a_concurrent_map_has_no_channel_with_two_writers_and_no_reducer() -> None:  # CMP-AC9 (CMP-B17)
    from typing import get_type_hints

    from tempergraph.compiler.state import RunState, replace

    from .test_compiler import Scripted

    hints = get_type_hints(RunState, include_extras=True)
    spec = concurrent()
    cw = compile_workflow(spec, Scripted(spec, {}), InMemorySaver())
    assert "phase.item_step" in cw.nodes
    for channel, hint in hints.items():
        reducers = [m for m in getattr(hint, "__metadata__", ()) if callable(m)]
        assert len(reducers) == 1, channel
        if channel in ("attempts", "judgements", "feedback", "counters", "route", "pause", "artifacts", "values",
                       "facts", "maps"):
            assert reducers[0] is not replace, channel  # items write these in one superstep, keyed by their slot
    from tempergraph.compiler.state import merge_units

    merged = merge_units({"phase.p1": {"attempt": 1}}, {"phase.p2": {"attempt": 1}})
    assert merged == {"phase.p1": {"attempt": 1}, "phase.p2": {"attempt": 1}}  # two items' records both survive


def test_a_read_only_item_that_changes_the_run_worktree_fails(repo: Path) -> None:  # WSP-AC18 (WSP-B11), MAP-AC5
    ex = ByItem(THREE[:2], touch={"phase.p2": "leak.txt"})
    out = go(repo, concurrent(concurrency=1, retry_budget=0), ex)
    assert out.exit_code is ExitCode.PAUSED, out.message
    assert (out.payload["kind"], out.payload["unit"], out.payload["item"]) == ("budget", "phase", "p2")
    assert [b["problem"] for b in out.payload["blockers"]] == ["branch_changed_the_workspace"]
    assert ex.steps("p1") == 1 and ex.steps("p2") == 1  # p1 changed nothing and passed; p2 ran once


def test_a_read_only_item_that_changes_nothing_passes(repo: Path) -> None:  # WSP-AC18 (WSP-B11), MAP-AC5
    out = go(repo, concurrent(concurrency=2), ByItem(THREE[:2]))
    assert out.exit_code is ExitCode.FINISHED, out.message


def test_a_sequential_map_item_may_change_the_worktree(repo: Path) -> None:  # WSP-AC18 (the rule is the concurrent map's)
    ex = ByItem(THREE[:2], touch={"phase.p2": "leak.txt"})
    out = go(repo, mapped(), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message  # the item's write went to the run's worktree, not refused
