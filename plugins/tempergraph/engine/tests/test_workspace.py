"""Workspace and the release-1 worktree mode (WSP-B1–B3, B6, WSP-AC-1; WTR §2.2, §2.4–§2.6)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tempergraph.api import Gate, Judge, Step, Workflow
from tempergraph.contracts import WorktreeDecl
from tempergraph.git import branch
from tempergraph.store.layout import ensure_state_root, state_root_path
from tempergraph.workspace import (
    WorkspaceRefused,
    attach_workspace,
    check_plan,
    flat_name,
    list_worktrees,
    prepare_workspace,
    python_for,
    release_workspace,
    resolve_workspace,
    run_branch,
    worktree_path,
)

from .fixtures.workflows import crit, named, two_step


def reader() -> object:
    return named(Workflow(order=["look"], units={"look": Step(prompt="Read {request}", tools=["read"],
                                                              gate=Gate(judge=Judge(stance="V."), criteria=[crit("c")]))}))


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.mark.parametrize(("wf", "task", "flat"), [
    ("demo", "ABC-1", "demo--ABC-1"),
    ("demo", "feature/x y", "demo--feature-x-y"),
    ("demo", "..hidden.lock", "demo--hidden-lock"),
])
def test_flat_names(wf: str, task: str, flat: str) -> None:
    assert flat_name(wf, task) == flat


def test_long_flat_name_is_cut_with_a_digest() -> None:
    name = flat_name("demo", "x" * 200)
    assert len(name) == 80 and name[71] == "-"
    assert run_branch("demo", "feature/x") == "tg/demo/feature-x"


def test_auto_resolution(repo: Path, tmp_path: Path) -> None:
    assert resolve_workspace(two_step(), repo, task_id="T-1").resolved_by == "writes_files"
    plan = resolve_workspace(reader(), repo, task_id="T-1")  # type: ignore[arg-type]
    assert (plan.mode, plan.resolved_by) == ("in_place", "read_only")
    plain = tmp_path / "plain"
    plain.mkdir()
    assert resolve_workspace(two_step(), plain, task_id="T-1").resolved_by == "not_git"
    with pytest.raises(WorkspaceRefused):
        resolve_workspace(two_step(), plain, "worktree", task_id="T-1")
    warn = resolve_workspace(two_step(), repo, "in_place", task_id="T-1")
    assert warn.mode == "in_place" and warn.warnings


def test_worktree_lifecycle(repo: Path) -> None:
    (repo / ".env").write_text("SECRET_FOR_TEST=1\n")
    (repo / ".gitignore").write_text(".env\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-q", "-m", "ignore")
    (repo / "dirty.txt").write_text("x")
    root = ensure_state_root(state_root_path(repo))
    plan = resolve_workspace(two_step(), repo, task_id="T-1")
    assert plan.path == repo.parent / "repo.worktrees" / "demo--T-1" and plan.branch == "tg/demo/T-1"
    assert any(w.startswith("uncommitted") for w in plan.warnings)
    assert check_plan(plan) == []
    rec = prepare_workspace("demo/T-1", plan, WorktreeDecl(include=(".env",)), root)
    wt = Path(rec.path)
    assert branch(wt) == "tg/demo/T-1" and (wt / ".env").read_text() == "SECRET_FOR_TEST=1\n"
    assert not (wt / "dirty.txt").exists() and rec.bootstrap["included"] == 1
    assert state_root_path(wt) == root  # WSP-AC-1: the state root from inside the worktree
    assert worktree_path(repo, "demo/T-1") == wt
    assert [r["thread"] for r in list_worktrees(wt)] == ["demo/T-1"]
    assert check_plan(plan)  # a second start would collide
    # resume after the worktree was deleted (WSP-B1)
    git(repo, "worktree", "unlock", str(wt))
    shutil.rmtree(wt)
    again = attach_workspace(rec, "demo/T-1", None, root)
    assert again.action == "attached" and branch(wt) == "tg/demo/T-1"
    (wt / "new.txt").write_text("person's change")
    assert attach_workspace(again, "demo/T-1", None, root).action == "external_change"
    done = release_workspace(again)
    assert done.state == "released" and wt.exists()  # never removed in release 1


def test_failed_bootstrap_removes_worktree_and_branch(repo: Path) -> None:
    root = ensure_state_root(state_root_path(repo))
    plan = resolve_workspace(two_step(), repo, task_id="T-2")
    with pytest.raises(WorkspaceRefused) as err:
        prepare_workspace("demo/T-2", plan, WorktreeDecl(setup=(("make", "setup"),)), root,
                          run_command=lambda argv, cwd, t: 2)
    assert err.value.word == "bootstrap_failed"
    assert not plan.path.exists()
    assert "tg/demo/T-2" not in git(repo, "branch", "--list")


def test_interpreter_resolution(tmp_path: Path) -> None:
    ws, main = tmp_path / "ws", tmp_path / "main"
    (main / ".venv" / "bin").mkdir(parents=True)
    (main / ".venv" / "bin" / "python").write_text("")
    assert python_for(ws, main) == str(main / ".venv" / "bin" / "python")
    (ws / ".venv" / "bin").mkdir(parents=True)
    (ws / ".venv" / "bin" / "python").write_text("")
    assert python_for(ws, main) == str(ws / ".venv" / "bin" / "python")
    assert python_for(tmp_path / "none", None) == sys.executable
