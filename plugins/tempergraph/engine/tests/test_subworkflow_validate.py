"""Validation refuses a bad child before any spend (SWF-B6, SWF-AC1; task AC 2): offline, on engine fixture workflows."""

from __future__ import annotations

from pathlib import Path

import pytest

from tempergraph.builtin.upgrade import NAME as BUILTIN
from tempergraph.contracts import WorkflowSpec
from tempergraph.executors.capabilities import CLAUDE
from tempergraph.model.validate import Finding, errors, validate

from .fixtures.subworkflows import home_dir, parent_spec, register_workflow
from .fixtures.workflows import two_step

CAPS = {"claude": CLAUDE}
REQUEST = {"request": "request"}


def found(spec: WorkflowSpec) -> list[Finding]:
    return errors(validate(spec, CAPS))


def codes(spec: WorkflowSpec) -> set[str]:
    return {f.code for f in found(spec)}


def sub(name: str, **kw: object) -> dict[str, object]:
    return {"workflow": name, "inputs": REQUEST, **kw}


@pytest.fixture
def pkgs(tmp_path: Path) -> Path:
    return tmp_path / "pkgs"


def test_a_child_that_names_the_parent_is_recursive(pkgs: Path) -> None:  # SWF-AC1, AC 2
    got = [f for f in found(parent_spec("deliver", workflow="deliver", inputs=REQUEST)) if f.code == "subworkflow-recursive"]
    assert got and got[0].unit == "setup" and "deliver" in got[0].message


def test_a_child_that_reaches_the_parent_through_another_child_is_recursive(pkgs: Path) -> None:  # SWF-AC1, AC 2
    register_workflow(home_dir(), pkgs, "a", children={"next": sub("b")})
    register_workflow(home_dir(), pkgs, "b", children={"back": sub("deliver")})
    got = [f for f in found(parent_spec("deliver", **sub("a"))) if f.code == "subworkflow-recursive"]
    assert got and got[0].unit == "setup"


def test_three_levels_pass_the_depth_check_and_four_fail_it(pkgs: Path) -> None:  # SWF-AC1, AC 2
    register_workflow(home_dir(), pkgs, "a", children={"next": sub("b")})
    register_workflow(home_dir(), pkgs, "b", children={"next": sub("c")})
    register_workflow(home_dir(), pkgs, "c")
    assert "subworkflow-depth" not in codes(parent_spec("deliver", **sub("a")))
    register_workflow(home_dir(), pkgs, "c", children={"next": sub("d")})
    register_workflow(home_dir(), pkgs, "d")
    got = [f for f in found(parent_spec("deliver", **sub("a"))) if f.code == "subworkflow-depth"]
    assert got and got[0].unit == "setup"


def test_a_child_no_registry_entry_names_is_unknown(pkgs: Path) -> None:  # SWF-AC1, AC 2
    got = [f for f in found(parent_spec("deliver", **sub("ghost"))) if f.code == "subworkflow-unknown"]
    assert got and "ghost" in got[0].message and got[0].unit == "setup"


def test_a_registered_child_that_does_not_load_is_unknown(pkgs: Path) -> None:  # SWF-AC1, AC 2
    register_workflow(home_dir(), pkgs, "wrecked", broken=True)
    got = [f for f in found(parent_spec("deliver", **sub("wrecked"))) if f.code == "subworkflow-unknown"]
    assert got and "wrecked" in got[0].message


def test_a_child_version_outside_requires_fails(pkgs: Path) -> None:  # SWF-AC1, AC 2
    register_workflow(home_dir(), pkgs, "child", version="0.4.0")
    assert "subworkflow-version" in codes(parent_spec("deliver", **sub("child", requires=">=0.3,<0.4")))
    assert "subworkflow-version" not in codes(parent_spec("deliver", **sub("child", requires=">=0.3,<1")))
    assert "subworkflow-version" not in codes(parent_spec("deliver", **sub("child")))  # none: any version


@pytest.mark.parametrize("requires", ["newer", "", ">=0.3,newer", "~=0.3"])
def test_an_invalid_range_fails(pkgs: Path, requires: str) -> None:  # SWF-AC1, AC 2
    register_workflow(home_dir(), pkgs, "child")
    assert "subworkflow-version" in codes(parent_spec("deliver", **sub("child", requires=requires)))


def test_a_built_in_workflow_is_no_child(pkgs: Path) -> None:  # SWF-AC1, AC 2
    got = [f for f in found(parent_spec("deliver", **sub(BUILTIN))) if f.code == "subworkflow-builtin"]
    assert got and BUILTIN in got[0].message


def test_a_valid_child_gives_no_structure_finding(pkgs: Path) -> None:  # SWF-AC1, AC 2
    register_workflow(home_dir(), pkgs, "child")
    assert codes(parent_spec("deliver", **sub("child", requires=">=0.3,<1"))) == set()


def test_a_workflow_without_a_sub_workflow_unit_never_reads_the_registry() -> None:  # SWF-AC1, AC 2
    (home_dir()).mkdir(parents=True, exist_ok=True)
    (home_dir() / "registry.json").write_text("{ not json", encoding="utf-8")
    assert found(two_step()) == []
    assert "subworkflow-unknown" in codes(parent_spec("deliver", **sub("child")))  # an unreadable registry: no raise
