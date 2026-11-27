"""The run's workspace: in place, or one engine-owned git worktree (WSP-B8, WSP-B9, WSP-B11, WTR-B17 to WTR-B27; release-1 part, ADR `first-release-is-simple-trusted-workflows-on-one-machine`).

Release 1 builds `run.workspace` (`auto`, `worktree`, `in_place`), the `sibling` root, the `head` base,
derived names, start with bootstrap, resume with re-attach, release without removal, and the data behind
`worktree list` and `worktree path`. Names are derived, never typed, and every git call puts
`--end-of-options` before a ref or path (WTR-B20).
"""

from __future__ import annotations

import contextlib
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from tempergraph.contracts import WorkflowSpec, WorktreeDecl
from tempergraph.durability.lock import LockHeld, RunLock
from tempergraph.git import GitError, branch, git, is_safe_ref, main_checkout, toplevel
from tempergraph.model import flow

Mode = Literal["in_place", "worktree"]
WRITE_TOOLS = frozenset({"edit", "write", "shell"})
BRANCH_PREFIX = "tg"
LOCK_REASON = "tempergraph "
MAX_FLAT = 80
FETCH_TIMEOUT_S = 30.0  # WTR-B21: `git fetch origin <default branch>`


class WorkspaceRefused(Exception):
    """A start refused before spend (exit 2), with a reason word."""

    def __init__(self, word: str, message: str) -> None:
        super().__init__(message)
        self.word = word


# ---------------------------------------------------------------------------------------------
# Names (WTR-B20)


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


def worktree_root(main: Path, root: str = "sibling") -> tuple[Path, str]:
    """WTR-B20: the folder the run worktrees live in and the root's kind (`sibling`, `in_repo` or `path`).
    Pure: it creates nothing. A `path:` root must be absolute and outside the main checkout, which holds the
    tracked tree, the state root and `.git`; anything else is refused before spend."""
    if root == "sibling":
        return sibling_root(main), "sibling"
    if root == "in_repo":
        return main / ".claude" / "worktrees", "in_repo"
    if not root.startswith("path:"):
        raise WorkspaceRefused("root_invalid", f"run.worktree.root {root!r} is not sibling, in_repo or "
                                               "path:<absolute path>")
    path = Path(root[5:])
    if not path.is_absolute():
        raise WorkspaceRefused("root_invalid", f"run.worktree.root {root!r}: the path must be absolute")
    path = Path(os.path.abspath(path))
    real, real_main = Path(os.path.realpath(path)), Path(os.path.realpath(main))
    if real == real_main or real_main in real.parents:
        raise WorkspaceRefused("root_misplaced", f"run.worktree.root {root!r} lies inside the main checkout "
                                                 "(its tracked tree, state root or .git); use in_repo or a "
                                                 "folder outside it")
    return path, "path"


def place(main: Path, root: str, workflow: str, task_id: str) -> tuple[Path, str]:
    """The worktree folder of a thread under a root, with the root's kind; `in_repo` folders take the `tg-` prefix."""
    folder, kind = worktree_root(main, root)
    flat = flat_name(workflow, task_id)
    return folder / (f"tg-{flat}" if kind == "in_repo" else flat), kind


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
    base_fetch: str = ""  # `default_branch` only: `ok` or `failed`, set at start (WTR-B21, WTR-B7)
    warnings: tuple[str, ...] = ()


@dataclass(kw_only=True)
class WorkspaceRecord:
    """WTR-B24; stored in state as a plain dict."""

    mode: Mode
    requested: str
    resolved_by: str
    path: str
    root_kind: str = ""
    branch: str = ""
    base_ref: str = ""
    base_commit: str = ""
    base_branch: str = ""
    base_fetch: str = ""
    children: list[dict[str, Any]] = field(default_factory=list)
    state: Literal["active", "released", "removed"] = "active"
    bootstrap: dict[str, Any] = field(default_factory=dict)
    last_head: str = ""
    action: str = ""
    cleanup: list[dict[str, Any]] = field(default_factory=list)  # WTR-B23: what `on_finish` did per worktree

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


