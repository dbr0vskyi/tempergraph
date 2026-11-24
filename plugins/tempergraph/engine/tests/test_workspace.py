"""Workspace and the release-1 worktree mode (WSP-B1–B3, B6, WSP-AC1; WTR-B18, WTR-B20, WTR-B21, WTR-B22)."""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from tempergraph import workspace as wsmod
from tempergraph.api import Gate, Judge, Step, Workflow
from tempergraph.contracts import WorktreeDecl
from tempergraph.git import branch
from tempergraph.store.layout import ensure_state_root, state_root_path
from tempergraph.workspace import (
    WorkspaceRefused,
    attach_workspace,
    check_plan,
    cut_writers,
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
from .test_parallel import wf as parallel_wf


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


def with_writer(tools: tuple[str, ...] = ("read", "write")) -> Any:
    """The parallel fixture with a writer branch (`security`), a read-only branch (`perf`) and a join."""
    spec = parallel_wf()
    step = spec.units["security"]
    assert step.step is not None
    units = {**spec.units, "security": dataclasses.replace(step, step=dataclasses.replace(step.step, tools=tools))}
    return dataclasses.replace(spec, units=units)


def test_a_writer_branch_resolves_to_a_worktree_and_refuses_in_place(repo: Path) -> None:  # WTR-AC1, AC 1
    plan = resolve_workspace(with_writer(), repo, task_id="T-1")
    assert (plan.mode, plan.resolved_by) == ("worktree", "writers") and plan.path.parent == repo.parent / "repo.worktrees"
    for asked in ("in_place",):  # the flag or the setting: an explicit `in_place` on a workflow with a writer branch
        with pytest.raises(WorkspaceRefused) as err:
            resolve_workspace(with_writer(), repo, asked, task_id="T-1")
        assert err.value.word == "writers_need_worktree" and not (repo.parent / "repo.worktrees").exists()
    assert resolve_workspace(with_writer(), repo, "worktree", task_id="T-1").mode == "worktree"
    # `shell` alone makes no writer branch, and a workflow with only read-only branches resolves as before
    shell = resolve_workspace(with_writer(("read", "shell")), repo, task_id="T-1")
    assert shell.resolved_by == "writes_files"
    assert resolve_workspace(parallel_wf(), repo, task_id="T-1").resolved_by == "read_only"
    assert resolve_workspace(parallel_wf(), repo, "in_place", task_id="T-1").mode == "in_place"


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
    assert state_root_path(wt) == root  # WSP-AC1: the state root from inside the worktree
    assert worktree_path(repo, "demo/T-1") == wt
    assert [r["thread"] for r in list_worktrees(wt)] == ["demo/T-1"]
    # WTR-AC11: a writer worktree is listed after the run's row and marked; `worktree path` stays the run's
    rec = cut_writers(rec, "demo/T-1", ["lint"], None, root)
    rows = list_worktrees(wt)
    assert [(r["thread"], r.get("writer")) for r in rows] == [("demo/T-1", None), ("demo/T-1", "lint")]
    assert rows[0]["path"] == str(wt) and rows[1]["path"] == rec.children[0]["path"] != str(wt)
    assert worktree_path(repo, "demo/T-1") == wt and Path(rec.children[0]["path"]).name == "demo--T-1--w-lint"
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


def test_slot_worktrees_are_cut_after_a_checkpoint_and_named_by_their_slot(repo: Path) -> None:  # CTS-AC4 (CTS-B5, WTR-B20)
    root = ensure_state_root(state_root_path(repo))
    plan = resolve_workspace(two_step(), repo, task_id="T-5")
    rec = prepare_workspace("demo/T-5", plan, WorktreeDecl(), root)
    run_path = Path(rec.path)
    (run_path / "early.txt").write_text("left by an earlier unit\n")
    from tempergraph import git as gitmod

    gitmod.commit_all(run_path, "tempergraph: checkpoint before pick")  # the checkpoint a contest takes when entered
    checkpoint = gitmod.head(run_path)
    rec = cut_writers(rec, "demo/T-5", ["pick.s1", "pick.s2"], None, root, kind="s")
    assert [c["unit"] for c in rec.children] == ["pick.s1", "pick.s2"]
    assert [Path(c["path"]).name for c in rec.children] == ["demo--T-5--s-s1", "demo--T-5--s-s2"]  # `--s-<slot>`
    assert [c["branch"] for c in rec.children] == ["tg/demo/T-5--s-s1", "tg/demo/T-5--s-s2"]
    for c in rec.children:
        assert gitmod.head(Path(c["path"])) == checkpoint  # cut after the checkpoint: it holds `early.txt`
        assert (Path(c["path"]) / "early.txt").exists()
    with pytest.raises(WorkspaceRefused) as err:  # a second cut would meet the slots' branches: refused, never overwritten
        cut_writers(rec, "demo/T-5", ["pick.s1"], None, root, kind="s")
    assert err.value.word == "name_collision"
    assert [Path(c["path"]).name for c in rec.children] == ["demo--T-5--s-s1", "demo--T-5--s-s2"]  # nothing removed
    kept = cut_writers(rec, "demo/T-5", ["lint"], None, root)  # the other kinds keep their names and their reuse
    assert Path(kept.children[-1]["path"]).name == "demo--T-5--w-lint"
    assert cut_writers(kept, "demo/T-5", ["lint"], None, root).children == kept.children


def test_a_later_attempts_slot_worktrees_are_named_by_their_attempt_and_the_first_stay_untouched(repo: Path) -> None:
    # WTR-AC14 (WTR-B20, CTS-B11, CTS-B12)
    from tempergraph import git as gitmod

    root = ensure_state_root(state_root_path(repo))
    plan = resolve_workspace(two_step(), repo, task_id="T-5")
    rec = prepare_workspace("demo/T-5", plan, WorktreeDecl(), root)
    gitmod.commit_all(Path(rec.path), "tempergraph: checkpoint before pick")
    rec = cut_writers(rec, "demo/T-5", ["pick.s1", "pick.s2"], None, root, kind="s")
    first = [dict(c) for c in rec.children]
    assert all("visit" not in c for c in first)
    run_path = Path(rec.path)
    assert gitmod.head(run_path)
    rec = cut_writers(rec, "demo/T-5", ["pick.s1", "pick.s2"], None, root, kind="s", visit=2)
    assert rec.children[:2] == first  # the first attempt's records: names, branches, no `visit`, state `active`
    assert all(c["state"] == "active" and Path(c["path"]).exists() for c in rec.children[:2])
    later = rec.children[2:]
    assert [c["unit"] for c in later] == ["pick.s1", "pick.s2"] and [c["visit"] for c in later] == [2, 2]
    assert [Path(c["path"]).name for c in later] == ["demo--T-5--s2-s1", "demo--T-5--s2-s2"]
    assert [c["branch"] for c in later] == ["tg/demo/T-5--s2-s1", "tg/demo/T-5--s2-s2"]
    assert all(Path(c["path"]).exists() for c in later)
    with pytest.raises(WorkspaceRefused) as err:  # one slot is cut once in one attempt
        cut_writers(rec, "demo/T-5", ["pick.s1"], None, root, kind="s", visit=2)
    assert err.value.word == "name_collision"
    assert wsmod.writer_names(run_path, rec.branch, "pick.s1", "demo/T-5", kind="s")[0] == "demo--T-5--s-s1"
    assert wsmod.writer_names(run_path, rec.branch, "m.a", "demo/T-5", kind="i", visit=2)[0] == "demo--T-5--i2-a"
    assert wsmod.writer_names(run_path, rec.branch, "pick.s1", "demo/T-5", kind="s", visit=3)[1] == "tg/demo/T-5--s3-s1"


def test_failed_bootstrap_removes_worktree_and_branch(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # WTR-AC5 (WTR-B22, WTR-B23): the rollback needs no `--force`, `branch -D` or `branch -d`
    seen: list[list[str]] = []
    real = wsmod.git

    def spy(args: list[str], cwd: Path, **kw: Any) -> str:
        seen.append(list(args))
        return real(args, cwd, **kw)

    monkeypatch.setattr(wsmod, "git", spy)
    root = ensure_state_root(state_root_path(repo))
    plan = resolve_workspace(two_step(), repo, task_id="T-2")
    with pytest.raises(WorkspaceRefused) as err:
        prepare_workspace("demo/T-2", plan, WorktreeDecl(setup=(("make", "setup"),)), root,
                          run_command=lambda argv, cwd, t: 2)
    assert err.value.word == "bootstrap_failed"
    assert not plan.path.exists()
    assert "tg/demo/T-2" not in git(repo, "branch", "--list")
    assert git(repo, "worktree", "list", "--porcelain").count("worktree ") == 1  # only the main checkout is left
    assert git(repo, "for-each-ref", "refs/heads/tg/demo/T-2").strip() == ""
    after_add = next(i for i, a in enumerate(seen) if a[:2] == ["worktree", "add"])
    rollback = [a for a in seen[after_add + 1:] if a[0] in ("worktree", "update-ref", "branch")]
    assert [a[:2] for a in rollback if a[:2] != ["worktree", "lock"]] == [
        ["worktree", "unlock"], ["worktree", "prune"], ["update-ref", "-d"]]
    assert all("--force" not in a and a[:2] not in (["branch", "-D"], ["branch", "-d"]) for a in seen)
    plan = resolve_workspace(two_step(), repo, task_id="T-2")  # a retry meets no `branch_exists`
    assert check_plan(plan) == []


def test_no_code_path_forces_a_removal_or_deletes_a_branch() -> None:  # WTR-AC5 (WTR-B23)
    import re

    src = Path(__file__).resolve().parent.parent / "src" / "tempergraph"
    squashed = re.compile(r"""["']\s*(worktree)\s*["']\s*,\s*["']\s*remove\s*["'][^\]]*?["']--force["']|"""
                          r"""["']\s*branch\s*["']\s*,\s*["']-[dD]["']|["']git branch -[dD]|worktree remove --force""",
                          re.S)
    hits = [str(p.relative_to(src)) for p in src.rglob("*.py") if squashed.search(p.read_text(encoding="utf-8"))]
    assert hits == []


def _origin(tmp_path: Path, repo: Path) -> Path:
    """A bare `origin` with `main`, set up as the repository's remote."""
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "-u", "origin", "main")
    git(repo, "remote", "set-head", "origin", "main")
    return bare


def _push_from_elsewhere(tmp_path: Path, bare: Path) -> str:
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(bare), str(other)], check=True)
    (other / "remote.txt").write_text("from the remote\n")
    git(other, "add", "remote.txt")
    git(other, "-c", "user.name=T", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "remote")
    git(other, "push", "-q", "origin", "main")
    return git(other, "rev-parse", "HEAD").strip()


