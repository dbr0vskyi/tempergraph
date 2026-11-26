"""`cleanup: on_finish` against real git worktrees (WTR-B23, WTR-B11, WTR-B22, WTR-B17; WTR-AC3, WTR-AC5)."""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tempergraph import workspace as wsmod
from tempergraph.constants import ExitCode
from tempergraph.contracts import WorktreeDecl
from tempergraph.executors.standins import standin
from tempergraph.git import GitError
from tempergraph.run.runner import resume
from tempergraph.store.layout import ensure_state_root, state_root_path
from tempergraph.workspace import (
    WorkspaceRecord,
    list_worktrees,
    prepare_workspace,
    release_workspace,
    resolve_workspace,
)

from .fixtures.workflows import two_step
from .test_run import DRAFT, NO_SLEEP, REVIEW, go, judge, records, registry, verdict_block

ON_FINISH = {"run.worktree.cleanup": "on_finish"}


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def workspace_actions(repo: Path, task: str = "T-1") -> list[str]:
    return [r["action"] for r in records(repo, task) if r["kind"] == "workspace"]


def finished_run(repo: Path, task: str = "T-1", *, step: Any = DRAFT, **kw: Any) -> Path:
    ex = standin("claude", steps=[step, REVIEW], judges=[judge(), judge()])
    out = go(repo, ex, task=task, **kw)
    assert out.exit_code is ExitCode.FINISHED, out.message
    return Path(next(r for r in records(repo, task) if r["kind"] == "workspace")["path"])


def test_a_clean_finished_run_is_removed_and_its_branch_stays(repo: Path) -> None:  # WTR-AC5, WTR-AC3 (WTR-B23, WTR-B11)
    wt = finished_run(repo, flags=ON_FINISH)
    assert not wt.exists()
    assert "tg/demo/T-1" in git(repo, "branch", "--list")  # never deletes a branch
    assert list_worktrees(repo) == [] and str(wt) not in git(repo, "worktree", "list")
    assert workspace_actions(repo) == ["prepared", "released", "removed"]  # released, then removed


def test_without_cleanup_nothing_is_removed(repo: Path) -> None:  # WTR-AC5 (WTR-B23)
    wt = finished_run(repo)
    assert wt.exists() and workspace_actions(repo) == ["prepared", "kept"]


def test_a_dirty_worktree_is_kept_with_the_reason(repo: Path) -> None:  # WTR-AC3 (WTR-B11)
    def stray(req: Any) -> Any:
        (req.workdir / "stray.txt").write_text("a person's file\n")
        return DRAFT

    wt = finished_run(repo, step=stray, flags=ON_FINISH)
    assert wt.exists() and (wt / "stray.txt").exists()
    recs = [r for r in records(repo) if r["kind"] == "workspace"]
    assert [r["action"] for r in recs] == ["prepared", "released", "kept"]
    assert recs[-1]["reason"] == "dirty"
    assert "tg/demo/T-1" in git(repo, "branch", "--list")


def test_the_workflows_own_cleanup_is_the_default(repo: Path) -> None:  # WTR-AC5 (WTR-B17, WTR-B19)
    spec = dataclasses.replace(two_step(), worktree=WorktreeDecl(cleanup="on_finish"))
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    assert go(repo, ex, spec).exit_code is ExitCode.FINISHED
    assert workspace_actions(repo) == ["prepared", "released", "removed"]


def test_a_paused_run_keeps_its_worktree_and_cleanup_can_change_at_resume(repo: Path) -> None:
    # WTR-AC5 (WTR-B23: anything of an unfinished run stays), WTR-B17: `run.worktree.cleanup` changes at resume
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    assert go(repo, ex, flags=ON_FINISH).exit_code is ExitCode.PAUSED
    wt = Path(next(r for r in records(repo) if r["kind"] == "workspace")["path"])
    assert wt.exists()  # nothing of an unfinished run is removed
    ex.steps, ex.judges = [REVIEW], [judge()]
    out = resume(two_step(), "T-1", repo, registry(ex), decision="proceed",
                 settings=dataclasses.replace(NO_SLEEP, flags={"run.worktree.cleanup": "never"}))
    assert out.exit_code is ExitCode.FINISHED and wt.exists()  # changed at resume: kept
    assert workspace_actions(repo)[-1] == "kept"


def test_cleanup_set_at_resume_removes_at_the_finish(repo: Path) -> None:  # WTR-AC5 (WTR-B17)
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    assert go(repo, ex).exit_code is ExitCode.PAUSED
    wt = Path(next(r for r in records(repo) if r["kind"] == "workspace")["path"])
    ex.steps, ex.judges = [REVIEW], [judge()]
    out = resume(two_step(), "T-1", repo, registry(ex), decision="proceed",
                 settings=dataclasses.replace(NO_SLEEP, flags=ON_FINISH))
    assert out.exit_code is ExitCode.FINISHED and not wt.exists()
    assert workspace_actions(repo)[-2:] == ["released", "removed"]


