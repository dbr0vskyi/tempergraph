"""Measured switches: shadow mode, arm overrides, re-arming and the operator's arm (SWM-AC-1 to AC-3, CMP-B7)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph import settings as rst
from tempergraph.api import Gate, Judge, Rearm, Routing, Step, Switch, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import RunOptions, SessionResult, WorkflowSpec
from tempergraph.executors.capabilities import DECLARED
from tempergraph.executors.standins import answer, standin
from tempergraph.model.validate import validate
from tempergraph.run.runner import RunSettings, start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.workflows import crit, named
from .test_run import judge, registry, verdict_block

NO_SLEEP = RunSettings(sleep=lambda s: None)
FAIL = verdict_block("UNMET")
REARM = Rearm(from_arm="single", to="per_phase", units=["code"], on=["budget_spent", "timeout"])


def small_plan(view: Any) -> Any:
    return "single", {"phases": 2, "rows": 18}


def big_plan(view: Any) -> Any:
    return "per_phase", {"phases": 9, "rows": 80}


def boom(view: Any) -> str:
    raise RuntimeError("no")


def chatty(view: Any) -> Any:
    return "single", {f"s{i}": "x" * 100 for i in range(14)}


def wf(predicate: Any = small_plan, mode: str = "route", **sw: Any) -> WorkflowSpec:
    fields: dict[str, Any] = {"arm_overrides": {"single": {"code": {"timeout_s": 5400}}}, "rearm": [REARM]}
    fields.update(sw)
    units = {
        "triage": Step(prompt="Triage {request}", tools=["read"],
                       gate=Gate(judge=Judge(stance="V."), criteria=[crit("c1")])),
        "code_mode": Switch(predicate=predicate, arms={"single": "code", "per_phase": "phases"}, default="per_phase",
                            mode=mode, **fields),
        "phases": Step(prompt="Split", tools=["read"], gate=Gate(judge=Judge(stance="V."), criteria=[crit("c2")])),
        "code": Step(prompt="Code", tools=["read"], timeout_s=1800,
                     gate=Gate(judge=Judge(stance="V."), criteria=[crit("c3")])),
    }
    return named(Workflow(order=["triage", "code_mode", "phases", "code"], units=units, issue_repository="acme/x",
                          routing=Routing(description="Pick a code mode")))


def ok(sid: str) -> SessionResult:
    return answer("Done.", session_id=sid)


def go(repo: Path, spec: WorkflowSpec, steps: int, judges: list[Any], task: str = "S-1", **kw: Any) -> Any:
    ex = standin("claude", steps=[ok(f"s{i}") for i in range(steps)] if isinstance(steps, int) else steps,
                 judges=judges)
    out = start(spec, task, {"request": "x"}, repo, registry(ex), dataclasses.replace(NO_SLEEP, **kw))
    return out, ex


def recs(repo: Path, kind: str, task: str = "S-1") -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", task) / "run.jsonl"
    return [r for r in map(json.loads, p.read_text().splitlines()) if r["kind"] == kind]


def entered(repo: Path, task: str = "S-1") -> list[str]:
    return [r["unit"] for r in recs(repo, "unit_entered", task)]


def code_requests(ex: Any) -> list[Any]:
    return [c.request for c in ex.calls if c.kind == "step" and c.request.session_key.startswith("code")]


def test_shadow_records_the_pick_and_takes_the_default(repo: Path) -> None:  # SWM-B1, SWM-AC-2
    out, _ = go(repo, wf(mode="shadow"), 3, [judge(), judge(), judge()])
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert entered(repo) == ["triage", "phases", "code"]
    (r,) = recs(repo, "route")
    assert (r["arm"], r["chosen_by"], r["shadow"], r["would_choose"]) == ("per_phase", "default", True, "single")
    assert r["signals"] == {"phases": 2, "rows": 18}


@pytest.mark.parametrize("predicate", [small_plan, big_plan, boom, chatty])
def test_shadow_always_takes_the_default(repo: Path, predicate: Any) -> None:  # SWM-AC-2, SWM §4
    out, _ = go(repo, wf(predicate, mode="shadow"), 3, [judge(), judge(), judge()])
    assert out.exit_code is ExitCode.FINISHED and entered(repo) == ["triage", "phases", "code"]
    (r,) = recs(repo, "route")
    assert r["arm"] == "per_phase" and r["shadow"] is True
    if predicate is boom:
        assert r["fault"] == "RuntimeError" and r["would_choose"] is None
    if predicate is chatty:  # signals over their limits are clipped and counted
        assert len(r["signals"]) == 10 and all(len(v) == 60 for v in r["signals"].values())
        assert r["signals_clipped"] == 14


def test_an_arm_override_applies_only_while_its_arm_is_in_force(repo: Path) -> None:  # SWM-B2, SWM-AC-3
    out, ex = go(repo, wf(), 2, [judge(), judge()])
    assert out.exit_code is ExitCode.FINISHED and entered(repo) == ["triage", "code"]
    assert code_requests(ex)[0].timeout_s == 5400
    starts = [r for r in recs(repo, "attempt_start") if r["session_key"].startswith("code") and r["session_kind"] == "step"]
    assert starts[0]["sources"] == {"timeout_s": "arm:code_mode.single"}
    out, ex = go(repo, wf(big_plan), 3, [judge(), judge(), judge()], task="S-2")
    assert code_requests(ex)[0].timeout_s == 1800
    assert all("sources" not in r for r in recs(repo, "attempt_start", "S-2"))


def test_an_operator_value_beats_an_arm_override(repo: Path) -> None:  # SWM-B2
    out, ex = go(repo, wf(), 2, [judge(), judge()], flags={"code.timeout_s": 7200})
    assert out.exit_code is ExitCode.FINISHED and code_requests(ex)[0].timeout_s == 7200


def test_an_arm_override_sets_model_idle_and_effort(repo: Path) -> None:  # SWM §2.3
    spec = wf(arm_overrides={"single": {"code": {"model": "large", "idle_s": 900, "effort": "high"}}})
    out, ex = go(repo, spec, 2, [judge(), judge()])
    req = code_requests(ex)[0]
    assert (req.alias, req.idle_s, req.options.effort) == ("large", 900, "high")
    rows = [r for r in recs(repo, "attempt_start") if r["session_key"].startswith("code") and r["session_kind"] == "step"]
    assert set(rows[0]["sources"]) == {"model", "idle_s", "effort"}


def test_a_spent_budget_re_arms_once(repo: Path) -> None:  # SWM-B3, rows 1 and 3 of its table
    # triage, code x3 (budget of 2 retries spent), phases, code x3 (spent again): the gate's own policy
    out, _ = go(repo, wf(), 8, [judge(), judge(FAIL), judge(FAIL), judge(FAIL), judge(), judge(FAIL), judge(FAIL),
                              judge(FAIL)])
    assert entered(repo) == ["triage", "code", "phases", "code"]
    first, second = recs(repo, "route")
    assert (first["arm"], first["chosen_by"]) == ("single", "predicate")
    assert (second["unit"], second["arm"], second["chosen_by"], second["target"]) == (
        "code_mode", "per_phase", "rearm", "phases")
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget"
    # the re-armed code step no longer takes the single arm's override
    starts = [r for r in recs(repo, "attempt_start") if r["session_key"].startswith("code") and r["session_kind"] != "judge"]
    assert [r["timeout_s"] for r in starts] == [5400, 5400, 5400, 1800, 1800, 1800]


def test_a_step_timeout_re_arms(repo: Path) -> None:  # SWM-B3, row 2
    slow = SessionResult(ok=False, timed_out=True, session_id="slow")
    out, _ = go(repo, wf(), [ok("t"), slow, ok("p"), ok("c")], [judge(), judge(), judge()])
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert entered(repo) == ["triage", "code", "phases", "code"]
    assert recs(repo, "route")[-1]["chosen_by"] == "rearm"


def test_the_safer_arm_never_re_arms(repo: Path) -> None:  # SWM-B3, row 4
    out, _ = go(repo, wf(big_plan), 5, [judge(), judge(), judge(FAIL), judge(FAIL), judge(FAIL)])
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget"
    assert [r["chosen_by"] for r in recs(repo, "route")] == ["predicate"]


def test_an_operator_picks_the_arm(repo: Path) -> None:  # CMP-B7
    out, _ = go(repo, wf(big_plan), 2, [judge(), judge()], flags={"code_mode.arm": "single"})
    assert out.exit_code is ExitCode.FINISHED and entered(repo) == ["triage", "code"]
    (r,) = recs(repo, "route")
    assert (r["arm"], r["chosen_by"], r["would_choose"]) == ("single", "operator", "per_phase")
    out, _ = go(repo, wf(mode="shadow"), 2, [judge(), judge()], task="S-2", flags={"code_mode.arm": "single"})
    assert entered(repo, "S-2") == ["triage", "code"]  # the operator's arm wins in shadow mode too
    _, findings = rst.options_snapshot(wf(), {"code_mode.arm": "nowhere"}, (), rst.ConfigFiles())
    assert [f.code for f in findings] == ["setting_value"]
    _, findings = rst.options_snapshot(wf(), {"code.arm": "single"}, (), rst.ConfigFiles())
    assert [f.code for f in findings] == ["setting_not_for_kind"]


def test_resolution_marks_what_an_operator_set() -> None:
    spec = wf()
    opts, _ = rst.options_snapshot(spec, {"code.timeout_s": 7200}, (), rst.ConfigFiles())
    eff = rst.effective_spec(spec, rst.resolve(spec, opts))
    assert eff.units["code"].extra["operator_set"] == ("timeout_s",)
    eff = rst.effective_spec(spec, rst.resolve(spec, RunOptions()))
    assert "operator_set" not in eff.units["code"].extra


@pytest.mark.parametrize(("fields", "code"), [
    ({"arm_overrides": {"nowhere": {"code": {"timeout_s": 60}}}}, "switch-arm-unknown"),
    ({"arm_overrides": {"single": {"triage": {"timeout_s": 60}}}}, "switch-override-unreachable"),
    ({"arm_overrides": {"single": {"code": {"timeout_s": 0}}}}, "switch-override-invalid"),
    ({"arm_overrides": {"single": {"code": {"model": "huge"}}}}, "alias-unbound"),
    ({"arm_overrides": {"single": {"code": {"retry_budget": 9}}}}, "switch-override-invalid"),
    ({"arm_overrides": {"single": {"code": {"effort": "extreme"}}}}, "switch-override-invalid"),
    ({"rearm": [Rearm(from_arm="per_phase", to="single", units=["phases"], on=["budget_spent"])]},
     "switch-rearm-invalid"),  # the entry of `single` (code) comes after `phases`
    ({"rearm": [Rearm(from_arm="single", to="nowhere", units=["code"], on=["budget_spent"])]}, "switch-arm-unknown"),
    ({"rearm": [Rearm(from_arm="single", to="per_phase", units=["code"], on=["verdict"])]}, "switch-rearm-invalid"),
    ({"mode": "dry"}, "switch-invalid"),
])
def test_validation(fields: dict[str, Any], code: str) -> None:  # SWM §4
    base: dict[str, Any] = {"arm_overrides": {}, "rearm": []}
    base.update(fields)
    mode = base.pop("mode", "route")
    findings = validate(wf(mode=mode, **base), {"claude": DECLARED["claude"]})
    assert code in [f.code for f in findings if f.severity == "error"], findings


def test_the_fixture_is_valid_and_ladder_fields_are_accepted() -> None:  # R2-T1.1 goal
    spec = wf(arm_overrides={"single": {"code": {"effort_ladder": ["medium", "high"], "escalation": "off"}}})
    assert not [f for f in validate(spec, {"claude": DECLARED["claude"]}) if f.severity == "error"]
    assert not [f for f in validate(wf(), {"claude": DECLARED["claude"]}) if f.severity == "error"]