def test_in_repo_root_places_the_worktree_under_the_checkout(repo: Path) -> None:  # WTR-AC1, WTR-AC3 (WTR-B20, WTR-B17)
    root = ensure_state_root(state_root_path(repo))
    plan = resolve_workspace(two_step(), repo, task_id="T-1", root="in_repo")
    assert plan.root_kind == "in_repo"
    assert plan.path == repo / ".claude" / "worktrees" / "tg-demo--T-1"
    assert not (repo / ".claude").exists()  # resolving writes nothing
    rec = prepare_workspace("demo/T-1", plan, None, root)
    assert Path(rec.path) == plan.path and rec.root_kind == "in_repo" and plan.path.is_dir()
    assert ".claude/worktrees/" in (repo / ".git" / "info" / "exclude").read_text()
    assert git(repo, "status", "--porcelain").strip() == ""  # the checkout does not see its own worktrees
    assert git(repo, "ls-files", "--", ".claude").strip() == ""  # never added to a tracked file
    assert [r["thread"] for r in list_worktrees(repo)] == ["demo/T-1"]


def test_in_repo_root_keeps_an_existing_ignore(repo: Path) -> None:  # WTR-AC3 (WTR-B20)
    (repo / ".gitignore").write_text(".claude/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-q", "-m", "ignore")
    root = ensure_state_root(state_root_path(repo))
    plan = resolve_workspace(two_step(), repo, task_id="T-1", root="in_repo")
    prepare_workspace("demo/T-1", plan, None, root)
    assert not (repo / ".git" / "info" / "exclude").exists() or ".claude" not in (
        repo / ".git" / "info" / "exclude").read_text()  # git already ignores it


