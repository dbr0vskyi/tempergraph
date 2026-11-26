"""A judge's changed paths cover what its visit changed since the visit's entry commit, committed or not
(SRV-B34, SRV-B36, SRV-B11; SRV-AC21 to SRV-AC26, SRV-AC30, SRV-AC31; task AC 1 to AC 7).

Every fixture is an engine run on a scratch repository. The unit's `after` script commits the step's files, as a
workflow's own script does (the engine makes no commit). Nothing here names a workflow package.
"""

from __future__ import annotations

import dataclasses
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import Gate, Judge, Routing, Script, Step, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionRequest, SessionResult, WorkflowSpec
from tempergraph.executors.standins import ScriptedExecutor, answer, standin
from tempergraph.improve import digest, review
from tempergraph.improve.record import judged_units, read_findings
from tempergraph.store.layout import state_root_path

from .fixtures.subworkflows import home_dir, register_workflow
from .fixtures.workflows import crit, named, two_step
from .test_run import DRAFT, MET, REVIEW, go, judge, records, verdict_block, with_outcome_spec
from .test_session_review import read, session
from .test_subworkflow_run import go as go_parent
from .test_subworkflow_run import parent
from .test_subworkflow_run import records as parent_records

Step_ = Callable[[SessionRequest], SessionResult]


def commit_in(workdir: Path) -> None:
    """Commit whatever the workspace holds, as a workflow's own script does; nothing to commit is no error."""
    subprocess.run(["git", "add", "-A", "--", ".", ":(exclude).tempergraph"], cwd=workdir, check=True,
                   capture_output=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "step"],
                   cwd=workdir, check=False, capture_output=True)


def commit_script(ctx: Any) -> dict[str, str]:
    commit_in(Path(ctx.workdir))
    return {}


def writes(*names: str, text: str = "x\n", also: Callable[[Path], None] | None = None) -> Step_:
    """A step reply that writes the named files into the workspace it runs in."""

    def reply(req: SessionRequest) -> SessionResult:
        for name in names:
            (req.workdir / name).write_text(text)
        if also is not None:
            also(req.workdir)
        return answer("Built.", session_id="s")

    return reply


def one_unit(*, commits: bool = True) -> WorkflowSpec:
    """One unit `build`; with `commits` its `after` script commits whatever the step wrote."""
    units = {"build": Step(prompt="Build {request}", tools=["read", "write"],
                           after=[Script(call=commit_script)] if commits else [],
                           gate=Gate(judge=Judge(stance="V."), criteria=[crit("c1")]))}
    spec = named(Workflow(order=["build"], units=units, issue_repository="acme/x",
                          routing=Routing(description="Build and commit")))
    return dataclasses.replace(spec, session_review="off")


def judge_run(repo: Path, task: str, key: str) -> dict[str, Any]:
    """The `agent_run` record of one judge session."""
    return next(r for r in records(repo, task) if r["kind"] == "agent_run" and r["session_key"] == key)


def judge_digest(repo: Path, task: str, key: str) -> dict[str, Any]:
    doc = digest.read(state_root_path(repo), "demo", task, key)
    assert doc is not None, key
    return doc


def causes_of(repo: Path, task: str) -> set[tuple[str, str]]:
    return {(str(f["unit"]), str(f["cause"])) for f in read_findings(state_root_path(repo), "demo", task)}


# -- the digest and the findings of a judge whose visit committed its work ------------------------------------------


def test_a_judge_that_opens_none_of_the_committed_files_and_passes_is_unread(repo: Path) -> None:  # SRV-AC21, AC 4
    ex = standin("claude", steps=[writes("a.md", "b.md")], judges=[judge()])
    assert go(repo, ex, one_unit(), task="J-1").exit_code is ExitCode.FINISHED
    d = judge_digest(repo, "J-1", "build.1.judge")
    assert d["changed_total"] == 2 and d["changed_read"] == 0
    assert ("build", "judge_unread_pass") in causes_of(repo, "J-1")


def test_a_judge_that_opens_one_of_ten_committed_files_read_a_part(repo: Path) -> None:  # SRV-AC22, AC 5
    names = [f"f{i}.md" for i in range(10)]
    ex = standin("claude", steps=[writes(*names)], judges=[judge()])
    assert go(repo, ex, one_unit(), task="J-2").exit_code is ExitCode.FINISHED
    rec = judge_run(repo, "J-2", "build.1.judge")
    assert sorted(rec["changed_paths"]) == sorted(names)
    # the stand-in executor's tool events carry no capability or input summary: the judge's own session folder is
    # written with the one read, and the digest is built again from the engine run's own record
    root = state_root_path(repo)
    sdir = session(root, "J-2", "build.1.judge", [read("f0.md")])
    d = digest.build(sdir, rec, changed=rec["changed_paths"])
    assert d["changed_total"] == 10 and d["changed_read"] == 1
    found = digest.causes([d], judged=judged_units(records(repo, "J-2")))
    assert {(c["unit"], c["cause"]) for c in found} == {("build", "judge_partial_read")}


def test_the_citation_check_keeps_a_judge_unread_observation_of_the_committed_work(repo: Path) -> None:  # SRV-AC23, AC 6
    ex = standin("claude", steps=[writes("a.md", "b.md")], judges=[judge()])
    assert go(repo, ex, one_unit(), task="J-3").exit_code is ExitCode.FINISHED
    d = judge_digest(repo, "J-3", "build.1.judge")
    seen = {"category": "judge_unread", "turns": [1], "remedy_class": "brief"}
    assert review.check(seen, d, [1]) == "kept"


