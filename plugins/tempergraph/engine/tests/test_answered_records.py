"""The check record holds `failed` and the intervention row of a decision at a pause holds `item` and `answered`
(CHK-B26, CHK-AC20, HUM-B19, HUM-AC14; task AC 1, AC 2). Every record here comes from a fixture run of the engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.executors.standins import answer, standin
from tempergraph.run.runner import ledger_rows, resume
from tempergraph.store.layout import run_dir, state_root_path

from . import test_map as tmap
from . import test_map_concurrent_writers as writers
from .fixtures.workflows import two_step
from .test_fallback_breakpoint import wf as breakpoint_wf
from .test_gate_back import A_DONE, _state_file, fail, finding, fixture, plan  # noqa: F401  (the autouse state file)
from .test_run import DRAFT, NO_SLEEP, REVIEW, go, judge, records, registry, verdict_block
from .test_usage_limit import _plain, refused

CANARY = "CANARY-free-text-9f3a"
FACTS = ("check", "failed", "environmental", "blockers", "gap", "guard", "claim")
NOT_RECORDED = "not recorded"


def checks_of(repo: Path, unit: str, task: str = "T-1") -> list[dict[str, Any]]:
    return [r for r in records(repo, task) if r["kind"] == "check" and r["unit"] == unit]


def rows_of(repo: Path) -> list[dict[str, Any]]:
    return [r for r in ledger_rows(state_root_path(repo)) if r.get("kind") == "intervention"]


def pause_env(*findings: dict[str, Any]) -> None:
    """An environmental FAIL of the script unit `s`: the run pauses there with no retry."""
    plan(fail(*findings, environmental=True))


def run_s(repo: Path) -> Any:
    ex = standin("claude", steps=[A_DONE], judges=[judge()])
    out = go(repo, ex, fixture())
    assert out.exit_code is ExitCode.PAUSED, out.message
    return ex


def answer_s(repo: Path, ex: Any, decision: str = "proceed", **kw: Any) -> Any:
    return resume(fixture(), "T-1", repo, registry(ex), decision=decision, settings=NO_SLEEP, **kw)


def log_path(repo: Path, task: str = "T-1") -> Path:
    return run_dir(state_root_path(repo), "demo", task) / "run.jsonl"


def rewrite_log(repo: Path, edit: Any, task: str = "T-1") -> None:
    rows = [json.loads(x) for x in log_path(repo, task).read_text().splitlines()]
    log_path(repo, task).write_text("".join(json.dumps(r) + "\n" for r in edit(rows)))


# ---- CHK-B26: the check record names the criteria that failed


def test_chk_ac20_failed_holds_each_failing_id_once_in_the_checks_order(repo: Path) -> None:  # CHK-AC20, AC 1
    pause_env(finding("b", "x"), finding("a", "x"), finding("b", "again"), finding("c", "fine", status="pass"),
              {"status": "fail", "criterion": None, "message": "no id", "place": None, "fix": None})
    run_s(repo)
    (rec,) = checks_of(repo, "s")
    assert rec["failed"] == ["b", "a"]


def test_chk_ac20_failed_holds_at_most_twenty_ids(repo: Path) -> None:  # CHK-AC20, AC 1
    pause_env(*[finding(f"c{n:02d}", "x") for n in range(25)])
    run_s(repo)
    (rec,) = checks_of(repo, "s")
    assert rec["failed"] == [f"c{n:02d}" for n in range(20)]


def test_chk_ac20_a_fail_that_names_no_id_leaves_an_empty_list(repo: Path) -> None:  # CHK-AC20, AC 1
    pause_env()
    run_s(repo)
    (rec,) = checks_of(repo, "s")
    assert rec["failed"] == []


def test_chk_ac20_the_record_holds_no_message_place_or_fix(repo: Path) -> None:  # CHK-AC20, AC 1
    pause_env(finding("b", CANARY, place=CANARY, fix=CANARY))
    run_s(repo)
    (rec,) = checks_of(repo, "s")
    assert rec["failed"] == ["b"]
    assert CANARY not in json.dumps(rec) and not {"message", "place", "fix", "findings"} & set(rec)


def test_chk_ac20_a_map_items_check_record_holds_failed(repo: Path) -> None:  # CHK-AC20, AC 1
    spec = tmap.mapped(check=tmap.p2_fails_once)
    steps = [tmap.planner(tmap.THREE[:2]), tmap.item_ok("one"), tmap.item_ok("bad"), tmap.item_ok("two"),
             answer("Joined.")]
    out, _ = tmap.run(repo, spec, steps, [judge(), judge(), judge(), judge()])
    assert out.exit_code is ExitCode.FINISHED, out.message
    got = [(c["item"], c["failed"]) for c in tmap.recs(repo, "check") if c["unit"] == "phase"]
    assert got == [("p1", []), ("p2", ["c-item"]), ("p2", [])]


def test_chk_ac20_the_join_check_of_a_map_holds_failed(repo: Path) -> None:  # CHK-AC20, AC 1
    ex = writers.Writes(writers.TWO, {"p1": {"one.txt": "1\n"}, "p2": {"two.txt": "2\n"}})
    out = writers.go(repo, writers.writing(check=writers.clashes), ex)
    assert out.exit_code is ExitCode.PAUSED, out.message
    (joined,) = [r for r in writers.recs_of(repo, "check") if r["unit"] == "phase" and r["item"] is None]
    assert joined["failed"] == ["c-item"]


# ---- HUM-B19: the intervention row holds what the decision answered


def test_hum_ac14_a_proceed_at_an_environmental_fail_holds_the_check_facts(repo: Path) -> None:  # HUM-AC14, AC 2
    pause_env(finding("c-a", "no git"), finding("c-b", "no git"))
    ex = run_s(repo)
    assert answer_s(repo, ex).exit_code is ExitCode.FINISHED
    (row,) = rows_of(repo)
    assert row["unit"] == "s" and row["item"] == "none"
    assert row["answered"] == {"check": "FAIL", "failed": ["c-a", "c-b"], "environmental": True,
                               "blockers": NOT_RECORDED, "gap": NOT_RECORDED, "guard": NOT_RECORDED,
                               "claim": NOT_RECORDED}


def test_hum_ac14_a_proceed_at_a_gap_pause_holds_the_last_judgement(repo: Path) -> None:  # HUM-AC14, AC 2
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge(verdict_block("UNVERIFIABLE"))])
    assert go(repo, ex).exit_code is ExitCode.PAUSED
    (j,) = [r for r in records(repo) if r["kind"] == "judgement" and r["unit"] == "review"]
    done = resume(two_step(), "T-1", repo, registry(ex), decision="proceed", settings=NO_SLEEP)
    assert done.exit_code is ExitCode.FINISHED, done.message
    (row,) = rows_of(repo)
    assert row["unit"] == "review" and row["item"] == "none" and set(row["answered"]) == set(FACTS)
    a = row["answered"]
    assert (a["check"], a["failed"], a["environmental"]) == ("PASS", [], False)  # a gate with no check records PASS
    assert (a["blockers"], a["gap"], a["guard"]) == (j["blockers"], j["gap"], j["guard"]) and a["claim"] == "none"


def test_hum_ac14_a_map_items_pause_reads_the_records_of_that_item(repo: Path) -> None:  # HUM-AC14, AC 2
    spec = tmap.mapped(retry_budget=0)
    out, _ = tmap.run(repo, spec, [tmap.planner(tmap.THREE), tmap.item_ok(), tmap.item_ok()],
                      [judge(), judge(), judge(tmap.FAIL)])
    assert out.exit_code is ExitCode.PAUSED and out.payload["item"] == "p2"
    ex2 = standin("claude", steps=[tmap.item_ok(), answer("Joined.")], judges=[judge(), judge()])
    done = resume(spec, "M-1", repo, registry(ex2), decision="proceed", settings=NO_SLEEP)
    assert done.exit_code is ExitCode.FINISHED, done.message
    (row,) = rows_of(repo)
    assert row["unit"] == "phase" and row["item"] == "p2"
    assert row["answered"]["blockers"] == ["c-item"]  # p2's judgement, not p1's (which passed)


def test_hum_ac14_a_pause_with_no_item_reads_the_join_check(repo: Path) -> None:  # HUM-AC14, AC 2
    ex = writers.Writes(writers.TWO, {"p1": {"one.txt": "1\n"}, "p2": {"two.txt": "2\n"}})
    out = writers.go(repo, writers.writing(check=writers.clashes), ex)
    assert out.exit_code is ExitCode.PAUSED and out.payload["item"] is None
    done = resume(writers.writing(check=writers.clashes), "M-1", repo, registry(ex), decision="stop",
                  settings=NO_SLEEP)
    assert done.exit_code is ExitCode.STOPPED, done.message
    (row,) = rows_of(repo)
    assert row["item"] == "none" and row["answered"]["check"] == "FAIL" and row["answered"]["failed"] == ["c-item"]


def test_hum_ac14_the_result_of_an_earlier_visit_never_labels_a_later_decision(repo: Path) -> None:  # HUM-AC14, AC 2
    pause_env(finding("c-a", "no git"))
    ex = run_s(repo)

    def reenter(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        top = max(r["seq"] for r in rows if isinstance(r.get("seq"), int))
        return [*rows, {"kind": "unit_entered", "unit": "s", "visit": 2, "seq": top + 1, "entered_from": "start"}]

    rewrite_log(repo, reenter)  # a later visit of `s` that has not yet written a check record
    assert answer_s(repo, ex).exit_code is ExitCode.FINISHED
    (row,) = rows_of(repo)
    assert row["answered"] == {k: NOT_RECORDED for k in FACTS}


def test_hum_ac14_an_older_record_without_failed_reads_as_not_recorded(repo: Path) -> None:  # HUM-AC14, AC 2
    pause_env(finding("c-a", "no git"))
    ex = run_s(repo)
    rewrite_log(repo, lambda rows: [{k: v for k, v in r.items() if k != "failed"} for r in rows])
    assert answer_s(repo, ex).exit_code is ExitCode.FINISHED
    (row,) = rows_of(repo)
    assert row["answered"]["failed"] == NOT_RECORDED
    assert (row["answered"]["check"], row["answered"]["environmental"]) == ("FAIL", True)


def test_hum_ac14_a_log_with_no_check_or_judgement_gives_not_recorded_and_fails_nothing(repo: Path) -> None:
    # HUM-AC14, AC 2
    pause_env(finding("c-a", "no git"))
    ex = run_s(repo)
    rewrite_log(repo, lambda rows: [r for r in rows if r["kind"] not in ("check", "judgement")])
    assert answer_s(repo, ex).exit_code is ExitCode.FINISHED
    (row,) = rows_of(repo)
    assert row["item"] == "none" and row["answered"] == {k: NOT_RECORDED for k in FACTS}


def test_hum_ac14_a_breakpoint_row_holds_no_item_and_every_fact_not_recorded(repo: Path) -> None:  # HUM-AC14, AC 2
    spec = breakpoint_wf()
    ex = standin("claude", steps=[answer("Done.", session_id="s")] * 3, judges=[judge()] * 3)
    from .test_fallback_breakpoint import go as bgo

    out = bgo(repo, spec, ex, pause_before=("build",))
    assert out.exit_code is ExitCode.PAUSED and out.reason == "breakpoint"
    done = resume(spec, "F-1", repo, registry(ex), decision="proceed", settings=NO_SLEEP)
    assert done.exit_code is ExitCode.FINISHED, done.message
    row = rows_of(repo)[-1]
    assert row["pause_kind"] == "breakpoint" and row["item"] == "none"
    assert row["answered"] == {k: NOT_RECORDED for k in FACTS}


def test_hum_ac14_a_usage_limit_rerun_is_no_decision_and_holds_neither_field(repo: Path) -> None:  # HUM-AC14, AC 2
    import time

    ex = standin("claude", steps=[refused(time.time() + 3600, error_kind="model")] * 3 + [DRAFT, REVIEW],
                 judges=[judge(), judge()])
    assert go(repo, ex).exit_code is ExitCode.PAUSED
    _plain(repo, ex)
    rows = rows_of(repo)
    assert rows and all("item" not in r and "answered" not in r for r in rows)


def test_hum_ac14_the_answered_facts_are_ids_enums_and_numbers_only(repo: Path) -> None:  # HUM-AC14, AC 2
    pause_env(finding("c-a", CANARY, place=CANARY, fix=CANARY))
    ex = run_s(repo)
    assert answer_s(repo, ex, feedback=CANARY).exit_code is ExitCode.FINISHED
    (row,) = rows_of(repo)
    assert CANARY not in json.dumps(row)
    for v in row["answered"].values():
        assert isinstance(v, str | bool | int | float) or (isinstance(v, list) and all(isinstance(i, str) for i in v))


@pytest.mark.parametrize("fact", FACTS)
def test_hum_ac14_every_fact_is_named_on_the_row(repo: Path, fact: str) -> None:  # HUM-AC14, AC 2
    pause_env(finding("c-a", "no git"))
    ex = run_s(repo)
    assert answer_s(repo, ex).exit_code is ExitCode.FINISHED
    assert fact in rows_of(repo)[0]["answered"]
