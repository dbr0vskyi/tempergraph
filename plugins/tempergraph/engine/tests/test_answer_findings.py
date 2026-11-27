"""The five causes of an answered pause: what a decision overrode, confirmed or repeated (FRC-B7 to FRC-B15; task AC 3
to AC 8, AC 11, AC 14). Fixture runs of the engine's stand-in executors; the sums, medians and missing-fact cases
feed `causes.derive` the rows and records a run writes."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode
from tempergraph.executors.standins import answer, standin
from tempergraph.improve import causes
from tempergraph.improve.record import fingerprint, read_findings
from tempergraph.run.runner import resume
from tempergraph.store.layout import state_root_path

from . import test_map as tmap
from .fixtures.workflows import two_step
from .test_answered_records import answer_s, pause_env, run_s
from .test_fallback_breakpoint import wf as breakpoint_wf
from .test_gate_back import A_DONE, _state_file, fail, finding, fixture, plan  # noqa: F401  (the autouse state file)
from .test_pause_findings_at_final_exit import committed_in_worktree
from .test_run import CLAIM as CLAIMING
from .test_run import DRAFT, NO_SLEEP, REVIEW, go, judge, registry, verdict_block
from .test_stop_at_pause import paused_on_retries

UNVERIFIABLE = verdict_block("UNVERIFIABLE")
NEW = ("answer_overrode", "upstream_confirmed", "retry_passed_unchanged", "retry_same_failure", "resume_no_progress")
AGENT = {"kind": "agent", "host": "claude-code", "host_session": "sess-1"}


def found(repo: Path, task: str = "T-1") -> list[dict[str, Any]]:
    return read_findings(state_root_path(repo), "demo", task)


def of(repo: Path, cause: str, task: str = "T-1") -> list[dict[str, Any]]:
    return [f for f in found(repo, task) if f["cause"] == cause or f["cause"].startswith(cause + ":")]


def new_causes(repo: Path, task: str = "T-1") -> set[str]:
    return {f["cause"] for f in found(repo, task) if f["cause"].split(":")[0] in NEW}


def paused_on_gap(repo: Path, task: str, **kw: Any) -> Any:
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge(UNVERIFIABLE)])
    out = go(repo, ex, task=task, **kw)
    assert out.exit_code is ExitCode.PAUSED and out.payload["unit"] == "review", out.message
    return ex


def decide(repo: Path, task: str, ex: Any, decision: str, spec: Any = None, **kw: Any) -> Any:
    return resume(spec or two_step(), task, repo, registry(ex), decision=decision,
                  settings=dataclasses.replace(NO_SLEEP, **kw))


def paused_on_failing_check(repo: Path) -> Any:
    """A script unit whose second failing check pauses it with kind `budget`."""
    plan(fail(finding("c-a", "first")), fail(finding("c-b", "second")))
    ex = standin("claude", steps=[A_DONE, A_DONE], judges=[judge(), judge()])
    out = go(repo, ex, fixture())
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget", out.message
    return ex


def row(**kw: Any) -> dict[str, Any]:
    """A decision's ledger row as the engine writes it."""
    base: dict[str, Any] = {"kind": "intervention", "unit": "gate", "pause_kind": "escalation", "cause": "blocked",
                            "decision": "proceed", "item": "none", "wait_s": None, "caller": {},
                            "touches": [{"class": "designed", "action": "decide"}],
                            "answered": {"check": "FAIL", "failed": ["a"], "environmental": False, "blockers": [],
                                         "gap": False, "guard": "none", "claim": "none"}}
    answered = {**base["answered"], **kw.pop("answered", {})}
    return {**base, **kw, "answered": answered}


