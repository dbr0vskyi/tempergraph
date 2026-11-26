"""The two open questions of task i171 stay in the specs (AC 8, AC 9): they are questions for the owner, so no
behaviour states them and a test keeps their content."""

from __future__ import annotations

from pathlib import Path

SPECS = Path(__file__).resolve().parents[2] / "docs" / "specs"


def open_questions(name: str) -> str:
    text = (SPECS / name).read_text(encoding="utf-8")
    assert "\n## Open questions\n" in text, name
    return text.split("\n## Open questions\n", 1)[1]


def test_ac8_the_friction_floor_question_carries_the_measured_distribution() -> None:  # AC 8
    section = open_questions("self-improvement.spec.md")
    (item,) = [ln for ln in section.splitlines() if "0.75" in ln and ln.startswith("- ")]
    for part in ("friction.file_confidence", "2026-11-25", "64", "0.70", "0.50", "16", "attributed: false"):
        assert part in item, part


def test_ac9_the_review_repeat_question_is_kept_with_its_default() -> None:  # AC 9
    section = open_questions("review-repeats.spec.md")
    (item,) = [ln for ln in section.splitlines() if "review_repeat" in ln and ln.startswith("- ")]
    assert "improve backlog" in item and "SRV-B28" in item
    assert "Until answered: no" in item and "files no issue" in item
