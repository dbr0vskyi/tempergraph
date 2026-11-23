"""A sub-workflow unit is declared with `Subworkflow(...)` and recorded field by field (SWF-B7, SWF-AC1; task AC 1)."""

from __future__ import annotations

import pytest

from tempergraph.api import Council, Gate, Judge, Subworkflow
from tempergraph.contracts import GateSpec, SubworkflowSpec, UnitSpec
from tempergraph.package.inventory import canonical

from .fixtures.workflows import crit


def declared() -> UnitSpec:
    return Subworkflow(
        workflow="repo-setup", requires=">=0.3,<1",
        inputs={"request": "request", "scope": "triage.scope", "mode": '"fast"'},
        produces=["overview"], gate=Gate(judge=Judge(stance="Verify."), criteria=[crit("c-setup")]),
        summary="Set up the repository")


def test_the_builder_records_every_field_of_swf_b7() -> None:  # SWF-AC1, AC 1
    unit = declared()
    assert isinstance(unit, UnitSpec) and unit.kind == "subworkflow"
    rec = unit.subworkflow
    assert isinstance(rec, SubworkflowSpec)
    assert rec.workflow == "repo-setup" and rec.requires == ">=0.3,<1"
    assert dict(rec.inputs) == {"request": "request", "scope": "triage.scope", "mode": '"fast"'}
    assert rec.produces == ("overview",) and rec.summary == "Set up the repository"
    assert [c.id for c in unit.gate.criteria] == ["c-setup"] and unit.gate.judge is not None


def test_defaults_mean_any_version_no_inputs_and_an_empty_gate() -> None:  # SWF-AC1, AC 1
    unit = Subworkflow(workflow="child")
    rec = unit.subworkflow
    assert rec is not None and rec.requires is None and dict(rec.inputs) == {} and rec.produces == ()
    assert rec.summary == "" and unit.gate == GateSpec()


@pytest.mark.parametrize("name,value", [
    ("scope", "two words"), ("scope", "a.b.c"), ("scope", "unquoted"), ("scope", ""), ("scope", "triage."),
    ("scope", '"open'),
])
def test_an_input_of_another_form_fails_when_the_unit_is_built(name: str, value: str) -> None:  # SWF-AC1, AC 1
    with pytest.raises(ValueError, match=name):
        Subworkflow(workflow="child", inputs={name: value})


def test_every_form_of_an_input_is_read() -> None:  # SWF-AC1, AC 1
    rec = Subworkflow(workflow="child", inputs={"a": "request", "b": "plan.notes", "c": '"two words"'}).subworkflow
    assert rec is not None and dict(rec.inputs) == {"a": "request", "b": "plan.notes", "c": '"two words"'}


def test_equal_declarations_have_equal_canonical_forms() -> None:  # SWF-AC1, AC 1
    assert canonical(declared()) == canonical(declared())
    assert canonical(declared()) != canonical(Subworkflow(workflow="other"))


def test_the_other_later_kinds_still_build_as_placeholders() -> None:  # SWF-AC1, AC 1
    assert Council(branches=["a", "b"]).kind == "council"
