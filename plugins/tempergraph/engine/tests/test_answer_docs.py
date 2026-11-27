"""AC 15 of task i255: the guide, the operate skill and CLAUDE.md name the answer causes and `--reason`."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
GUIDE = ROOT / "plugins/tempergraph/docs/guides/improving-workflows.guide.md"
OPERATE = ROOT / "plugins/tempergraph/skills/operate/SKILL.md"
CLAUDE = ROOT / "CLAUDE.md"

CAUSES = (
    "answer_overrode:<kind>",
    "upstream_confirmed:<unit>",
    "retry_passed_unchanged:<reason>",
    "retry_same_failure",
    "resume_no_progress",
)
WORDS = "engine_defect|judge_error|environment|plan|request|other"


def test_ac15_guide_names_causes_section_and_reason() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    for cause in CAUSES:
        assert cause in text, cause
    assert "## What was answered" in text
    assert "required" in text and "`resume --reason`" in text
    assert "every answer by another agent is judged" not in text
    assert "even for the starting agent" in text


def test_ac15_guide_keeps_final_exit_paragraph() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    assert "final exit" in text and "exit 5" in text


def test_ac15_operate_skill_shows_reason() -> None:
    text = OPERATE.read_text(encoding="utf-8")
    assert f"--reason <{WORDS.replace('|', chr(92) + '|')}> --as-agent" in text or (
        f"--reason <{WORDS}> --as-agent" in text
    )
    assert "--as-agent" in text


def test_ac15_claude_md_shows_reason() -> None:
    text = CLAUDE.read_text(encoding="utf-8")
    assert "--reason <word>" in text
    assert "--as-agent" in text
