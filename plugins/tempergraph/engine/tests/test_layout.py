"""State root and home layouts (LOS §2.1, §2.2; WSP-AC-1; LOS-B4)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tempergraph.docs import write_json
from tempergraph.store.layout import (
    LayoutNewer,
    ensure_home,
    ensure_state_root,
    session_key,
    state_root_path,
)


def test_state_root_from_nested_worktree(repo: Path, tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "side", str(wt)], cwd=repo, check=True)
    (wt / "deep" / "er").mkdir(parents=True)
    assert state_root_path(wt / "deep" / "er") == repo / ".tempergraph"
    assert state_root_path(repo) == repo / ".tempergraph"


def test_state_root_ignored_by_git(repo: Path) -> None:
    root = ensure_state_root(repo / ".tempergraph")
    (root / "runs" / "x.txt").write_text("x")
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True).stdout
    assert status == ""
    assert (root.stat().st_mode & 0o777) == 0o700


def test_newer_layout_refused(repo: Path) -> None:
    root = repo / ".tempergraph"
    write_json(root / "manifest.json", {"schema_version": 1, "kind": "state_root", "layout": 9})
    with pytest.raises(LayoutNewer):
        ensure_state_root(root)


def test_home_has_machine_id(tmp_path: Path) -> None:
    home = ensure_home(tmp_path / "h")
    assert (home / "machine.json").exists() and (home / "manifest.json").exists()


def test_session_keys() -> None:
    assert session_key("plan", 2, "judge") == "plan.2.judge"
    assert session_key("code", 1, "judge_reask", item="p3", n=2) == "code.p3.1.judge_reask.2"