def file_missing_at_base(main: Path, base_commit: str, base_ref: str, file_path: str) -> str | None:
    """WTR-B21: None when the file exists at the base commit; an error message when it is absent.

    Returns None when the check cannot be performed (no git, path outside the repo, empty commit).
    """
    if not base_commit or not file_path:
        return None
    top = toplevel(main)
    if top is None:
        return None
    try:
        rel = Path(file_path).relative_to(top)
    except ValueError:
        return None
    result = git(["rev-parse", "--verify", "--quiet", f"{base_commit}:{rel.as_posix()}"], main, check=False).strip()
    if result:
        return None
    return f"{file_path}: not found at {base_ref}"


def resolve_workspace(spec: WorkflowSpec, target: Path, requested: str | None = None, *, task_id: str = "",
                      prefix: str = BRANCH_PREFIX, base: str = "head", root: str = "sibling") -> WorkspacePlan:
    """WTR-B18, WTR-B20, WTR-B21; pure and model-free (it reads git, writes and fetches nothing)."""
    req = requested or spec.workspace or "auto"
    if req not in ("auto", "worktree", "in_place"):
        raise WorkspaceRefused("workspace_invalid", f"run.workspace {req!r} is not auto, worktree or in_place")
    main = main_checkout(target)
    if main is None or _is_bare(target):
        if req == "worktree":
            raise WorkspaceRefused("not_git", "a worktree run needs a git checkout")
        return WorkspacePlan(mode="in_place", requested=req, resolved_by="not_git", main=None, path=target)
    writes = writes_files(spec)
    writers = flow.has_writer_branch(spec) or flow.has_writer_contest(spec)
    if writers and req == "in_place":  # WTR-B18: a writer branch or a writing contest needs its own worktrees
        raise WorkspaceRefused("writers_need_worktree", "an explicit in_place run cannot hold a writer branch; a "
                                                        "parallel branch that declares `write` or `edit`, or a contest "
                                                        "of `writes: true`, needs a worktree")
    if req == "auto":
        mode: Mode = "worktree" if writes or writers else "in_place"
        by = "writers" if writers else "writes_files" if writes else "read_only"
    else:
        mode, by = ("worktree" if req == "worktree" else "in_place"), "requested"
    warnings: list[str] = []
    if mode == "in_place":
        if req == "in_place" and writes:
            warnings.append("in_place_writes: the workflow writes files in your checkout")
        here = toplevel(target)  # started inside a linked worktree, the run stays in that worktree
        return WorkspacePlan(mode="in_place", requested=req, resolved_by=by, main=main, path=here or main,
                             warnings=tuple(warnings))
    head = git(["rev-parse", "--verify", "HEAD"], main, check=False).strip()
    if not head:
        raise WorkspaceRefused("base_unresolved", "the main checkout has no commit to start a worktree from")
    cur = branch(main)
    base_branch = cur if cur and cur != "HEAD" else _default_branch(main)
    base_ref = "head"
    if base.startswith("ref:"):  # WTR-B21: a trial or eval case starts at its own commit (release 1 for trials)
        name = base[4:]
        if not name or not is_safe_ref(name) or name.startswith("-"):
            raise WorkspaceRefused("base_unresolved", f"run.worktree.base {base!r} is not a valid ref")
        commit = git(["rev-parse", "--verify", "--quiet", "--end-of-options", f"{name}^{{commit}}"], main,
                     check=False).strip()
        if not commit:
            raise WorkspaceRefused("base_unresolved", f"run.worktree.base {base!r} does not resolve to a commit")
        local = git(["rev-parse", "--verify", "--quiet", f"refs/heads/{name}"], main, check=False).strip()
        head, base_ref = commit, base
        base_branch = name if local else _default_branch(main)
    elif base == "default_branch":  # WTR-B21: the fetch happens at start, after `run --check` could not have made it
        name = _default_branch(main)
        if not is_safe_ref(name):
            raise WorkspaceRefused("base_unresolved", f"the default branch {name!r} is not a valid ref")
        head = _local_default(main, name)
        if not head:
            raise WorkspaceRefused("base_unresolved", f"run.worktree.base default_branch: no local copy of "
                                                      f"{name!r} to start from")
        base_ref, base_branch = "default_branch", name
    elif base != "head":
        raise WorkspaceRefused("base_unresolved", f"run.worktree.base {base!r} is not head, default_branch or "
                                                  "ref:<name>")
    dirty = [ln for ln in git(["status", "--porcelain=v1"], main, check=False).splitlines()
             if ".tempergraph/" not in ln]
    if dirty:
        warnings.append(f"uncommitted: {len(dirty)} changed paths in the main checkout are not in the worktree")
    br = run_branch(spec.name, task_id, prefix)
    if not is_safe_ref(br) or git(["check-ref-format", "--branch", br], main, check=False).strip() != br:
        raise WorkspaceRefused("branch_invalid", f"derived branch {br!r} is not a valid ref")
    path, root_kind = place(main, root, spec.name, task_id)
    return WorkspacePlan(mode="worktree", requested=req, resolved_by=by, main=main, path=path, root_kind=root_kind,
                         branch=br, base_ref=base_ref, base_commit=head, base_branch=base_branch,
                         warnings=tuple(warnings))


