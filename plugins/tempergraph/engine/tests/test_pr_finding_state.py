"""The finding follows the run's state, and reads that overlap leave one entry and one finding for each unit
(SIL-AC33, OUT-AC13, OUT-AC15; task AC 2, AC 3)."""

from __future__ import annotations

import dataclasses
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from tempergraph.durability import lock
from tempergraph.executors.standins import standin
from tempergraph.improve import child, escape
from tempergraph.model import flow

from .test_outcome_escape_finding import escapes, hand, loop_kinds, make_run, process
from .test_pr_later import QUIET, REPO, CountingHost, commit, head, pr_host, rows, state
from .test_pr_later import review as pr_review
from .test_run import registry


def units(root: Path, task: str = "T-1") -> list[str]:
    return sorted(str(f["unit"]) for f in escapes(root, task))


# -- SIL-AC33: the finding follows the state ------------------------------------------------------------------------

def test_a_later_follow_up_commit_adds_the_finding_of_the_unit_that_wrote_the_file(tmp_path: Path) -> None:
    # SIL-AC33, task AC 2
    root = state(tmp_path)
    make_run(root, "T-1", {"a": ["a.py"], "b": ["b.py"]}, request="R1")
    host = pr_host()
    host.reviews[(REPO, 1)] = [pr_review()]
    process(root, host)
    assert units(root) == [flow.OUTCOME_UNIT]
    host.commits[(REPO, 1)] = [commit(head(root), []), commit("bbbbbbb2", ["a.py"])]
    process(root, host)
    assert units(root) == sorted([flow.OUTCOME_UNIT, "a"])
    process(root, host)  # a third read adds none
    assert units(root) == sorted([flow.OUTCOME_UNIT, "a"])
    assert len(rows(root)) == 2


def test_a_finding_that_could_not_be_written_is_left_to_the_next_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # SIL-AC33, OUT-AC13, task AC 3
    root = state(tmp_path)
    make_run(root, "T-1", {"a": ["a.py"]}, request="R1")
    host = pr_host()
    host.reviews[(REPO, 1)] = [pr_review()]
    real = escape.append_findings
    calls: list[int] = []

    def flaky(*a: Any, **k: Any) -> Any:
        calls.append(1)
        if len(calls) == 1:
            raise OSError("disk full")
        return real(*a, **k)

    monkeypatch.setattr(escape, "append_findings", flaky)
    process(root, host)
    assert len(rows(root)) == 1 and escapes(root, "T-1") == []
    skipped = [r for r in loop_kinds(root) if r["kind"] == "loop_skipped" and r.get("step") == "pull_request_read"]
    assert len(skipped) == 1 and skipped[0]["thread"] == "demo/T-1"
    process(root, host)
    assert len(rows(root)) == 1  # no second entry
    assert units(root) == [flow.OUTCOME_UNIT]


# -- OUT-AC15: overlapping reads -------------------------------------------------------------------------------------

@dataclasses.dataclass(kw_only=True)
class WaitingHost(CountingHost):
    barrier: threading.Barrier = dataclasses.field(default_factory=lambda: threading.Barrier(2))

    def pull_state(self, repo: str, number: int) -> dict[str, Any]:
        try:
            self.barrier.wait(timeout=1.5)  # both reads meet here, unless the second waits at the lock
        except threading.BrokenBarrierError:
            pass
        return super().pull_state(repo, number)


def test_two_reads_that_overlap_leave_one_entry_and_one_finding_for_each_unit(tmp_path: Path) -> None:
    # OUT-AC15, OUT-AC13, task AC 3
    root = state(tmp_path)
    make_run(root, "T-1", {"a": ["a.py"], "b": ["b.py"]}, request="R1")
    host = WaitingHost()
    host.pulls.append({"repo": REPO, "number": 1, "state": "open", "draft": True})
    host.commits[(REPO, 1)] = [commit(head(root), []), commit("bbbbbbb2", ["a.py", "b.py"])]
    t = hand(root, dataclasses.replace(QUIET, improvement_mode="stable"))
    errors: list[BaseException] = []

    def run() -> None:
        try:
            child.process(t, registry(standin("claude")), host)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=60)
    assert errors == []
    assert len(rows(root)) == 1
    assert units(root) == ["a", "b"] and len(escapes(root, "T-1")) == 2
    assert len([r for r in loop_kinds(root) if r["kind"] == "loop_lens"]) == 1


def test_an_exclusive_lock_makes_a_second_holder_wait(tmp_path: Path) -> None:  # OUT-AC15, task AC 3
    path = tmp_path / "locks" / "pull-request-read" / "demo.lock"
    order: list[str] = []

    def second() -> None:
        with lock.exclusive(path):
            order.append("second")

    with lock.exclusive(path):
        assert lock.is_held(path)
        th = threading.Thread(target=second)
        th.start()
        time.sleep(0.3)
        assert order == []
        with pytest.raises(lock.LockHeld):
            with lock.exclusive(path, timeout_s=0.1):
                pass
        order.append("first")
    th.join(timeout=10)
    assert order == ["first", "second"]
    assert not lock.is_held(path)
