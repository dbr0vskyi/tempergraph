"""The run's workspace: in place, or one engine-owned git worktree (WSP §2, WTR §2; release-1 part, ADR-0090).

Release 1 builds `run.workspace` (`auto`, `worktree`, `in_place`), the `sibling` root, the `head` base,
derived names, start with bootstrap, resume with re-attach, release without removal, and the data behind
`worktree list` and `worktree path`. Names are derived, never typed, and every git call puts
`--end-of-options` before a ref or path (WTR §2.4).
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import shutil
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from tempergraph.contracts import WorkflowSpec, WorktreeDecl
from tempergraph.durability.lock import LockHeld, RunLock
from tempergraph.git import GitError, branch, git, is_safe_ref, main_checkout

Mode = Literal["in_place", "worktree"]
WRITE_TOOLS = frozenset({"edit", "write", "shell"})
BRANCH_PREFIX = "tg"
LOCK_REASON = "tempergraph "
MAX_FLAT = 80


class WorkspaceRefused(Exception):
    """A start refused before spend (exit 2), with a reason word."""

    def __init__(self, word: str, message: str) -> None:
        super().__init__(message)
        self.word = word


# ---------------------------------------------------------------------------------------------
# Names (WTR §2.4)


def flat_part(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]", "-", text).replace("..", "-")
    s = re.sub(r"-{2,}", "-", s).lstrip(".-").rstrip(".")
    if s.endswith(".lock"):
        s = s[: -len(".lock")] + "-lock"
    return s or "x"


def flat_name(workflow: str, task_id: str) -> str:
    name = f"{flat_part(workflow)}--{flat_part(task_id)}"
    if len(name) <= MAX_FLAT:
        return name
    digest = hashlib.sha256(f"{workflow}/{task_id}".encode()).hexdigest()[:8]
    return name[:71] + "-" + digest


def run_branch(workflow: str, task_id: str, prefix: str = BRANCH_PREFIX) -> str:
    return f"{prefix}/{flat_part(workflow)}/{flat_part(task_id)}"


def sibling_root(main: Path) -> Path:
    return main.parent / f"{main.name}.worktrees"


# ---------------------------------------------------------------------------------------------
# Plan and record


@dataclass(frozen=True, kw_only=True)
class WorkspacePlan:
    mode: Mode
    requested: str
    resolved_by: str
    main: Path | None
    path: Path
    root_kind: str = ""
    branch: str = ""
    base_ref: str = "head"
    base_commit: str = ""
    base_branch: str = ""
    warnings: tuple[str, ...] = ()


@dataclass(kw_only=True)
class WorkspaceRecord:
    """WTR §2.8; stored in state as a plain dict."""

    mode: Mode
    requested: str
    resolved_by: str
    path: str
    root_kind: str = ""
    branch: str = ""
    base_ref: str = ""
    base_commit: str = ""
    base_branch: str = ""
    children: list[dict[str, Any]] = field(default_factory=list)
    state: Literal["active", "released", "removed"] = "active"
    bootstrap: dict[str, Any] = field(default_factory=dict)
    last_head: str = ""
    action: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> WorkspaceRecord:
        known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        return cls(**known)


def writes_files(spec: WorkflowSpec) -> bool:
    for u in spec.units.values():
        st = u.step
        if st is not None:
            if WRITE_TOOLS & set(st.tools):
                return True
            if any(sc.side_effects == "workspace" for sc in st.before + st.after):
                return True
        if u.script is not None and u.script.side_effects == "workspace":
            return True
    return False


def resolve_workspace(spec: WorkflowSpec, target: Path, requested: str | None = None, *, task_id: str = "",
                      prefix: str = BRANCH_PREFIX) -> WorkspacePlan:
    """WTR §2.2 and §2.5 for the release-1 values; pure and model-free (it reads git, writes nothing)."""
    req = requested or spec.workspace or "auto"
    if req not in ("auto", "worktree", "in_place"):
        raise WorkspaceRefused("workspace_invalid", f"run.workspace {req!r} is not auto, worktree or in_place")
    main = main_checkout(target)
    if main is None or _is_bare(target):
        if req == "worktree":
            raise WorkspaceRefused("not_git", "a worktree run needs a git checkout")
        return WorkspacePlan(mode="in_place", requested=req, resolved_by="not_git", main=None, path=target)
    writes = writes_files(spec)
    if req == "auto":
        mode: Mode = "worktree" if writes else "in_place"
        by = "writes_files" if writes else "read_only"
    else:
        mode, by = ("worktree" if req == "worktree" else "in_place"), "requested"
    warnings: list[str] = []
    if mode == "in_place":
        if req == "in_place" and writes:
            warnings.append("in_place_writes: the workflow writes files in your checkout")
        return WorkspacePlan(mode="in_place", requested=req, resolved_by=by, main=main, path=main,
                             warnings=tuple(warnings))
    head = git(["rev-parse", "--verify", "HEAD"], main, check=False).strip()
    if not head:
        raise WorkspaceRefused("base_unresolved", "the main checkout has no commit to start a worktree from")
    cur = branch(main)
    base_branch = cur if cur and cur != "HEAD" else _default_branch(main)
    dirty = [ln for ln in git(["status", "--porcelain=v1"], main, check=False).splitlines()
             if ".tempergraph/" not in ln]
    if dirty:
        warnings.append(f"uncommitted: {len(dirty)} changed paths in the main checkout are not in the worktree")
    br = run_branch(spec.name, task_id, prefix)
    if not is_safe_ref(br) or git(["check-ref-format", "--branch", br], main, check=False).strip() != br:
        raise WorkspaceRefused("branch_invalid", f"derived branch {br!r} is not a valid ref")
    path = sibling_root(main) / flat_name(spec.name, task_id)
    return WorkspacePlan(mode="worktree", requested=req, resolved_by=by, main=main, path=path, root_kind="sibling",
                         branch=br, base_ref="head", base_commit=head, base_branch=base_branch,
                         warnings=tuple(warnings))


def _is_bare(target: Path) -> bool:
    return git(["rev-parse", "--is-bare-repository"], target, check=False).strip() == "true"


def _default_branch(main: Path) -> str:
    ref = git(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], main, check=False).strip()
    return ref.split("/", 1)[1] if "/" in ref else "main"


def check_plan(plan: WorkspacePlan) -> list[str]:
    """`run --check`: what a start would refuse, creating nothing (WTR §2.6)."""
    problems: list[str] = []
    if plan.mode != "worktree" or plan.main is None:
        return problems
    if _branch_exists(plan.main, plan.branch):
        problems.append(f"branch_exists: {plan.branch}")
    if plan.path.exists():
        problems.append(f"path_exists: {plan.path}")
    parent = plan.path.parent if plan.path.parent.exists() else plan.path.parent.parent
    if not os.access(parent, os.W_OK):
        problems.append(f"root_not_writable: {parent}")
    return problems


def _branch_exists(main: Path, br: str) -> bool:
    return bool(git(["rev-parse", "--verify", "--quiet", "--end-of-options", f"refs/heads/{br}"], main,
                    check=False).strip())


# ---------------------------------------------------------------------------------------------
# Lifecycle (WTR §2.6)

RunCommand = Callable[[Sequence[str], Path, float], int]  # argv, cwd, timeout -> exit code


def _repo_lock(state_root: Path, wait_s: float = 30.0) -> RunLock:
    lock = RunLock(state_root / "locks" / "repository.lock")
    deadline = time.monotonic() + wait_s
    while True:
        try:
            return lock.acquire()
        except LockHeld:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.1)


def prepare_workspace(thread: str, plan: WorkspacePlan, decl: WorktreeDecl | None, state_root: Path,
                      run_command: RunCommand | None = None, *, read_include: bool = True) -> WorkspaceRecord:
    if plan.mode == "in_place":
        return WorkspaceRecord(mode="in_place", requested=plan.requested, resolved_by=plan.resolved_by,
                               path=str(plan.path), action="prepared")
    assert plan.main is not None
    problems = check_plan(plan)
    if problems:
        raise WorkspaceRefused(problems[0].split(":", 1)[0], "; ".join(problems))
    main = plan.main
    lock = _repo_lock(state_root)
    try:
        plan.path.parent.mkdir(parents=True, exist_ok=True)
        git(["worktree", "add", "-b", plan.branch, "--end-of-options", str(plan.path), plan.base_commit], main)
        git(["worktree", "lock", "--reason", LOCK_REASON + thread, "--end-of-options", str(plan.path)], main)
    finally:
        lock.release()
    rec = WorkspaceRecord(mode="worktree", requested=plan.requested, resolved_by=plan.resolved_by,
                          path=str(plan.path), root_kind=plan.root_kind, branch=plan.branch, base_ref=plan.base_ref,
                          base_commit=plan.base_commit, base_branch=plan.base_branch, last_head=plan.base_commit,
                          action="prepared")
    try:
        rec.bootstrap = bootstrap(main, plan.path, decl, run_command, read_include=read_include)
    except WorkspaceRefused:
        _remove_new(main, plan.path, plan.branch)
        raise
    return rec


def _remove_new(main: Path, path: Path, br: str) -> None:
    git(["worktree", "unlock", "--end-of-options", str(path)], main, check=False)
    git(["worktree", "remove", "--force", "--end-of-options", str(path)], main, check=False)
    git(["branch", "-D", "--end-of-options", br], main, check=False)


def bootstrap(main: Path, path: Path, decl: WorktreeDecl | None, run_command: RunCommand | None, *,
              read_include: bool = True) -> dict[str, Any]:
    """WSP-B2: copy the declared untracked or ignored files, init submodules, run the setup commands."""
    decl = decl or WorktreeDecl()
    patterns = list(decl.include)
    wti = main / ".worktreeinclude"
    if read_include and wti.is_file() and not wti.is_symlink():
        patterns += [ln.strip() for ln in wti.read_text(encoding="utf-8").splitlines()
                     if ln.strip() and not ln.startswith("#")]
    copied = 0
    if patterns:
        out = git(["ls-files", "--others", "--exclude-standard", "-z"], main, check=False)
        out += git(["ls-files", "--others", "--ignored", "--exclude-standard", "-z"], main, check=False)
        for rel in dict.fromkeys(p for p in out.split("\0") if p):
            if rel.startswith((".tempergraph/", ".git/")) or ".." in Path(rel).parts:
                continue
            if not any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(Path(rel).name, pat) for pat in patterns):
                continue
            src = main / rel
            if src.is_symlink() or not src.is_file():
                continue
            dst = path / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
    result: dict[str, Any] = {"included": copied, "setup": [], "submodules": "none"}
    deadline = time.monotonic() + decl.setup_timeout_s
    if decl.submodules == "auto" and (path / ".gitmodules").exists():
        try:
            git(["submodule", "update", "--init", "--recursive"], path)
            result["submodules"] = "initialised"
        except GitError as exc:
            raise WorkspaceRefused("bootstrap_failed", f"submodules: {exc}") from None
    for argv in decl.setup:
        if run_command is None:
            raise WorkspaceRefused("bootstrap_failed", "setup commands need the command runner")
        left = deadline - time.monotonic()
        t = time.monotonic()
        code = run_command(list(argv), path, max(1.0, left)) if left > 0 else 124
        result["setup"].append({"argv0": argv[0] if argv else "", "exit_code": code,
                                "duration_s": round(time.monotonic() - t, 3)})
        if code != 0:
            raise WorkspaceRefused("bootstrap_failed", f"setup command {argv[0] if argv else ''!r} exited {code}")
    return result


def attach_workspace(rec: WorkspaceRecord, thread: str, decl: WorktreeDecl | None, state_root: Path,
                     run_command: RunCommand | None = None) -> WorkspaceRecord:
    """On resume: reuse the worktree, or re-attach one to the run's branch (WSP-B1)."""
    if rec.mode == "in_place":
        rec.action = "reused"
        return rec
    path = Path(rec.path)
    main = main_checkout(state_root.parent) or state_root.parent
    if path.exists() and branch(path) == rec.branch:
        head = git(["rev-parse", "HEAD"], path, check=False).strip()
        changed = [ln for ln in git(["status", "--porcelain=v1"], path, check=False).splitlines() if ln]
        if rec.last_head and head != rec.last_head:
            n = git(["rev-list", "--count", f"{rec.last_head}..{head}", "--"], path, check=False).strip()
            rec.action = "external_change"
            rec.bootstrap = {**rec.bootstrap, "external_commits": int(n or 0), "external_changed": len(changed)}
        else:
            rec.action = "external_change" if changed else "reused"
            if changed:
                rec.bootstrap = {**rec.bootstrap, "external_commits": 0, "external_changed": len(changed)}
        rec.last_head = head
        return rec
    lock = _repo_lock(state_root)
    try:
        git(["worktree", "prune"], main)
        path.parent.mkdir(parents=True, exist_ok=True)
        git(["worktree", "add", "--end-of-options", str(path), rec.branch], main)
        git(["worktree", "lock", "--reason", LOCK_REASON + thread, "--end-of-options", str(path)], main)
    finally:
        lock.release()
    rec.bootstrap = bootstrap(main, path, decl, run_command)
    rec.action = "attached"
    rec.last_head = git(["rev-parse", "HEAD"], path, check=False).strip()
    return rec


