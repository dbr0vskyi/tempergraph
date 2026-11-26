"""Friction causes read from the engine's own records: a trip back, a stop at the attempt cap, an undelivered last
stage, a session the usage limit refused and a pause at an ask unit (FRC-B1 to FRC-B5; task AC 2 to AC 6, AC 8).

Every cause here comes from a fixture run of the engine (SIL-AC7), never from a record typed into a test."""

from __future__ import annotations

import dataclasses
import time
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import Gate, Judge, Routing, Step, Value, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import InfraCause, SessionResult, Usage
from tempergraph.executors.standins import answer, standin
from tempergraph.improve import causes, child
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.improve.record import findings_path, read_findings
from tempergraph.run.runner import resume

from . import test_ask_wait as ask
from .fixtures.workflows import crit, draft_check, named, two_step
from .test_finalizer_outcomes import CANARY, happy, pushes_nothing, raises, skips, spec_with
from .test_run import DRAFT, NO_SLEEP, REVIEW, go, judge, records, registry, verdict_block
from .test_stop_at_pause import asks, loop_on
from .test_usage_limit import refused

SHIP = answer("Shipped", session_id="s-ship")
BACK = verdict_block("UNMET", defect_in="notes")


def found(repo: Path, task: str = "T-1") -> list[dict[str, Any]]:
    return read_findings(repo / ".tempergraph", "demo", task)


def of(repo: Path, cause: str, task: str = "T-1") -> list[dict[str, Any]]:
    return [f for f in found(repo, task) if f["cause"] == cause or f["cause"].startswith(cause + ":")]


def chain(ship: bool = False, loop_budget: int = 1) -> Any:
    """draft, then review whose gate may send the run back to draft, then optionally a unit that has not run before."""
    units: dict[str, Any] = {
        "draft": Step(prompt="Write the notes for {request} into notes.md", tools=["read", "write", "shell"],
                      commands=["pytest"], produces={"notes": "file"},
                      gate=Gate(check=draft_check, judge=Judge(stance="Verify.", brief="Read notes.md"),
                                criteria=[crit("c-file")])),
        "review": Step(prompt="Review {notes} for {task_id}", tools=["read"],
                       produces={"verdict": Value(choices=["ok", "redo"])},
                       gate=Gate(judge=Judge(stance="Verify.", references=["notes"]), criteria=[crit("c-review")],
                                 back_targets=["draft"], loop_budget=loop_budget)),
    }
    order = ["draft", "review"]
    if ship:
        units["ship"] = Step(prompt="Ship the notes", tools=["read"],
                             gate=Gate(judge=Judge(stance="Verify."), criteria=[crit("c-ship")]))
        order.append("ship")
    return named(Workflow(order=order, units=units, issue_repository="acme/notes",
                          routing=Routing(description="Draft, review, ship"), allow_commands=["pytest", "git status"]))


def assert_fault_remedy(finding: dict[str, Any], names: tuple[str, ...]) -> None:
    """AC 8: the remedy of a fault cause names a kind of change that fits a unit with no step and no prompt."""
    text = str(finding["remedy"]).lower()
    assert any(n in text for n in names), text
    assert "prompt" not in text and "step" not in text, text


# ---- FRC-B1: a trip back


def test_frc_ac1_a_trip_back_is_a_finding_of_the_gate_that_sent_the_run_back(repo: Path) -> None:  # FRC-AC1, AC 2
    ex = standin("claude", steps=[DRAFT, REVIEW, DRAFT, REVIEW],
                 judges=[judge(), judge(BACK), judge(), judge()])
    assert go(repo, ex, chain()).exit_code is ExitCode.FINISHED
    (f,) = of(repo, "trip_back")
    assert f["cause"] == "trip_back:draft" and f["unit"] == "review" and f["count"] == 4
    assert (f["class"], f["side"]) == ("fault", "workflow")
    assert_fault_remedy(f, ("gate criterion", "check"))  # AC 8


def test_frc_ac1_a_unit_that_had_not_run_before_is_not_counted(repo: Path) -> None:  # FRC-AC1, AC 2
    ex = standin("claude", steps=[DRAFT, REVIEW, DRAFT, REVIEW, SHIP],
                 judges=[judge(), judge(BACK), judge(), judge(), judge()])
    assert go(repo, ex, chain(ship=True)).exit_code is ExitCode.FINISHED
    assert [c.kind for c in ex.calls].count("step") == 5  # the third unit ran, after the trip back
    (f,) = of(repo, "trip_back")
    assert f["cause"] == "trip_back:draft" and f["unit"] == "review" and f["count"] == 4


