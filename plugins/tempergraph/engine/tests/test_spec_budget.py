"""Spec budget rule of the docs README: at most 400 lines and 30 KB per spec (OVR-AC2)."""

from __future__ import annotations

from .conftest import DOCS, workflow_names

CHANGED_SPECS = ("compiler-and-flow", "run-control", "durability-and-resume", "run-settings-and-overrides",
                 "map-unit")


def test_the_specs_of_the_attempt_cap_and_stop_change_stay_within_budget_and_name_no_workflow() -> None:
    # AC 10 (CMP-AC11, CMP-AC12, CMP-AC13, CMP-AC14, RCT-AC11, DUR-AC12, DUR-AC13)
    names = workflow_names()
    assert names, "no workflow package found: the check would prove nothing"
    for stem in CHANGED_SPECS:
        data = (DOCS / "specs" / f"{stem}.spec.md").read_bytes()
        assert len(data) <= 30 * 1024 and data.count(b"\n") <= 400, (stem, len(data), data.count(b"\n"))
        text = data.decode("utf-8").lower()
        assert [n for n in names if n.lower() in text] == [], stem


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
