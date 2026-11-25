"""The documents say what is built of the sub-workflow unit and what is left (SWF-AC1, SWF-AC2, SWF-AC3, SWF-AC5; task AC 6)."""

from __future__ import annotations

import re

from .conftest import DOCS

SPEC = DOCS / "specs" / "subworkflow-unit.spec.md"
UPGRADE = DOCS / "specs" / "workflow-upgrade.spec.md"
PLAN = DOCS / "plans" / "third-release.plan.md"


def test_the_spec_has_no_open_question_left() -> None:  # SWF-AC1, SWF-AC3, AC 6
    text = SPEC.read_text(encoding="utf-8")
    assert "## Open questions" not in text and "Not built yet" not in text
    assert "sub-workflows are release 3 work" not in text and "running a child" not in text
    assert text.rstrip().splitlines()[-1].startswith("- SWF-AC5")  # the acceptance criteria end the spec


def test_the_upgrade_spec_no_longer_lists_a_sub_workflows_change_notes_as_not_built() -> None:  # SWF-AC1, WUP-B6, AC 6
    text = UPGRADE.read_text(encoding="utf-8")
    not_built = next(ln for ln in text.splitlines() if ln.startswith("- Not built yet:"))
    assert "change notes" not in not_built and "--trial" in not_built  # only that clause went
    assert "sub-workflow" not in not_built


def test_the_interim_refusal_is_gone_from_the_spec() -> None:  # SWF-AC1, AC 6
    text = SPEC.read_text(encoding="utf-8")
    assert "SWF-B11" not in text and "SWF-AC4" not in text and "not_in_release" not in text


def test_the_release_plan_records_the_sub_workflow_track_as_built() -> None:  # SWF-AC1, SWF-AC3, AC 6
    plan = PLAN.read_text(encoding="utf-8")
    for phase in ("R3-T2.1 ", "R3-T2.2 ", "R3-T2.3 "):
        body = plan.split(f"#### {phase}", 1)[1].split("\n####", 1)[0]
        assert re.search(r"^Status: built\.", body, re.M), phase
    built = plan.split("#### R3-T2.2 ", 1)[1].split("\n####", 1)[0]
    assert "SWF-AC1" in built and "SWF-AC2" in built
    assert "SWF-B9 and SWF-AC3 are left" not in built and "R3-T2.3" not in built  # nothing is left of R3-T2.2
    first = plan.split("#### R3-T2.1 ", 1)[1].split("\n####", 1)[0]
    assert "SWF-B11" not in first
    last = plan.split("#### R3-T2.3 ", 1)[1].split("\n####", 1)[0]
    assert "SWF-B9" in last and "SWF-AC3" in last
    status = next(ln for ln in plan.splitlines() if ln.startswith("**Status:"))
    assert "R3-T2.3" in status and "R3-T2" in status.replace("R3-T2.3", "")  # the phase and the track are recorded
