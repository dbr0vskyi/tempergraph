"""The documents say what is built of the sub-workflow unit and what is left (task AC 5; SWF-AC1, SWF-AC4, SWF-AC5)."""

from __future__ import annotations

import re

from .conftest import DOCS

SPEC = DOCS / "specs" / "99-subworkflow-unit.spec.md"
PLAN = DOCS / "plans" / "third-release.plan.md"


def open_questions() -> str:
    return SPEC.read_text(encoding="utf-8").split("## Open questions", 1)[1]


def test_the_spec_names_only_what_is_left() -> None:  # AC 5
    text = open_questions()
    assert "sub-workflows are release 3 work" not in text
    for left in ("running a child", "SWF-B9", "SWF-AC3"):
        assert left in text


def test_the_release_plan_records_the_declaration_and_validation_as_built() -> None:  # AC 5
    body = PLAN.read_text(encoding="utf-8").split("#### R3-T2.1 ", 1)[1].split("\n####", 1)[0]
    assert re.search(r"^Status: built\.", body, re.M)
