"""Until a child can run, a valid parent stops before any spend with one message (SWF-B11, SWF-AC4; task AC 4)."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import Subworkflow
from tempergraph.catalog import Catalog
from tempergraph.constants import ExitCode
from tempergraph.contracts import WorkflowSpec
from tempergraph.executors.capabilities import CLAUDE
from tempergraph.model.validate import errors, validate

from .conftest import hash_tree
from .fixtures.subworkflows import home_dir, parent_spec, register_workflow
from .test_cli import cli, happy

REQUEST = {"request": "request"}


def catalog(spec: WorkflowSpec) -> Catalog:
    return Catalog(specs={"deliver": spec})


def run(repo: Path, spec: WorkflowSpec, *extra: str) -> tuple[int, Any, str, Any]:
    ex = happy()
    code, doc, err = cli(repo, ex, "run", "deliver", "notes", "--task-id", "T-1", "--json", *extra, catalog=catalog(spec))
    return code, doc, err, ex


@pytest.fixture
def child(tmp_path: Path) -> None:
    register_workflow(home_dir(), tmp_path / "pkgs", "child")


@pytest.fixture
def plain(tmp_path: Path) -> Path:
    folder = tmp_path / "plain"
    folder.mkdir()
    return folder


def valid() -> WorkflowSpec:
    return parent_spec("deliver", workflow="child", inputs=REQUEST)


def test_the_stop_is_no_finding_of_validation(child: None) -> None:  # SWF-AC4, AC 4
    assert errors(validate(valid(), {"claude": CLAUDE})) == []


def test_run_stops_with_one_message_and_creates_nothing(repo: Path, child: None) -> None:  # SWF-AC4, AC 4
    before = hash_tree(repo / ".tempergraph")
    code, doc, _, ex = run(repo, valid())
    assert code == ExitCode.USAGE == 2 and doc["reason"] == "not_in_release"
    assert "setup" in doc["message"] and "running a child is not built yet" in doc["message"]
    assert "\n" not in doc["message"] and doc["refusals"] == []
    assert ex.calls == [] and hash_tree(repo / ".tempergraph") == before


def test_run_check_gives_the_same_finding_and_creates_nothing(repo: Path, child: None) -> None:  # SWF-AC4, AC 4
    before = hash_tree(repo / ".tempergraph")
    code, doc, _, ex = run(repo, valid(), "--check")
    assert code == 2 and doc["status"] == "error"
    assert [(r["code"], r["unit"]) for r in doc["refusals"]] == [("not_in_release", "setup")]
    assert "running a child is not built yet" in doc["refusals"][0]["message"]
    assert ex.calls == [] and hash_tree(repo / ".tempergraph") == before


@pytest.mark.parametrize("extra", [(), ("--check",)])
def test_the_message_names_the_first_unit_in_order(repo: Path, child: None, extra: tuple[str, ...]) -> None:  # SWF-AC4, AC 4
    spec = valid()
    units = {**spec.units, "again": Subworkflow(workflow="child", inputs=REQUEST)}
    spec = dataclasses.replace(spec, units=units, order=(*spec.order, "again"))
    code, doc, _, _ = run(repo, spec, *extra)
    assert code == 2
    text = doc["message"] if not extra else doc["refusals"][0]["message"]
    assert "'setup'" in text and "'again'" not in text


@pytest.mark.parametrize("extra", [(), ("--check",)])
def test_another_refusal_comes_first_a_finding(repo: Path, child: None, extra: tuple[str, ...]) -> None:  # SWF-AC4, AC 4
    spec = parent_spec("deliver", workflow="child", inputs=REQUEST, requires=">=9")
    code, doc, _, _ = run(repo, spec, *extra)
    assert code == 2
    if extra:
        assert doc["status"] == "error" and [r["code"] for r in doc["refusals"]] == ["subworkflow-version"]
    else:
        assert doc["reason"] == "subworkflow-version"


@pytest.mark.parametrize("extra", [(), ("--check",)])
def test_another_refusal_comes_first_needs_git(tmp_path: Path, plain: Path, extra: tuple[str, ...]) -> None:  # SWF-AC4, AC 4
    register_workflow(home_dir(), tmp_path / "pkgs", "risky", needs_git=True)
    code, doc, _, ex = run(plain, parent_spec("deliver", workflow="risky", inputs=REQUEST), *extra)
    assert code == 2 and ex.calls == []
    if extra:
        assert doc["status"] == "error" and [r["code"] for r in doc["refusals"]] == ["needs_git"]
    else:
        assert doc["reason"] == "needs_git"
    assert not (plain / ".tempergraph").exists()