def _is_bare(target: Path) -> bool:
    return git(["rev-parse", "--is-bare-repository"], target, check=False).strip() == "true"


def _default_branch(main: Path) -> str:
    ref = git(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], main, check=False).strip()
    return ref.split("/", 1)[1] if "/" in ref else "main"


def _local_default(main: Path, name: str) -> str:
    """The commit of the local copy of the default branch: the branch itself, else its remote-tracking ref."""
    for ref in (f"refs/heads/{name}", f"refs/remotes/origin/{name}"):
        commit = git(["rev-parse", "--verify", "--quiet", "--end-of-options", f"{ref}^{{commit}}"], main,
                     check=False).strip()
        if commit:
            return commit
    return ""


def _fetch_base(main: Path, name: str) -> str:
    """WTR-B21: `git fetch origin <branch>` within 30 s; the fetched commit, or "" when the fetch failed."""
    try:
        git(["fetch", "--end-of-options", "origin", name], main, timeout_s=FETCH_TIMEOUT_S)
        return git(["rev-parse", "--verify", "--quiet", "FETCH_HEAD^{commit}"], main, check=False).strip()
    except GitError:
        return ""


def check_plan(plan: WorkspacePlan) -> list[str]:
    """`run --check`: what a start would refuse, creating nothing (WTR-B22)."""
    problems: list[str] = []
    if plan.mode != "worktree" or plan.main is None:
        return problems
    if _branch_exists(plan.main, plan.branch):
        problems.append(f"branch_exists: {plan.branch}")
    if plan.path.exists():
        problems.append(f"path_exists: {plan.path}")
    parent = plan.path.parent  # the nearest folder that exists must take a new root or a new worktree
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    if not parent.is_dir() or not os.access(parent, os.W_OK):
        problems.append(f"root_not_writable: {parent}")
    return problems


def _branch_exists(main: Path, br: str) -> bool:
    return bool(git(["rev-parse", "--verify", "--quiet", "--end-of-options", f"refs/heads/{br}"], main,
                    check=False).strip())


# ---------------------------------------------------------------------------------------------
# Lifecycle (WTR-B22)

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
    base_commit, base_fetch = plan.base_commit, ""
    if plan.base_ref == "default_branch":  # WTR-B21, WTR-B7: the fetch, or the local copy and `failed`
        fetched = _fetch_base(main, plan.base_branch)
        base_commit, base_fetch = (fetched, "ok") if fetched else (plan.base_commit, "failed")
    lock = _repo_lock(state_root)
    try:
        root_dir = plan.path.parent
        created = not root_dir.exists()
        root_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if created and plan.root_kind == "path":  # WTR-B20: owner-only when the engine makes it
            os.chmod(root_dir, 0o700)
        if plan.root_kind == "in_repo":
            _exclude_in_repo(main)
        git(["worktree", "add", "-b", plan.branch, "--end-of-options", str(plan.path), base_commit], main)
        git(["worktree", "lock", "--reason", LOCK_REASON + thread, "--end-of-options", str(plan.path)], main)
    finally:
        lock.release()
    rec = WorkspaceRecord(mode="worktree", requested=plan.requested, resolved_by=plan.resolved_by,
                          path=str(plan.path), root_kind=plan.root_kind, branch=plan.branch, base_ref=plan.base_ref,
                          base_commit=base_commit, base_branch=plan.base_branch, base_fetch=base_fetch,
                          last_head=base_commit, action="prepared")
    try:
        rec.bootstrap = bootstrap(main, plan.path, decl, run_command, read_include=read_include)
    except WorkspaceRefused:
        _remove_new(main, plan.path, plan.branch)
        raise
    return rec


