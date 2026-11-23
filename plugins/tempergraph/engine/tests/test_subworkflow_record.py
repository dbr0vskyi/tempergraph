"""What a parent run with a child leaves behind: one log, one thread, one ledger row, the child's version, its outcome record (SWF-B8; SWF-AC2; task AC 2)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from tempergraph.constants import ExitCode
from tempergraph.durability import engine_file as enginefile
from tempergraph.durability.checkpoint import open_readonly, thread_ids
from tempergraph.executors.standins import standin
from tempergraph.run.outcome import parse_outcome
from tempergraph.run.runner import ledger_rows
from tempergraph.store.layout import state_root_path

from .fixtures.subworkflows import home_dir, register_workflow
from .test_run import DRAFT, REVIEW, judge
from .test_subworkflow_run import WORK, go, happy, parent, records


@pytest.fixture
def ran(tmp_path: Path, repo: Path) -> Path:
    register_workflow(home_dir(), tmp_path / "pkgs", "child", version="0.3.1", produces=["overview"])
    out = go(repo, happy(), parent())
    assert out.exit_code is ExitCode.FINISHED, out.message
    return repo


def test_one_run_log_one_thread_and_one_ledger_row(ran: Path) -> None:  # SWF-AC2, AC 2
    root = state_root_path(ran)
    assert [p.parent.name for p in sorted((root / "runs").glob("*/*/run.jsonl"))] == ["T-1"]
    assert [p.name for p in (root / "runs").iterdir()] == ["deliver"]  # no folder of the child's own
    with open_readonly(enginefile.checkpoint_of(root, "deliver", "T-1")) as saver:
        assert saver is not None and thread_ids(saver) == ["deliver/T-1"]
    rows = [r for r in ledger_rows(root) if r.get("kind") == "run_segment"]
    assert [r["workflow"] for r in rows] == ["deliver"]


def test_the_childs_outcome_row_is_no_run_segment_and_adds_no_folder(ran: Path) -> None:  # SWF-AC1, SWF-AC2, AC 3
    root = state_root_path(ran)
    everything = ledger_rows(root)
    child = [r for r in everything if r.get("kind") == "child_outcome"]
    assert [(r["workflow"], r["parent"], r["thread_id"], r["child"]) for r in child] == [
        ("child", "deliver", "deliver/T-1", "setup")]
    assert not [r for r in everything if r.get("kind") == "run_segment" and r.get("workflow") == "child"]
    assert [r["workflow"] for r in everything if r.get("kind") == "run_segment"] == ["deliver"]
    assert [p.name for p in (root / "runs").iterdir()] == ["deliver"]  # the child's row made no folder of its own
    assert [p.name for p in (root / "runs" / "deliver").iterdir()] == ["T-1"]


def test_every_child_record_carries_child(ran: Path) -> None:  # SWF-AC2, AC 2
    rows = records(ran)
    kids = [r for r in rows if r.get("child")]
    assert kids and {r["child"] for r in kids} == {"setup"}
    own = {"draft", "review", "setup"}
    assert not [r for r in kids if r.get("unit") in own]  # a record of the child names the child's unit, not the parent's
    assert all(r.get("child") for r in rows if r["kind"] in ("agent_run", "attempt_start") and
               str(r.get("session_key") or "").startswith("setup/"))


def test_the_childs_version_is_in_run_started_and_the_engine_file(ran: Path) -> None:  # SWF-AC2, AC 2
    started = next(r for r in records(ran) if r["kind"] == "run_started")
    kid = started["children"]["setup"]
    assert kid["workflow"] == "child" and kid["workflow_version"] == "0.3.1" and kid["content_version"].startswith("0.3.1")
    last = enginefile.last(enginefile.read(state_root_path(ran), "deliver", "T-1"))
    assert last["children"]["setup"]["workflow_version"] == kid["content_version"]
    assert set(last["children"]["setup"]["units"]) == {"work"}  # the child's units, for the resume check


def test_the_parents_outcome_record_keeps_the_childs_as_children_setup(tmp_path: Path, repo: Path) -> None:  # SWF-AC2, AC 2
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"])
    outcome = parse_outcome({
        "schema_version": 1, "revision": 1, "statement": "The parent is done.", "deliverables": [],
        "intermediate": {"draft": {"statement": "drafted", "criteria": []}},
        "final": [{"id": "p-done", "text": "All of it is done", "verified_by": "judge", "check_method": "Read"}]})
    spec = dataclasses.replace(parent(), outcome=outcome)
    ex = standin("claude", steps=[DRAFT, WORK, REVIEW], judges=[judge() for _ in range(5)])
    out = go(repo, ex, spec)
    assert out.exit_code is ExitCode.FINISHED, out.message
    rec = [r for r in records(repo) if r["kind"] == "outcome" and not r.get("child")][-1]
    assert [c["id"] for c in rec["criteria"]] == ["p-done"] and rec["verdict"] == "met"
    kid = rec["children"]["setup"]
    assert kid["verdict"] == "met" and [c["id"] for c in kid["criteria"]] == ["done"]
    row = [r for r in ledger_rows(state_root_path(repo)) if r.get("kind") == "run_segment"][-1]
    assert row["outcome"]["children"]["setup"]["verdict"] == "met"
