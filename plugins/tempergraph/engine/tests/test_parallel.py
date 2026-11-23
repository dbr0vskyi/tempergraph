"""Parallel branches and their engine-owned join (CMP-B10 to CMP-B16, CMP-B4, HUM-B3, WSP-B11, WSP-B12)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from tempergraph.api import Gate, Judge, Parallel, Routing, Step, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionRequest, SessionResult
from tempergraph.durability.status import row
from tempergraph.executors.standins import answer, standin
from tempergraph.model.validate import errors, validate
from tempergraph.run.runner import RunSettings, resume, start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.workflows import crit, named
from .test_run import MET, registry, verdict_block

NO_SLEEP = RunSettings(sleep=lambda s: None)
CAPS = {"claude": standin("claude").capabilities()}
FAIL = verdict_block("UNMET")


def step(prompt: str, **gate: Any) -> Any:
    return Step(prompt=prompt, tools=["read"], gate=Gate(judge=Judge(stance="V."), criteria=[crit("c1")], **gate))


def wf(**sec_gate: Any) -> Any:
    units = {"plan": step("Plan {request}"), "security": step("Security review of {request}", **sec_gate),
             "perf": Step(prompt="Performance review of {request}", tools=["read"], produces={"perf_notes": "file"},
                          gate=Gate(judge=Judge(stance="V."), criteria=[crit("c1")])), "reviews": Parallel(branches=["security", "perf"]),
             "report": step("Report on {request}")}
    return named(Workflow(order=["plan", "security", "perf", "reviews", "report"], units=units,
                          issue_repository="acme/x", routing=Routing(description="Plan, review twice, report")))


class ByUnit:
    """A stand-in that answers by unit, since branches of one block run in any order."""

    def __init__(self, judges: dict[str, list[str]] | None = None, write: str | None = None) -> None:
        self.inner = standin("claude")
        self.name = self.inner.name
        self.judges = {k: list(v) for k, v in (judges or {}).items()}
        self.write = write
        self.calls: list[tuple[str, str]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        unit = req.session_key.split(".")[0]
        self.calls.append(("step", unit))
        if self.write == unit:
            (Path(req.workdir) / "leak.txt").write_text("a branch wrote this\n")
        (Path(req.workdir) / ".git" / "perf.md").write_text("notes\n")
        return answer("Done.\nARTIFACT perf_notes: .git/perf.md" if unit == "perf" else "Done.", session_id=f"s-{unit}")

    def run_judge(self, req: SessionRequest, views: Any, sink: Any) -> SessionResult:
        unit = req.session_key.split(".")[0]
        self.calls.append(("judge", unit))
        queue = self.judges.get(unit) or []
        return answer(queue.pop(0) if queue else MET, tools=("Read",), session_id=f"j-{unit}")


def recs(repo: Path, kind: str, task: str = "P-1") -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", task) / "run.jsonl"
    return [r for r in map(json.loads, p.read_text().splitlines()) if r["kind"] == kind]


def go(repo: Path, spec: Any, ex: Any, task: str = "P-1") -> Any:
    return start(spec, task, {"request": "x"}, repo, registry(ex), NO_SLEEP)


def steps(ex: ByUnit) -> list[str]:
    return [u for k, u in ex.calls if k == "step"]


def test_both_branches_run_and_the_join_fires_once(repo: Path) -> None:
    ex = ByUnit()
    out = go(repo, wf(), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    got = steps(ex)
    assert got[0] == "plan" and sorted(got[1:3]) == ["perf", "security"] and got[3:] == ["report"]
    entered = [r["unit"] for r in recs(repo, "unit_entered")]
    assert entered.count("reviews") == 1 and entered.index("reviews") > max(entered.index("security"),
                                                                          entered.index("perf"))
    seqs = [r["seq"] for r in map(json.loads, (run_dir(state_root_path(repo), "demo", "P-1") / "run.jsonl")
                                  .read_text().splitlines()) if "seq" in r]
    assert len(seqs) == len(set(seqs))  # two branches write one log
    (exit_rec,) = recs(repo, "run_exit")
    assert exit_rec["cost"]["counters"]["sessions"] == 8  # four steps and four judges, none lost at the fork


def test_the_join_waits_for_a_retrying_branch(repo: Path) -> None:  # CMP-B4
    ex = ByUnit(judges={"perf": [FAIL, MET]})
    out = go(repo, wf(), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    got = steps(ex)
    assert got.count("perf") == 2 and got.count("security") == 1 and got[-1] == "report"
    assert got.index("report") > max(i for i, u in enumerate(got) if u == "perf")
    assert [r["unit"] for r in recs(repo, "unit_entered")].count("reviews") == 1


def test_a_branch_that_stops_stops_the_block(repo: Path) -> None:  # CMP-B4
    ex = ByUnit(judges={"security": [FAIL]})
    out = go(repo, wf(retry_budget=0, on_budget_spent="stop"), ex)
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA and out.reason == "budget", out.message
    assert "report" not in steps(ex) and "reviews" not in [r["unit"] for r in recs(repo, "unit_entered")]


def test_a_branch_that_changes_the_workspace_fails(repo: Path) -> None:  # WSP-B11, WSP-B12
    ex = ByUnit(write="security")
    out = go(repo, wf(retry_budget=0, on_budget_spent="stop"), ex)
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA, out.message
    stopped = [g for g in recs(repo, "gate") if g["unit"] == "security"][-1]
    assert "report" not in steps(ex) and stopped["token"] == "STOP" and stopped["verdict"] == "RETRY"


def test_two_pending_gates_are_answered_by_unit(repo: Path) -> None:  # HUM-B3
    spec = wf()
    units = {**spec.units, "security": step("Security review", approval=True),
             "perf": step("Performance review", approval=True)}
    spec = dataclasses.replace(spec, units=units)
    ex = ByUnit()
    out = go(repo, spec, ex)
    assert out.exit_code is ExitCode.PAUSED, out.message
    gates = row(state_root_path(repo), spec, "demo/P-1")["pending_gates"]
    assert sorted(g["unit"] for g in gates) == ["perf", "security"]
    neither = resume(spec, "P-1", repo, registry(ex), decision="proceed", settings=NO_SLEEP)
    assert neither.exit_code is ExitCode.USAGE and neither.reason == "unit_missing"
    assert len(neither.refusals) == 2 and all("--unit" in line for line in neither.refusals)
    one = resume(spec, "P-1", repo, registry(ex), decision="proceed",
                 settings=dataclasses.replace(NO_SLEEP, unit="security"))
    assert one.exit_code is ExitCode.PAUSED and "report" not in steps(ex), one.message
    (left,) = row(state_root_path(repo), spec, "demo/P-1")["pending_gates"]
    assert left["unit"] == "perf"
    done = resume(spec, "P-1", repo, registry(ex), decision="proceed", settings=NO_SLEEP)
    assert done.exit_code is ExitCode.FINISHED and steps(ex)[-1] == "report", done.message


def test_a_trip_back_to_the_block_runs_every_branch_again(repo: Path) -> None:
    spec = wf()
    units = {**spec.units, "report": step("Report", back_targets=["reviews"])}
    spec = dataclasses.replace(spec, units=units)
    back = verdict_block("UNMET", defect_in="perf_notes")
    ex = ByUnit(judges={"report": [back, MET]})
    out = go(repo, spec, ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    got = steps(ex)
    assert got.count("security") == 2 and got.count("perf") == 2 and got.count("report") == 2
    assert got.count("plan") == 1


def test_the_block_refusals() -> None:  # WFM-B7
    def codes(**change: Any) -> set[str]:
        spec = wf()
        units = dict(spec.units)
        order = list(spec.order)
        if "join" in change:
            units["reviews"] = change["join"]
        if "security" in change:
            units["security"] = change["security"]
        if "perf" in change:
            units["perf"] = change["perf"]
        if "order" in change:
            order = change["order"]
        spec = dataclasses.replace(spec, units=units, order=tuple(order), workspace=change.get("workspace", "auto"))
        return {f.code for f in errors(validate(spec, CAPS))}

    assert not codes()
    assert "parallel-branches" in codes(join=Parallel(branches=["security"]))
    assert "parallel-branch-unknown" in codes(join=Parallel(branches=["security", "nowhere"]))
    assert "parallel-join-before-branch" in codes(order=["plan", "security", "reviews", "perf", "report"])
    assert "parallel-branches-not-adjacent" in codes(join=Parallel(branches=["plan", "perf"]))
    assert "parallel-branch-flow" in codes(security=step("S", back_targets=["plan"]))
    writer = Step(prompt="S", tools=["read", "write"], gate=Gate(judge=Judge(stance="V."), criteria=[crit("c")]))
    editor = Step(prompt="S", tools=["read", "edit"], gate=Gate(judge=Judge(stance="V."), criteria=[crit("c")]))
    shell_only = Step(prompt="S", tools=["read", "shell"], gate=Gate(judge=Judge(stance="V."), criteria=[crit("c")]))
    # AC 5, WFM-AC7: a branch that declares `write` or `edit` validates; the old `parallel-writer-branch` refusal is gone
    assert not codes(security=writer) and not codes(perf=editor) and not codes(security=shell_only)
    assert "parallel-writer-in-place" in codes(security=writer, workspace="in_place")
    assert "parallel-writer-in-place" in codes(perf=editor, workspace="in_place")
    assert "parallel-writer-in-place" not in codes(security=shell_only, workspace="in_place")  # `shell` is no writer
    assert "parallel-writer-in-place" not in codes(security=writer, workspace="worktree")
    assert "parallel-join-gate" in codes(join=Parallel(branches=["security", "perf"], gate=Gate(approval=True)))
