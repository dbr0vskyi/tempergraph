"""What the first schedule phase built and assumed is written where the next reader looks (task criteria 8 and 9)."""

from __future__ import annotations

import re

from .conftest import DOCS

SPEC = DOCS / "specs" / "83-schedules.spec.md"
RATIONALE = DOCS / "research" / "R-150-rationale-carried-from-the-engine-specs.rsrch.md"
PLAN = DOCS / "plans" / "third-release.plan.md"


def _open_question(text: str) -> str:
    found = [line for line in text.split("## Open questions", 1)[1].splitlines() if line.startswith("- Not built yet")]
    assert len(found) == 1
    return found[0]


def test_ac8_the_open_question_says_what_r3_t5_1_built_and_what_r3_t5_2_keeps() -> None:
    q = _open_question(SPEC.read_text(encoding="utf-8"))
    assert "R3-T5.1, is built" in q  # what the first phase is, now
    assert "The first, R3-T5.1, builds" not in q  # no longer the plan of something not yet made
    for verb in ("`schedule fire`", "`tick`", "`loop`", "`trigger`", "`runs`", "`export`"):
        assert verb in q  # what the second phase keeps, refused `not_in_release` meanwhile
    assert "R3-T5.2" in q and "not_in_release" in q and "SCH-B33" in q
    assert "token_digest" in q and "executors_checked" in q  # written empty until R3-T5.2


def test_ac8_the_release_three_plan_says_r3_t5_1_is_built() -> None:
    text = PLAN.read_text(encoding="utf-8")
    status = next(line for line in text.splitlines() if line.startswith("**Status:"))
    assert "R3-T5.1" in status and "built" in status
    row = text.split("#### R3-T5.1 The schedule command", 1)[1].split("####", 1)[0]
    assert re.search(r"^Status: built\.", row, re.M)  # the form of the R3-T1.1 and R3-T1.2 rows
    assert "test_schedule_" in row and "R3-T5.2" in row  # the proof, and what is left
    rest = text.split("#### R3-T5.2 Ticks and unattended fires", 1)[1].split("###", 1)[0]
    assert "Status: built" not in rest  # the second phase is not built


def test_ac9_the_assumptions_made_while_coding_are_recorded_in_the_rationale() -> None:
    f50 = RATIONALE.read_text(encoding="utf-8").split("### F50 SCH", 1)[1].split("### F51", 1)[0]
    for heading in ("Cron (R3-T5.1)", "Assumptions, parsing and slots (R3-T5.1", "Assumptions, entry and verbs (R3-T5.1",
                    "Assumptions, fire-decision functions (R3-T5.1", "Assumptions, word grammar and verbs (R3-T5.1, found "):
        assert heading in f50, heading
    assert "live runs, failures and period spend read 0" in f50  # what `list` reports with no tick
    assert "the first run of the test settles it" not in f50  # SCH-AC2's reference was settled by the test
    for found in ("choose_invalid", "schedule_state", "fire_date", "BYMONTHDAY", "23:59"):
        assert found in f50, found  # each assumption the code makes beyond the spec has a line
