"""The documents say the council is built and what is left (CNL-AC1, CNL-AC7, BUD-AC12, WFM-B13, ARC-B15; task AC 7)."""

from __future__ import annotations

import re
from pathlib import Path

from tempergraph.model.validate import LATER_KINDS

from .conftest import DOCS, REPO_ROOT

SRC = Path(__file__).resolve().parents[1] / "src" / "tempergraph"
PLAN = DOCS / "plans" / "third-release.plan.md"


def test_cnl_ac1_council_is_gone_from_the_not_in_release_kinds() -> None:  # CNL-AC1 (WFM-B13)
    assert "council" not in LATER_KINDS


def test_the_release_3_plan_records_r3_t4_1_as_built() -> None:  # AC 7
    plan = PLAN.read_text(encoding="utf-8")
    body = plan.split("#### R3-T4.1 ", 1)[1].split("\n####", 1)[0]
    assert re.search(r"^Status: built\.", body, re.M)
    assert "CNL-AC1 to CNL-AC7" in body and "BUD-AC12 to BUD-AC14" in body
    status = next(ln for ln in plan.splitlines() if ln.startswith("**Status:"))
    assert "R3-T4.1 and R3-T4.2 are built" in status
    reservations = plan.split("#### R3-T1.1 Reservations", 1)[1].split("\n####", 1)[0]
    assert "councils" not in reservations and "maps" not in reservations  # both shapes are built
    audit = plan.split("#### R3-T8.3 ", 1)[1].split("\n####", 1)[0]
    assert "council-one-family" not in audit


def test_spec_08_no_longer_says_reservations_are_not_built_for_councils() -> None:  # BUD-AC12
    line = next(ln for ln in (DOCS / "specs" / "08-budgets-and-failures.spec.md").read_text(encoding="utf-8")
                .splitlines() if ln.startswith("- Not built yet"))
    assert "not built for" not in line and "member and chair sessions of a council" in line


def test_spec_55_names_no_council_rule_as_unbuilt() -> None:  # ARC-B15
    line = next(ln for ln in (DOCS / "specs" / "55-workflow-audit.spec.md").read_text(encoding="utf-8").splitlines()
                if ln.startswith("- Not built yet"))
    first = line.split(";", 1)[0]
    assert "council" not in first


def test_no_skip_reason_says_the_council_is_not_built() -> None:  # AC 7
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "council unit is not built" not in text, path.name
        assert not re.search(r"council[^.\n]{0,40}not built yet", text), path.name


def test_the_readme_roadmap_no_longer_lists_councils_as_designed_not_built() -> None:  # AC 7
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if ln.startswith("- Advanced node types"))
    assert "councils" not in line and "contests" in line


def test_the_rationale_note_does_not_say_the_council_is_not_built() -> None:  # AC 7
    text = (DOCS / "research" / "R-150-rationale-carried-from-the-engine-specs.rsrch.md").read_text(encoding="utf-8")
    assert "councils are release 3 work" not in text and "those units are not built" not in text
