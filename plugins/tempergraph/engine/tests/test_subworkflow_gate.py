"""The parent's gate for a sub-workflow unit takes the child's verdict; the child's finalizer and outcome gate stay its own (SWF-B5, SWF-B8, SWF-B10; SWF-AC1; task AC 5)."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import Gate
from tempergraph.constants import ExitCode
from tempergraph.executors.capabilities import CLAUDE
from tempergraph.executors.standins import ScriptedExecutor, standin
from tempergraph.model.validate import errors, validate
from tempergraph.run.runner import resume

from .fixtures.subworkflows import FINALIZER_MARK, home_dir, register_workflow
from .test_run import DRAFT, REVIEW, judge, verdict_block
from .test_subworkflow_run import NO_SLEEP, WORK, go, keys, parent, records, registry

SCOPE_DEFECT = verdict_block("UNMET", defect_in="scope")
UNMET = verdict_block("UNMET")


@pytest.fixture
def scoped(tmp_path: Path) -> None:
    """A child that declares the input `scope`, which the parent maps from the `draft` unit's `notes`."""
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"], inputs=["scope"])


def scoped_parent(*back: str) -> Any:
    return parent({"scope": "draft.notes"}, gate=Gate(back_targets=list(back)))


def test_an_upstream_defect_in_a_mapped_key_sends_the_parent_back_once(repo: Path, scoped: None) -> None:  # SWF-AC1, AC 5
    ex = standin("claude", steps=[DRAFT, WORK, DRAFT, WORK, REVIEW],
                 judges=[judge(), judge(SCOPE_DEFECT), judge(), judge(), judge(), judge()])
    out = go(repo, ex, scoped_parent("draft"))
    assert out.exit_code is ExitCode.FINISHED, (out.message, out.payload)
    rows = records(repo)
    gates = [(r["verdict"], r["route_target"]) for r in rows if r["kind"] == "gate" and r["unit"] == "setup"
             and not r.get("child")]
    assert gates == [("BACK", "draft.step"), ("PROCEED", "review.step")]  # back to `draft` once, then through
    assert "sent back by `setup`" in ex.calls[4].request.prompt and "UNMET" in ex.calls[4].request.prompt  # the child's reason
    assert not [r for r in rows if r["kind"] == "human"]  # no person was asked


def test_an_upstream_defect_that_is_no_back_target_asks_a_person(repo: Path, scoped: None) -> None:  # SWF-AC1, AC 5
    ex = standin("claude", steps=[DRAFT, WORK], judges=[judge(), judge(SCOPE_DEFECT)])
    out = go(repo, ex, scoped_parent())
    assert out.exit_code is ExitCode.PAUSED and out.payload is not None
    assert out.payload["unit"] == "setup" and out.payload["kind"] == "escalation" and out.payload["reason"] == "upstream"
    assert "scope" in out.payload["blockers"][0]["problem"] or out.payload["blockers"][0]["defect_in"] == "scope"


def test_a_defect_in_a_key_nobody_mapped_stays_in_the_child(repo: Path, scoped: None) -> None:  # SWF-AC1, AC 5
    ex = standin("claude", steps=[DRAFT, WORK, WORK, REVIEW],
                 judges=[judge(), judge(verdict_block("UNMET", defect_in="other")), judge(), judge(), judge()])
    out = go(repo, ex, scoped_parent("draft"))
    assert out.exit_code is ExitCode.FINISHED, (out.message, out.payload)
    assert keys(ex)[2:5] == ["setup/work.1.step", "setup/work.1.judge", "setup/work.2.retry"]  # the child retried itself


def test_the_childs_retries_and_trips_back_stay_within_its_own_budgets(tmp_path: Path, repo: Path) -> None:  # SWF-AC1, AC 5
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"])
    ex = standin("claude", steps=[DRAFT, WORK, WORK, WORK], judges=[judge(), judge(UNMET), judge(UNMET), judge(UNMET)])
    out = go(repo, ex, parent())
    assert out.exit_code is ExitCode.PAUSED and out.payload is not None
    assert out.payload["unit"] == "setup/work" and out.payload["reason"] == "retry_budget"  # the child's budget, not the parent's
    budgets = [r for r in records(repo) if r["kind"] == "budget"]
    assert [(r.get("child"), r["unit"], r["counter"]) for r in budgets] == [("setup", "work", "retries")] * 2


@pytest.mark.parametrize("how", ["stop"])
def test_a_child_that_ends_unmet_fails_the_units_gate_with_its_failing_criteria(
        tmp_path: Path, repo: Path, how: str) -> None:  # SWF-AC1, AC 5
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"])
    spec = parent(gate=Gate(retry_budget=0))
    ex = standin("claude", steps=[DRAFT, WORK], judges=[judge(), judge(), judge(UNMET)])  # the outcome gate says UNMET
    out = go(repo, ex, spec)
    assert out.exit_code is ExitCode.PAUSED and out.payload["unit"] == "setup/outcome"  # the child asks a person
    out = resume(spec, "T-1", repo, registry(ScriptedExecutor(caps=CLAUDE)), decision=how, settings=NO_SLEEP)
    assert out.exit_code is ExitCode.PAUSED and out.payload is not None, (out.message, out.payload)
    assert out.payload["unit"] == "setup" and out.payload["kind"] == "budget"  # the unit's own gate, budget spent
    assert [b["criterion"] for b in out.payload["blockers"]] == ["done"]  # the child's failing final criterion


def last_unit(spec: Any) -> Any:
    return dataclasses.replace(spec, order=("draft", "review", "setup"))


def test_the_childs_finalizer_never_runs_and_its_outcome_gate_always_does(tmp_path: Path, repo: Path) -> None:  # SWF-AC1, AC 5
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"], finalizer=True)
    spec = last_unit(parent(produces=("overview",), finalizer=True, reads=False))
    ex = standin("claude", steps=[DRAFT, REVIEW, WORK], judges=[judge(), judge(), judge(), judge()])
    out = go(repo, ex, spec)
    assert out.exit_code is ExitCode.FINISHED, (out.message, out.payload)
    rows = records(repo)
    assert [r["unit"] for r in rows if r["kind"] == "judgement" and r.get("child") == "setup"] == ["work", "outcome"]
    assert len([r for r in rows if r["kind"] == "finalize"]) == 1 and not [r for r in rows if r["kind"] == "finalize" and r.get("child")]
    work = Path(next(r for r in rows if r["kind"] == "workspace")["path"])
    assert not (work / FINALIZER_MARK).exists() and (work / "parent-finalizer.txt").read_text() == "x"


def test_validation_warns_once_that_the_childs_finalizer_is_skipped(tmp_path: Path) -> None:  # SWF-AC1, AC 5
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"], finalizer=True)
    found = validate(parent(), {"claude": CLAUDE})
    warned = [f for f in found if f.code == "subworkflow-finalizer-skipped"]
    assert errors(found) == [] and len(warned) == 1 and warned[0].severity == "warning" and warned[0].unit == "setup"
    assert "child" in warned[0].message
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"])  # no finalizer: no warning
    assert not [f for f in validate(parent(), {"claude": CLAUDE}) if f.code == "subworkflow-finalizer-skipped"]