def _exclude_in_repo(main: Path) -> None:
    """WTR-B20: the `in_repo` root goes into `.git/info/exclude` when git does not already ignore it; never a
    tracked file."""
    probe = ".claude/worktrees/x"
    if git(["check-ignore", "--end-of-options", probe], main, check=False).strip():
        return
    where = git(["rev-parse", "--path-format=absolute", "--git-path", "info/exclude"], main).strip()
    exclude = Path(where)
    exclude.parent.mkdir(parents=True, exist_ok=True)
    have = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    sep = "" if not have or have.endswith("\n") else "\n"
    exclude.write_text(f"{have}{sep}/.claude/worktrees/\n", encoding="utf-8")


def _remove_new(main: Path, path: Path, br: str) -> None:
    """WSP-B2, WTR-B22: undo a start that has just failed without `--force` and without deleting a branch by
    name (WTR-B23): unlock, remove the new folder, let git forget it, then drop the new branch's ref."""
    git(["worktree", "unlock", "--end-of-options", str(path)], main, check=False)
    shutil.rmtree(path, ignore_errors=True)
    git(["worktree", "prune"], main, check=False)
    git(["update-ref", "-d", f"refs/heads/{br}"], main, check=False)


def writer_names(run_path: Path, run_branch_name: str, unit: str, thread: str, *, kind: str = "w", visit: int = 1
                 ) -> tuple[str, str]:
    """WTR-B20: the flat name and branch of a writer branch's worktree, the suffix `--w-<branch>` on the run's own,
    never a child path of the run branch. With `kind="i"` the child is an item of a concurrent map, named by its slot
    `<unit>.<item id>`, and the suffix is `--i-<item id>` with the whole id (up to 40 characters, so two items whose
    ids share their first 24 characters get two names); from the map's second visit (`visit` above 1) the suffix is
    `--i<visit>-<item id>`, so no visit meets the names of another; with `kind="s"` it is a slot of a contest, named the
    same way, and the suffix is `--s-<slot>` for the first attempt and `--s<attempt>-<slot>` from the second (`visit`
    above 1), so no attempt meets the names of another; a name over the limit shortens the run's part, not the
    suffix."""
    label = unit.split(".", 1)[1] if kind in ("i", "s") and "." in unit else unit
    tag = f"{kind}{visit}" if kind in ("i", "s") and visit > 1 else kind
    part = f"--{tag}-" + flat_part(label)[: 40 if kind in ("i", "s") else 24]
    name = run_path.name + part
    if len(name) > MAX_FLAT:
        digest = hashlib.sha256(f"{thread}/{tag}-{unit}".encode()).hexdigest()[:8]
        name = run_path.name[: MAX_FLAT - len(part) - 9] + "-" + digest + part
    return name, run_branch_name + part