def test_path_root_is_created_owner_only(repo: Path, tmp_path: Path) -> None:  # WTR-AC3 (WTR-B20, WTR-B17)
    wts = tmp_path / "elsewhere" / "wts"
    root = ensure_state_root(state_root_path(repo))
    plan = resolve_workspace(two_step(), repo, task_id="T-1", root=f"path:{wts}")
    assert plan.root_kind == "path" and plan.path == wts / "demo--T-1" and not wts.exists()
    rec = prepare_workspace("demo/T-1", plan, None, root)
    assert Path(rec.path) == wts / "demo--T-1" and rec.root_kind == "path"
    assert (wts.stat().st_mode & 0o777) == 0o700
    assert branch(Path(rec.path)) == "tg/demo/T-1"


def test_default_branch_base_fetches_origin_first(repo: Path, tmp_path: Path) -> None:  # WTR-AC3 (WTR-B21)
    bare = _origin(tmp_path, repo)
    newest = _push_from_elsewhere(tmp_path, bare)
    local = git(repo, "rev-parse", "HEAD").strip()
    assert newest != local
    root = ensure_state_root(state_root_path(repo))
    plan = resolve_workspace(two_step(), repo, task_id="T-1", base="default_branch")
    assert plan.base_ref == "default_branch" and plan.base_branch == "main"
    assert git(repo, "rev-parse", "refs/remotes/origin/main").strip() == local  # resolving fetched nothing
    rec = prepare_workspace("demo/T-1", plan, None, root)
    assert rec.base_commit == newest and rec.base_fetch == "ok" and rec.base_branch == "main"
    assert git(Path(rec.path), "rev-parse", "HEAD").strip() == newest
    assert git(repo, "rev-parse", "HEAD").strip() == local  # the person's checkout stays where it was


