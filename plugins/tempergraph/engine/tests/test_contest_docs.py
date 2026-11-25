"""The contest is built and its documents say so: `contest` is in no not-in-release list, no Not built yet line names it,
and the release 3 plan records the phase (AC 6; CTS-AC1 to CTS-AC6)."""

from __future__ import annotations

from pathlib import Path

from tempergraph import settings
from tempergraph.model import validate
from tempergraph.model.validate import errors

from .test_contest_validate import CLAUDE_ONLY, contest_unit, workflow

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "plugins" / "tempergraph" / "docs").is_dir())
DOCS = ROOT / "plugins" / "tempergraph" / "docs"
SRC = Path(__file__).resolve().parents[1] / "src" / "tempergraph"


def not_built_line(spec: str) -> str:
    return next(ln for ln in (DOCS / "specs" / spec).read_text(encoding="utf-8").splitlines()
                if ln.startswith("- Not built yet")).lower()


def test_contest_is_in_no_not_in_release_list_of_the_source() -> None:  # AC 6
    assert "contest" not in validate.LATER_KINDS
    assert "contest" not in " ".join(settings.NOT_IN_RELEASE.values()).lower()
    assert settings.NOT_IN_RELEASE == {}
    assert errors(validate.validate(workflow(contest_unit()), CLAUDE_ONLY)) == []
    for name in ("settings.py", "model/validate.py", "audit/__init__.py"):
        for n, line in enumerate((SRC / name).read_text(encoding="utf-8").splitlines(), start=1):
            low = line.lower()
            assert not ("contest" in low and ("not built yet" in low or "release 3" in low or "not_in_release" in low
                                              or "not yet built" in low)), f"{name}:{n}: {line}"


def test_no_not_built_yet_line_of_a_spec_names_the_contest() -> None:  # AC 6
    assert "contest" not in not_built_line("workflow-audit.spec.md")
    assert "contest" not in not_built_line("worktree-mode.spec.md")
    assert "contests" not in not_built_line("budgets-and-failures.spec.md")
    assert "contest" not in " ".join(ln for ln in (DOCS / "specs" / "contest-unit.spec.md").read_text(
        encoding="utf-8").lower().splitlines() if ln.startswith("- not built yet"))


def test_the_rationale_bullet_of_f39_says_the_contest_is_built() -> None:  # AC 6
    text = (DOCS / "research" / "rationale-carried-from-the-engine-specs.rsrch.md").read_text(encoding="utf-8")
    f39 = text.split("### F39 CTS Contest unit", 1)[1].split("\n### ", 1)[0]
    assert [ln for ln in f39.splitlines() if ln.startswith("- As built (R3-T4.2)")]
    assert "Not built" not in f39 and "release 3 work" not in f39


def test_the_release_3_plan_records_the_contest_as_built() -> None:  # AC 6
    plan = (DOCS / "plans" / "third-release.plan.md").read_text(encoding="utf-8")
    assert "R3-T4.1 and R3-T4.2 are built" in plan.split("**Status: In progress.**", 1)[1].split("\n", 1)[0]
    section = plan.split("#### R3-T4.2 Contest", 1)[1].split("\n### ", 1)[0]
    assert "Status: built" in section and "CTS-AC1 to CTS-AC6" in section
