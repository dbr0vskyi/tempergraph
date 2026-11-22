"""Inputs and produced keys of a child are checked before spend (SWF-B6, SWF-B7, SWF-AC1; task AC 2, AC 3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tempergraph.catalog import from_registry
from tempergraph.contracts import WorkflowSpec
from tempergraph.executors.capabilities import CLAUDE
from tempergraph.model.validate import Finding, errors, validate
from tempergraph.package.registry import check_package

from .fixtures.subworkflows import home_dir, parent_spec, register_workflow

CAPS = {"claude": CLAUDE}


def found(spec: WorkflowSpec, code: str) -> list[Finding]:
    return [f for f in errors(validate(spec, CAPS)) if f.code == code]


@pytest.fixture
def pkgs(tmp_path: Path) -> Path:
    return tmp_path / "pkgs"


def test_an_unmapped_declared_input_fails_naming_it(pkgs: Path) -> None:  # SWF-AC1, AC 2
    register_workflow(home_dir(), pkgs, "child", inputs=("scope",))
    got = found(parent_spec("deliver", workflow="child", inputs={"request": "request"}), "subworkflow-input-missing")
    assert got and "scope" in got[0].message and got[0].unit == "setup"
    assert not found(parent_spec("deliver", workflow="child", inputs={"scope": '"all"'}), "subworkflow-input-missing")
    assert not found(parent_spec("deliver", workflow="child", inputs={"scope": "draft.notes"}), "subworkflow-input-missing")


def test_every_declared_input_is_required(pkgs: Path) -> None:  # SWF-AC1, AC 2
    register_workflow(home_dir(), pkgs, "child", inputs=("scope", "depth"))
    got = found(parent_spec("deliver", workflow="child", inputs={"scope": '"all"'}), "subworkflow-input-missing")
    assert [("depth" in f.message) for f in got] == [True]


def test_a_child_that_declares_no_input_has_the_one_input_request(pkgs: Path) -> None:  # SWF-AC1, AC 2
    register_workflow(home_dir(), pkgs, "child")
    got = found(parent_spec("deliver", workflow="child", inputs={}), "subworkflow-input-missing")
    assert got and "request" in got[0].message
    assert not found(parent_spec("deliver", workflow="child", inputs={"request": "request"}), "subworkflow-input-missing")


def test_a_produces_key_the_child_has_no_producer_for_fails_naming_it(pkgs: Path) -> None:  # SWF-AC1, AC 2
    register_workflow(home_dir(), pkgs, "child")
    got = found(parent_spec("deliver", workflow="child", inputs={"request": "request"}, produces=["overview"]),
                "subworkflow-produces")
    assert got and "overview" in got[0].message and got[0].unit == "setup"
    register_workflow(home_dir(), pkgs, "child", produces=("overview",))
    assert not found(parent_spec("deliver", workflow="child", inputs={"request": "request"}, produces=["overview"]),
                     "subworkflow-produces")


def test_the_valid_parent_of_swf_b7_has_no_error_and_a_valid_catalog_row(pkgs: Path) -> None:  # SWF-AC1, AC 3
    register_workflow(home_dir(), pkgs, "repo-setup", version="0.3.1", produces=("overview",))
    root = register_workflow(
        home_dir(), pkgs, "deliver",
        children={"setup": {"workflow": "repo-setup", "requires": ">=0.3,<1", "inputs": {"request": "request"},
                            "produces": ["overview"]}})
    spec = parent_spec("deliver", workflow="repo-setup", requires=">=0.3,<1", inputs={"request": "request"},
                       produces=["overview"])
    assert errors(validate(spec, CAPS)) == []
    checked = check_package(root, CAPS)
    assert [f.code for f in checked.findings if f.severity == "error"] == [] and checked.entry["state"] == "ok"
    rows = {r["name"]: r for r in from_registry(home_dir()).to_json()["workflows"]}
    assert rows["deliver"]["state"] == "ok" and rows["deliver"]["units"] == ["work", "setup"]
