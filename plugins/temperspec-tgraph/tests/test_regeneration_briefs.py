"""What the briefs tell a session about a failed regeneration (spec regeneration-failures, RGF-B5)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _code_prompt() -> str:
    return (ROOT / "prompts" / "code.md").read_text(encoding="utf-8")


def _said(*parts: str) -> str:
    return re.sub(r"\s+", " ", (ROOT.joinpath(*parts)).read_text(encoding="utf-8")).lower()


def test_rgn_ac14_the_plan_and_expand_prompts_give_a_generated_file_no_row() -> None:
    # RGN-AC14 (RGN-B14), AC 8
    for name in ("plan.md", "expand.md"):
        text = _said("prompts", name)
        assert "tempergraph.regenerations.json" in text, name
        assert "gets no task row" in text, name
        assert "written by the regeneration and never edited by hand" in text, name


def test_rgn_ac15_the_code_judge_brief_names_the_files_the_regeneration_wrote() -> None:
    # RGN-AC15 (RGN-B15), AC 8
    text = _said("judges", "code.md")
    assert "written by the regeneration" in text and "need no row" in text


def test_rgf_ac5_the_code_prompt_says_to_fix_the_listed_findings_and_nothing_else() -> None:
    # RGF-AC5 (RGF-B5), AC 5
    text = re.sub(r"\s+", " ", _code_prompt()).lower()
    assert "failed regeneration" in text and "numbered findings" in text
    assert "fix those findings and change nothing else" in text
    assert "touch no file that fixing them does not need" in text
    assert "no stamp, authoring record or diagram by hand" in text