# -- what the count is: a unit that commits nothing, a retry, a trip back ------------------------------------------


def test_a_unit_that_commits_nothing_gives_the_modified_and_untracked_paths(repo: Path) -> None:  # SRV-AC24, AC 7

    def modify(workdir: Path) -> None:
        (workdir / "README.md").write_text("changed\n")

    ex = standin("claude", steps=[writes("new.md", also=modify)], judges=[judge()])
    assert go(repo, ex, one_unit(commits=False), task="J-4").exit_code is ExitCode.FINISHED
    rec = judge_run(repo, "J-4", "build.1.judge")
    assert sorted(rec["changed_paths"]) == ["README.md", "new.md"]
    assert judge_digest(repo, "J-4", "build.1.judge")["changed_total"] == 2


def test_a_retrys_judge_counts_the_whole_visit(repo: Path) -> None:  # SRV-AC25, AC 1
    ex = standin("claude", steps=[writes("a.md"), writes("b.md")], judges=[judge(verdict_block("UNMET")), judge()])
    assert go(repo, ex, one_unit(), task="J-5").exit_code is ExitCode.FINISHED
    assert [c.request.session_key for c in ex.calls] == ["build.1.step", "build.1.judge", "build.2.retry",
                                                         "build.2.judge"]
    assert judge_digest(repo, "J-5", "build.1.judge")["changed_total"] == 1
    assert judge_digest(repo, "J-5", "build.2.judge")["changed_total"] == 2  # a.md of attempt 1 and b.md of attempt 2


def test_a_visit_begun_by_a_trip_back_counts_that_visit_only(repo: Path) -> None:  # SRV-AC26, AC 1
    def draft(req: SessionRequest) -> SessionResult:
        (req.workdir / "notes.md").write_text("the notes\n")  # the second visit writes the same content again
        return answer("Wrote notes.md\nARTIFACT notes: notes.md", session_id="s-draft")

    base = two_step()
    assert base.units["draft"].step is not None
    step = dataclasses.replace(base.units["draft"].step, after=(Script(call=commit_script),))
    spec = dataclasses.replace(base, units={**base.units, "draft": dataclasses.replace(base.units["draft"], step=step)},
                               session_review="off")
    ex = standin("claude", steps=[draft, REVIEW, draft, REVIEW],
                 judges=[judge(), judge(verdict_block("UNMET", defect_in="notes")), judge(), judge()])
    assert go(repo, ex, spec, task="J-6").exit_code is ExitCode.FINISHED
    drafts = [r for r in records(repo, "J-6") if r["kind"] == "agent_run" and r["session_key"].startswith("draft.")
              and r["session_key"].endswith(".judge")]
    assert [len(r["changed_paths"]) for r in drafts] == [1, 0]  # the first visit wrote the file, the second did not
    assert [judge_digest(repo, "J-6", r["session_key"])["changed_total"] for r in drafts] == [1, 0]


# -- a gate whose unit has no step session counts from its own unit's entry ------------------------------------------


@pytest.fixture
def child(tmp_path: Path) -> Path:
    return register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"])


def test_a_sub_workflow_unit_counts_from_its_own_entry(repo: Path, child: Path) -> None:  # SRV-AC30, AC 3
    def work(req: SessionRequest) -> SessionResult:
        (req.workdir / "overview.md").write_text("an overview\n")
        commit_in(req.workdir)  # the child committed its work before the parent's gate for the unit judges it
        return answer("Made the overview\nARTIFACT overview: overview.md", session_id="s-work")

    gate = Gate(judge=Judge(stance="V."), criteria=[crit("c1")])
    ex: ScriptedExecutor = standin("claude", steps=[DRAFT, work, REVIEW], judges=[judge() for _ in range(6)])
    out = go_parent(repo, ex, parent(gate=gate), task="J-7")
    assert out.exit_code is ExitCode.FINISHED, (out.message, out.payload)
    mine = [r for r in parent_records(repo, "J-7") if r["kind"] == "agent_run" and r["session_key"] == "setup.1.judge"]
    assert len(mine) == 1 and mine[0]["changed_paths"] == ["overview.md"]
    d = digest.read(state_root_path(repo), "deliver", "J-7", "setup.1.judge")
    assert d is not None and d["changed_total"] == 1


def test_the_outcome_gate_counts_from_its_own_entry(repo: Path) -> None:  # SRV-AC31, AC 3
    def draft(req: SessionRequest) -> SessionResult:
        (req.workdir / "notes.md").write_text("the notes\n")
        return answer("Wrote notes.md\nARTIFACT notes: notes.md", session_id="s-draft")

    spec = with_outcome_spec()
    step = dataclasses.replace(spec.units["draft"].step, after=(Script(call=commit_script),))
    spec = dataclasses.replace(spec, units={**spec.units, "draft": dataclasses.replace(spec.units["draft"], step=step)},
                               session_review="off")
    met2 = verdict_block("MET", "MET")
    ex = standin("claude", steps=[draft, REVIEW], judges=[judge(met2), judge(MET), judge(MET, sid="o")])
    out = go(repo, ex, spec, task="J-8")
    assert out.exit_code is ExitCode.FINISHED, out.message
    outcome = [r for r in records(repo, "J-8") if r["kind"] == "agent_run" and r["session_key"].startswith("outcome.")
               and r["session_key"].endswith(".judge")]
    assert len(outcome) == 1 and outcome[0]["changed_paths"] == []  # every unit committed its work before the gate
    assert judge_digest(repo, "J-8", outcome[0]["session_key"])["changed_total"] == 0