def cut_writers(rec: WorkspaceRecord, thread: str, units: Sequence[str], decl: WorktreeDecl | None, state_root: Path,
                run_command: RunCommand | None = None, *, read_include: bool = True, kind: str = "w", visit: int = 1
                ) -> WorkspaceRecord:
    """WSP-B11, WSP-B19: one sibling worktree and branch per writer branch (`kind="i"`: per item of a concurrent map,
    `kind="s"`: per slot of a contest, the child's unit being its slot), cut from the run branch's head, locked and
    bootstrapped, each appended to `rec.children`. A unit that already has one of the same `visit` is reused, except a
    contest's slot: its branch is never cut over or reused, the cut is refused (`name_collision`) per slot and attempt.
    A child of a map's visit or a contest's attempt above 1 (`visit`) is recorded with its `visit` and named
    `--i<visit>-<item>` or `--s<visit>-<slot>` (WTR-B20, WSP-B20): a first-visit child has no such key, and the
    children of other visits stay in `rec.children`, untouched. A failure removes what this call made and raises
    `WorkspaceRefused` naming the writer branch, item or slot."""
    what = {"i": "map item", "s": "contest slot"}.get(kind, "writer branch")
    main = main_checkout(state_root.parent) or state_root.parent
    run_path = Path(rec.path)
    made: list[tuple[Path, str]] = []
    children = list(rec.children)
    try:
        for unit in units:
            if any(c.get("unit") == unit and int(c.get("visit", 1)) == visit and Path(str(c.get("path"))).exists()
                   for c in children):
                if kind == "s":  # a second cut of a slot would meet the first one's branch (CTS-B5, CTS-B9)
                    raise WorkspaceRefused("name_collision", "its worktree and branch already exist")
                continue
            name, br = writer_names(run_path, rec.branch, unit, thread, kind=kind, visit=visit)
            path = run_path.parent / name
            if _branch_exists(main, br) or path.exists():
                raise WorkspaceRefused("name_collision", f"{what} {unit}: {br} or {path} already exists")
            lock = _repo_lock(state_root)
            try:
                base = git(["rev-parse", "--verify", "--end-of-options", f"refs/heads/{rec.branch}"], main).strip()
                path.parent.mkdir(parents=True, exist_ok=True)
                git(["worktree", "add", "-b", br, "--end-of-options", str(path), base], main)
                made.append((path, br))
                git(["worktree", "lock", "--reason", LOCK_REASON + thread, "--end-of-options", str(path)], main)
            finally:
                lock.release()
            bootstrap(main, path, decl, run_command, read_include=read_include)
            children = [c for c in children if not (c.get("unit") == unit and int(c.get("visit", 1)) == visit)]
            child: dict[str, Any] = {"unit": unit, "name": name, "path": str(path), "branch": br, "state": "active"}
            children.append({**child, "visit": visit} if visit > 1 else child)
    except (WorkspaceRefused, GitError) as exc:
        for path, br in made:
            _remove_new(main, path, br)
        word = exc.word if isinstance(exc, WorkspaceRefused) else "worktree_failed"
        raise WorkspaceRefused(word, f"{what} {unit}: {exc}") from None
    rec.children = children
    return rec


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


def write_pause_mark(path: Path, worktree: Path) -> None:
    """Write the head and the sorted status lines of `worktree` where a resume reads them (WTR-B28)."""
    from tempergraph.git import fingerprint

    fp = fingerprint(worktree)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"head": fp.head, "status": sorted(ln for ln in fp.status.splitlines() if ln)}))
    os.chmod(path, 0o600)


def take_pause_mark(path: Path) -> dict[str, Any] | None:
    """Read and remove the marker a paused segment left; None when it is absent or unreadable."""
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        doc = None
    with contextlib.suppress(OSError):
        path.unlink()
    if not isinstance(doc, dict) or not isinstance(doc.get("status"), list):
        return None
    return doc


def attach_workspace(rec: WorkspaceRecord, thread: str, decl: WorktreeDecl | None, state_root: Path,
                     run_command: RunCommand | None = None, *,
                     marked: Mapping[str, Any] | None = None) -> WorkspaceRecord:
    """On resume: reuse the worktree, or re-attach one to the run's branch (WSP-B1). With `marked`, the head and
    status the paused segment left are what the worktree is compared with (WTR-B28)."""
    if rec.mode == "in_place":
        rec.action = "reused"
        return rec
    path = Path(rec.path)
    main = main_checkout(state_root.parent) or state_root.parent
    if path.exists() and branch(path) == rec.branch and marked is not None:
        from tempergraph.git import fingerprint

        fp = fingerprint(path)
        now = [ln for ln in fp.status.splitlines() if ln]
        was = [str(ln) for ln in marked.get("status", [])]
        extra = [ln for ln in now if ln not in was]
        mark_head = str(marked.get("head") or "")
        if fp.head == mark_head and not extra and sorted(now) == sorted(was):
            rec.action = "reused"
        else:
            n = "0"
            if mark_head and fp.head != mark_head:
                n = git(["rev-list", "--count", f"{mark_head}..{fp.head}", "--"], path, check=False).strip()
            rec.action = "external_change"
            rec.bootstrap = {**rec.bootstrap, "external_commits": int(n or 0),
                             "external_changed": len(extra)}
        rec.last_head = fp.head
        return rec
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


