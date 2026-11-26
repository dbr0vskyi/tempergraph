"""What the attempt cap counts: an attempt counts only when its unit, item or slot has attempted before in the
thread (CMP-B19; CMP-AC11 to CMP-AC13, RST-B20)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from tempergraph.api import CheckResult, Gate, Judge, Map, Routing, Step, Value, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import CheckFinding, WorkflowSpec
from tempergraph.executors.standins import answer, standin
from tempergraph.run.runner import RunSettings, start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.subworkflows import home_dir, register_workflow
from .fixtures.workflows import crit, named, two_step
from .test_council_run import UNIT, Crew, council_wf
from .test_map import THREE, item_ok, planner
from .test_run import DRAFT, REVIEW, judge, registry, verdict_block
from .test_subworkflow_run import WORK, parent

NO_SLEEP = RunSettings(sleep=lambda s: None)
UNMET = verdict_block("UNMET")


def log(repo: Path, workflow: str = "demo", task: str = "T-1") -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), workflow, task) / "run.jsonl"
    return [json.loads(ln) for ln in p.read_text().splitlines()]


def forward_only() -> WorkflowSpec:
    """One step, a sequential map of twenty items, then three more steps."""
    def step(cid: str) -> Step:
        return Step(prompt="Do {request}", tools=["read", "write"],
                    gate=Gate(judge=Judge(stance="V."), criteria=[crit(cid)]))

    item = Step(prompt="Do {item_id}: {item}", tools=["read", "write"], produces={"note": Value()},
                gate=Gate(judge=Judge(stance="V."), criteria=[crit("c-item")]))
    units: dict[str, Any] = {
        "plan": Step(prompt="Plan {request}", tools=["read", "write"], produces={"phases": "file"},
                     gate=Gate(judge=Judge(stance="V."), criteria=[crit("c-plan")])),
        "phase": Map(items_from=("plan", "phases"), step=item),
        "s1": step("c-1"), "s2": step("c-2"), "s3": step("c-3"),
    }
    return named(Workflow(order=["plan", "phase", "s1", "s2", "s3"], units=units, issue_repository="acme/x",
                          routing=Routing(description="Plan, map, finish")))


def run_forward(repo: Path, **kw: Any) -> Any:
    items = [{"id": f"i{n}", "text": f"item {n}"} for n in range(20)]
    steps = [planner(items), *[item_ok() for _ in items], *[answer("Done.", session_id=f"s{n}") for n in range(3)]]
    ex = standin("claude", steps=steps, judges=[judge() for _ in range(24)])
    return start(forward_only(), "T-1", {"request": "x"}, repo, registry(ex), dataclasses.replace(NO_SLEEP, **kw))


def test_a_run_that_only_moves_forward_is_never_stopped_by_the_cap(repo: Path) -> None:  # CMP-AC11 (CMP-B19)
    out = run_forward(repo)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert [r for r in log(repo) if r["kind"] == "run_exit" and r.get("reason") == "attempt_cap"] == []


def test_the_setting_counts_as_the_spec_says(repo: Path) -> None:  # CMP-AC11 (RST-B20)
    out = run_forward(repo, flags={"run.attempt_cap": 1})
    assert out.exit_code is ExitCode.FINISHED, out.message  # no attempt repeated, so none counted


def stops_at_cap(repo: Path, out: Any) -> list[dict[str, Any]]:
    assert out.exit_code is ExitCode.STOPPED and out.reason == "attempt_cap", out.message
    recs = log(repo)
    assert not [r for r in recs if r["kind"] == "engine_error"]
    (exit_rec,) = [r for r in recs if r["kind"] == "run_exit"]
    assert exit_rec["reason"] == "attempt_cap"
    return [r for r in recs if r["kind"] == "attempt_start" and r["session_kind"] in ("step", "retry")]


def test_two_units_that_send_each_other_back_stop_at_the_cap(repo: Path) -> None:  # CMP-AC12 (CMP-B5, CMP-B19)
    back = verdict_block("UNMET", defect_in="notes")
    spec = two_step()
    units = dict(spec.units)
    units["review"] = dataclasses.replace(units["review"], gate=dataclasses.replace(units["review"].gate, loop_budget=10))
    spec = dataclasses.replace(spec, units=units)
    ex = standin("claude", steps=[DRAFT, REVIEW] * 6, judges=[judge(), judge(back)] * 6)
    out = start(spec, "T-1", {"request": "x"}, repo, registry(ex), dataclasses.replace(NO_SLEEP, flags={"run.attempt_cap": 2}))
    started = stops_at_cap(repo, out)
    assert len(started) == 2 + 2  # each unit's first attempt counts nothing; the next two visits count the cap


def test_a_step_that_fails_its_gate_stops_at_the_cap_under_a_larger_retry_budget(repo: Path) -> None:  # CMP-AC12 (CMP-B5, CMP-B19)
    spec = two_step()
    units = dict(spec.units)
    units["draft"] = dataclasses.replace(units["draft"], gate=dataclasses.replace(units["draft"].gate, retry_budget=10))
    spec = dataclasses.replace(spec, units=units)
    ex = standin("claude", steps=[DRAFT] * 8, judges=[judge(UNMET)] * 8)
    out = start(spec, "T-1", {"request": "x"}, repo, registry(ex), dataclasses.replace(NO_SLEEP, flags={"run.attempt_cap": 2}))
    started = stops_at_cap(repo, out)
    assert [r["unit"] for r in started] == ["draft"] * 3  # the first attempt, then two counted retries


KEYS = ("attempts_counted", "trips_back", "repeated")


def _cap_catalog(spec: WorkflowSpec) -> Any:
    from tempergraph.catalog import Catalog

    return Catalog(specs={"demo": spec})


def _loop_spec() -> WorkflowSpec:
    spec = two_step()
    units = dict(spec.units)
    units["review"] = dataclasses.replace(units["review"], gate=dataclasses.replace(units["review"].gate, loop_budget=10))
    return dataclasses.replace(spec, units=units)


def _retry_spec() -> WorkflowSpec:
    spec = two_step()
    units = dict(spec.units)
    units["draft"] = dataclasses.replace(units["draft"], gate=dataclasses.replace(units["draft"].gate, retry_budget=10))
    return dataclasses.replace(spec, units=units)


def _expected(records: list[dict[str, Any]]) -> dict[str, Any]:
    """What the run log of one invocation shows: its counted attempts, its trips back and each repeated unit."""
    starts: dict[str, int] = {}
    for r in records:
        if r["kind"] == "attempt_start" and r["session_kind"] in ("step", "retry"):
            starts[r["unit"]] = starts.get(r["unit"], 0) + 1
    trips: dict[str, int] = {}
    for r in records:
        if r["kind"] == "gate" and r["token"] == "BACK":
            unit = r["route_target"].split(".")[0]  # the node `draft.step` enters the unit `draft`
            trips[unit] = trips.get(unit, 0) + 1
    return {"starts": starts, "trips": trips}


def _check_report(doc: dict[str, Any], records: list[dict[str, Any]], counted: int) -> None:
    exp = _expected(records)
    assert doc["attempts_counted"] == counted
    assert doc["trips_back"] == sum(exp["trips"].values())
    for entry in doc["repeated"]:
        assert entry["item"] is None
        assert entry["attempts"] == exp["starts"][entry["unit"]]
        assert entry["trips_back"] == exp["trips"].get(entry["unit"], 0)
    assert doc["repeated"], doc


def test_the_exit_at_the_cap_says_what_repeated(repo: Path) -> None:  # CMP-AC14 (CMP-B20)
    from .test_cli import cli

    back = verdict_block("UNMET", defect_in="notes")
    ex = standin("claude", steps=[DRAFT, REVIEW] * 6, judges=[judge(), judge(back)] * 6)
    code, doc, _ = cli(repo, ex, "run", "demo", "x", "--task-id", "L-1", "--set", "run.attempt_cap=2", "--json",
                       catalog=_cap_catalog(_loop_spec()))
    assert code == 4 and doc["reason"] == "attempt_cap", doc
    (rec,) = [r for r in log(repo, task="L-1") if r["kind"] == "run_exit"]
    assert {k: rec[k] for k in KEYS} == {k: doc["payload"][k] for k in KEYS}
    _check_report(rec, log(repo, task="L-1"), 2)
    assert rec["trips_back"] >= 1

    code, doc, _ = cli(repo, standin("claude", steps=[DRAFT] * 8, judges=[judge(UNMET)] * 8), "run", "demo", "x",
                       "--task-id", "R-1", "--set", "run.attempt_cap=2", "--json", catalog=_cap_catalog(_retry_spec()))
    assert code == 4 and doc["reason"] == "attempt_cap", doc
    recs = log(repo, task="R-1")
    (rec,) = [r for r in recs if r["kind"] == "run_exit"]
    assert {k: rec[k] for k in KEYS} == {k: doc["payload"][k] for k in KEYS}
    _check_report(rec, recs, 2)
    assert rec["trips_back"] == 0 and rec["repeated"] == [{"unit": "draft", "item": None, "attempts": 3,
                                                          "trips_back": 0}]


def test_a_resumed_invocation_counts_from_zero_and_reports_it(repo: Path) -> None:  # CMP-AC14 (CMP-B20)
    from .test_cli import cli

    cat = _cap_catalog(_retry_spec())
    ex = standin("claude", steps=[DRAFT] * 12, judges=[judge(UNMET)] * 12)
    code, _, _ = cli(repo, ex, "run", "demo", "x", "--task-id", "R-2", "--set", "run.attempt_cap=2", "--json", catalog=cat)
    assert code == 4
    first = len([r for r in log(repo, task="R-2") if r["kind"] == "run_exit"])
    code, doc, _ = cli(repo, ex, "resume", "demo", "R-2", "--set", "run.attempt_cap=2", "--json", catalog=cat)
    assert code == 4 and doc["reason"] == "attempt_cap", doc
    recs = log(repo, task="R-2")
    exits = [r for r in recs if r["kind"] == "run_exit"]
    assert len(exits) == first + 1
    assert {k: exits[-1][k] for k in KEYS} == {k: doc["payload"][k] for k in KEYS}
    assert exits[-1]["attempts_counted"] == 2  # not 4: the count starts at 0 in the new invocation
    cut = max(i for i, r in enumerate(recs) if r["kind"] == "run_exit")
    prev = max(i for i, r in enumerate(recs[:cut]) if r["kind"] == "run_exit")
    _check_report(exits[-1], recs[prev + 1:cut], 2)


def test_an_exit_with_another_reason_carries_none_of_the_keys(repo: Path) -> None:  # CMP-AC14 (CMP-B20)
    from .test_cli import cli

    code, doc, _ = cli(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()]), "run", "demo", "x",
                       "--task-id", "F-1", "--json", catalog=_cap_catalog(two_step()))
    assert code == 0
    (rec,) = [r for r in log(repo, task="F-1") if r["kind"] == "run_exit"]
    assert not [k for k in KEYS if k in rec] and not [k for k in KEYS if k in (doc.get("payload") or {})]


def fails_once(ctx: Any) -> CheckResult:
    if ctx.attempt == 1:
        return CheckResult(result="FAIL", evidence="no", findings=[CheckFinding(status="fail", criterion="c-s",
                                                                               message="again")])
    return CheckResult(result="PASS", evidence="ok")


def with_after(spec: WorkflowSpec) -> WorkflowSpec:
    """The council unit, then one plain step, so a stop at the cap shows before the step."""
    after = Step(prompt="After", tools=["read"], gate=Gate(judge=Judge(stance="V."), criteria=[crit("c-after")]))
    return dataclasses.replace(spec, order=(UNIT, "after"), units={**spec.units, "after": after})


def run_council(repo: Path, judges: list[str], cap: int) -> Any:
    ex = Crew(judges=judges)
    return start(with_after(council_wf()), "T-1", {"request": "the jobs"}, repo, registry(ex),
                 dataclasses.replace(NO_SLEEP, flags={"run.attempt_cap": cap}))


def test_a_council_counts_nothing_at_its_first_attempt(repo: Path) -> None:  # CMP-AC13 (CMP-B19)
    assert run_council(repo, [], 1).exit_code is ExitCode.FINISHED  # three members, one attempt: nothing counted


def test_a_council_retry_counts_exactly_one_attempt(tmp_path: Path, repo: Path) -> None:  # CMP-AC13 (CMP-B19)
    out = start(with_after(council_wf()), "T-2", {"request": "the jobs"}, repo, registry(Crew(judges=[UNMET])),
                dataclasses.replace(NO_SLEEP, flags={"run.attempt_cap": 1}))
    assert out.exit_code is ExitCode.STOPPED and out.reason == "attempt_cap", out.message  # one counted, at the cap
    out = start(with_after(council_wf()), "T-3", {"request": "the jobs"}, repo, registry(Crew(judges=[UNMET])),
                dataclasses.replace(NO_SLEEP, flags={"run.attempt_cap": 2}))
    assert out.exit_code is ExitCode.FINISHED, out.message  # exactly one, not one for each member session


def test_a_sub_workflow_with_several_child_units_counts_nothing_at_its_first_attempt(
        tmp_path: Path, repo: Path) -> None:  # CMP-AC13 (CMP-B19)
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"])
    ex = standin("claude", steps=[DRAFT, WORK, REVIEW], judges=[judge() for _ in range(4)])
    out = start(parent(), "T-1", {"request": "x"}, repo, registry(ex),
                dataclasses.replace(NO_SLEEP, flags={"run.attempt_cap": 1}))
    assert out.exit_code is ExitCode.FINISHED, (out.message, out.payload)


def test_a_sub_workflow_retry_counts_exactly_one_attempt(tmp_path: Path, repo: Path) -> None:  # CMP-AC13 (CMP-B19)
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"])

    spec = parent(gate=Gate(check=fails_once, retry_budget=2))
    steps = [DRAFT, WORK, WORK, REVIEW]
    out = start(spec, "T-1", {"request": "x"}, repo, registry(standin("claude", steps=steps, judges=[judge()] * 8)),
                dataclasses.replace(NO_SLEEP, flags={"run.attempt_cap": 1}))
    assert out.exit_code is ExitCode.STOPPED and out.reason == "attempt_cap", (out.message, out.payload)
    out = start(spec, "T-2", {"request": "x"}, repo, registry(standin("claude", steps=steps, judges=[judge()] * 8)),
                dataclasses.replace(NO_SLEEP, flags={"run.attempt_cap": 2}))
    assert out.reason != "attempt_cap", (out.message, out.payload)  # the one counted attempt is under a cap of two


def test_a_map_item_retried_once_counts_one_attempt(repo: Path) -> None:  # CMP-AC13 (CMP-B19)
    from .test_map import mapped, p2_fails_once

    def run(task: str, cap: int) -> Any:
        ex = standin("claude", steps=[planner(THREE), item_ok(), item_ok(), item_ok(), item_ok(), answer("Joined.")],
                     judges=[judge() for _ in range(6)])
        return start(mapped(check=p2_fails_once), task, {"request": "x"}, repo, registry(ex),
                     dataclasses.replace(NO_SLEEP, flags={"run.attempt_cap": cap}))

    out = run("M-1", 1)
    assert out.exit_code is ExitCode.STOPPED and out.reason == "attempt_cap", out.message
    assert run("M-2", 2).exit_code is ExitCode.FINISHED
