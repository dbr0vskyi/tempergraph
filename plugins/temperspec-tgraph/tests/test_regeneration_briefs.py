"""What the briefs tell a session about a failed regeneration (spec regeneration-failures, RGF-B5)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _code_prompt() -> str:
    return (ROOT / "prompts" / "code.md").read_text(encoding="utf-8")


def test_rgf_ac5_the_code_prompt_says_to_fix_the_listed_findings_and_nothing_else() -> None:
    # RGF-AC5 (RGF-B5), AC 5
    text = re.sub(r"\s+", " ", _code_prompt()).lower()
    assert "failed regeneration" in text and "numbered findings" in text
    assert "fix those findings and change nothing else" in text
    assert "touch no file that fixing them does not need" in text
    assert "no stamp, authoring record or diagram by hand" in text
