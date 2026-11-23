"""A council unit is declared with `Council(...)` and validates; each refusal of CNL-B16 has its own finding code
(CNL-AC1, CNL-B9, CNL-B16, WFM-B10, WFM-B13; task AC 1)."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

import pytest

from tempergraph import api
from tempergraph.api import Chair, Council, Gate, Judge, Member, Step, Value
from tempergraph.contracts import CouncilSpec, MemberSpec, UnitSpec, WorkflowSpec
from tempergraph.executors.capabilities import ANTIGRAVITY, CLAUDE, DECLARED
from tempergraph.model.validate import Finding, errors, validate

from .fixtures.workflows import crit, named, two_step

CLAUDE_ONLY = {"claude": CLAUDE}


def members(n: int = 2, **each: Any) -> list[MemberSpec]:
    return [Member(name=f"m{i}", stance=f"Lens {i}", **each) for i in range(n)]


def gate() -> Any:
    return Gate(judge=Judge(stance="Verify.", references=["positions"]), criteria=[crit("c-dec")])


def council(**fields: Any) -> UnitSpec:
    base: dict[str, Any] = {"question": "Which design for {request}?", "members": members(), "chair": Chair(),
                            "gate": gate()}
    base.update(fields)
    return Council(**base)


def workflow(unit: UnitSpec, **changes: Any) -> WorkflowSpec:
    spec = two_step()
    units = {"decide": unit, **spec.units}
    return dataclasses.replace(spec, units=units, order=("decide", *spec.order), **changes)


def found(spec: WorkflowSpec, executors: Any = CLAUDE_ONLY) -> list[Finding]:
    return validate(spec, executors)


def codes(spec: WorkflowSpec, executors: Any = CLAUDE_ONLY) -> set[str]:
    return {f.code for f in errors(found(spec, executors))}


def test_a_well_formed_synthesize_council_has_no_error_finding() -> None:  # CNL-AC1 (CNL-B9)
    spec = workflow(council())
    assert errors(found(spec)) == []
    unit = spec.units["decide"]
    assert unit.kind == "council" and isinstance(unit.council, CouncilSpec)
    c = unit.council
    assert [m.name for m in c.members] == ["m0", "m1"] and c.mode == "synthesize" and c.rounds == 0
    assert c.anonymize is True and c.on_no_decision == "escalate" and c.retry_scope == "all"
    assert c.rule is None and c.options is None and c.quorum is None and c.cost_cap_usd is None


def test_the_builder_records_every_field_of_cnl_b9() -> None:  # CNL-AC1 (CNL-B9)
    unit = Council(question="Ship {request}?", members=members(3, tools=["read", "search"], timeout_s=90, idle_s=30),
                   mode="vote", options=["ship", "hold"], rule="supermajority", rounds=2, anonymize=False,
                   chair=Chair(model="large", prompt="Write the rationale"), quorum=2, on_no_decision="retry",
                   cost_cap_usd=2.0, gate=gate())
    c = unit.council
    assert c is not None and c.options == ("ship", "hold") and c.rule == "supermajority" and c.rounds == 2
    assert c.anonymize is False and c.quorum == 2 and c.on_no_decision == "retry" and c.cost_cap_usd == 2.0
    assert c.chair is not None and c.chair.model == "large" and c.chair.prompt == "Write the rationale"
    first = c.members[0]
    assert first.tools == ("read", "search") and first.timeout_s == 90 and first.idle_s == 30


def test_an_unknown_argument_fails_when_the_unit_is_built() -> None:  # CNL-AC1
    with pytest.raises(TypeError):
        Council(question="q", members=members(), branches=["a", "b"])


def test_council_is_not_refused_as_not_in_release() -> None:  # CNL-AC1, WFM-B10, WFM-B13
    assert "not_in_release" not in codes(workflow(council()))


def test_a_field_of_a_later_release_is_still_refused() -> None:  # WFM-B10
    spec = workflow(council())
    units = dict(spec.units)
    units["decide"] = dataclasses.replace(units["decide"], extra={"council_seats": 3})
    assert "not_in_release" in codes(dataclasses.replace(spec, units=units))


def test_a_blueprint_with_a_council_is_still_refused_not_in_release() -> None:  # CNL-AC1 (WFM-B13, SCF-B9)
    from tempergraph.author.blueprint import BLUEPRINT_LATER_KINDS, RELEASE_KINDS

    assert "council" in BLUEPRINT_LATER_KINDS and "council" not in RELEASE_KINDS


def _mutate(spec: WorkflowSpec, **changes: Any) -> WorkflowSpec:
    unit = spec.units["decide"]
    assert unit.council is not None
    units = dict(spec.units)
    units["decide"] = dataclasses.replace(unit, council=dataclasses.replace(unit.council, **changes))
    return dataclasses.replace(spec, units=units)


def _gate_of(spec: WorkflowSpec, **changes: Any) -> WorkflowSpec:
    units = dict(spec.units)
    units["decide"] = dataclasses.replace(units["decide"], gate=dataclasses.replace(units["decide"].gate, **changes))
    return dataclasses.replace(spec, units=units)


def vote(**fields: Any) -> WorkflowSpec:
    return workflow(council(mode="vote", options=["ship", "hold"], chair=None, **fields))


def member_with(*tools: str) -> list[MemberSpec]:
    return [Member(name="m0", tools=list(tools)), Member(name="m1")]


def writer_block() -> WorkflowSpec:
    """A parallel block whose branches are a writer step and a council."""
    spec = two_step()
    writer = Step(prompt="Write {request}", tools=["read", "write"], gate=Gate(judge=Judge(stance="V."),
                                                                                criteria=[crit("w1")]))
    units = {"writer": writer, "decide": council(), "join": api.Parallel(branches=["writer", "decide"])}
    del spec
    return named(api.Workflow(order=["writer", "decide", "join"], units=units, issue_repository="acme/x",
                              routing=api.Routing(description="Writer beside a council")))


def in_map_item() -> WorkflowSpec:
    spec = workflow(council())
    units = dict(spec.units)
    units["decide"] = dataclasses.replace(units["decide"], kind="map")
    return dataclasses.replace(spec, units=units)


# One fixture per cause of CNL-B16, each with its own finding code (CNL-AC1).
REFUSALS: list[tuple[str, Callable[[], WorkflowSpec]]] = [
    ("council-members-count", lambda: workflow(council(members=members(1)))),
    ("council-members-count", lambda: workflow(council(members=members(8)))),
    ("council-member-duplicate", lambda: workflow(council(members=[Member(name="a"), Member(name="a")]))),
    ("council-member-tool-not-read-only", lambda: workflow(council(members=member_with("edit")))),
    ("council-member-tool-not-read-only", lambda: workflow(council(members=member_with("write")))),
    ("council-member-tool-not-read-only", lambda: workflow(council(members=member_with("shell")))),
    ("council-member-tool-not-read-only", lambda: workflow(council(members=member_with("mcp:tracker/create_issue")))),
    ("council-chair-missing", lambda: workflow(council(chair=None))),
    ("council-options-missing", lambda: workflow(council(mode="vote", options=None, chair=None))),
    ("council-options-missing", lambda: workflow(council(mode="vote", options=["ship"], chair=None))),
    ("council-options-unknown", lambda: workflow(council(mode="vote", options="ghost_list", chair=None))),
    ("council-rule-outside-vote", lambda: workflow(council(rule="majority"))),
    ("council-options-outside-vote", lambda: workflow(council(options=["a", "b"]))),
    ("council-retry-scope-vote", lambda: vote(retry_scope="chair")),
    ("council-in-map-item", in_map_item),
    ("council-in-writer-block", writer_block),
    ("council-judge-missing", lambda: _gate_of(workflow(council()), judge=None)),
    ("council-stance-too-long", lambda: workflow(council(members=[Member(name="a", stance="x" * 401),
                                                                   Member(name="b")]))),
    ("council-rounds-invalid", lambda: workflow(council(rounds=4))),
    ("council-quorum-invalid", lambda: workflow(council(quorum=3))),
]


@pytest.mark.parametrize("code,build", REFUSALS, ids=[f"{c}-{i}" for i, (c, _) in enumerate(REFUSALS)])
def test_each_refusal_of_cnl_b16_has_its_code(code: str, build: Callable[[], WorkflowSpec]) -> None:  # CNL-AC1 (CNL-B16)
    assert code in codes(build())


def test_the_refusals_have_distinct_codes() -> None:  # CNL-AC1 (CNL-B16)
    causes = {c for c, _ in REFUSALS}
    assert len(causes) >= 15


def test_the_refusal_names_the_unit() -> None:  # CNL-AC1
    got = [f for f in found(workflow(council(chair=None))) if f.code == "council-chair-missing"]
    assert got and got[0].unit == "decide" and got[0].severity == "error"


def test_options_from_an_artifact_an_earlier_unit_produces_validate() -> None:  # CNL-AC1 (CNL-B16)
    spec = two_step()
    pick = Step(prompt="List the options for {request}", tools=["read"], produces={"choices": Value()},
                gate=Gate(judge=Judge(stance="V."), criteria=[crit("p1")]))
    units = {"pick": pick, "decide": council(mode="vote", options="choices", chair=None), **spec.units}
    wf = dataclasses.replace(spec, units=units, order=("pick", "decide", *spec.order))
    assert "council-options-unknown" not in codes(wf)
    assert errors(found(wf)) == []


def warnings(spec: WorkflowSpec, executors: Any = CLAUDE_ONLY) -> set[str]:
    return {f.code for f in found(spec, executors) if f.severity == "warning"}


def test_every_member_on_one_model_family_warns() -> None:  # CNL-AC1 (CNL-B16, ARC-B15)
    spec = workflow(council())
    assert "council-one-family" in warnings(spec)
    assert errors(found(spec)) == []
    mixed = workflow(council(members=[Member(name="a", executor="claude"), Member(name="b", executor="antigravity")]))
    both = {"claude": CLAUDE, "antigravity": ANTIGRAVITY}
    assert "council-one-family" not in warnings(mixed, both)


def test_majority_with_an_even_member_count_warns() -> None:  # CNL-AC1 (CNL-B16, ARC-B15)
    assert "council-even-majority" in warnings(vote(rule="majority"))
    assert "council-even-majority" in warnings(vote())  # the default rule is majority
    odd = workflow(council(members=members(3), mode="vote", options=["ship", "hold"], chair=None))
    assert "council-even-majority" not in warnings(odd)
    assert "council-even-majority" not in warnings(vote(rule="plurality"))


def test_rounds_without_anonymity_warn() -> None:  # CNL-AC1 (CNL-B16)
    assert "council-anonymize-off" in warnings(workflow(council(rounds=1, anonymize=False)))
    assert "council-anonymize-off" not in warnings(workflow(council(rounds=1, anonymize=True)))
    assert "council-anonymize-off" not in warnings(workflow(council(rounds=0, anonymize=False)))


def test_the_limits_of_cnl_b9_are_inclusive() -> None:  # CNL-AC1 (CNL-B9)
    ok = workflow(council(members=[Member(name=f"m{i}", stance="x" * 400) for i in range(7)], rounds=3, quorum=7))
    assert errors(found(ok)) == []
    assert errors(found(ok, DECLARED)) == []