def test_default_branch_base_falls_back_to_the_local_copy(repo: Path, tmp_path: Path) -> None:  # WTR-AC3 (WTR-B7)
    _origin(tmp_path, repo)
    git(repo, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    local = git(repo, "rev-parse", "HEAD").strip()
    root = ensure_state_root(state_root_path(repo))
    plan = resolve_workspace(two_step(), repo, task_id="T-1", base="default_branch")
    t0 = time.monotonic()
    rec = prepare_workspace("demo/T-1", plan, None, root)
    assert time.monotonic() - t0 < 30
    assert rec.base_fetch == "failed" and rec.base_commit == local
    assert git(Path(rec.path), "rev-parse", "HEAD").strip() == local


def test_misplaced_or_unwritable_root_is_refused_before_anything_is_created(repo: Path, tmp_path: Path) -> None:
    # WTR-AC6 (WTR-B20): exit 2 before spend; `check_plan` creates nothing
    for bad in (f"path:{repo}", f"path:{repo / 'sub' / 'wts'}", f"path:{repo / '.git' / 'wts'}",
                f"path:{state_root_path(repo) / 'wts'}", "path:relative/wts"):
        with pytest.raises(WorkspaceRefused) as err:
            resolve_workspace(two_step(), repo, task_id="T-1", root=bad)
        assert err.value.word in ("root_misplaced", "root_invalid"), bad
    blocker = tmp_path / "a-file"
    blocker.write_text("x")
    plan = resolve_workspace(two_step(), repo, task_id="T-1", root=f"path:{blocker / 'wts'}")
    assert [p.split(":", 1)[0] for p in check_plan(plan)] == ["root_not_writable"]
    with pytest.raises(WorkspaceRefused) as err2:
        prepare_workspace("demo/T-1", plan, None, ensure_state_root(state_root_path(repo)))
    assert err2.value.word == "root_not_writable"
    assert git(repo, "worktree", "list", "--porcelain").count("worktree ") == 1
    assert "tg/demo/T-1" not in git(repo, "branch", "--list")


def test_a_run_with_a_misplaced_root_exits_2_before_spend(repo: Path) -> None:  # WTR-AC6 (WTR-B20)
    from tempergraph.constants import ExitCode
    from tempergraph.executors.standins import standin

    from .test_run import go

    ex = standin("claude", steps=[], judges=[])
    out = go(repo, ex, flags={"run.worktree.root": f"path:{repo / 'inside'}"})
    assert out.exit_code is ExitCode.USAGE and out.reason == "root_misplaced"
    assert not (repo / "inside").exists()


def test_check_plan_worktree_list_and_path_create_nothing_for_the_new_roots(repo: Path, tmp_path: Path) -> None:
    # WTR-AC6 (WTR-B27, WTR-B22)
    from .conftest import hash_tree

    bare = _origin(tmp_path, repo)
    _push_from_elsewhere(tmp_path, bare)

    def state() -> tuple[str, str, str, dict[str, str]]:
        return (git(repo, "for-each-ref"), git(repo, "worktree", "list", "--porcelain"),
                (repo / ".git" / "info" / "exclude").read_text() if (repo / ".git" / "info" / "exclude").exists() else "",
                hash_tree(tmp_path))

    before = state()
    for kw in ({"root": "in_repo"}, {"root": f"path:{tmp_path / 'made-later'}"}, {"base": "default_branch"}):
        plan = resolve_workspace(two_step(), repo, task_id="T-1", **kw)
        assert check_plan(plan) == []
    assert list_worktrees(repo) == [] and worktree_path(repo, "demo/T-1") is None
    assert state() == before


def test_interpreter_resolution(tmp_path: Path) -> None:
    ws, main = tmp_path / "ws", tmp_path / "main"
    (main / ".venv" / "bin").mkdir(parents=True)
    (main / ".venv" / "bin" / "python").write_text("")
    assert python_for(ws, main) == str(main / ".venv" / "bin" / "python")
    (ws / ".venv" / "bin").mkdir(parents=True)
    (ws / ".venv" / "bin" / "python").write_text("")
    assert python_for(ws, main) == str(ws / ".venv" / "bin" / "python")
    assert python_for(tmp_path / "none", None) == sys.executable