def derived(ivs: list[dict[str, Any]], seg: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    return [f for f in causes.derive(seg or [], ivs) if f["cause"].split(":")[0] in NEW]


# ---- FRC-B7: a proceed over a check, an environment, a gap or a budget

def test_frc_ac7_a_gap_answered_proceed_makes_answer_overrode_gap(repo: Path) -> None:  # FRC-AC7, AC 3, AC 14
    ex = paused_on_gap(repo, "T-1")
    assert decide(repo, "T-1", ex, "proceed").exit_code is ExitCode.FINISHED
    (f,) = of(repo, "answer_overrode")
    assert (f["cause"], f["unit"], f["count"]) == ("answer_overrode:gap", "review", 1)
    assert new_causes(repo) == {"answer_overrode:gap"}


def test_frc_ac7_an_environmental_fail_answered_proceed_makes_answer_overrode_environment(
        repo: Path) -> None:  # FRC-AC7, AC 3, AC 14
    pause_env(finding("c-a", "no git"))
    ex = run_s(repo)
    assert answer_s(repo, ex).exit_code is ExitCode.FINISHED
    (f,) = of(repo, "answer_overrode")
    assert (f["cause"], f["unit"]) == ("answer_overrode:environment", "s")
    assert new_causes(repo) == {"answer_overrode:environment"}


def test_frc_ac7_a_check_fail_answered_proceed_makes_answer_overrode_check_and_no_budget(
        repo: Path) -> None:  # FRC-AC7, AC 3, AC 14
    ex = paused_on_failing_check(repo)  # the pause is of kind `budget` over a FAIL that is not environmental
    assert answer_s(repo, ex).exit_code is ExitCode.FINISHED
    (f,) = of(repo, "answer_overrode")
    assert (f["cause"], f["unit"]) == ("answer_overrode:check", "s")
    assert new_causes(repo) == {"answer_overrode:check"}


def test_frc_ac7_a_spent_budget_answered_proceed_makes_answer_overrode_budget(
        repo: Path) -> None:  # FRC-AC7, AC 3
    ex = paused_on_retries(repo, "T-1")
    ex.steps, ex.judges = [REVIEW], [judge()]
    assert decide(repo, "T-1", ex, "proceed").exit_code is ExitCode.FINISHED
    (f,) = of(repo, "answer_overrode")
    assert (f["cause"], f["unit"]) == ("answer_overrode:budget", "draft")


def test_frc_ac7_a_retry_makes_no_answer_overrode(repo: Path) -> None:  # FRC-AC7, AC 3
    ex = paused_on_gap(repo, "T-1")
    ex.steps, ex.judges = [REVIEW], [judge()]
    decide(repo, "T-1", ex, "retry")
    assert not of(repo, "answer_overrode")


def test_frc_ac7_a_breakpoint_proceed_makes_no_answer_overrode(repo: Path) -> None:  # FRC-AC7, AC 3
    from .test_fallback_breakpoint import go as bgo

    spec = breakpoint_wf()
    ex = standin("claude", steps=[answer("Done.", session_id="s")] * 3, judges=[judge()] * 3)
    out = bgo(repo, spec, ex, pause_before=("build",))
    assert out.reason == "breakpoint"
    done = resume(spec, "F-1", repo, registry(ex), decision="proceed", settings=NO_SLEEP)
    assert done.exit_code is ExitCode.FINISHED, done.message
    assert not [f for f in found(repo, "F-1") if f["cause"].split(":")[0] in NEW]


# ---- FRC-B8: one finding for a unit and kind

def test_frc_ac8_two_decisions_over_two_criteria_make_one_finding_with_counts() -> None:  # FRC-AC8, AC 4
    ivs = [row(answered={"failed": ["a", "b"]}), row(answered={"failed": ["b"], "blockers": ["c"]}, item="i2")]
    (f,) = derived(ivs)
    assert f["cause"] == "answer_overrode:check" and f["unit"] == "gate" and f["count"] == 2
    assert f["criteria"] == {"a": 1, "b": 2, "c": 1} and list(f["criteria"]) == ["a", "b", "c"]
    assert f["items"] == 1


def test_frc_ac8_a_decision_at_a_unit_with_no_items_leaves_items_zero() -> None:  # FRC-AC8, AC 4
    (f,) = derived([row(answered={"failed": ["a", "b"]})])
    assert (f["count"], f["items"], f["criteria"]) == (1, 0, {"a": 1, "b": 1})


def test_frc_ac8_a_map_items_pause_leaves_items_one(repo: Path) -> None:  # FRC-AC8, AC 4, AC 14
    spec = tmap.mapped(retry_budget=0)
    out, _ = tmap.run(repo, spec, [tmap.planner(tmap.THREE), tmap.item_ok(), tmap.item_ok()],
                      [judge(), judge(), judge(tmap.FAIL)])
    assert out.exit_code is ExitCode.PAUSED and out.payload["item"] == "p2"
    ex = standin("claude", steps=[tmap.item_ok(), answer("Joined.")], judges=[judge(), judge()])
    done = resume(spec, "M-1", repo, registry(ex), decision="proceed", settings=NO_SLEEP)
    assert done.exit_code is ExitCode.FINISHED, done.message
    (f,) = of(repo, "answer_overrode", "M-1")
    assert f["unit"] == "phase" and f["items"] == 1 and f["criteria"] == {"c-item": 1}
    assert {x["cause"] for x in found(repo, "M-1") if x["cause"].split(":")[0] in NEW} == {f["cause"]}


def test_frc_ac8_decisions_of_two_segments_share_one_fingerprint() -> None:  # FRC-AC8, AC 4
    (first,) = derived([row(answered={"failed": ["a"]})])
    (second,) = derived([row(answered={"failed": ["b"]})])
    assert (first["cause"], first["unit"]) == (second["cause"], second["unit"])
    fps = {fingerprint("workflow", "demo", f["cause"], f["unit"]) for f in (first, second)}
    assert len(fps) == 1


def test_frc_ac8_a_decision_at_a_sub_workflow_unit_keeps_the_whole_unit_string() -> None:  # FRC-AC8, AC 4
    (f,) = derived([row(unit="child/draft")])
    assert f["unit"] == "child/draft" and "child" not in f


# ---- FRC-B9: a back that confirms an upstream claim

def test_frc_ac9_a_back_to_the_claimed_unit_makes_upstream_confirmed(repo: Path) -> None:  # FRC-AC9, AC 5, AC 14
    ex = standin("claude", steps=[DRAFT, CLAIMING], judges=[judge(), judge(UNVERIFIABLE)])
    out = go(repo, ex)
    assert out.exit_code is ExitCode.PAUSED and out.payload["reason"] == "upstream", out.message
    ex.steps, ex.judges = [DRAFT, REVIEW], [judge(), judge()]
    assert decide(repo, "T-1", ex, "back:draft").exit_code is ExitCode.FINISHED
    (f,) = of(repo, "upstream_confirmed")
    assert (f["cause"], f["unit"], f["from_unit"], f["count"]) == ("upstream_confirmed:draft", "draft", "review", 1)
    assert new_causes(repo) == {"upstream_confirmed:draft"}


def test_frc_ac9_a_back_to_another_unit_or_with_no_claim_makes_none(repo: Path) -> None:  # FRC-AC9, AC 5
    assert not derived([row(decision="back:c", answered={"claim": "a"})])
    assert not derived([row(decision="back:a", answered={"claim": "none"})])
    assert not derived([row(decision="proceed", answered={"claim": "a", "check": "PASS", "failed": []})])
    ex = paused_on_gap(repo, "T-1")  # a gap pause: the judgement holds no claim
    ex.steps, ex.judges = [DRAFT, REVIEW], [judge(), judge()]
    decide(repo, "T-1", ex, "back:draft")
    assert not of(repo, "upstream_confirmed")


# ---- FRC-B10: a retry that passes with nothing changed

def discarded_judgement(repo: Path, task: str, **kw: Any) -> Any:
    """The review's judge calls a tool outside its views: the judgement is discarded and the unit pauses."""
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge(tools=("Read", "Write"))])
    out = go(repo, ex, task=task, **kw)
    assert out.exit_code is ExitCode.PAUSED and out.payload["unit"] == "review", out.message
    return ex


