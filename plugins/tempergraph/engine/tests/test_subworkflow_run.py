"""A parent run runs its sub-workflow child as one unit (SWF-B1, SWF-B7, SWF-B8, SWF-B10; SWF-AC1; task AC 1)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import Gate, Subworkflow, callable_ref
from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionRequest, SessionResult, WorkflowSpec
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import ScriptedExecutor, answer, standin
from tempergraph.run.finalize import FinalizerResult
from tempergraph.run.runner import RunSettings, start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.subworkflows import FINALIZER_MARK, home_dir, register_workflow
from .fixtures.workflows import two_step
from .test_run import DRAFT, REVIEW, judge, verdict_block

NO_SLEEP = RunSettings(sleep=lambda s: None)


def _work(req: SessionRequest) -> SessionResult:
    """The child's work step: it writes `overview.md` in the workspace it runs in and says so."""
    (req.workdir / "overview.md").write_text("an overview\n")
    return answer("Made the overview\nARTIFACT overview: overview.md", session_id="s-work")


WORK = _work
NOTHING = answer("Did the work, nothing to hand over", session_id="s-work")
UNMET = verdict_block("UNMET")
REQUEST_TEXT = "Release 1.2 notes"


def parent_finish(ctx: Any) -> FinalizerResult:
    """The parent's finalizer: it counts its calls in a file of the workspace."""
    with (ctx.workdir / "parent-finalizer.txt").open("a") as fh:
        fh.write("x")
    return FinalizerResult(outcome="done")


def parent(inputs: dict[str, str] | None = None, *, gate: Gate | None = None, produces: tuple[str, ...] = ("overview",),
           workflow: str = "child", finalizer: bool = False, name: str = "deliver", reads: bool = True) -> WorkflowSpec:
    """`draft`, then the sub-workflow unit `setup`, then `review`, whose prompt reads `{setup.overview}` (unless `reads` is off)."""
    base = two_step()
    review = base.units["review"]
    assert review.step is not None
    prompt = "Review {notes} with {setup.overview}" if reads and "overview" in produces else "Review {notes}"
    units = {"draft": base.units["draft"],
             "setup": Subworkflow(workflow=workflow, inputs=inputs or {"request": "request"}, produces=produces,
                                  **({"gate": gate} if gate is not None else {})),
             "review": dataclasses.replace(review, step=dataclasses.replace(review.step, prompt=prompt))}
    extra: dict[str, Any] = {}
    if finalizer:
        extra = {"finalizer": callable_ref(parent_finish), "finalizer_outcomes": ("done",)}
    return dataclasses.replace(base, name=name, units=units, order=("draft", "setup", "review"), **extra)


def registry(ex: ScriptedExecutor) -> Registry:
    r = Registry()
    r.register(ex)
    return r


def go(repo: Path, ex: ScriptedExecutor, spec: WorkflowSpec, task: str = "T-1", **kw: Any) -> Any:
    return start(spec, task, {"request": REQUEST_TEXT}, repo, registry(ex), dataclasses.replace(NO_SLEEP, **kw))


def records(repo: Path, task: str = "T-1", workflow: str = "deliver") -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), workflow, task) / "run.jsonl"
    return [json.loads(ln) for ln in p.read_text().splitlines()]


def keys(ex: ScriptedExecutor) -> list[str]:
    return [c.request.session_key for c in ex.calls]


@pytest.fixture
def child(tmp_path: Path) -> Path:
    return register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"])


def happy(ex_steps: list[Any] | None = None) -> ScriptedExecutor:
    """draft, the child's work, the child's outcome gate, then review: every verdict MET."""
    return standin("claude", steps=ex_steps or [DRAFT, WORK, REVIEW], judges=[judge(), judge(), judge(), judge()])


def test_the_child_runs_in_the_parents_worktree_and_the_next_unit_reads_its_key(repo: Path, child: Path) -> None:  # SWF-AC1, AC 1
    ex = happy()
    out = go(repo, ex, parent())
    assert out.exit_code is ExitCode.FINISHED, (out.message, out.payload)
    assert keys(ex) == ["draft.1.step", "draft.1.judge", "setup/work.1.step", "setup/work.1.judge",
                        "setup/outcome.1.judge", "review.1.step", "review.1.judge"]
    workdirs = {c.request.workdir for c in ex.calls if c.request.kind in ("step", "retry")}
    assert len(workdirs) == 1  # the child's step ran where the parent's did: the run worktree
    assert "overview.md" in ex.calls[-2].request.prompt  # `{setup.overview}` read by the unit after the child


def test_child_inputs_read_the_request_an_earlier_unit_and_a_literal(tmp_path: Path, repo: Path) -> None:  # SWF-AC1, AC 1
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"], inputs=["topic", "earlier", "tag"])
    spec = parent({"topic": "request", "earlier": "draft.notes", "tag": "'v9-literal'"})
    ex = happy()
    assert go(repo, ex, spec).exit_code is ExitCode.FINISHED
    prompt = next(c.request.prompt for c in ex.calls if c.request.session_key == "setup/work.1.step")
    assert REQUEST_TEXT in prompt and "notes.md" in prompt and "v9-literal" in prompt