def _entries(main: Path) -> list[dict[str, str]]:
    """`git worktree list --porcelain` as one dict per worktree (`worktree`, `HEAD`, `branch`, `locked`, ...)."""
    out = git(["worktree", "list", "--porcelain"], main, check=False)
    rows: list[dict[str, str]] = []
    cur: dict[str, str] = {}
    for line in [*out.splitlines(), ""]:
        if not line:
            if cur:
                rows.append(cur)
            cur = {}
            continue
        key, _, value = line.partition(" ")
        cur[key] = value
    return sorted(rows, key=lambda r: "writer" in r)  # a run's own worktree first, its writers after it


def _lock_of(main: Path, path: str | Path) -> str | None:
    """The reason a worktree is locked with, "" for a lock with no reason, None when it is not locked."""
    want = os.path.realpath(path)
    for e in _entries(main):
        if os.path.realpath(e.get("worktree", "")) == want:
            return e.get("locked")
    return None


def _clean_removal(main: Path, path: Path) -> tuple[bool, str]:
    """WTR-B23: remove one worktree only when it is clean, has no submodules and is locked by no one else, with
    `git worktree remove` and never `--force`. Returns whether it is gone and, when not, why it was kept."""
    if not path.exists():
        return False, "missing"
    lock = _lock_of(main, path)
    if lock is not None and not lock.startswith(LOCK_REASON):
        return False, f"locked: {lock}" if lock else "locked"
    dirty = [ln for ln in git(["status", "--porcelain=v1"], path, check=False).splitlines()
             if ln and ".tempergraph/" not in ln]
    if dirty:
        return False, "dirty"
    if (path / ".gitmodules").exists():
        return False, "submodules"
    if lock is not None:
        git(["worktree", "unlock", "--end-of-options", str(path)], main, check=False)
    try:
        git(["worktree", "remove", "--end-of-options", str(path)], main)
    except GitError as exc:
        if lock is not None:  # still the run's: put its lock back
            git(["worktree", "lock", "--reason", lock, "--end-of-options", str(path)], main, check=False)
        return False, str(exc)
    return True, "removed"


def release_workspace(rec: WorkspaceRecord, cleanup: str = "never", state_root: Path | None = None, *,
                      outcome: str = "finished") -> WorkspaceRecord:
    """After the finalizer (WTR-B22, WTR-B23): unlock the run's worktree when the lock is the engine's and, under
    `cleanup: on_finish` and any outcome but `error`, remove each clean worktree of the run (the run's own and its
    writer, slot and item children) without `--force`, keeping the rest and every branch. `rec.cleanup` holds one
    `{name, path, result, reason}` per worktree; `rec.action` is then `removed` or `kept`."""
    path = Path(rec.path)
    main = (main_checkout(state_root.parent) or state_root.parent) if state_root is not None else None
    if rec.mode == "worktree" and path.exists():
        probe = main or main_checkout(path)
        lock = _lock_of(probe, path) if probe is not None else ""
        if lock is None or lock.startswith(LOCK_REASON):
            git(["worktree", "unlock", "--end-of-options", rec.path], path, check=False)
    rec.state = "released"
    rec.action = "kept"
    if cleanup != "on_finish" or outcome == "error" or rec.mode != "worktree" or main is None:
        return rec
    targets = [{"name": "run", "path": rec.path}, *({"name": str(c.get("name") or ""), "path": str(c.get("path"))}
                                                     for c in rec.children if c.get("path"))]
    rec.cleanup = []
    for t in targets:
        gone, reason = _clean_removal(main, Path(t["path"]))
        rec.cleanup.append({**t, "result": "removed" if gone else "kept", "reason": "" if gone else reason})
    if all(c["result"] == "removed" for c in rec.cleanup):
        rec.state, rec.action = "removed", "removed"
    return rec