def test_frc_ac10_a_retry_that_passes_unchanged_makes_the_finding(repo: Path) -> None:  # FRC-AC10, AC 6, AC 14
    ex = discarded_judgement(repo, "T-1")
    ex.steps, ex.judges = [REVIEW], [judge()]
    assert decide(repo, "T-1", ex, "retry").exit_code is ExitCode.FINISHED
    (f,) = of(repo, "retry_passed_unchanged")
    assert f["unit"] == "review" and f["cause"].startswith("retry_passed_unchanged:") and f["count"] == 1
    pause_reason = f["cause"].split(":", 1)[1]
    assert pause_reason and pause_reason != "retry_same_failure"
    assert not (new_causes(repo) - {f["cause"]})


def test_frc_ac10_a_change_in_the_worktree_makes_none(repo: Path) -> None:  # FRC-AC10, AC 6
    ex = discarded_judgement(repo, "T-2")
    committed_in_worktree(repo, "T-2")
    ex.steps, ex.judges = [REVIEW], [judge()]
    assert decide(repo, "T-2", ex, "retry").exit_code is ExitCode.FINISHED
    assert not of(repo, "retry_passed_unchanged", "T-2")


def test_frc_ac10_a_run_in_place_makes_none(repo: Path) -> None:  # FRC-AC10, AC 6
    place = two_step(workspace="in_place")
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge(tools=("Read", "Write"))])
    assert go(repo, ex, place, task="T-3").exit_code is ExitCode.PAUSED
    ex.steps, ex.judges = [REVIEW], [judge()]
    assert decide(repo, "T-3", ex, "retry", spec=place).exit_code is ExitCode.FINISHED
    assert not of(repo, "retry_passed_unchanged", "T-3")