def test_the_childs_gate_and_retries_are_its_own(repo: Path, child: Path) -> None:  # SWF-AC1, AC 1, CMP-AC3 (CMP-B14 sub-workflow)
    ex = standin("claude", steps=[DRAFT, WORK, WORK, REVIEW],
                 judges=[judge(), judge(UNMET), judge(), judge(), judge()])
    out = go(repo, ex, parent())
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert keys(ex)[2:7] == ["setup/work.1.step", "setup/work.1.judge", "setup/work.2.retry", "setup/work.2.judge",
                             "setup/outcome.1.judge"]
    gates = [(r.get("child"), r["unit"], r["verdict"]) for r in records(repo) if r["kind"] == "gate"]
    assert ("setup", "work", "RETRY") in gates and ("setup", "work", "PROCEED") in gates
    assert [g for g in gates if g[1] == "setup"] == [(None, "setup", "PROCEED")]  # the parent's gate ran once, on `produces`


def test_the_childs_outcome_gate_grades_its_final_criteria(repo: Path, child: Path) -> None:  # SWF-AC1, AC 1
    ex = happy()
    go(repo, ex, parent())
    outcome = [r for r in records(repo) if r["kind"] == "judgement" and r.get("child") == "setup"
               and r["unit"] == "outcome"]
    assert len(outcome) == 1 and [s["id"] for s in outcome[0]["statuses"]] == ["done"]


def test_a_produces_key_the_child_did_not_make_fails_the_gate_as_a_missing_artifact(
        tmp_path: Path, repo: Path) -> None:  # SWF-AC1, AC 1
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"], deliverables=False)
    ex = standin("claude", steps=[DRAFT, NOTHING], judges=[judge(), judge(), judge()])
    out = go(repo, ex, parent(gate=Gate(retry_budget=0), produces=("overview",)))
    assert out.exit_code is ExitCode.PAUSED, out.message  # the unit's gate failed and its budget is spent
    assert out.payload is not None and out.payload["unit"] == "setup"
    assert any("overview" in b["problem"] for b in out.payload["blockers"])


def test_every_child_record_carries_child_and_its_own_unit(repo: Path, child: Path) -> None:  # SWF-AC1, AC 1
    go(repo, happy(), parent())
    rows = records(repo)
    kids = [r for r in rows if r.get("child")]
    assert kids and {r["child"] for r in kids} == {"setup"}
    assert {r["unit"] for r in kids if r["kind"] in ("gate", "judgement", "unit_entered")} == {"work", "outcome"}
    sessions = [r for r in kids if r["kind"] == "agent_run"]
    assert [r["session_key"] for r in sessions] == ["setup/work.1.step", "setup/work.1.judge", "setup/outcome.1.judge"]
    assert [r["unit"] for r in sessions] == ["work", "work", "outcome"] and [r["attempt"] for r in sessions] == [1, 1, 1]
    assert not [r for r in rows if r["kind"] in ("gate", "agent_run") and r["unit"] in ("draft", "review", "setup")
                and r.get("child")]


def test_a_flag_reaches_the_child_as_unit_slash_child_unit_key(repo: Path, child: Path) -> None:  # SWF-AC1, AC 1
    ex = happy()
    out = go(repo, ex, parent(), flags={"setup/work.model": "small"})
    assert out.exit_code is ExitCode.FINISHED, out.message
    aliases = {c.request.session_key: c.request.alias for c in ex.calls if c.request.kind == "step"}
    assert aliases["setup/work.1.step"] == "small" and aliases["draft.1.step"] != "small"


def test_a_flag_naming_a_key_the_child_does_not_have_is_refused(repo: Path, child: Path) -> None:  # SWF-AC1, AC 1
    ex = happy()
    out = go(repo, ex, parent(), flags={"setup/nothing.model": "small"})
    assert out.exit_code is ExitCode.USAGE and ex.calls == []


def test_the_childs_declared_defaults_and_settings_flags_apply(tmp_path: Path, repo: Path) -> None:  # SWF-AC1, AC 1
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"], defaults=True)
    out = go(repo, happy(), parent(), flags={"setup/settings.depth": 5})
    assert out.exit_code is ExitCode.FINISHED, out.message
    bad = go(repo, happy(), parent(), task="T-2", flags={"setup/settings.depth": 99})
    assert bad.exit_code is ExitCode.USAGE  # the child's own declared bounds hold


def test_the_childs_own_workspace_is_ignored_with_one_note(tmp_path: Path, repo: Path) -> None:  # SWF-AC1, AC 1
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"], workspace="in_place")
    ex = happy()
    out = go(repo, ex, parent())
    assert out.exit_code is ExitCode.FINISHED, out.message
    notes = [r for r in records(repo) if r["kind"] == "note" and r.get("child") == "setup"]
    assert len(notes) == 1 and "run.workspace" in notes[0]["message"]
    assert len({c.request.workdir for c in ex.calls if c.request.kind == "step"}) == 1


def test_the_childs_finalizer_never_runs_and_the_parents_runs_once(tmp_path: Path, repo: Path) -> None:  # SWF-AC1, AC 1
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"], finalizer=True)
    ex = happy()
    out = go(repo, ex, parent(finalizer=True))
    assert out.exit_code is ExitCode.FINISHED, out.message
    rows = records(repo)
    assert [r["kind"] for r in rows if r.get("child") and r["kind"] == "finalize"] == []
    assert len([r for r in rows if r["kind"] == "finalize" and not r.get("child")]) == 1
    judged = [r for r in rows if r["kind"] == "judgement" and r.get("child") == "setup" and r["unit"] == "outcome"]
    assert len(judged) == 1  # the child's outcome gate ran
    row = next(r for r in rows if r["kind"] == "workspace")
    work = Path(row["path"])
    assert not (work / FINALIZER_MARK).exists()
    assert (work / "parent-finalizer.txt").read_text() == "x"
