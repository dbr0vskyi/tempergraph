"""A judge's changed paths are its own list: declared file artifacts, the gate's `judge_may_skip` patterns, deleted
paths and the recorded base (SRV-B34, SRV-B37 to SRV-B43, SRV-B44; SRV-AC32 to SRV-AC43, SRV-AC48, SRV-AC49; task AC 1
to AC 5).

Every fixture is an engine run on a scratch repository with stand-in sessions that open paths through `reads=`; no
journal is written by hand. Nothing here names a workflow package.
"""

from __future__ import annotations

import dataclasses
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tempergraph import git as gitmod
from tempergraph.api import Gate, Judge, Routing, Script, Step, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import CheckFinding, SessionRequest, SessionResult, WorkflowSpec
from tempergraph.executors.standins import answer, standin
from tempergraph.improve.record import read_findings
from tempergraph.run.nodes import EngineNodes
from tempergraph.store.layout import state_root_path

from .fixtures.workflows import crit, named
from .test_judge_changed_paths import causes_of, commit_script, judge_digest, judge_run
from .test_judge_changed_paths_map import item_writes, plan_commits
from .test_map import THREE, item_ok, mapped
from .test_map import run as map_go
from .test_run import MET, go, judge, records, verdict_block

Reply = Callable[[SessionRequest], SessionResult]


def build_gate(*skip: str) -> Any:
    return Gate(judge=Judge(stance="V."), criteria=[crit("c1")], judge_may_skip=skip)


def flow_of(units: dict[str, Any]) -> WorkflowSpec:
    spec = named(Workflow(order=list(units), units=units, issue_repository="acme/x",
                          routing=Routing(description="Build and judge")))
    return dataclasses.replace(spec, session_review="off")


def build_unit(*skip: str, commits: bool = False, produces: dict[str, str] | None = None) -> Any:
    return Step(prompt="Build {request}", tools=["read", "write"], produces=produces or {},
                after=[Script(call=commit_script)] if commits else [], gate=build_gate(*skip))


def plain_unit(produces: dict[str, str]) -> Any:
    return Step(prompt="Prepare {request}", tools=["read", "write"], produces=produces, gate=build_gate())


def put(req: SessionRequest, name: str, text: str = "x\n") -> None:
    path = req.workdir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def writer(*names: str, artifact: str = "", text: str = "x\n") -> Reply:
    """A step reply that writes the named files; `artifact` is the line it reports (`key: value`)."""

    def reply(req: SessionRequest) -> SessionResult:
        for n in names:
            put(req, n, text)
        tail = f"\nARTIFACT {artifact}" if artifact else ""
        return answer("Built." + tail, session_id="s")

    return reply


def opened(*paths: str, text: str = MET) -> SessionResult:
    return answer(text, tools=("Read",), session_id="j", reads=paths)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def entered(repo: Path, task: str, unit: str) -> dict[str, Any]:
    return next(r for r in records(repo, task) if r["kind"] == "unit_entered" and r["unit"] == unit)


# -- declared file artifacts leave the counts (SRV-B41) --------------------------------------------------------------


def test_a_declared_notes_file_is_left_out_and_a_judge_that_opened_only_it_is_unread(repo: Path) -> None:  # SRV-AC38, AC 1
    spec = flow_of({"build": build_unit(produces={"notes": "file"})})
    steps = [writer("notes.md", "a.md", "b.md", "c.md", artifact="notes: notes.md")]
    ex = standin("claude", steps=steps, judges=[opened("notes.md")])
    assert go(repo, ex, spec, task="S-1").exit_code is ExitCode.FINISHED
    d = judge_digest(repo, "S-1", "build.1.judge")
    assert d["changed_total"] == 3 and d["changed_read"] == 0
    assert ("build", "judge_unread_pass") in causes_of(repo, "S-1")


def test_an_earlier_units_declared_file_in_any_spelling_is_left_out_of_a_later_judge(repo: Path) -> None:  # SRV-AC39, AC 1
    def memo(req: SessionRequest) -> SessionResult:
        put(req, "memo.md")
        return answer(f"Made.\nARTIFACT memo: {req.workdir / 'memo.md'}", session_id="s")

    spec = flow_of({"draft": plain_unit({"notes": "file"}), "memo": plain_unit({"memo": "file"}),
                    "build": build_unit()})
    steps = [writer("notes.md", artifact="notes: ./notes.md"), memo, writer("x.md", "y.md")]
    ex = standin("claude", steps=steps, judges=[judge(), judge(), opened()])
    assert go(repo, ex, spec, task="S-2").exit_code is ExitCode.FINISHED
    rec = judge_run(repo, "S-2", "build.1.judge")
    assert sorted(rec["changed_paths"]) == ["x.md", "y.md"]
    assert judge_digest(repo, "S-2", "build.1.judge")["changed_total"] == 2


