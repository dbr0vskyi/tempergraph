"""`worktree list --all` and `worktree prune` against real git worktrees (WTR-B27, WTR-B16, WTR-B13; WTR-AC3)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode
from tempergraph.durability.lock import RunLock
from tempergraph.executors.standins import standin
from tempergraph.run.runner import resume
from tempergraph.store.layout import lock_path, run_dir, state_root_path
from tempergraph.workspace import list_worktrees, prune_apply, prune_plan

from .fixtures.workflows import two_step
from .test_run import DRAFT, NO_SLEEP, REVIEW, go, judge, records, registry, verdict_block


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def pause(repo: Path, task: str) -> Path:
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    assert go(repo, ex, task=task).exit_code is ExitCode.PAUSED
    return Path(next(r for r in records(repo, task) if r["kind"] == "workspace")["path"])


def finish(repo: Path, task: str, *, dirty: bool = False) -> Path:
    def stray(req: Any) -> Any:
        (req.workdir / "stray.txt").write_text("x")
        return DRAFT

    ex = standin("claude", steps=[stray if dirty else DRAFT, REVIEW], judges=[judge(), judge()])
    assert go(repo, ex, task=task).exit_code is ExitCode.FINISHED
    return Path(next(r for r in records(repo, task) if r["kind"] == "workspace")["path"])


def four(repo: Path) -> dict[str, Path]:
    """Running, finished and clean, finished and dirty, paused and clean (WTR-B16)."""
    return {"running": pause(repo, "T-run"), "clean": finish(repo, "T-clean"), "dirty": finish(repo, "T-dirty", dirty=True),
            "paused": pause(repo, "T-paused")}


def test_prune_keeps_work_and_branches(repo: Path) -> None:  # WTR-AC3 (WTR-B16, WTR-B27)
    wts = four(repo)
    root = state_root_path(repo)
    held = RunLock(lock_path(root, "demo", "T-run")).acquire()  # a live run holds its lock
    try:
        rows = {r["thread"]: r for r in list_worktrees(repo)}
        assert {t: r["state"] for t, r in rows.items()} == {"demo/T-run": "running", "demo/T-clean": "finished",
                                                            "demo/T-dirty": "finished", "demo/T-paused": "paused"}
        assert {t: r["removable"] for t, r in rows.items()} == {"demo/T-run": False, "demo/T-clean": True,
                                                                "demo/T-dirty": False, "demo/T-paused": True}
        assert rows["demo/T-dirty"]["dirty"] == 1 and rows["demo/T-clean"]["dirty"] == 0
        assert {"ahead", "behind", "lock"} <= set(rows["demo/T-clean"])
        branches = git(repo, "for-each-ref", "refs/heads")
        plan = prune_plan(repo)
        assert sorted(r["thread"] for r in plan) == ["demo/T-clean", "demo/T-paused"]
        assert all(p.exists() for p in wts.values())  # listing removed nothing
        done = prune_apply(repo, plan)
        assert {d["thread"]: d["result"] for d in done} == {"demo/T-clean": "removed", "demo/T-paused": "removed"}
        assert wts["running"].exists() and wts["dirty"].exists()
        assert not wts["clean"].exists() and not wts["paused"].exists()
        assert git(repo, "for-each-ref", "refs/heads") == branches  # no branch is deleted
        assert "T-clean" not in git(repo, "worktree", "list")  # and git forgot them
    finally:
        held.release()
    ex = standin("claude", steps=[REVIEW], judges=[judge()])  # the paused thread can still resume (WTR-B9)
    out = resume(two_step(), "T-paused", repo, registry(ex), decision="proceed", settings=NO_SLEEP)
    assert out.exit_code is ExitCode.FINISHED and wts["paused"].exists()


def test_prune_never_touches_a_running_thread_even_when_named(repo: Path) -> None:  # WTR-AC3 (WTR-B27)
    wt = pause(repo, "T-run")
    held = RunLock(lock_path(state_root_path(repo), "demo", "T-run")).acquire()
    try:
        assert prune_plan(repo, thread="demo/T-run") == []
        row = {**list_worktrees(repo)[0], "removable": True}  # a stale plan that still lists it
        assert prune_apply(repo, [row])[0] == {"thread": "demo/T-run", "path": str(wt), "result": "kept",
                                               "reason": "running"}
        assert wt.exists()
    finally:
        held.release()


def test_prune_selectors(repo: Path) -> None:  # WTR-AC3 (WTR-B27)
    four(repo)
    assert [r["thread"] for r in prune_plan(repo, thread="demo/T-clean")] == ["demo/T-clean"]
    assert [r["thread"] for r in prune_plan(repo, finished=True)] == ["demo/T-clean"]
    assert sorted(r["thread"] for r in prune_plan(repo, older_than=0)) == ["demo/T-clean", "demo/T-paused",
                                                                              "demo/T-run"]
    assert prune_plan(repo, older_than=1) == []  # nothing is a day old
    old = run_dir(state_root_path(repo), "demo", "T-clean") / "run.jsonl"
    os.utime(old, (1_000_000_000, 1_000_000_000))
    assert [r["thread"] for r in prune_plan(repo, older_than=30)] == ["demo/T-clean"]


def test_prune_leaves_a_worktree_git_refuses_to_remove(repo: Path) -> None:  # WTR-AC3 (WTR-B16: the cleanup rule)
    wt = finish(repo, "T-lock")
    git(repo, "worktree", "lock", "--reason", "a person's lock", str(wt))
    (row,) = prune_plan(repo)
    assert row["lock"] == "a person's lock"
    (res,) = prune_apply(repo, [row])
    assert res["result"] == "kept" and res["reason"].startswith("locked: a person's lock") and wt.exists()


def test_list_all_adds_foreign_and_unowned_worktrees(repo: Path, tmp_path: Path) -> None:  # WTR-AC3 (WTR-B27, WTR-B13)
    finish(repo, "T-1")
    stray = tmp_path / "somebody-elses-tree"
    git(repo, "worktree", "add", "-b", "somebody-else", str(stray), "HEAD")
    assert [r["thread"] for r in list_worktrees(repo)] == ["demo/T-1"]
    rows = {r["path"]: r for r in list_worktrees(repo, all=True)}
    assert len(rows) == 2
    extra = rows[str(stray)]
    assert extra["thread"] is None and extra["state"] == "unowned" and extra["removable"] is False
    assert extra["branch"] == "somebody-else"
    assert plan_paths(repo) == [str(next(p for p, r in rows.items() if r["thread"] == "demo/T-1"))]  # never prunes it


def plan_paths(repo: Path) -> list[str]:
    return [r["path"] for r in prune_plan(repo)]


def test_listing_and_planning_write_nothing(repo: Path) -> None:  # WTR-AC6 (WTR-B27)
    four(repo)
    before = (git(repo, "for-each-ref"), git(repo, "worktree", "list", "--porcelain"),
              git(repo, "status", "--porcelain", "--ignored"))
    list_worktrees(repo)
    list_worktrees(repo, all=True)
    prune_plan(repo)
    after = (git(repo, "for-each-ref"), git(repo, "worktree", "list", "--porcelain"),
             git(repo, "status", "--porcelain", "--ignored"))
    assert before == after
