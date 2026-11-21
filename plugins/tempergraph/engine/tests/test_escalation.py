"""One-step model escalation: E1 to E9, stages, the offer and `resume --escalate` (LAD-AC-3, AC-5, LAD-B4 to B7)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import Escalation, Gate, Judge, Rearm, Routing, Step, Switch, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import WorkflowSpec
from tempergraph.executors.capabilities import DECLARED
from tempergraph.executors.standins import answer, standin
from tempergraph.model.validate import validate
from tempergraph.observe import report as rep
from tempergraph.run import ladder
from tempergraph.run.runner import RunSettings, resume, start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.workflows import crit, named
from .test_run import judge, registry, verdict_block

C2 = verdict_block("UNMET", "MET")  # blocker c2
C5 = verdict_block("MET", "UNMET")  # blocker c5
MET = verdict_block("MET", "MET")
OK = answer("Done.", session_id="s")
AUTO = Escalation(to="large", stages={"local-stable": "auto"})
PERSON = {"kind": "person"}
AGENT = {"kind": "agent", "host": "claude-code"}


def accepted(unit: str) -> str:
    return "accepted"


def met(unit: str) -> bool:
    return True


def unmet(unit: str) -> bool:
    return False


def wf(*, escalation: Any = AUTO, judge_model: str = "large", retry_budget: int = 3, mode: str = "stable",
       cap: float | None = None, **step: Any) -> WorkflowSpec:
    step.setdefault("effort_ladder", ("high", "xhigh"))
    step.setdefault("model", "medium")
    units = {"work": Step(prompt="Do {request}", tools=["read", "write"], escalation=escalation,
                          gate=Gate(judge=Judge(stance="V.", model=judge_model), criteria=[crit("c2"), crit("c5")],
                                    retry_budget=retry_budget), **step)}
    return named(Workflow(order=["work"], units=units, issue_repository="acme/x", improvement_mode=mode,
                          run_cost_cap_usd=cap, routing=Routing(description="Do a task")))


def go(repo: Path, spec: WorkflowSpec, verdicts: list[str], task: str = "E-1", record: Any = met,
       judge_state: Any = accepted, **kw: Any) -> Any:
    ex = standin("claude", steps=[OK for _ in verdicts], judges=[judge(v) for v in verdicts])
    out = start(spec, task, {"request": "x"}, repo, registry(ex),
                RunSettings(sleep=lambda s: None, judge_state=judge_state, escalation_record=record, **kw))
    return out, ex


def recs(repo: Path, kind: str, task: str = "E-1") -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", task) / "run.jsonl"
    return [r for r in map(json.loads, p.read_text().splitlines()) if r["kind"] == kind]


def ran(ex: Any) -> list[tuple[str, str | None]]:
    return [(c.request.alias, c.request.options.effort) for c in ex.calls if c.kind == "step"]


def held(repo: Path, task: str = "E-1") -> list[Any]:
    return [(d.get("escalation") or {}).get("held_by") for d in recs(repo, "ladder_decision", task)]


def test_escalation_on_a_repeated_blocker(repo: Path) -> None:  # LAD-B4
    out, ex = go(repo, wf(), [C2, C2, C2, C2])
    assert ran(ex) == [("medium", "high"), ("medium", "xhigh"), ("medium", "xhigh"), ("large", "xhigh")]
    assert held(repo) == ["E2", "E2", None]  # one attempt, then two, below the top rung on both of the last two
    last = recs(repo, "ladder_decision")[-1]["escalation"]
    assert (last["take"], last["to"], last["criteria"]) == ("auto", "large", ["c2"])
    starts = [r["ladder"] for r in recs(repo, "attempt_start") if r["session_kind"] in ("step", "retry")]
    assert [s["source"] for s in starts][-1] == "escalation:+1" and starts[-1]["alias"] == "large"
    # a failed escalated attempt ends the escalation: the gate's own policy at once
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget"
    assert out.payload["reason"] == "escalation"
    assert [c.request.alias for c in ex.calls if c.kind == "judge"] == ["large"] * 4  # LAD-AC-4: judges stay fixed


def test_an_escalated_attempt_that_passes_ends_the_visit(repo: Path) -> None:  # LAD §2.4
    out, ex = go(repo, wf(), [C2, C2, C2, MET])
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert ran(ex)[-1] == ("large", "xhigh")
    rows = [json.loads(x) for x in (state_root_path(repo) / "ledger.jsonl").read_text().splitlines()]
    (row,) = [r for r in rows if r.get("kind") == "escalation"]
    assert (row["unit"], row["passed"], row["judge_state"], row["to"]) == ("work", True, "accepted", "large")


def test_a_fixed_effort_escalates_after_two_attempts(repo: Path) -> None:  # E2: "or the step has a fixed effort"
    out, ex = go(repo, wf(effort_ladder=(), effort="high"), [C2, C2, MET])
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert ran(ex) == [("medium", "high"), ("medium", "high"), ("large", "high")]


def test_different_blockers_do_not_escalate(repo: Path) -> None:  # LAD-B5
    out, ex = go(repo, wf(), [C2, C2, C5, MET])
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert [a for a, _ in ran(ex)] == ["medium"] * 4 and held(repo)[-1] == "E3"


def lone(repo: Path, spec: WorkflowSpec, **kw: Any) -> tuple[list[str], Any]:
    """The top-rung attempts of LAD-B4 with one thing changed: the aliases that ran and what held the step."""
    _, ex = go(repo, spec, [C2, C2, C2, MET], **kw)
    return [a for a, _ in ran(ex)], held(repo)[-1]


@pytest.mark.parametrize(("change", "why"), [
    ({"spec": {"escalation": Escalation(to="large", stages={"local-stable": "off"})}}, "E1"),
    ({"spec": {"judge_model": "medium"}}, "E4"),
    ({"judge_state": lambda u: "provisional", "spec": {"mode": "dev",
                                                       "escalation": Escalation(to="large", stages={"local-dev": "auto"})}},
     "E4"),  # a provisional judge moves the effort ladder in local-dev, never the model
])
def test_each_condition_alone_blocks_the_escalation(repo: Path, change: dict[str, Any], why: str) -> None:  # LAD-AC-3
    spec = wf(**change.pop("spec", {}))
    aliases, held_by = lone(repo, spec, **change)
    assert aliases == ["medium"] * 4 and held_by == why


def test_a_cost_cap_that_cannot_cover_the_attempt_blocks_the_escalation(repo: Path) -> None:  # E6
    big = answer("Done.", session_id="s", tokens=(10_000, 5_000))  # about $0.14 on the tier above
    ex = standin("claude", steps=[big] * 4, judges=[judge(C2), judge(C2), judge(C2), judge(MET)])
    start(wf(cap=0.1), "E-1", {"request": "x"}, repo, registry(ex),
          RunSettings(sleep=lambda s: None, judge_state=accepted, escalation_record=met))
    assert [a for a, _ in ran(ex)] == ["medium"] * 4 and held(repo)[-1] == "E6"


def test_an_unmeasured_estimate_blocks_the_escalation(repo: Path) -> None:  # LAD §4 row 3
    ex = standin("claude", steps=[dataclasses.replace(OK, usage=dataclasses.replace(OK.usage, input_tokens=None,
                                                                                  output_tokens=None))] * 4,
                 judges=[judge(C2), judge(C2), judge(C2), judge(MET)])
    start(wf(), "E-1", {"request": "x"}, repo, registry(ex),
          RunSettings(sleep=lambda s: None, judge_state=accepted, escalation_record=met))
    assert [a for a, _ in ran(ex)] == ["medium"] * 4 and held(repo)[-1] == "E6_unmeasured"


def test_no_retry_left_means_no_escalation(repo: Path) -> None:  # E5
    out, ex = go(repo, wf(retry_budget=2), [C2, C2, C2])
    assert out.exit_code is ExitCode.PAUSED and out.payload["reason"] == "retry_budget"
    assert [a for a, _ in ran(ex)] == ["medium"] * 3


def flaky(view: Any) -> str:
    return "direct"


def test_escalation_waits_for_a_re_arm(repo: Path) -> None:  # LAD-B7, E8
    step = wf().units["work"]
    plan = Step(prompt="Plan {request}", tools=["read"], model="medium",
                gate=Gate(judge=Judge(stance="V.", model="large"), criteria=[crit("c2"), crit("c5")]))
    units = {"size": Switch(predicate=flaky, arms={"direct": "work", "planned": "plan"}, default="planned",
                            rearm=[Rearm(from_arm="direct", to="planned", units=["work"], on=["budget_spent"])]),
             "plan": plan, "work": step}
    spec = named(Workflow(order=["size", "plan", "work"], units=units, issue_repository="acme/x",
                          improvement_mode="stable", routing=Routing(description="Do a task")))
    assert [f for f in validate(spec, DECLARED) if f.severity == "error"] == []
    out, ex = go(repo, spec, [C2, C2, C2, C2, MET, MET])
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert [a for a, _ in ran(ex)] == ["medium"] * 6  # four direct attempts, then the plan and the work again
    assert held(repo)[2] == "E8" and recs(repo, "route")[-1]["chosen_by"] == "rearm"


@pytest.mark.parametrize(("mode", "stages", "record"), [
    ("dev", {"local-dev": "auto"}, met),  # `auto` is read as `offer` in local-dev
    ("dev", {}, met),  # the default
    ("stable", {"local-stable": "auto"}, unmet),  # no met escalation record: `auto` behaves as `offer`
    ("stable", {"local-stable": "offer"}, met),
])
def test_an_offer_pauses_and_a_person_takes_it(repo: Path, mode: str, stages: dict[str, str], record: Any) -> None:
    spec = wf(mode=mode, escalation=Escalation(to="large", stages=stages))  # LAD-B6
    out, ex = go(repo, spec, [C2, C2, C2], record=record)
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget"
    assert out.payload["reason"] == "escalation_offer"
    offer = out.payload["escalation"]
    assert (offer["to"], offer["criteria"]) == ("large", ["c2"])
    assert offer["command"] == "tempergraph resume demo E-1 --escalate"
    assert [a for a, _ in ran(ex)] == ["medium"] * 3
    settings = RunSettings(sleep=lambda s: None, judge_state=accepted, escalation_record=record)
    # an agent's resume with --escalate and no relay evidence is refused (PRV)
    refused = resume(spec, "E-1", repo, registry(ex), settings=dataclasses.replace(settings, escalate=True,
                                                                                  caller=AGENT))
    assert refused.exit_code is ExitCode.USAGE and refused.reason == "escalate_needs_person"
    ex.steps, ex.judges = [OK], [judge(MET)]
    out = resume(spec, "E-1", repo, registry(ex), settings=dataclasses.replace(settings, escalate=True,
                                                                              caller=PERSON))
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert ran(ex)[-1] == ("large", "xhigh")
    last = [r for r in recs(repo, "attempt_start") if r["session_kind"] in ("step", "retry")][-1]["ladder"]
    assert (last["source"], last["taken_by"]) == ("escalation:+1", "person")


def test_a_resume_without_escalate_retries_on_the_base_tier(repo: Path) -> None:  # LAD §2.4
    spec = wf(mode="dev")
    out, ex = go(repo, spec, [C2, C2, C2])
    assert out.payload["reason"] == "escalation_offer"
    ex.steps, ex.judges = [OK], [judge(MET)]
    out = resume(spec, "E-1", repo, registry(ex), decision="retry",
                 settings=RunSettings(sleep=lambda s: None, judge_state=accepted))
    assert out.exit_code is ExitCode.FINISHED and ran(ex)[-1] == ("medium", "high")


def test_escalate_without_an_offer_is_refused(repo: Path) -> None:
    spec = wf(retry_budget=0)
    out, ex = go(repo, spec, [C2])
    assert out.exit_code is ExitCode.PAUSED
    got = resume(spec, "E-1", repo, registry(ex), settings=RunSettings(escalate=True, caller=PERSON))
    assert got.exit_code is ExitCode.USAGE and got.reason == "no_escalation_offered"


def codes(spec: WorkflowSpec) -> set[str]:
    return {f.code for f in validate(spec, DECLARED) if f.severity == "error"}


def test_validation() -> None:  # LAD §2.1, §2.6
    assert codes(wf()) == set()
    assert codes(wf(model="small", escalation=Escalation(to="medium"))) == set()
    for bad in ({"model": "small"}, {"model": "large"}, {"model": "claude:opus"}, {"model": "inherit"},
                {"model": None}, {"escalation": Escalation(to="medium")},
                {"escalation": Escalation(to="large", stages={"local-stable": "always"})},
                {"escalation": Escalation(to="large", stages={"prod": "auto"})},
                {"escalation": Escalation(to="large", effort="extreme")}):
        assert "escalation-invalid" in codes(wf(**bad)), bad
    # a pipeline never waits on an offer it could not make
    assert "escalation-invalid" in codes(wf(escalation=Escalation(to="large", stages={"pipeline": "offer"})))


@pytest.mark.parametrize(("rows", "want"), [
    ([], False), ([True] * 4, False), ([True] * 5, True), ([True] * 5 + [False] * 5, False),
    ([True] * 9 + [False], True),
])
def test_the_escalation_record(tmp_path: Path, rows: list[bool], want: bool) -> None:  # LAD §2.5, §2.7
    for passed in rows:
        ladder.record_escalation(tmp_path, workflow="demo", version="0.1.0", unit="work", thread="demo/x",
                                 passed=passed, judge_state="accepted", to="large")
    ladder.record_escalation(tmp_path, workflow="demo", version="0.1.0", unit="work", thread="demo/x", passed=True,
                             judge_state="provisional", to="large")  # not graded by an accepted judge: not counted
    ladder.record_escalation(tmp_path, workflow="demo", version="0.2.0", unit="work", thread="demo/x", passed=True,
                             judge_state="accepted", to="large")  # another version
    assert ladder.record_met(tmp_path, "demo", "0.1.0", "work") is want
    (tmp_path / "ledger.jsonl").write_text("{not json\n")  # LAD §4: an unreadable record is not met
    assert ladder.record_met(tmp_path, "demo", "0.1.0", "work") is False


def test_the_report_shows_climbed_attempts_apart(repo: Path) -> None:  # LAD-AC-5
    go(repo, wf(), [C2, C2, C2, MET])
    go(repo, wf(escalation=None, effort_ladder=(), effort="high"), [MET], task="E-2")
    doc = rep.report(state_root_path(repo), None)
    (row,) = [r for r in doc["ladder"] if r["version"] == "0.1.0"]
    assert row["rung0"]["sessions"] == 4  # the first attempt of E-1 and the one of E-2, each with its judge
    assert row["climbed"]["sessions"] == 6 and row["escalated_runs"] == ["demo/E-1"]
    assert row["first_pass"] == {"gates": 2, "passed": 1}  # the climbed attempts never count as a first pass
