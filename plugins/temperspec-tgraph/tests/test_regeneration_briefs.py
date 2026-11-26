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
    # RGN-AC14 (RGN-B14), RGN-AC15 (RGN-B15), AC 8
    for name in ("plan.md", "expand.md"):
        text = _said("prompts", name)
        assert "tempergraph.regenerations.json" in text, name
        assert "gets no task row" in text, name
        assert "written by the regeneration and never edited by hand" in text, name


def test_rgn_ac13_the_code_judge_brief_names_the_files_the_regeneration_wrote() -> None:
    # RGN-AC13 (RGN-B13), AC 8
    text = _said("judges", "code.md")
    assert "written by the regeneration" in text and "need no row" in text


def test_rgf_ac5_the_code_prompt_says_to_fix_the_listed_findings_and_nothing_else() -> None:
    # RGF-AC5 (RGF-B5), AC 5
    text = re.sub(r"\s+", " ", _code_prompt()).lower()
    assert "failed regeneration" in text and "numbered findings" in text
    assert "fix those findings and change nothing else" in text
    assert "touch no file that fixing them does not need" in text
    assert "no stamp, authoring record or diagram by hand" in text


def test_rgf_ac5_the_code_brief_after_a_failed_regeneration_holds_the_numbered_findings_under_the_reason(
        tmp_path: Path) -> None:
    # RGF-AC5 (RGF-B5), AC 5: the prompt the stand-in read on the visit that follows a failed regeneration
    import importlib
    import subprocess
    import sys

    here = str(ROOT / "tests")
    if here not in sys.path:
        sys.path.insert(0, here)
    rr = importlib.import_module("test_regeneration_run")
    from tempergraph.constants import ExitCode

    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "Test")):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("scratch\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True, capture_output=True)
    rr._declare_flaky(repo, rr._flaky("gen", "1", "tools/three.json"), reports={"three.json": rr.THREE})
    stand = rr.irv.Stand()
    out = rr._go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    first, last = rr._code_prompts(stand)[0], rr._code_prompts(stand)[-1]
    assert "Why this unit runs again" not in first
    reason_at = last.index("Why this unit runs again")
    at = [last.index(f"{n}. [", reason_at) for n in (1, 2, 3)]
    assert at == sorted(at) and "4. [" not in last
    assert "summary-long" in last[at[0]:at[1]] and "blocker-unverified" in last[at[2]:]