def test_frc_ac1_an_attempt_cap_before_any_session_leaves_count_zero(repo: Path) -> None:  # FRC-AC1, AC 2
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge(BACK)])
    out = go(repo, ex, chain(), flags={"run.attempt_cap": 2})
    assert out.exit_code is ExitCode.STOPPED and out.reason == "attempt_cap", out.message
    (f,) = of(repo, "trip_back")
    assert f["cause"] == "trip_back:draft" and f["unit"] == "review" and f["count"] == 0
    assert (f["class"], f["side"]) == ("fault", "workflow")


# ---- FRC-B2: a stop at the attempt cap


def test_frc_ac2_a_stop_after_two_trips_back_counts_them(repo: Path) -> None:  # FRC-AC2, AC 3
    ex = standin("claude", steps=[DRAFT, REVIEW, DRAFT, REVIEW],
                 judges=[judge(), judge(BACK), judge(), judge(BACK)])
    out = go(repo, ex, chain(loop_budget=2), flags={"run.attempt_cap": 4})
    assert out.exit_code is ExitCode.STOPPED and out.reason == "attempt_cap", out.message
    (f,) = of(repo, "attempt_cap")
    assert f["cause"] == "attempt_cap" and f["unit"] == "" and f["count"] == 2
    assert (f["class"], f["side"]) == ("fault", "workflow") and f["segment_exit"] == 4
    assert_fault_remedy(f, ("gate criterion", "check", "attempt cap"))  # AC 8


def test_frc_ac2_a_stop_with_no_trip_back_leaves_count_zero(repo: Path) -> None:  # FRC-AC2, AC 3
    failed = verdict_block("UNMET")
    ex = standin("claude", steps=[DRAFT, DRAFT], judges=[judge(failed), judge(failed)])
    out = go(repo, ex, chain(), flags={"run.attempt_cap": 2})
    assert out.exit_code is ExitCode.STOPPED and out.reason == "attempt_cap", out.message
    (f,) = of(repo, "attempt_cap")
    assert f["unit"] == "" and f["count"] == 0
    assert not of(repo, "trip_back")


def test_frc_ac2_a_run_under_its_cap_leaves_no_such_finding(repo: Path) -> None:  # FRC-AC2, AC 3
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    assert go(repo, ex, chain()).exit_code is ExitCode.FINISHED
    assert not of(repo, "attempt_cap") and not of(repo, "trip_back")


# ---- FRC-B3: a last stage that delivered nothing


def undelivered(repo: Path) -> list[dict[str, Any]]:
    return of(repo, "finalizer_undelivered")


def with_steps(ctx: Any) -> Any:
    from tempergraph.run.finalize import FinalizerResult

    return FinalizerResult(outcome="opened", reason="pushed by hand", manual_steps=["push the branch"])


def test_frc_ac3_a_skipped_finalizer_with_manual_steps_is_a_finding(repo: Path) -> None:  # FRC-AC3, AC 4
    assert go(repo, happy(), spec_with(skips)).exit_code is ExitCode.FINISHED
    (f,) = undelivered(repo)
    assert f["cause"] == "finalizer_undelivered:skipped" and f["unit"] == "" and f["count"] == 1
    assert (f["class"], f["side"]) == ("fault", "workflow")
    assert "finalizer" in f["remedy"].lower()
    assert_fault_remedy(f, ("finalizer",))  # AC 8
    text = findings_path(repo / ".tempergraph", "demo", "T-1").read_text()
    assert "add a remote" not in text and "no origin" not in text and "push the branch" not in text


def test_frc_ac3_a_declared_outcome_with_a_manual_step_is_a_finding(repo: Path) -> None:  # FRC-AC3, AC 4
    assert go(repo, happy(), spec_with(with_steps)).exit_code is ExitCode.FINISHED
    (f,) = undelivered(repo)
    assert f["cause"] == "finalizer_undelivered:opened" and f["count"] == 1
    assert (f["class"], f["side"]) == ("fault", "workflow")
    assert "pushed by hand" not in findings_path(repo / ".tempergraph", "demo", "T-1").read_text()


def test_frc_ac3_a_raising_finalizer_is_a_finding_with_no_text(repo: Path) -> None:  # FRC-AC3, AC 4
    assert go(repo, happy(), spec_with(raises)).exit_code is ExitCode.FINISHED
    (f,) = undelivered(repo)
    assert f["cause"] == "finalizer_undelivered:error" and f["unit"] == "" and f["count"] == 1
    assert_fault_remedy(f, ("finalizer",))  # AC 8
    text = findings_path(repo / ".tempergraph", "demo", "T-1").read_text()
    assert CANARY not in text and "RuntimeError" not in text


