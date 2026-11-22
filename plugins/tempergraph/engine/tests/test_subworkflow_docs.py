"""The documents say what is built of the sub-workflow unit and what is left (SWF-AC1, SWF-AC2, SWF-AC5; task AC 6)."""

from __future__ import annotations

import re

from .conftest import DOCS

SPEC = DOCS / "specs" / "99-subworkflow-unit.spec.md"
PLAN = DOCS / "plans" / "third-release.plan.md"


def open_questions() -> str:
    return SPEC.read_text(encoding="utf-8").split("## Open questions", 1)[1]


def test_the_spec_names_only_what_is_left() -> None:  # SWF-AC1, AC 6
    text = open_questions()
    assert "sub-workflows are release 3 work" not in text
    for left in ("SWF-B9", "SWF-AC3"):
        assert left in text
    assert "running a child" not in text and "SWF-B11" not in text


def test_the_interim_refusal_is_gone_from_the_spec() -> None:  # SWF-AC1, AC 6
    text = SPEC.read_text(encoding="utf-8")
    assert "SWF-B11" not in text and "SWF-AC4" not in text and "not_in_release" not in text


def test_the_release_plan_records_the_declaration_and_running_a_child_as_built() -> None:  # SWF-AC1, AC 6
    plan = PLAN.read_text(encoding="utf-8")
    for phase in ("R3-T2.1 ", "R3-T2.2 "):
        body = plan.split(f"#### {phase}", 1)[1].split("\n####", 1)[0]
        assert re.search(r"^Status: built\.", body, re.M), phase
    built = plan.split("#### R3-T2.2 ", 1)[1].split("\n####", 1)[0]
    assert "SWF-AC1" in built and "SWF-AC2" in built
    first = plan.split("#### R3-T2.1 ", 1)[1].split("\n####", 1)[0]
    assert "SWF-B11" not in first