# -- the gate's patterns (SRV-B42, SRV-B43, SRV-B34) -----------------------------------------------------------------

FOUR = ("generated/a.md", "generated/b.md", "c.md", "d.md")


def test_a_gate_pattern_leaves_its_paths_out_of_the_count(repo: Path) -> None:  # SRV-AC40, SRV-AC41, AC 2
    spec = flow_of({"build": build_unit("generated/**")})
    ex = standin("claude", steps=[writer(*FOUR)], judges=[judge()])
    assert go(repo, ex, spec, task="S-3").exit_code is ExitCode.FINISHED
    assert judge_digest(repo, "S-3", "build.1.judge")["changed_total"] == 2
    assert judge_run(repo, "S-3", "build.1.judge")["changed_left_out"] == 2


def test_the_same_files_with_no_pattern_all_count(repo: Path) -> None:  # SRV-AC40, SRV-AC41, AC 2
    spec = flow_of({"build": build_unit()})
    ex = standin("claude", steps=[writer(*FOUR)], judges=[judge()])
    assert go(repo, ex, spec, task="S-4").exit_code is ExitCode.FINISHED
    assert judge_digest(repo, "S-4", "build.1.judge")["changed_total"] == 4
    assert judge_run(repo, "S-4", "build.1.judge")["changed_left_out"] == 0


def test_the_cap_of_200_applies_after_paths_are_left_out(repo: Path) -> None:  # SRV-AC49, AC 2
    spec = flow_of({"build": build_unit("generated/**")})
    names = [f"generated/f{i}.md" for i in range(250)] + ["a.md", "b.md", "c.md"]
    ex = standin("claude", steps=[writer(*names)], judges=[judge()])
    assert go(repo, ex, spec, task="S-5").exit_code is ExitCode.FINISHED
    assert judge_digest(repo, "S-5", "build.1.judge")["changed_total"] == 3


# -- deleted paths and names git quotes (SRV-B39, SRV-B40) -----------------------------------------------------------


def with_tracked(repo: Path, *names: str) -> None:
    for n in names:
        (repo / n).write_text("tracked\n")
    git(repo, "add", *names)
    git(repo, "commit", "-q", "-m", "more")


def test_a_deleted_path_is_no_changed_path_of_the_judge_and_quoted_names_match(repo: Path) -> None:  # SRV-AC36, SRV-AC37, AC 3
    with_tracked(repo, "t1.md")

    def visit(req: SessionRequest) -> SessionResult:
        (req.workdir / "t1.md").unlink()
        put(req, "with space.md")
        put(req, "café.md")
        return answer("Built.", session_id="s")

    ex = standin("claude", steps=[visit], judges=[opened("with space.md", "café.md")])
    assert go(repo, ex, flow_of({"build": build_unit()}), task="S-6").exit_code is ExitCode.FINISHED
    d = judge_digest(repo, "S-6", "build.1.judge")
    assert d["changed_total"] == 2 and d["changed_read"] == 2


def test_two_deleted_paths_and_one_added_leave_one_and_a_rewritten_path_counts_once(repo: Path) -> None:  # SRV-AC36, AC 3
    with_tracked(repo, "t1.md", "t2.md")

    def visit(req: SessionRequest) -> SessionResult:
        (req.workdir / "t1.md").unlink()
        (req.workdir / "t2.md").unlink()
        put(req, "new.md")
        return answer("Built.", session_id="s")

    ex = standin("claude", steps=[visit], judges=[judge()])
    assert go(repo, ex, flow_of({"build": build_unit()}), task="S-7").exit_code is ExitCode.FINISHED
    assert judge_digest(repo, "S-7", "build.1.judge")["changed_total"] == 1

    again = standin("claude", steps=[writer("t1.md", text="rewritten\n")], judges=[judge()])
    git(repo, "worktree", "prune")
    assert go(repo, again, flow_of({"build": build_unit()}), task="S-8").exit_code is ExitCode.FINISHED
    assert judge_digest(repo, "S-8", "build.1.judge")["changed_total"] == 1


