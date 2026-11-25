"""Spec budget rule of the docs README: at most 400 lines and 30 KB per spec (OVR-AC2)."""

from __future__ import annotations

from .conftest import DOCS


def test_every_spec_within_budget() -> None:
    over = []
    for p in sorted((DOCS / "specs").glob("*.spec.md")):
        data = p.read_bytes()
        lines = data.count(b"\n")
        if len(data) > 30 * 1024 or lines > 400:
            over.append(f"{p.name}: {len(data)} bytes, {lines} lines")
    assert over == [], over


def test_the_schedule_specs_stay_within_budget_after_the_ticks_task_changed_their_text() -> None:  # AC 13
    for name in ("schedules.spec.md", "schedule-ticks-and-unattended-fires.spec.md"):
        data = (DOCS / "specs" / name).read_bytes()
        assert len(data) <= 30 * 1024 and data.count(b"\n") <= 400, (name, len(data))