def test_resume_refuses_a_start_only_setting(repo: Path) -> None:  # WTR-AC3 (WTR-B15, WTR-B17)
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    assert go(repo, ex).exit_code is ExitCode.PAUSED
    for key, value in (("run.worktree.base", "default_branch"), ("run.worktree.root", "in_repo"),
                       ("run.worktree.branch_prefix", "x"), ("run.workspace", "in_place")):
        out = resume(two_step(), "T-1", repo, registry(ex), decision="proceed",
                     settings=dataclasses.replace(NO_SLEEP, flags={key: value}))
        assert out.exit_code is ExitCode.USAGE and out.reason == "fixed_at_start", key


# -- release_workspace on real worktrees -----------------------------------------------------------------------


def prepared(repo: Path, task: str = "T-1") -> tuple[WorkspaceRecord, Path]:
    root = ensure_state_root(state_root_path(repo))
    plan = resolve_workspace(two_step(), repo, task_id=task)
    return prepare_workspace(f"demo/{task}", plan, None, root), root


def test_submodules_keep_the_worktree(repo: Path) -> None:  # WTR-AC5 (WTR-B23)
    (repo / ".gitmodules").write_text('[submodule "x"]\n\tpath = x\n\turl = ./x\n')
    git(repo, "add", ".gitmodules")
    git(repo, "commit", "-q", "-m", "gitmodules")
    rec, root = prepared(repo)
    done = release_workspace(rec, "on_finish", root)
    assert Path(rec.path).exists() and done.action == "kept"
    assert done.cleanup == [{"name": "run", "path": rec.path, "result": "kept", "reason": "submodules"}]


def test_a_worktree_locked_by_someone_else_is_kept(repo: Path) -> None:  # WTR-AC5 (WTR-B23)
    rec, root = prepared(repo)
    git(repo, "worktree", "unlock", rec.path)
    git(repo, "worktree", "lock", "--reason", "a person's own lock", rec.path)
    done = release_workspace(rec, "on_finish", root)
    assert Path(rec.path).exists() and done.cleanup[0]["result"] == "kept"
    assert done.cleanup[0]["reason"].startswith("locked: a person's own lock")
    assert "locked" in git(repo, "worktree", "list", "--porcelain")  # the lock was not touched


def test_a_removal_git_refuses_is_kept_and_never_forced(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # WTR-AC5 (WTR-B23): kept with git's reason, never retried with `--force`
    rec, root = prepared(repo)
    seen: list[list[str]] = []
    real = wsmod.git

    def refusing(args: list[str], cwd: Path, **kw: Any) -> str:
        seen.append(list(args))
        if args[:2] == ["worktree", "remove"]:
            raise GitError("git worktree exited 128: fatal: cannot remove: refused by the test")
        return real(args, cwd, **kw)

    monkeypatch.setattr(wsmod, "git", refusing)
    done = release_workspace(rec, "on_finish", root)
    assert done.action == "kept" and "refused by the test" in done.cleanup[0]["reason"]
    removals = [a for a in seen if a[:2] == ["worktree", "remove"]]
    assert len(removals) == 1 and all("--force" not in a and "-f" not in a for a in removals)
    assert Path(rec.path).exists()


def test_an_error_outcome_removes_nothing(repo: Path) -> None:  # WTR-AC5 (WTR-B23: any outcome but `error`)
    rec, root = prepared(repo)
    done = release_workspace(rec, "on_finish", root, outcome="error")
    assert Path(rec.path).exists() and done.action == "kept" and done.cleanup == []
    ok = release_workspace(rec, "on_finish", root, outcome="pr_opened")
    assert not Path(rec.path).exists() and ok.state == "removed" and ok.action == "removed"
    assert "tg/demo/T-1" in git(repo, "branch", "--list")


def test_children_are_removed_by_the_same_rule(repo: Path) -> None:  # WTR-AC5 (WTR-B23: writer, slot and item)
    rec, root = prepared(repo)
    child = repo.parent / "repo.worktrees" / "demo--T-1--w-a"
    git(repo, "worktree", "add", "-b", "tg/demo/T-1--w-a", str(child), "HEAD")
    dirty = repo.parent / "repo.worktrees" / "demo--T-1--s-b"
    git(repo, "worktree", "add", "-b", "tg/demo/T-1--s-b", str(dirty), "HEAD")
    (dirty / "new.txt").write_text("x")
    rec.children = [{"name": "w-a", "path": str(child), "branch": "tg/demo/T-1--w-a", "state": "active"},
                    {"name": "s-b", "path": str(dirty), "branch": "tg/demo/T-1--s-b", "state": "active"}]
    done = release_workspace(rec, "on_finish", root)
    assert [(c["name"], c["result"]) for c in done.cleanup] == [("run", "removed"), ("w-a", "removed"),
                                                                ("s-b", "kept")]
    assert done.state == "released" and done.action == "kept" and dirty.exists()
    assert not child.exists() and not Path(rec.path).exists()