# ---- FRC-B11: a retry followed by the same pause

def test_frc_ac11_a_retry_followed_by_the_same_pause_makes_retry_same_failure(repo: Path) -> None:
    # FRC-AC11, AC 6, AC 14
    ex = paused_on_retries(repo, "T-1")
    ex.steps, ex.judges = [DRAFT] * 3, [judge(verdict_block("UNMET"))] * 3
    again = decide(repo, "T-1", ex, "retry")
    assert again.exit_code is ExitCode.PAUSED and again.payload["unit"] == "draft", again.message
    ex.steps, ex.judges = [REVIEW], [judge()]
    assert decide(repo, "T-1", ex, "proceed").exit_code is ExitCode.FINISHED
    (f,) = of(repo, "retry_same_failure")
    assert (f["unit"], f["count"]) == ("draft", 1)
    assert not [c for c in new_causes(repo) if c.split(":")[0] in NEW[1:3] + NEW[4:]]


def test_frc_ac11_a_chain_of_retries_counts_each_decision_once(repo: Path) -> None:  # FRC-AC11, AC 6
    ex = paused_on_retries(repo, "T-1")
    for _ in range(2):
        ex.steps, ex.judges = [DRAFT] * 3, [judge(verdict_block("UNMET"))] * 3
        assert decide(repo, "T-1", ex, "retry").exit_code is ExitCode.PAUSED
    fs = of(repo, "retry_same_failure")
    assert [f["count"] for f in fs] == [1, 1] and len({f["fingerprint"] for f in fs}) == 1


def test_frc_ac11_a_retry_that_passes_makes_none(repo: Path) -> None:  # FRC-AC11, AC 6
    ex = paused_on_retries(repo, "T-1")
    ex.steps, ex.judges = [DRAFT, REVIEW], [judge(), judge()]
    assert decide(repo, "T-1", ex, "retry").exit_code is ExitCode.FINISHED
    assert not of(repo, "retry_same_failure")


# ---- FRC-B12: a resume that goes nowhere

def session_free(*extra: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"kind": "run_started", "ts": "2026-01-01T00:00:00+00:00"}, *extra]


def exit4() -> dict[str, Any]:
    return {"kind": "run_exit", "exit_code": 4, "reason": "attempt_cap"}