def release_workspace(rec: WorkspaceRecord, cleanup: str = "never", state_root: Path | None = None
                      ) -> WorkspaceRecord:
    """After the finalizer: unlock. Release 1 keeps every worktree (`cleanup: on_finish` is release 2)."""
    if rec.mode == "worktree" and Path(rec.path).exists():
        git(["worktree", "unlock", "--end-of-options", rec.path], Path(rec.path), check=False)
    rec.state = "released"
    rec.action = "kept" if cleanup == "never" else "kept_cleanup_later"
    return rec


# ---------------------------------------------------------------------------------------------
# `worktree list` and `worktree path`


def list_worktrees(start: Path) -> list[dict[str, Any]]:
    main = main_checkout(start)
    if main is None:
        return []
    out = git(["worktree", "list", "--porcelain"], main, check=False)
    rows: list[dict[str, Any]] = []
    cur: dict[str, Any] = {}
    for line in [*out.splitlines(), ""]:
        if not line:
            reason = str(cur.get("locked", ""))
            if reason.startswith(LOCK_REASON):
                path = Path(cur["worktree"])
                rows.append({"thread": reason[len(LOCK_REASON):], "path": str(path),
                             "branch": str(cur.get("branch", "")).removeprefix("refs/heads/"),
                             "exists": path.exists(), "locked": True})
            cur = {}
            continue
        key, _, value = line.partition(" ")
        cur[key] = value
    return rows


def worktree_path(start: Path, thread: str) -> Path | None:
    for r in list_worktrees(start):
        if r["thread"] == thread:
            return Path(r["path"])
    return None


def python_for(workspace: Path, main: Path | None) -> str:
    """WSP-B3: the workspace's virtual environment, else the main checkout's, else the engine's; never PATH."""
    rel = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    for base in (workspace, main):
        if base is not None:
            for venv in (".venv", "venv"):
                cand = base / venv / rel
                if cand.exists():
                    return str(cand)
    return sys.executable
