"""The repository records the worktree probes before any worktree control is marked `LIVE-PROVEN` (WTR-AC7). A probe can
only be proved live: this offline test pins what the repository records, the live test and its row of the live-checks
plan, and that nothing claims more."""

from __future__ import annotations

from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "plugins" / "tempergraph" / "docs").is_dir())
DOCS = ROOT / "plugins" / "tempergraph" / "docs"
PROBES = ("P-WTR-1", "P-WTR-2", "P-WTR-3", "P-WTR-4")


def lines_of(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_spec_82_names_the_four_probes_as_not_run() -> None:  # WTR-AC7 (WTR-B26, WTR-B13, WTR-B25)
    (line,) = [ln for ln in lines_of(DOCS / "specs" / "82-worktree-mode.spec.md") if ln.startswith("- Not built yet")]
    assert PROBES[0] in line and PROBES[-1] in line and "P-WTR-1 to P-WTR-4" in line  # the four, named as a range


def test_the_live_test_for_p_wtr_1_exists_and_the_live_checks_plan_has_its_row() -> None:  # WTR-AC7 (WTR-B25)
    live = (Path(__file__).resolve().parent / "live" / "test_probes.py").read_text(encoding="utf-8")
    assert "def test_p_wtr_1_no_worktree_tools(" in live
    rows = [ln for ln in lines_of(DOCS / "plans" / "live-checks.plan.md") if ln.startswith("| L-8 ")]  # its check, its result
    assert rows and "P-WTR-1" in rows[0] and "test_p_wtr_1_no_worktree_tools" in rows[0]


def test_no_spec_or_plan_marks_a_worktree_control_live_proven() -> None:  # WTR-AC7 (WTR-B26, WTR-B13, WTR-B25)
    marked: list[str] = []
    for folder in ("specs", "plans"):
        for path in sorted((DOCS / folder).glob("*.md")):
            for n, ln in enumerate(lines_of(path), start=1):
                low = ln.lower()
                if "live-proven" in low and ("worktree" in low or "wtr" in low) and "WTR-AC7" not in ln:
                    marked.append(f"{path.name}:{n}")
    assert marked == []  # the criterion's own line, which states the rule, is the one that names the flag