# ---------------------------------------------------------------------------------------------
# `worktree list` and `worktree path`


def _owners(state_root: Path) -> dict[str, str]:
    """Real path of a worktree -> the thread whose run log last recorded it (the local log is the one place a
    path is kept, WTR-B24). A finished run's worktree carries no lock, so the records are what name its owner."""
    owners: dict[str, str] = {}
    runs = state_root / "runs"
    if not runs.is_dir():
        return owners
    for log in sorted(runs.glob("*/*/run.jsonl")):
        last = ""
        try:
            for ln in log.read_text(encoding="utf-8").splitlines():
                if '"kind": "workspace"' in ln and '"path"' in ln:
                    rec = json.loads(ln)
                    if rec.get("kind") == "workspace" and rec.get("mode") == "worktree" and rec.get("path") \
                            and rec.get("action") != "foreign":
                        last = str(rec["path"])
        except (OSError, ValueError):
            continue
        if last:
            owners[os.path.realpath(last)] = f"{log.parent.parent.name}/{log.parent.name}"
    return owners


def _foreign_paths(state_root: Path) -> set[str]:
    """Paths (relative to the repository's parent) of the `foreign` workspace records of every run."""
    out: set[str] = set()
    for log in (state_root / "runs").glob("*/*/run.jsonl"):
        try:
            for ln in log.read_text(encoding="utf-8").splitlines():
                if '"action": "foreign"' in ln:
                    rec = json.loads(ln)
                    if rec.get("kind") == "workspace" and rec.get("path"):
                        out.add(str(rec["path"]))
        except (OSError, ValueError):
            continue
    return out


def thread_state(state_root: Path, thread: str) -> str:
    """`running` (its lock is held), else from its exit file: `finished`, `paused`, `stopped`; `unfinished`
    when the segment left none. Read-only, and it needs no workflow."""
    from tempergraph.durability.lock import is_held
    from tempergraph.store.layout import lock_path, run_dir

    workflow, _, task = thread.partition("/")
    if is_held(lock_path(state_root, workflow, task)):
        return "running"
    try:
        code = int(json.loads((run_dir(state_root, workflow, task) / "exit.json").read_text(encoding="utf-8"))
                   .get("exit_code"))
    except (OSError, ValueError, TypeError):
        return "unfinished"
    return {0: "finished", 3: "paused"}.get(code, "stopped")


def _age_days(state_root: Path, thread: str) -> float:
    from tempergraph.store.layout import run_dir

    workflow, _, task = thread.partition("/")
    try:
        return max(0.0, (time.time() - (run_dir(state_root, workflow, task) / "run.jsonl").stat().st_mtime) / 86400)
    except OSError:
        return 0.0


def _count(main: Path, path: Path, spec: str) -> int:
    out = git(["rev-list", "--count", spec, "--"], path, check=False).strip()
    return int(out) if out.isdigit() else 0


def list_worktrees(start: Path, *, all: bool = False) -> list[dict[str, Any]]:
    """WTR-B27: the engine's worktrees of this repository from the records and `git worktree list` (thread,
    thread state, path, branch, ahead and behind its base, dirty count, lock, `removable`); `all` adds foreign
    worktrees and git worktrees no record owns. Read-only."""
    from tempergraph.store.layout import state_root_path

    main = main_checkout(start)
    if main is None:
        return []
    state_root = state_root_path(main)
    owners = _owners(state_root)
    foreign = _foreign_paths(state_root)
    rows: list[dict[str, Any]] = []
    for e in _entries(main):
        path = Path(e["worktree"])
        if os.path.realpath(path) == os.path.realpath(main) or "bare" in e:
            continue
        lock = e.get("locked")
        thread = lock[len(LOCK_REASON):] if lock is not None and lock.startswith(LOCK_REASON) else \
            owners.get(os.path.realpath(path))
        owned = thread is not None
        if not owned and not all:
            continue
        exists = path.exists()
        dirty = [ln for ln in git(["status", "--porcelain=v1"], path, check=False).splitlines()
                 if ln and ".tempergraph/" not in ln] if exists else []
        row: dict[str, Any] = {"thread": thread, "path": str(path),
                               "branch": e.get("branch", "").removeprefix("refs/heads/"), "exists": exists,
                               "locked": lock is not None}
        if "--w-" in path.name.split("--", 1)[-1]:  # WTR-B20: `<workflow>--<task>--w-<branch>`, a writer's
            row["writer"] = path.name.rsplit("--w-", 1)[1]
        if owned:
            assert thread is not None
            state = thread_state(state_root, thread)
            base = _base_of(state_root, thread)
            ahead, behind = ((_count(main, path, f"{base}..HEAD"), _count(main, path, f"HEAD..{base}"))
                             if base and exists else (0, 0))
            row.update(state=state, ahead=ahead, behind=behind, dirty=len(dirty), lock=lock,
                       removable=bool(exists and state != "running" and not dirty
                                      and not (path / ".gitmodules").exists()))
        else:
            rel = os.path.relpath(path, main.parent)
            row.update(state="foreign" if rel in foreign else "unowned", dirty=len(dirty), lock=lock,
                       removable=False)
        rows.append(row)
    return rows


