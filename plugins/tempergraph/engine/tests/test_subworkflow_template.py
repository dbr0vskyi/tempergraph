"""`{<unit>.<key>}` in a template validates only for a key an earlier sub-workflow unit exposes (SWF-B12, SWF-AC5)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from tempergraph.api import Step
from tempergraph.contracts import WorkflowSpec
from tempergraph.executors.capabilities import CLAUDE
from tempergraph.model.validate import Finding, errors, validate

from .fixtures.subworkflows import home_dir, parent_spec, register_workflow
from .fixtures.workflows import crit

CAPS = {"claude": CLAUDE}


def reader(prompt: str, **kw: object) -> Step:
    return Step(prompt=prompt, tools=["read"], gate=dataclasses.replace(parent_spec("p", workflow="c").units["draft"].gate,
                                                                          criteria=(crit("c-late"),)), **kw)  # type: ignore[arg-type]


def with_reader(prompt: str, *, before: bool = False, **unit: object) -> WorkflowSpec:
    """The parent with a step `late` that reads `prompt`, after `setup` (or before it)."""
    spec = parent_spec("deliver", **unit)
    units = {**spec.units, "late": reader(prompt)}
    order = [n for n in spec.order if n != "setup"]
    order = [*order, "late", "setup"] if before else [*order, "setup", "late"]
    return dataclasses.replace(spec, units=units, order=tuple(order))


def template_errors(spec: WorkflowSpec) -> list[Finding]:
    return [f for f in errors(validate(spec, CAPS)) if f.code == "template-unknown-field"]


@pytest.fixture
def child(tmp_path: Path) -> None:
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=("overview",))


def test_a_key_the_unit_produces_validates(child: None) -> None:  # SWF-AC5
    spec = with_reader("Read {setup.overview}", workflow="child", inputs={"request": "request"}, produces=["overview"])
    assert errors(validate(spec, CAPS)) == []


def test_with_produces_empty_the_childs_deliverables_are_exposed(child: None) -> None:  # SWF-AC5
    spec = with_reader("Read {setup.overview}", workflow="child", inputs={"request": "request"})
    assert errors(validate(spec, CAPS)) == []


def test_a_key_the_unit_does_not_expose_fails(child: None) -> None:  # SWF-AC5
    spec = with_reader("Read {setup.notes}", workflow="child", inputs={"request": "request"}, produces=["overview"])
    got = template_errors(spec)
    assert got and got[0].unit == "late" and "setup.notes" in got[0].message


def test_a_unit_that_comes_after_the_template_fails(child: None) -> None:  # SWF-AC5
    spec = with_reader("Read {setup.overview}", before=True, workflow="child", inputs={"request": "request"},
                       produces=["overview"])
    got = template_errors(spec)
    assert got and got[0].unit == "late"


def test_a_step_unit_exposes_no_dotted_key(child: None) -> None:  # SWF-AC5
    spec = with_reader("Read {draft.notes}", workflow="child", inputs={"request": "request"})
    assert [f.unit for f in template_errors(spec)] == ["late"]


def test_a_child_that_cannot_be_read_exposes_nothing() -> None:  # SWF-AC5
    spec = with_reader("Read {setup.overview}", workflow="ghost", inputs={"request": "request"}, produces=["overview"])
    codes = {f.code for f in errors(validate(spec, CAPS))}
    assert {"template-unknown-field", "subworkflow-unknown"} <= codes