def seen_by_check(ctx: Any) -> Any:
    from tempergraph.api import CheckResult

    ok = "t1.md" in ctx.changed_paths  # CHK-B10: a check still receives the deleted path
    return CheckResult(result="PASS" if ok else "FAIL", evidence="deleted path listed" if ok else "not listed",
                       findings=[CheckFinding(status="pass" if ok else "fail", criterion="c1")])


def test_checks_and_the_sessions_own_record_still_list_a_deleted_path(repo: Path) -> None:  # SRV-AC36, CHK-B10, SIL-B33, AC 3
    with_tracked(repo, "t1.md")

    def visit(req: SessionRequest) -> SessionResult:
        (req.workdir / "t1.md").unlink()
        put(req, "new.md")
        return answer("Built.", session_id="s")

    gate = Gate(check=seen_by_check, judge=Judge(stance="V."), criteria=[crit("c1")])
    unit = dataclasses.replace(build_unit(), gate=gate)
    ex = standin("claude", steps=[visit], judges=[judge()])
    out = go(repo, ex, flow_of({"build": unit}), task="S-9")
    assert out.exit_code is ExitCode.FINISHED, out.message
    step = next(r for r in records(repo, "S-9") if r["kind"] == "agent_run" and r["session_key"] == "build.1.step")
    assert "t1.md" in step["wrote_paths"]
    assert judge_run(repo, "S-9", "build.1.judge")["changed_paths"] == ["new.md"]


def test_the_judge_helper_leaves_changed_paths_as_it_was(tmp_path: Path) -> None:  # SRV-AC36, SIL-B33, AC 3
    root = tmp_path / "r"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.invalid")
    git(root, "config", "user.name", "T")
    (root / "gone.md").write_text("x\n")
    git(root, "add", "gone.md")
    git(root, "commit", "-q", "-m", "init")
    base = gitmod.head(root)
    (root / "gone.md").unlink()
    (root / "café x.md").write_text("x\n")
    assert "gone.md" in gitmod.changed_paths(root, base)
    assert gitmod.judge_changed_paths(root, base, 200) == ["café x.md"]
    assert gitmod.base_problem(root, base) is None


# -- the base of the count (SRV-B34, SRV-B37) ------------------------------------------------------------------------


def test_the_judge_record_holds_the_commit_the_visit_was_entered_at(repo: Path) -> None:  # SRV-AC32, AC 4
    ex = standin("claude", steps=[writer("a.md")], judges=[judge()])
    assert go(repo, ex, flow_of({"build": build_unit()}), task="S-10").exit_code is ExitCode.FINISHED
    rec = judge_run(repo, "S-10", "build.1.judge")
    assert rec["changed_base"] == entered(repo, "S-10", "build")["head_commit"]
    assert "changed_base_reason" not in rec or rec["changed_base_reason"] is None


@pytest.mark.parametrize(("entry", "reason"), [("", "no_entry_commit"), ("0" * 40, "commit_unknown")])
def test_an_entry_that_is_missing_or_unknown_to_git_leaves_no_base(repo: Path, monkeypatch: pytest.MonkeyPatch,
                                                                   entry: str, reason: str) -> None:  # SRV-AC33, AC 4
    monkeypatch.setattr(EngineNodes, "_entry_commit", lambda self, unit, visit: entry)
    ex = standin("claude", steps=[writer("a.md")], judges=[judge()])
    assert go(repo, ex, flow_of({"build": build_unit()}), task=f"S-{reason}").exit_code is ExitCode.FINISHED
    rec = judge_run(repo, f"S-{reason}", "build.1.judge")
    assert rec["changed_base"] is None and rec["changed_base_reason"] == reason
    assert rec.get("changed_paths", []) == []


def test_a_workspace_outside_a_repository_has_no_base(tmp_path: Path) -> None:  # SRV-AC33, AC 4
    plain = tmp_path / "plain"
    plain.mkdir()
    assert gitmod.base_problem(plain, "a" * 40) == "outside_repository"
    assert gitmod.base_problem(plain, "") == "outside_repository"  # it comes before the entry's own problems


def test_a_clean_visit_with_a_base_counts_nothing(repo: Path) -> None:  # SRV-AC35, AC 4
    ex = standin("claude", steps=[writer()], judges=[judge()])
    assert go(repo, ex, flow_of({"build": build_unit()}), task="S-11").exit_code is ExitCode.FINISHED
    d = judge_digest(repo, "S-11", "build.1.judge")
    assert d["changed_total"] == 0 and d["changed_read"] == 0
    assert judge_run(repo, "S-11", "build.1.judge")["changed_base"] is not None