def test_frc_ac12_a_segment_with_no_session_that_exits_4_makes_resume_no_progress() -> None:  # FRC-AC12, AC 7
    (f,) = [x for x in derived([row(), row(decision="retry", item="none")], session_free(exit4()))
            if x["cause"] == "resume_no_progress"]
    assert f["cause"] == "resume_no_progress" and f["unit"] == "gate" and f["count"] == 1  # once per segment
    assert f["decisions"] == {"proceed": 1, "retry": 1}


def test_frc_ac12_a_retry_that_pauses_again_with_no_session_makes_both_causes() -> None:  # FRC-AC12, AC 7
    pause = {"kind": "pause", "unit": "gate", "item": None, "pause_kind": "escalation", "reason": "blocked"}
    paused = {"kind": "run_exit", "exit_code": 3, "reason": "escalation"}
    got = {f["cause"]: f for f in derived([row(decision="retry")], session_free(pause, paused))}
    assert got["resume_no_progress"]["count"] == 1 and got["retry_same_failure"]["count"] == 1


def test_frc_ac12_a_stop_makes_none() -> None:  # FRC-AC12, AC 7
    assert not derived([row(decision="stop")], session_free(exit4()))


def test_frc_ac12_a_segment_that_starts_a_session_makes_none() -> None:  # FRC-AC12, AC 7
    ran = {"kind": "attempt_start", "unit": "gate", "session_kind": "retry"}
    assert "resume_no_progress" not in {f["cause"] for f in derived([row(decision="retry")],
                                                                    session_free(ran, exit4()))}


def test_frc_ac12_a_script_that_fails_again_makes_no_resume_no_progress() -> None:  # FRC-AC12, AC 7
    ran = {"kind": "script", "unit": "gate", "exit_code": 1}
    pause = {"kind": "pause", "unit": "gate", "item": None, "pause_kind": "escalation", "reason": "blocked"}
    got = {f["cause"] for f in derived([row(decision="retry")], session_free(ran, pause))}
    assert "resume_no_progress" not in got and "retry_same_failure" in got


def test_frc_ac12_a_resume_with_a_proceed_over_a_stopped_thread_in_a_fixture_run(repo: Path) -> None:
    # FRC-AC12, AC 7, AC 14: a person's stop, then a stop again: no finding of the cause
    ex = paused_on_retries(repo, "T-1")
    assert decide(repo, "T-1", ex, "stop").exit_code is ExitCode.STOPPED
    assert "resume_no_progress" not in {f["cause"] for f in found(repo)}


# ---- FRC-B13, FRC-B14: what its decisions gave; a fault whoever decided

def test_frc_ac13_a_finding_holds_decisions_reasons_and_the_median_wait() -> None:  # FRC-AC13, AC 11
    ivs = [row(wait_s=60.0, operator_reason="plan"), row(wait_s=400.0, operator_reason="plan"),
           row(wait_s=100.0)]
    (f,) = derived(ivs)
    assert f["decisions"] == {"proceed": 3} and f["reasons"] == {"plan": 2, "not given": 1}
    assert f["wait_s_median"] == 100


def test_frc_ac13_an_even_number_of_waits_takes_the_mean_of_the_middle_two() -> None:  # FRC-AC13, AC 11
    (f,) = derived([row(wait_s=60.0), row(wait_s=100.0)])
    assert f["wait_s_median"] == 80


def test_frc_ac13_a_row_with_no_wait_is_left_out_and_none_gives_null() -> None:  # FRC-AC13, AC 11
    (f,) = derived([row(wait_s=60.0), row(wait_s=None), row(wait_s=100.0)])
    assert f["wait_s_median"] == 80
    (g,) = derived([row(wait_s=None)])
    assert g["wait_s_median"] is None


