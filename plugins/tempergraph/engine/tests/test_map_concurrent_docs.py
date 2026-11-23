"""The concurrent map is built and its documents say so: no `not_in_release` refusal of a map's mode, no document that
calls the mode, item worktrees or the reservations for maps unbuilt, and the release 3 plan records the phase (MAP-AC1,
MAP-AC2, MAP-AC5 to MAP-AC9)."""

from __future__ import annotations

from pathlib import Path

from tempergraph.model.validate import errors, validate

from .test_map import mapped

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "plugins" / "tempergraph" / "docs").is_dir())
DOCS = ROOT / "plugins" / "tempergraph" / "docs"
SRC = Path(__file__).resolve().parents[1] / "src" / "tempergraph"


def test_the_source_has_no_not_in_release_refusal_of_a_maps_mode() -> None:  # MAP-AC1, MAP-AC2 (MAP-B7)
    for path in SRC.rglob("*.py"):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            assert not ("not_in_release" in line and "map mode" in line), f"{path.name}:{n}"
    found = [f.code for f in errors(validate(mapped(mode="concurrent"), {}))]
    assert "not_in_release" not in found, found  # a concurrent map validates


def test_spec_77_does_not_call_the_concurrent_mode_unbuilt() -> None:  # MAP-AC1, MAP-AC5
    text = (DOCS / "specs" / "77-map-unit.spec.md").read_text(encoding="utf-8")
    assert not [ln for ln in text.splitlines() if ln.lower().startswith("- not built yet")]
    for ln in text.splitlines():
        low = ln.lower()
        assert not ("concurrent" in low and ("not_in_release" in low or "not built" in low or "later release" in low)), ln


def test_the_not_built_lines_of_specs_08_and_82_name_only_what_is_left() -> None:  # BUD-AC9, WTR-AC12
    line_08 = next(ln for ln in (DOCS / "specs" / "08-budgets-and-failures.spec.md").read_text(encoding="utf-8")
                   .splitlines() if ln.startswith("- Not built yet")).lower()
    assert all(w in line_08 for w in ("contests", "projection", "bud-b12", "bud-b15"))
    assert "councils" not in line_08 and "maps" not in line_08  # a council's sessions reserve too (BUD-AC12)
    line_82 = next(ln for ln in (DOCS / "specs" / "82-worktree-mode.spec.md").read_text(encoding="utf-8").splitlines()
                   if ln.startswith("- Not built yet")).lower()
    assert "slot" in line_82 and "item" not in line_82


def test_the_rationale_note_does_not_say_the_concurrent_mode_is_refused() -> None:  # MAP-AC2
    text = (DOCS / "research" / "R-150-rationale-carried-from-the-engine-specs.rsrch.md").read_text(encoding="utf-8")
    bullets = [ln for ln in text.splitlines() if ln.startswith("- As built (R2-T1.2, sequential mode)")]
    assert len(bullets) == 1 and "refused" not in bullets[0] and "R3-T3.2" in bullets[0]


def test_the_release_3_plan_records_the_concurrent_map_as_built() -> None:  # MAP-AC1
    plan = (DOCS / "plans" / "third-release.plan.md").read_text(encoding="utf-8")
    t3 = plan.split("### R3-T3 Writer branches and the concurrent map", 1)[1].split("\n### ", 1)[0]
    assert t3.count("Status: built") == 2  # R3-T3.1 and R3-T3.2
    first = t3.split("#### R3-T3.2", 1)[0]
    assert "stay with R3-T3.2" not in first
    assert "R3-T3.1 and R3-T3.2 are built" in plan.split("**Status: In progress.**", 1)[1].split("\n", 1)[0]
