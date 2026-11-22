"""A parent with a sub-workflow unit starts: the interim refusal `not_in_release` is gone, every other refusal stays (SWF-B1, SWF-B6; task AC 1, AC 6)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tempergraph.catalog import Catalog
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


def test_the_stop_is_no_finding_of_validation(child: None) -> None:  # SWF-AC1, AC 6
    assert errors(validate(valid(), {"claude": CLAUDE})) == []


def test_run_check_no_longer_refuses_a_valid_parent_and_creates_nothing(repo: Path, child: None) -> None:  # SWF-AC1, AC 6
    before = hash_tree(repo / ".tempergraph")
    code, doc, _, ex = run(repo, valid(), "--check")
    assert code == 0 and doc["status"] == "ok" and doc["refusals"] == []
    assert "not_in_release" not in str(doc)
    assert ex.calls == [] and hash_tree(repo / ".tempergraph") == before


def test_run_starts_a_valid_parent_with_no_not_in_release_finding(repo: Path, child: None) -> None:  # SWF-AC1, AC 6
    code, doc, err, ex = run(repo, valid())
    assert "not_in_release" not in err and "not_in_release" not in str(doc)
    assert ex.calls != [] and (repo / ".tempergraph").exists()  # the run began: sessions started, a state root exists


@pytest.mark.parametrize("extra", [(), ("--check",)])
def test_a_finding_is_still_a_refusal(repo: Path, child: None, extra: tuple[str, ...]) -> None:  # SWF-AC1, AC 6
    spec = parent_spec("deliver", workflow="child", inputs=REQUEST, requires=">=9")
    code, doc, _, _ = run(repo, spec, *extra)
    assert code == 2
    if extra:
        assert doc["status"] == "error" and [r["code"] for r in doc["refusals"]] == ["subworkflow-version"]
    else:
        assert doc["reason"] == "subworkflow-version"


@pytest.mark.parametrize("extra", [(), ("--check",)])
def test_needs_git_is_still_a_refusal(tmp_path: Path, plain: Path, extra: tuple[str, ...]) -> None:  # SWF-AC1, AC 6
    register_workflow(home_dir(), tmp_path / "pkgs", "risky", needs_git=True)
    code, doc, _, ex = run(plain, parent_spec("deliver", workflow="risky", inputs=REQUEST), *extra)
    assert code == 2 and ex.calls == []
    if extra:
        assert doc["status"] == "error" and [r["code"] for r in doc["refusals"]] == ["needs_git"]
    else:
        assert doc["reason"] == "needs_git"
    assert not (plain / ".tempergraph").exists()