def test_frc_ac3_a_finalizer_that_published_leaves_no_finding(repo: Path) -> None:  # FRC-AC3, AC 4
    assert go(repo, happy(), spec_with(pushes_nothing)).exit_code is ExitCode.FINISHED
    assert undelivered(repo) == []


def test_frc_ac3_a_workflow_with_no_finalizer_leaves_no_finding(repo: Path) -> None:  # FRC-AC3, AC 4
    assert go(repo, happy()).exit_code is ExitCode.FINISHED
    assert undelivered(repo) == []


# ---- FRC-B4: a session the usage limit refused


@pytest.mark.parametrize("flavour", [{"error_kind": "model"}, {"infra_cause": InfraCause.THROTTLED}])
def test_frc_ac4_a_refused_step_session_is_one_infra_finding(repo: Path, flavour: dict[str, Any]) -> None:
    # FRC-AC4, AC 5
    ex = standin("claude", steps=[refused(time.time() + 3600, **flavour)] * 3)
    assert go(repo, ex).exit_code is ExitCode.PAUSED
    rows = [f for f in found(repo) if f["unit"] == "draft"]
    assert [f["cause"] for f in rows] == ["usage_limit"], rows  # no retries_spent, no escalation, no infra:<cause>
    (f,) = rows
    assert (f["class"], f["side"], f["count"]) == ("infra", "host", 1)
    assert f["remedy"].startswith("Recorded only")
    assert not of(repo, "retries_spent")


def test_frc_ac4_a_refused_judge_session_is_the_judged_units_finding(repo: Path) -> None:  # FRC-AC4, AC 5
    ex = standin("claude", steps=[DRAFT], judges=[refused(time.time() + 3600)])
    assert go(repo, ex).exit_code is ExitCode.PAUSED
    rows = [f for f in found(repo) if f["unit"] == "draft"]
    assert [f["cause"] for f in rows] == ["usage_limit"], rows
    assert (rows[0]["class"], rows[0]["side"], rows[0]["count"]) == ("infra", "host", 1)


def test_frc_ac4_a_failure_without_the_limit_spends_the_retry_budget(repo: Path) -> None:  # FRC-AC4, AC 5
    failed = SessionResult(ok=False, error_kind="model", usage=Usage())
    ex = standin("claude", steps=[failed] * 3)
    assert go(repo, ex).exit_code is not ExitCode.FINISHED
    assert of(repo, "retries_spent") and not of(repo, "usage_limit")


# ---- FRC-B5: a pause at an ask unit


def test_frc_ac5_a_pause_at_an_ask_unit_is_designed(repo: Path) -> None:  # FRC-AC5, AC 6
    out = ask.begin(repo, ask.asking_wf(), ask.ex())
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "input"
    rows = [f for f in found(repo, "A-1") if f["unit"] == "details"]
    assert [f["cause"] for f in rows] == ["input"], rows
    (f,) = rows
    assert (f["class"], f["side"]) == ("designed", "workflow") and f["remedy"].startswith("Recorded only")
    assert not [x for x in found(repo, "A-1") if x["class"] == "fault"]


def test_frc_ac5_an_answered_ask_does_not_fire_the_friction_lens_in_dev_mode(repo: Path) -> None:  # FRC-AC5, AC 6
    spec = ask.asking_wf()
    assert dataclasses.replace(spec).improvement_mode == "dev"
    ask.begin(repo, spec)
    done = ask.again(repo, spec, answers={"env": "prod", "ticket": "PRJ-1"})
    assert done.exit_code is ExitCode.FINISHED, done.message
    rec = [r for r in records(repo, "A-1") if r["kind"] == "finding_recorded"][-1]
    assert rec["lenses"]["mode"] == "dev" and rec["lenses"]["friction"] is False


# ---- FRC-B6: an agent's decision of the caller that started the run is designed


