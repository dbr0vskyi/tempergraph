"""What the first schedule phase built and assumed is written where the next reader looks (task criteria 8 and 9)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tempergraph.cli import schedule_cli

from .conftest import DOCS
from .test_schedule_cli import NOW, WARSAW, add


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schedule_cli, "CLOCK", lambda: NOW)
    monkeypatch.setattr(schedule_cli, "machine_zone", lambda: (WARSAW, "TZ"))

SPEC = DOCS / "specs" / "schedules.spec.md"
RATIONALE = DOCS / "research" / "R-150-rationale-carried-from-the-engine-specs.rsrch.md"
PLAN = DOCS / "plans" / "third-release.plan.md"


def _open_question(text: str) -> str:
    found = [line for line in text.split("## Open questions", 1)[1].splitlines() if line.startswith("- Not built yet")]
    assert len(found) == 1
    return found[0]


SPEC_TCK = DOCS / "specs" / "schedule-ticks-and-unattended-fires.spec.md"
LIVE = DOCS / "plans" / "live-checks.plan.md"
R352 = DOCS / "plans" / "r3-t5-2.plan.md"
ENGINE_TESTS = Path(__file__).resolve().parent


def _section(text: str, start: str, stop: str) -> str:
    return text.split(start, 1)[1].split(stop, 1)[0]


def test_ac13_the_open_question_of_spec_83_says_what_r3_t5_2_built_and_what_waits() -> None:
    text = SPEC.read_text(encoding="utf-8")
    q = _open_question(text)
    assert "R3-T5.1 built" in q and "R3-T5.2" in q and "built" in q
    for verb in ("`schedule fire`", "`tick`", "`loop`", "`trigger`", "`runs`", "`export`"):
        assert verb in q  # built now: no longer refused `not_in_release` meanwhile
    assert "meanwhile" not in q and "written empty" not in q and "written null" not in q
    assert "release 4" in q and "ADR-0132" in q and "`add --orchestration` is refused `not_in_release`" in q
    assert "P-SCH-1 to P-SCH-4 have not run" in q


def test_ac13_sch_b33_and_sch_ac12_name_only_add_orchestration_and_sch_b27_has_no_carve_out() -> None:
    text = SPEC.read_text(encoding="utf-8")
    b33 = _section(text, "### SCH-B33", "\n## ")
    assert "`schedule add --orchestration`" in b33 and "`schedule fire`" not in b33 and "`schedule export`" not in b33
    ac12 = next(ln for ln in text.splitlines() if ln.startswith("- SCH-AC12"))
    assert "`schedule add --orchestration`" in ac12 and "`schedule fire`" not in ac12 and "`runs`" not in ac12
    b27 = _section(text, "### SCH-B27", "### SCH-B33")
    assert "that SCH-B33 does not refuse" not in b27 and b27.split("\n")[2].startswith("WHEN a `schedule` verb runs")


def test_ac13_the_open_question_of_spec_84_says_what_waits_and_that_the_probes_have_not_run() -> None:
    q = _open_question(SPEC_TCK.read_text(encoding="utf-8"))
    assert "TCK-B9" in q and "release 4" in q and "built" in q and "P-SCH-1 to P-SCH-4 have not run" in q
    for built in ("tick", "loop", "`host`", "`os`", "fire token", "credential check", "ledger", "export", "skill"):
        assert built in q, built


def test_ac13_the_release_plan_says_r3_t5_2_is_built_in_the_form_of_the_r3_t5_1_row() -> None:
    text = PLAN.read_text(encoding="utf-8")
    status = next(line for line in text.splitlines() if line.startswith("**Status:"))
    assert "R3-T5.1 and R3-T5.2 are built" in status
    row = _section(text, "#### R3-T5.2 Ticks and unattended fires", "###")
    assert re.search(r"^Status: built\.", row, re.M) and "test_schedule_" in row
    assert "release 4" in row and "P-SCH-1 to P-SCH-4" in row  # what waits


def test_tck_ac4_add_writes_a_sha256_digest_of_the_fire_token_in_the_entry(repo: Path) -> None:
    from tempergraph.schedule import store

    code, doc, err = add(repo)
    assert code == 0, err
    assert re.fullmatch(r"[0-9a-f]{64}", str(store.read_entry(str(doc["schedule_id"]))["token_digest"]))


def test_tck_ac6_add_writes_one_executors_checked_row_per_executor_and_judge_binding(repo: Path) -> None:
    from tempergraph.schedule import store

    code, doc, err = add(repo)
    assert code == 0, err
    rows = store.read_entry(str(doc["schedule_id"]))["executors_checked"]
    assert [(r["executor"], r["role"]) for r in rows] == [("claude", "step"), ("claude", "judge")]
    assert all({"kinds", "result"} <= set(r) for r in rows)  # kinds and the result, never a value


def test_ac8_the_release_three_plan_says_r3_t5_1_is_built() -> None:
    text = PLAN.read_text(encoding="utf-8")
    status = next(line for line in text.splitlines() if line.startswith("**Status:"))
    assert "R3-T5.1" in status and "built" in status
    row = text.split("#### R3-T5.1 The schedule command", 1)[1].split("####", 1)[0]
    assert re.search(r"^Status: built\.", row, re.M)  # the form of the R3-T1.1 and R3-T1.2 rows
    assert "test_schedule_" in row and "R3-T5.2" in row  # the proof, and what is left


def test_ac9_the_assumptions_made_while_coding_are_recorded_in_the_rationale() -> None:
    f50 = RATIONALE.read_text(encoding="utf-8").split("### F50 SCH", 1)[1].split("### F51", 1)[0]
    for heading in ("Cron (R3-T5.1)", "Assumptions, parsing and slots (R3-T5.1", "Assumptions, entry and verbs (R3-T5.1",
                    "Assumptions, fire-decision functions (R3-T5.1", "Assumptions, word grammar and verbs (R3-T5.1, found "):
        assert heading in f50, heading
    assert "live runs, failures and period spend read 0" in f50  # what `list` reports with no tick
    assert "the first run of the test settles it" not in f50  # SCH-AC2's reference was settled by the test
    for found in ("choose_invalid", "schedule_state", "fire_date", "BYMONTHDAY", "23:59"):
        assert found in f50, found  # each assumption the code makes beyond the spec has a line
    assert "Assumptions, ticks and unattended fires (R3-T5.2" in f50  # AC 13: what the second phase assumed
    for found in ("schedules/<id>/token", "tickets/<fire id>.json", "--if-autostart", "config/credentials/default",
                  "loop.stop", "eval-cases.md", "default.target.wants"):
        assert found in f50, found


def test_ac11_live_checks_lists_a_manual_row_for_each_of_the_four_probes_with_no_result() -> None:
    text = LIVE.read_text(encoding="utf-8")
    manual, results = _section(text, "## 3. Manual rows", "## 4. Results"), text.split("## 4. Results", 1)[1]
    for n in range(1, 5):
        rows = [ln for ln in manual.splitlines() if ln.startswith("| L-") and f"P-SCH-{n} " in ln]
        assert len(rows) == 1, n
        assert f"| P-SCH-{n} |" not in results and f"P-SCH-{n} | 2026" not in results  # no result is written


def test_ac14_no_engine_source_skill_or_test_names_a_workflow_package() -> None:
    from .conftest import SRC, workflow_names

    names = workflow_names()
    assert names
    skills = ENGINE_TESTS.parents[1] / "skills"
    # the engine's source, every skill, and the schedule tests; other older test files that use a package's name as sample
    # data (test_scaffold.py) are outside this task
    files = [*SRC.rglob("*.py"), *skills.rglob("*.md"),
             *(p for p in ENGINE_TESTS.glob("test_schedule_*.py") if p.name != Path(__file__).name)]
    assert len(files) > 100
    for path in files:
        text = path.read_text(encoding="utf-8")
        for name in names:
            assert name not in text, f"{path.name} names the workflow package {name!r} (ADR-0129)"


def test_ac15_every_offline_tck_criterion_and_sch_ac5_and_sch_ac7_is_carried_by_a_test_that_is_not_skipped() -> None:
    ids = ("TCK-AC1", "TCK-AC2", "TCK-AC3", "TCK-AC4", "TCK-AC5", "TCK-AC6", "TCK-AC7", "SCH-AC5", "SCH-AC7")
    tests = [p for p in ENGINE_TESTS.glob("test_*.py")]
    for ident in ids:
        slug = ident.lower().replace("-", "_")
        carried = [p.name for p in tests if re.search(rf"def test_{slug}_", p.read_text(encoding="utf-8"))]
        assert carried, f"no test is named for {ident}"
    for p in tests:
        if p.name.startswith("test_schedule_") and p.name != Path(__file__).name:
            text = p.read_text(encoding="utf-8")
            assert "pytest.mark" + ".skip" not in text and "pytest" + ".skip(" not in text, p.name  # never skipped


def test_ac15_specs_83_and_84_stay_within_the_spec_budget_and_the_plan_lists_the_three_checks() -> None:
    for path in (SPEC, SPEC_TCK):
        data = path.read_bytes()
        assert len(data) <= 30 * 1024 and data.count(b"\n") <= 400, (path.name, len(data))
    plan = R352.read_text(encoding="utf-8")
    for command in ("`cd plugins/tempergraph/engine && python3 -m pytest`", "`cd plugins/tempergraph/engine && ruff check src tests`",
                    "`cd plugins/tempergraph/engine && mypy`"):
        assert command in plan
