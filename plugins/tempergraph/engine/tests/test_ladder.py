"""The effort ladder: climbing evidence, held causes, resets, validation (LAD-AC1, AC-2, AC-4)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import Gate, Judge, Routing, Step, Value, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import CheckFinding, CheckResult, SessionOptions, SessionResult, WorkflowSpec
from tempergraph.executors.capabilities import DECLARED
from tempergraph.executors.preflight import preflight
from tempergraph.executors.standins import answer, standin
from tempergraph.model.validate import validate
from tempergraph.run import ladder
from tempergraph.run.runner import RunSettings, resume, start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.workflows import crit, named
from .test_run import judge, registry, verdict_block

FAIL = verdict_block("UNMET", "MET")
MET2 = verdict_block("MET", "MET")
RUNGS = ("medium", "high", "xhigh")


def accepted(unit: str) -> str:
    return "accepted"


def below_bar(unit: str) -> str:
    return "below_bar"


def provisional(unit: str) -> str:
    return "provisional"


def third_fails(ctx: Any) -> CheckResult:
    """A check whose third attempt fails a test it ran: substance (LAD-B10)."""
    if ctx.attempt == 3:
        return CheckResult(result="FAIL", evidence="pytest failed", findings=[
            CheckFinding(status="fail", criterion="c4", message="test_x failed", kind="substance")])
    return CheckResult(result="PASS", evidence="ok")


def contract_fails(ctx: Any) -> CheckResult:
    if ctx.attempt == 1:
        return CheckResult(result="FAIL", evidence="bad shape", findings=[
            CheckFinding(status="fail", criterion="c4", message="test_x failed", kind="substance"),
            CheckFinding(status="fail", criterion="c1", message="no heading", kind="output_contract")])
    return CheckResult(result="PASS", evidence="ok")


def unkinded_fails(ctx: Any) -> CheckResult:
    if ctx.attempt == 1:
        return CheckResult(result="FAIL", evidence="bad", findings=[
            CheckFinding(status="fail", criterion="c4", message="something")])
    return CheckResult(result="PASS", evidence="ok")


def wf(*, check: Any = None, retry_budget: int = 3, produces: dict[str, Any] | None = None,
       spec_fields: dict[str, Any] | None = None, **step: Any) -> WorkflowSpec:
    step.setdefault("effort_ladder", RUNGS)
    units = {"work": Step(prompt="Do {request}", tools=["read", "write"], produces=produces or {}, model="medium",
                          gate=Gate(check=check, judge=Judge(stance="V."), criteria=[crit("c2"), crit("c4")],
                                    retry_budget=retry_budget), **step)}
    return named(Workflow(order=["work"], units=units, issue_repository="acme/x",
                          routing=Routing(description="Do a task"), **(spec_fields or {})))


OK = answer("Done.", session_id="s")
SLOW = SessionResult(ok=False, timed_out=True, session_id="slow")


def go(repo: Path, spec: WorkflowSpec, steps: list[Any], judges: list[Any], task: str = "L-1",
       judge_state: Any = accepted, **kw: Any) -> Any:
    ex = standin("claude", steps=list(steps), judges=list(judges))
    out = start(spec, task, {"request": "x"}, repo, registry(ex),
                RunSettings(sleep=lambda s: None, judge_state=judge_state, **kw))
    return out, ex


def recs(repo: Path, kind: str, task: str = "L-1") -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", task) / "run.jsonl"
    return [r for r in map(json.loads, p.read_text().splitlines()) if r["kind"] == kind]


def efforts(ex: Any, kind: str = "step") -> list[str | None]:
    return [c.request.options.effort for c in ex.calls if c.kind == kind]


def test_climb_on_trusted_evidence_only(repo: Path) -> None:  # LAD-B1, LAD-AC4
    out, ex = go(repo, wf(check=third_fails), [OK, SLOW, OK, OK], [judge(FAIL), judge(MET2)])
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert efforts(ex) == ["medium", "high", "high", "xhigh"]
    assert efforts(ex, "judge") == [None, None]  # a judge never runs on a rung
    d = recs(repo, "ladder_decision")
    assert [(x["rung"], x["effort"], x["evidence"], x["held_by"]) for x in d] == [
        (1, "high", "judge_blocker", None), (1, "high", None, "timeout"), (2, "xhigh", "check_fail", None)]
    assert d[0]["criteria"] == ["c2"] and d[0]["judge_state"] == "accepted" and d[2]["criteria"] == ["c4"]
    starts = [r["ladder"] for r in recs(repo, "attempt_start") if r["session_kind"] in ("step", "retry")]
    assert [(s["rung"], s["effort"], s["alias"], s["source"]) for s in starts] == [
        (0, "medium", "medium", "ladder:effort[0]"), (1, "high", "medium", "ladder:effort[1]"),
        (1, "high", "medium", "ladder:effort[1]"), (2, "xhigh", "medium", "ladder:effort[2]")]


def test_the_top_rung_is_the_end(repo: Path) -> None:  # LAD-B11: a ladder never adds an attempt
    out, ex = go(repo, wf(effort_ladder=("low", "medium"), retry_budget=2), [OK, OK, OK],
                 [judge(FAIL), judge(FAIL), judge(FAIL)])
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget"
    assert efforts(ex) == ["low", "medium", "medium"]


@pytest.mark.parametrize(("state", "mode", "want", "held"), [
    (below_bar, "dev", ["medium", "medium"], "judge_not_trusted"),  # LAD-B2
    (lambda u: "unscored", "dev", ["medium", "medium"], "judge_not_trusted"),
    (lambda u: "contradicted", "dev", ["medium", "medium"], "judge_not_trusted"),
    (provisional, "dev", ["medium", "high"], None),
    (provisional, "stable", ["medium", "medium"], "judge_not_trusted"),
    (accepted, "stable", ["medium", "high"], None),
])
def test_an_untrusted_judge_holds_the_rung(repo: Path, state: Any, mode: str, want: list[str], held: Any) -> None:
    spec = wf(spec_fields={"improvement_mode": mode})
    out, ex = go(repo, spec, [OK, OK], [judge(FAIL), judge(MET2)], judge_state=state)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert efforts(ex) == want
    (d,) = recs(repo, "ladder_decision")
    assert d["held_by"] == held and d["evidence"] == (None if held else "judge_blocker")


def test_no_calibration_means_no_climb(repo: Path) -> None:  # the default seam reads the real calibration state
    ex = standin("claude", steps=[OK, OK], judges=[judge(FAIL), judge(MET2)])
    out = start(wf(), "L-1", {"request": "x"}, repo, registry(ex), RunSettings(sleep=lambda s: None))
    assert out.exit_code is ExitCode.FINISHED and efforts(ex) == ["medium", "medium"]
    assert recs(repo, "ladder_decision")[0]["judge_state"] == "unscored"


def test_an_output_contract_failure_holds_the_rung(repo: Path) -> None:  # LAD-B3
    spec = wf(produces={"grade": Value(choices=["a", "b"])})
    bad, good = answer("Done.\nARTIFACT grade: z", session_id="s"), answer("Done.\nARTIFACT grade: a", session_id="s")
    out, ex = go(repo, spec, [bad, good], [judge(MET2)])
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert efforts(ex) == ["medium", "medium"]
    assert recs(repo, "ladder_decision")[0]["held_by"] == "output_contract"


@pytest.mark.parametrize(("check", "held"), [(contract_fails, "output_contract"), (unkinded_fails, "check_no_substance")])
def test_a_check_failure_without_substance_holds_the_rung(repo: Path, check: Any, held: str) -> None:  # LAD-B10
    out, ex = go(repo, wf(check=check), [OK, OK], [judge(MET2)])
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert efforts(ex) == ["medium", "medium"] and recs(repo, "ladder_decision")[0]["held_by"] == held


def test_a_person_retry_starts_at_rung_zero(repo: Path) -> None:  # LAD-B8
    spec = wf(retry_budget=2)
    out, ex = go(repo, spec, [OK, OK, OK], [judge(FAIL), judge(FAIL), judge(FAIL)])
    assert out.exit_code is ExitCode.PAUSED and efforts(ex) == ["medium", "high", "xhigh"]
    ex.steps, ex.judges = [OK], [judge(MET2)]
    out = resume(spec, "L-1", repo, registry(ex), decision="retry", feedback="look at the flag",
                 settings=RunSettings(sleep=lambda s: None, judge_state=accepted))
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert efforts(ex)[-1] == "medium"
    assert "look at the flag" in [c for c in ex.calls if c.kind == "step"][-1].request.prompt


@pytest.mark.parametrize("flags", [{"work.effort": "high"}, {"work.model": "large"}])
def test_an_operator_pin_switches_the_ladder_off(repo: Path, flags: dict[str, Any]) -> None:  # LAD-B11 last row
    out, ex = go(repo, wf(), [OK, OK], [judge(FAIL), judge(MET2)], flags=flags)
    assert out.exit_code is ExitCode.FINISHED, out.message
    want = flags.get("work.effort")
    assert efforts(ex) == [want, want]
    assert [d["held_by"] for d in recs(repo, "ladder_decision")] == ["operator_pin"]
    start_rec = [r for r in recs(repo, "attempt_start") if r["session_kind"] == "retry"][0]
    assert start_rec["ladder"]["source"] == "operator"


@pytest.mark.parametrize("key", ["work.effort_ladder", "work.escalation"])
def test_an_operator_cannot_set_a_ladder(repo: Path, key: str) -> None:  # LAD-B14 last row
    out, _ = go(repo, wf(), [OK], [judge(MET2)], flags={key: "high"})
    assert out.exit_code is ExitCode.USAGE


def test_a_fixed_effort_runs_without_a_ladder(repo: Path) -> None:
    out, ex = go(repo, wf(effort_ladder=(), effort="high"), [OK, OK], [judge(FAIL), judge(MET2)])
    assert out.exit_code is ExitCode.FINISHED and efforts(ex) == ["high", "high"]
    assert recs(repo, "ladder_decision") == []


BLOCKER = {"criterion": "c2", "problem": "UNMET: x"}
JUDGED = {"verdict": "RETRY", "reason": "blockers", "blockers": [BLOCKER], "judge_state": "accepted",
          "trusted": True, "confidence_source": "judge"}
SUBSTANCE = {"result": "FAIL", "environmental": False,
             "findings": [{"status": "fail", "criterion": "c4", "kind": "substance"}]}


@pytest.mark.parametrize(("att", "judged", "evidence", "held"), [
    ({}, JUDGED, "judge_blocker", None),
    ({"check": SUBSTANCE}, {"verdict": "RETRY", "reason": "check_fail"}, "check_fail", None),
    ({"timed_out": True}, {"verdict": "RETRY", "reason": "step_failed"}, None, "timeout"),
    ({"stalled": True}, {"verdict": "RETRY", "reason": "step_failed"}, None, "stall"),
    ({"error_kind": "turn_cap"}, {"verdict": "RETRY", "reason": "step_failed"}, None, "turn_cap"),
    ({"error_kind": "cap_reached"}, {"verdict": "RETRY", "reason": "step_failed"}, None, "cost_cap"),
    ({"error_kind": "model"}, {"verdict": "RETRY", "reason": "step_failed"}, None, "model"),
    ({"error_kind": "infra", "infra_cause": "network"}, {"verdict": "RETRY", "reason": "step_failed"}, None, "infra"),
    ({}, {"verdict": "RETRY", "reason": "step_failed"}, None, "step_failed"),
    ({}, {"verdict": "RETRY", "reason": "output_contract"}, None, "output_contract"),
    ({}, {**JUDGED, "trusted": False, "judge_state": "below_bar"}, None, "judge_not_trusted"),
    ({}, {**JUDGED, "confidence_source": "engine_placeholder"}, None, "judge_placeholder"),
    ({}, {**JUDGED, "blockers": [{**BLOCKER, "no_change": True}]}, None, "no_substantive_blocker"),
    ({}, {**JUDGED, "blockers": [{**BLOCKER, "defect_in": "plan"}]}, None, "no_substantive_blocker"),
    ({}, {**JUDGED, "blockers": [{**BLOCKER, "defect_in": "plan"}, {"criterion": "c4"}]}, "judge_blocker", None),
    ({"timed_out": True}, JUDGED, None, "timeout"),
    ({"cut_off": True}, JUDGED, None, "cut_off"),
    ({"check": {**SUBSTANCE, "environmental": True}}, {"verdict": "RETRY", "reason": "check_fail"}, None,
     "environmental"),
    ({"check": {"result": "FAIL", "findings": [{"status": "fail", "criterion": None, "kind": "substance"}]}},
     {"verdict": "RETRY", "reason": "check_fail"}, None, "check_no_substance"),
    ({"check": {"result": "FAIL", "findings": [{"status": "pass", "criterion": "c4", "kind": "substance"}]}},
     {"verdict": "RETRY", "reason": "check_fail"}, None, "check_no_substance"),
])
def test_only_two_kinds_of_evidence_climb(att: dict[str, Any], judged: dict[str, Any], evidence: Any,
                                          held: Any) -> None:  # LAD-AC2, LAD-B10, LAD-B11
    got = ladder.classify(att, judged)
    assert (got.evidence, got.held_by) == (evidence, held)


def codes(spec: WorkflowSpec, caps: Any = DECLARED) -> set[str]:
    return {f.code for f in validate(spec, caps) if f.severity == "error"}


def test_validation() -> None:  # LAD-B9, LAD-B14
    assert codes(wf()) == set()
    for rungs in (("medium",), ("low", "medium", "high", "xhigh", "max"), ("high", "medium"), ("high", "high"),
                  ("medium", "extreme")):
        assert "ladder-invalid" in codes(wf(effort_ladder=rungs)), rungs
    assert "ladder-invalid" in codes(wf(effort="high"))  # a ladder excludes a fixed effort
    assert "ladder-invalid" in codes(wf(session_options=SessionOptions(effort="high")))
    assert codes(wf(effort_ladder=(), effort="xhigh")) == set()  # `xhigh` joins the enum (SSN-B1 to SSN-B6)


def test_a_rung_the_executor_cannot_apply_is_refused_before_the_run(repo: Path) -> None:  # LAD-B14 row 1
    weak = dataclasses.replace(DECLARED["claude"], efforts=frozenset({"low", "medium", "high"}),
                               efforts_uncertain=frozenset())
    ex = standin("claude", steps=[OK], judges=[judge(MET2)])
    ex.caps = weak
    rep = preflight(wf(), registry(ex))
    assert [f.code for f in rep.refusals] == ["effort-rung-unsupported"]
    assert "work" in rep.refusals[0].message and "xhigh" in rep.refusals[0].message
    out = start(wf(), "L-9", {"request": "x"}, repo, registry(ex), RunSettings(sleep=lambda s: None))
    assert out.exit_code is ExitCode.USAGE and ex.calls == []


def test_an_unprobed_rung_is_warned_and_runs() -> None:  # LAD-B14 row 2, pending probe P-LAD-1
    ex = standin("claude", steps=[OK], judges=[judge(MET2)])
    rep = preflight(wf(), registry(ex))
    assert rep.refusals == [] and "effort-rung-uncertain" in [f.code for f in rep.authoring_warnings]
    sure = preflight(wf(effort_ladder=("low", "medium", "high")), registry(ex))
    assert "effort-rung-uncertain" not in [f.code for f in sure.authoring_warnings]
