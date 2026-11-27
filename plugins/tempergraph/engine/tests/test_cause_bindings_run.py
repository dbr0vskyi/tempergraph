"""Fixture runs of the loop child for the bindings of a cause (BND-AC1 to BND-AC12), through `child.process`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tempergraph.executors.standins import standin
from tempergraph.improve import child, filing
from tempergraph.improve.codehost import MemoryCodeHost

from .test_loop_child import friction_ticket, judge_says, loop_rows
from .test_run import registry


def set_day(monkeypatch: pytest.MonkeyPatch, day: datetime) -> None:
    """The loop child's UTC day: its filing time and the time of its records move together."""
    monkeypatch.setattr(child, "filing_clock", lambda: day)
    monkeypatch.setattr(child, "now_iso", lambda: day.isoformat(timespec="milliseconds").replace("+00:00", "Z"))


def test_the_filing_clock_makes_two_utc_days(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # BND-AC6
    day1 = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    day2 = day1 + timedelta(days=1)
    root = tmp_path / ".tempergraph"
    host = MemoryCodeHost()
    reg = registry(standin("claude", judges=[judge_says(0.5) for _ in range(8)]))
    set_day(monkeypatch, day1)
    for n in (1, 2, 3):  # the third exit files the one issue
        child.process(friction_ticket(root, n), reg, host)
    assert len(host.issues) == 1
    ops = [[r["op"] for r in child.process(friction_ticket(root, n), reg, host)["results"]] for n in (4, 5)]
    assert ops == [["commented"], ["comment_capped"]]  # the bound of the day follows the set clock
    commented = [r for n in (4, 5) for r in loop_rows(root, f"F-{n}") if r["kind"] == "issue_commented"]
    assert [r["ts"][:10] for r in commented] == [day1.date().isoformat()]
    assert filing.comments_by_day(root, "demo", day1) == {("team/notes", 1): 1}
    set_day(monkeypatch, day2)  # the next UTC day starts at none
    out = child.process(friction_ticket(root, 6), reg, host)
    assert [r["op"] for r in out["results"]] == ["commented"]
    rows = [r for r in loop_rows(root, "F-6") if r["kind"] == "issue_commented"]
    assert rows[0]["ts"][:10] == day2.date().isoformat()
    assert filing.comments_by_day(root, "demo", day2) == {("team/notes", 1): 1}


def test_the_clock_of_the_retry_wait_keeps_its_meaning() -> None:
    assert isinstance(child.clock(), float)
    assert isinstance(child.filing_clock(), datetime) and child.filing_clock().tzinfo is not None
