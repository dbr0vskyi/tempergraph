"""The contest unit's declaration and its refusals, each with a finding code of its own (CTS-AC1; CTS-B6, CTS-B10)."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

import pytest

from tempergraph.api import Contest, Gate, Judge, Map, Parallel, Routing, Slot, Step, Value, Workflow
from tempergraph.contracts import WorkflowSpec
from tempergraph.executors.capabilities import CLAUDE
from tempergraph.model.validate import errors, validate

from .fixtures.workflows import crit, named

CLAUDE_ONLY = {"claude": CLAUDE}


def base_step(*, judge: bool = True, tools: tuple[str, ...] = ("read",)) -> Any:
    gate = Gate(judge=Judge(stance="V."), criteria=[crit("c-slot")]) if judge else Gate(criteria=[crit("c-slot")])
    return Step(prompt="Draft {request}", tools=list(tools), produces={"note": Value()}, gate=gate)


def slots3() -> list[Any]:
    return [Slot("s1", model="small"), Slot("s2", model="medium"), Slot("s3", model="large")]


def contest_unit(**fields: Any) -> Any:
    judge = fields.pop("judge", True)
    tools = fields.pop("tools", ("read",))
    fields.setdefault("slots", slots3())
    return Contest(step=base_step(judge=judge, tools=tools), **fields)


def workflow(unit: Any, *, before: dict[str, Any] | None = None, order: list[str] | None = None,
             **fields: Any) -> WorkflowSpec:
    units: dict[str, Any] = {**(before or {}), "pick": unit}
    return named(Workflow(order=order or [*(before or {}), "pick"], units=units, issue_repository="acme/x",
                          routing=Routing(description="Best of three"), **fields))


def codes(spec: WorkflowSpec) -> set[str]:
    return {f.code for f in errors(validate(spec, CLAUDE_ONLY))}


def test_a_valid_contest_of_three_slots_validates() -> None:  # CTS-AC1 (CTS-B6)
    spec = workflow(contest_unit())
    assert errors(validate(spec, CLAUDE_ONLY)) == []
    assert not [f for f in validate(spec, CLAUDE_ONLY) if f.code == "not_in_release"]


def test_a_slot_count_declares_s1_to_sn() -> None:  # CTS-AC1 (CTS-B6)
    from tempergraph.model import flow

    spec = workflow(contest_unit(slots=3))
    assert errors(validate(spec, CLAUDE_ONLY)) == []
    assert flow.slot_names(spec, "pick") == ("s1", "s2", "s3")
    assert flow.slot_names(workflow(contest_unit(slots=[Slot("a"), Slot("b", model="small")])), "pick") == ("a", "b")


def _inside_a_map_item() -> WorkflowSpec:
    plan = Step(prompt="Plan", tools=["read", "write"], produces={"phases": "file"},
                gate=Gate(judge=Judge(stance="V."), criteria=[crit("c-plan")]))
    return workflow(Map(items_from=("plan", "phases"), step=contest_unit()), before={"plan": plan})


def _inside_a_sequential_map_writing() -> WorkflowSpec:
    plan = Step(prompt="Plan", tools=["read", "write"], produces={"phases": "file"},
                gate=Gate(judge=Judge(stance="V."), criteria=[crit("c-plan")]))
    return workflow(Map(items_from=("plan", "phases"), step=contest_unit(writes=True), mode="sequential"),
                    before={"plan": plan})


def _inside_a_branch() -> WorkflowSpec:
    other = base_step()
    units = {"a": contest_unit(), "b": other, "both": Parallel(branches=["a", "b"])}
    return named(Workflow(order=["a", "b", "both"], units=units, issue_repository="acme/x",
                          routing=Routing(description="Branches")))


REFUSED: list[tuple[str, Callable[[], WorkflowSpec], str]] = [
    ("one slot", lambda: workflow(contest_unit(slots=1)), "contest-slot-count"),
    ("six slots", lambda: workflow(contest_unit(slots=6)), "contest-slot-count"),
    ("one listed slot", lambda: workflow(contest_unit(slots=[Slot("a")])), "contest-slot-count"),
    ("a duplicate slot name", lambda: workflow(contest_unit(slots=[Slot("a"), Slot("a", model="small")])),
     "contest-slot-duplicate"),
    ("concurrency 6", lambda: workflow(contest_unit(concurrency=6)), "contest-concurrency"),
    ("concurrency 0", lambda: workflow(contest_unit(concurrency=0)), "contest-concurrency"),
    ("cost_cap_usd 0", lambda: workflow(contest_unit(cost_cap_usd=0)), "contest-cost-cap"),
    ("cost_cap_usd below 0", lambda: workflow(contest_unit(cost_cap_usd=-1.0)), "contest-cost-cap"),
    ("writes without worktrees", lambda: workflow(contest_unit(writes=True), workspace="in_place"),
     "contest-writer-in-place"),
    ("writes in a sequential map", _inside_a_sequential_map_writing, "contest-writer-sequential-map"),
    ("inside a map item", _inside_a_map_item, "contest-in-map-item"),
    ("inside a parallel branch", _inside_a_branch, "contest-in-branch"),
    ("no judge on the gate", lambda: workflow(contest_unit(judge=False)), "contest-judge-missing"),
]


@pytest.mark.parametrize(("what", "build", "code"), REFUSED, ids=[w for w, _, _ in REFUSED])
def test_each_refusal_fails_validation_with_its_own_code(what: str, build: Callable[[], WorkflowSpec],
                                                         code: str) -> None:  # CTS-AC1 (CTS-B10)
    assert code in codes(build()), what


def test_the_refusals_have_codes_of_their_own() -> None:  # CTS-AC1 (CTS-B10)
    got = {code for _, _, code in REFUSED}
    assert got == {"contest-slot-count", "contest-slot-duplicate", "contest-concurrency", "contest-cost-cap",
                   "contest-writer-in-place", "contest-writer-sequential-map", "contest-in-map-item",
                   "contest-in-branch", "contest-judge-missing"}  # nine refusals of CTS-B10, nine codes
    assert "judge-missing" not in codes(workflow(contest_unit(judge=False)))  # the contest's own code, not the step's


def test_a_contest_in_a_valid_place_raises_none_of_them() -> None:  # CTS-AC1 (CTS-B10)
    spec = workflow(contest_unit(writes=True), workspace="worktree")
    assert errors(validate(spec, CLAUDE_ONLY)) == []


def test_identical_slots_are_warned_and_a_different_slot_is_not() -> None:  # CTS-AC1 (CTS-B10, ARC-B15)
    same = workflow(contest_unit(slots=[Slot("a"), Slot("b")]))
    assert "contest-identical-slots" in {f.code for f in validate(same, CLAUDE_ONLY) if f.severity == "warning"}
    assert errors(validate(same, CLAUDE_ONLY)) == []  # a warning, not a refusal
    counted = workflow(contest_unit(slots=3))
    assert "contest-identical-slots" in {f.code for f in validate(counted, CLAUDE_ONLY)}
    varied = workflow(contest_unit(slots=[Slot("a"), Slot("b", prompt_variant="Start from the tests.")]))
    assert "contest-identical-slots" not in {f.code for f in validate(varied, CLAUDE_ONLY)}
    other_model = workflow(contest_unit(slots=[Slot("a", model="small"), Slot("b", model="large")]))
    assert "contest-identical-slots" not in {f.code for f in validate(other_model, CLAUDE_ONLY)}


def test_a_contest_is_a_unit_of_kind_contest_with_its_own_fields() -> None:  # CTS-AC1 (CTS-B6)
    u = contest_unit(writes=True, retry_scope="all", concurrency=2, cost_cap_usd=0.5)
    assert u.kind == "contest" and u.contest is not None
    assert (u.contest.writes, u.contest.retry_scope, u.contest.concurrency, u.contest.cost_cap_usd) == (
        True, "all", 2, 0.5)
    assert u.step is not None and dataclasses.is_dataclass(u.contest)