def rescued_by(repo: Path, monkeypatch: pytest.MonkeyPatch, task: str, starter: dict[str, Any],
               decider: dict[str, Any]) -> list[str]:
    """A thread started by `starter`, paused on a gap, and answered `proceed` by `decider`; returns the prompts the
    friction judge was asked at the final exit."""
    monkeypatch.delenv("TEMPERGRAPH_AUTONOMY", raising=False)
    loop_on(monkeypatch)
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge(verdict_block("UNVERIFIABLE"))])
    assert go(repo, ex, task=task, caller=starter).exit_code is ExitCode.PAUSED
    done = resume(two_step(), task, repo, registry(ex), decision="proceed",
                  settings=dataclasses.replace(NO_SLEEP, caller=decider))
    assert done.exit_code is ExitCode.FINISHED, done.message
    seen, reply = asks()
    child.drain(registry=registry(standin("claude", judges=[reply])), host=lambda: MemoryCodeHost())
    return seen


def decided_finding(repo: Path, task: str) -> dict[str, Any]:
    (f,) = [x for x in found(repo, task) if x["cause"].startswith("agent_decided:")]
    return f


AGENT = {"kind": "agent", "host": "claude-code", "host_session": "sess-1"}


def test_frc_ac6_a_decision_by_the_starting_caller_is_designed_and_never_judged(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # FRC-AC6, AC 8
    seen = rescued_by(repo, monkeypatch, "D-1", AGENT, dict(AGENT))
    f = decided_finding(repo, "D-1")
    assert f["class"] == "designed"
    (prompt,) = seen
    assert f["fingerprint"] not in prompt and "agent_decided" not in prompt
    assert "cause `gap_escalation`" in prompt  # the pause's own fault is still judged


def test_frc_ac6_a_decision_by_another_agent_is_a_fault(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # FRC-AC6, AC 8
    seen = rescued_by(repo, monkeypatch, "D-2", AGENT, {**AGENT, "host_session": "sess-2"})
    f = decided_finding(repo, "D-2")
    assert f["class"] == "fault"
    (prompt,) = seen
    assert f["fingerprint"] in prompt


@pytest.mark.parametrize("order", [("other", "starter"), ("starter", "other"), ("other", "other")])
def test_frc_ac6_one_decision_of_another_agent_in_the_group_makes_the_finding_a_fault(
        order: tuple[str, ...]) -> None:  # FRC-AC6, AC 8
    """The same unit and cause decided twice in one segment: the class is `designed` only when every decision of the
    group is the starting caller's, whichever decision comes last."""
    callers = {"starter": dict(AGENT), "other": {**AGENT, "host_session": "sess-2"}}
    ivs = [{"unit": "review", "pause_kind": "escalation", "touches": [{"class": "rescue"}],
            "caller": {**callers[who], "decided_by": "agent"}} for who in order]
    (f,) = causes.derive([], ivs, starter=AGENT)
    assert f["cause"] == "agent_decided:escalation" and f["count"] == 2
    assert f["class"] == "fault", order


def test_frc_ac6_decisions_all_by_the_starting_caller_stay_designed() -> None:  # FRC-AC6, AC 8
    ivs = [{"unit": "review", "pause_kind": "escalation", "touches": [{"class": "rescue"}],
            "caller": {**AGENT, "decided_by": "agent"}} for _ in range(2)]
    (f,) = causes.derive([], ivs, starter=AGENT)
    assert f["class"] == "designed" and f["count"] == 2


def test_sup_ac5_agent_decided_clusters_by_cause_and_only_faults_reach_the_judge(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SUP-AC5, SUP-B7, SUP-B16, FRC-AC6, AC 8
    other = {**AGENT, "host_session": "sess-2"}
    seen4 = rescued_by(repo, monkeypatch, "D-4", AGENT, other)
    seen5 = rescued_by(repo, monkeypatch, "D-5", AGENT, other)
    seen6 = rescued_by(repo, monkeypatch, "D-6", AGENT, dict(AGENT))
    f4, f5, f6 = (decided_finding(repo, t) for t in ("D-4", "D-5", "D-6"))
    assert f4["class"] == f5["class"] == "fault" and f4["cause"] == f5["cause"]
    assert f4["fingerprint"] == f5["fingerprint"]
    assert f4["fingerprint"] in seen4[0] and f5["fingerprint"] in seen5[0]
    assert f6["class"] == "designed" and f6["cause"] == f4["cause"]
    assert f6["fingerprint"] not in seen6[0]


def test_frc_ac6_a_decision_by_a_caller_with_no_host_session_is_a_fault(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # FRC-AC6, AC 8
    bare = {"kind": "agent", "host": "claude-code"}
    seen = rescued_by(repo, monkeypatch, "D-3", bare, dict(bare))
    f = decided_finding(repo, "D-3")
    assert f["class"] == "fault"
    (prompt,) = seen
    assert f["fingerprint"] in prompt