def _base_of(state_root: Path, thread: str) -> str:
    from tempergraph.store.layout import run_dir

    workflow, _, task = thread.partition("/")
    base = ""
    try:
        for ln in (run_dir(state_root, workflow, task) / "run.jsonl").read_text(encoding="utf-8").splitlines():
            if '"kind": "workspace"' in ln and '"base_commit"' in ln:
                rec = json.loads(ln)
                base = str(rec.get("base_commit") or base)
    except (OSError, ValueError):
        return ""
    return base


def worktree_path(start: Path, thread: str) -> Path | None:
    """WTR-B27: the run's own worktree, never one of its writers'."""
    for r in list_worktrees(start):
        if r["thread"] == thread and "writer" not in r:
            return Path(r["path"])
    return None


def prune_plan(start: Path, *, thread: str | None = None, finished: bool = False,
               older_than: float | None = None) -> list[dict[str, Any]]:
    """WTR-B27: the removable worktrees the selectors match. Never one of a `running` thread."""
    from tempergraph.store.layout import state_root_path

    main = main_checkout(start)
    if main is None:
        return []
    state_root = state_root_path(main)
    out = []
    for r in list_worktrees(start):
        if not r.get("removable") or r["state"] == "running":
            continue
        if thread is not None and r["thread"] != thread:
            continue
        if finished and r["state"] != "finished":
            continue
        if older_than is not None and _age_days(state_root, str(r["thread"])) < older_than:
            continue
        out.append(r)
    return out


def prune_apply(start: Path, rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """WTR-B16, WTR-B27: remove the planned worktrees by the cleanup rule (clean, no submodules, no `--force`),
    then `git worktree prune`. A branch is never touched; a worktree whose thread started running since the plan
    is kept."""
    from tempergraph.store.layout import state_root_path

    main = main_checkout(start)
    if main is None:
        return []
    state_root = state_root_path(main)
    results = []
    for r in rows:
        if thread_state(state_root, str(r["thread"])) == "running":
            results.append({"thread": r["thread"], "path": r["path"], "result": "kept", "reason": "running"})
            continue
        gone, reason = _clean_removal(main, Path(str(r["path"])))
        results.append({"thread": r["thread"], "path": r["path"], "result": "removed" if gone else "kept",
                        "reason": "" if gone else reason})
    git(["worktree", "prune"], main, check=False)
    return results


def scan_foreign_worktrees(main: Path, known: Sequence[str | Path] = ()) -> dict[str, str]:
    """WTR-B26: `git worktree list --porcelain`, minus the main checkout, the paths in `known` (the run's own)
    and any worktree some run of the engine holds locked. Returns path -> branch. Reads only."""
    skip = {os.path.realpath(k) for k in known} | {os.path.realpath(main)}
    found: dict[str, str] = {}
    for e in _entries(main):
        path = e.get("worktree", "")
        if not path or "bare" in e or os.path.realpath(path) in skip:
            continue
        if e.get("locked", None) is not None and e["locked"].startswith(LOCK_REASON):
            continue
        found[path] = e.get("branch", "").removeprefix("refs/heads/")
    return found


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