def test_frc_ac14_each_cause_is_a_fault_with_its_side_and_a_fixed_remedy() -> None:  # FRC-AC14, AC 8
    expect = {"answer_overrode": "workflow", "upstream_confirmed": "workflow", "retry_passed_unchanged": "workflow",
              "retry_same_failure": "workflow", "resume_no_progress": "engine"}
    for code, side in expect.items():
        c = causes.cause_of(code + ":x")
        assert (c.klass, c.side) == ("fault", side), code
        text = c.remedy.lower()
        assert any(w in text for w in ("check", "gate criterion", "resume")), text
        assert "prompt" not in text and "step" not in text, text


def test_frc_ac14_a_person_deciding_leaves_answer_overrode_a_fault(repo: Path) -> None:  # FRC-AC14, AC 8
    pause_env(finding("c-a", "no git"))
    ex = run_s(repo)
    done = resume(fixture(), "T-1", repo, registry(ex), decision="proceed",
                  settings=dataclasses.replace(NO_SLEEP, caller={"kind": "person"}))
    assert done.exit_code is ExitCode.FINISHED
    (f,) = of(repo, "answer_overrode")
    assert (f["class"], f["side"]) == ("fault", "workflow")


def test_frc_ac14_one_agent_session_leaves_agent_decided_designed_and_the_override_a_fault(
        repo: Path) -> None:  # FRC-AC14, AC 8, AC 14
    pause_env(finding("c-a", "no git"))
    ex = standin("claude", steps=[A_DONE], judges=[judge()])
    assert go(repo, ex, fixture(), caller=AGENT).exit_code is ExitCode.PAUSED
    done = resume(fixture(), "T-1", repo, registry(ex), decision="proceed",
                  settings=dataclasses.replace(NO_SLEEP, caller=dict(AGENT), operator_reason="other"))
    assert done.exit_code is ExitCode.FINISHED, done.message
    (decided,) = [f for f in found(repo) if f["cause"].startswith("agent_decided:")]
    (over,) = of(repo, "answer_overrode")
    assert decided["class"] == "designed" and over["class"] == "fault"
    assert over["reasons"] == {"other": 1}


def test_frc_ac14_a_resume_that_goes_nowhere_is_an_engine_fault() -> None:  # FRC-AC14, AC 8
    (f,) = derived([row(decision="retry")], session_free(exit4()))
    c = causes.cause_of(f["cause"])
    assert (c.klass, c.side) == ("fault", "engine") and "resume" in c.remedy.lower()


# ---- FRC-B15: a fact the row lacks makes no finding

def test_frc_ac15_a_row_with_no_answered_makes_no_answer_overrode() -> None:  # FRC-AC15, AC 2
    bare = {k: v for k, v in row().items() if k != "answered"}
    assert derived([bare]) == []


def test_frc_ac15_a_row_with_no_item_makes_no_retry_same_failure() -> None:  # FRC-AC15, AC 2
    pause = {"kind": "pause", "unit": "gate", "item": None, "pause_kind": "escalation", "reason": "blocked"}
    bare = {k: v for k, v in row(decision="retry").items() if k != "item"}
    assert "retry_same_failure" not in {f["cause"] for f in derived([bare], session_free(pause))}


def test_frc_ac15_facts_that_are_not_recorded_make_no_finding() -> None:  # FRC-AC15, AC 2
    nothing = {k: "not recorded" for k in ("check", "failed", "environmental", "blockers", "gap", "guard", "claim")}
    ivs = [row(answered=nothing), row(answered=nothing, decision="back:a"), row(answered=nothing, decision="retry")]
    assert derived(ivs, [{"kind": "run_started"}, {"kind": "gate", "unit": "gate", "item": None, "token": "PROCEED"}]) == []


def test_frc_ac15_a_thread_resumed_by_an_older_engine_makes_findings_from_the_rows_that_hold_the_facts() -> None:
    # FRC-AC15, AC 2
    old = {"kind": "intervention", "unit": "gate", "pause_kind": "escalation", "decision": "proceed", "caller": {},
           "touches": [{"class": "rescue", "action": "decide"}]}
    (f,) = derived([old, row()])
    assert f["cause"] == "answer_overrode:check" and f["count"] == 1
    assert derived([old]) == []