def test_an_untracked_file_held_at_entry_and_a_modified_one_both_count(repo: Path) -> None:  # SRV-AC48, AC 4
    def modify(req: SessionRequest) -> SessionResult:
        (req.workdir / "README.md").write_text("changed\n")
        return answer("Built.", session_id="s")

    spec = flow_of({"prep": plain_unit({}), "build": build_unit()})
    ex = standin("claude", steps=[writer("held.md"), modify], judges=[judge(), judge()])
    assert go(repo, ex, spec, task="S-12").exit_code is ExitCode.FINISHED
    assert judge_digest(repo, "S-12", "build.1.judge")["changed_total"] == 2


# -- a map's judgements are read item by item (SRV-B44) --------------------------------------------------------------


def finding_counts(repo: Path, task: str, cause: str) -> dict[str, int]:
    return {str(f["unit"]): int(f["count"]) for f in read_findings(state_root_path(repo), "demo", task)
            if f["cause"] == cause}


def test_only_the_item_whose_judge_passed_unread_is_a_finding(repo: Path) -> None:  # SRV-AC43, SRV-AC42, AC 5
    steps = [plan_commits(THREE[:2]), item_writes, item_writes, answer("Joined.", session_id="join")]
    judges = [judge(), judge(), judge(verdict_block("UNMET")), judge()]
    map_run(repo, steps, judges, "SM-1", retry_budget=0)
    assert finding_counts(repo, "SM-1", "judge_unread_pass").get("phase") == 1  # p1's, not p2's failed judge
    steps = [plan_commits(THREE), item_writes, item_writes, item_writes, answer("Joined.", session_id="join")]
    map_run(repo, steps, [judge(), judge(), judge(verdict_block("UNMET")), judge(), judge()], "SM-2", retry_budget=0)
    assert finding_counts(repo, "SM-2", "judge_unread_pass").get("phase") == 1  # three items: still p1's only


def test_a_partial_read_is_a_finding_for_the_item_that_gave_a_judgement_only(repo: Path) -> None:  # SRV-AC43, AC 5
    def ten(req: SessionRequest) -> SessionResult:
        _, iid, _, _ = req.session_key.split(".")
        for n in range(10):
            (req.workdir / f"{iid}-f{n}.md").write_text("x\n")
        return item_ok()

    timed_out = dataclasses.replace(opened("p2-f0.md"), ok=False, timed_out=True)
    steps = [plan_commits(THREE[:2]), ten, ten, answer("Joined.", session_id="join")]
    map_run(repo, steps, [judge(), opened("p1-f0.md"), timed_out, judge()], "SM-3", retry_budget=0)
    assert finding_counts(repo, "SM-3", "judge_partial_read").get("phase") == 1


def test_a_map_items_declared_file_is_left_out_for_every_items_judge(repo: Path) -> None:  # SRV-AC38, SRV-B41, AC 1
    def two_files(req: SessionRequest) -> SessionResult:
        _, iid, _, _ = req.session_key.split(".")
        (req.workdir / f"out-{iid}.md").write_text("x\n")
        (req.workdir / f"extra-{iid}.md").write_text("x\n")
        return answer(f"Did it.\nARTIFACT note: done\nARTIFACT out: out-{iid}.md", session_id="item")

    steps = [plan_commits(THREE[:2]), two_files, two_files, answer("Joined.", session_id="join")]
    map_run(repo, steps, [judge(), judge(), judge(), judge()], "SM-4", produces={"out": "file"}, commits=False)
    # nothing is committed after the plan: p2's judge still holds p1's files, and `out[p1]` is as declared as `out[p2]`
    assert judge_digest(repo, "SM-4", "phase.p1.1.judge")["changed_total"] == 1
    assert judge_digest(repo, "SM-4", "phase.p2.1.judge")["changed_total"] == 2


def map_run(repo: Path, steps: list[Any], judges: list[Any], task: str, **kw: Any) -> Any:
    spec = mapped(retry_budget=kw.get("retry_budget", 1))
    phase = spec.units["phase"]
    step = dataclasses.replace(phase.step, after=(Script(call=commit_script),) if kw.get("commits", True) else (),
                               produces={**phase.step.produces, **kw.get("produces", {})})
    spec = dataclasses.replace(spec, units={**spec.units, "phase": dataclasses.replace(phase, step=step)},
                               session_review="off")
    out, _ = map_go(repo, spec, steps, judges, task=task)
    return out


