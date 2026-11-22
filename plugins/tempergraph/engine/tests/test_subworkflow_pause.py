"""A pause inside a child pauses the parent; a resume answers it; a child that changed or went away under a paused parent (SWF-B2, SWF-B3, SWF-B8; SWF-AC1; task AC 3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.durability.status import status
from tempergraph.executors.standins import ScriptedExecutor, standin
from tempergraph.run.runner import resume
from tempergraph.store.layout import state_root_path

from .fixtures.subworkflows import home_dir, register_workflow, remove_registry
from .test_run import DRAFT, REVIEW, judge
from .test_subworkflow_run import NO_SLEEP, WORK, go, keys, parent, records, registry


@pytest.fixture
def paused(tmp_path: Path, repo: Path) -> tuple[Path, ScriptedExecutor]:
    """A parent run paused at the approval gate of its child's `work` unit; no unit after the sub-workflow has started."""
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"], approval=True)
    ex = standin("claude", steps=[DRAFT, WORK], judges=[judge(), judge()])
    out = go(repo, ex, parent())
    assert out.exit_code is ExitCode.PAUSED, (out.message, out.payload)
    assert out.payload is not None and out.payload["unit"] == "setup/work" and out.payload["kind"] == "approval"
    assert "review.1.step" not in keys(ex)  # SWF-B2: no parent unit after the sub-workflow starts before the resume
    return repo, ex


def answer(repo: Path, ex: ScriptedExecutor, decision: str) -> Any:
    return resume(parent(), "T-1", repo, registry(ex), decision=decision, settings=NO_SLEEP)


def test_a_child_pause_pauses_the_parent_with_the_childs_payload(paused: tuple[Path, ScriptedExecutor]) -> None:  # SWF-AC1, AC 3
    repo, _ = paused
    row = status(state_root_path(repo), {"deliver": parent()})["threads"][0]
    assert row["state"] == "paused"
    assert [g["unit"] for g in row["pending_gates"]] == ["setup/work"]  # `status` shows the pause at the child's unit
    pause = [r for r in records(repo) if r["kind"] == "pause"][-1]
    assert pause["child"] == "setup" and pause["unit"] == "work" and pause["pause_kind"] == "approval"
    assert "proceed" in pause["decisions"]


def test_resume_proceed_releases_the_pause_and_the_run_goes_on(paused: tuple[Path, ScriptedExecutor]) -> None:  # SWF-AC1, AC 3
    repo, _ = paused
    ex = standin("claude", steps=[REVIEW], judges=[judge(), judge()])  # the child's outcome gate, then review
    out = answer(repo, ex, "proceed")
    assert out.exit_code is ExitCode.FINISHED, (out.message, out.payload)
    assert keys(ex) == ["setup/outcome.1.judge", "review.1.step", "review.1.judge"]  # the child's `work` did not run again


def test_another_decision_the_childs_gate_offers_answers_it_too(paused: tuple[Path, ScriptedExecutor]) -> None:  # SWF-AC1, AC 3
    repo, _ = paused
    ex = standin("claude", steps=[WORK], judges=[judge()])
    out = answer(repo, ex, "retry")
    assert out.exit_code is ExitCode.PAUSED and out.payload is not None and out.payload["unit"] == "setup/work"
    assert keys(ex) == ["setup/work.2.retry", "setup/work.2.judge"]  # the child's own retry, not a rerun of the parent's units
    assert answer(repo, standin("claude"), "back:draft").exit_code is ExitCode.USAGE  # not offered by the child's gate


def test_a_child_upgraded_under_the_pause_resumes_with_one_workflow_changed_record(
        tmp_path: Path, paused: tuple[Path, ScriptedExecutor]) -> None:  # SWF-AC1, AC 3
    repo, _ = paused
    register_workflow(home_dir(), tmp_path / "pkgs", "child", version="0.3.2", produces=["overview"], approval=True)
    ex = standin("claude", steps=[REVIEW], judges=[judge(), judge()])
    out = answer(repo, ex, "proceed")
    assert out.exit_code is ExitCode.FINISHED, (out.message, out.payload)
    changed = [r for r in records(repo) if r["kind"] == "workflow_changed"]
    assert len(changed) == 1 and changed[0]["child"] == "setup"
    assert changed[0]["from_version"].startswith("0.3.1") and changed[0]["to_version"].startswith("0.3.2")


def test_a_child_removed_under_the_pause_is_refused_naming_it_and_register_restores_it(
        tmp_path: Path, paused: tuple[Path, ScriptedExecutor]) -> None:  # SWF-AC1, AC 3
    repo, _ = paused
    remove_registry(home_dir())
    out = answer(repo, standin("claude"), "proceed")
    assert out.exit_code is ExitCode.USAGE and "child" in out.message and "workflows register" in out.message
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"], approval=True)  # `workflows register`
    ex = standin("claude", steps=[REVIEW], judges=[judge(), judge()])
    assert answer(repo, ex, "proceed").exit_code is ExitCode.FINISHED
