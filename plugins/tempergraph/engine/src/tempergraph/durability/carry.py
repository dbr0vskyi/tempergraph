"""A run's state carried on its own branch (CAR-B5): the carried subset, the state branch, the lease.

The engine writes the state branch with git plumbing only, so no checkout, index or work branch is touched.
A push or a deletion that fails never changes a run's exit (OVR-B4): the thread's carry record says what
is left to do, and `carry push` or `carry drop` finishes it.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from tempergraph import git as gitmod
from tempergraph.constants import ENGINE_VERSION, STORE_LAYOUT
from tempergraph.durability import engine_file
from tempergraph.security.scrub import scrub
from tempergraph.store.layout import now_iso, run_dir

PREFIX = ".tempergraph-carry"
BRANCH_ROOT = "tempergraph/state"
MARKER = "carry.local.json"  # this machine's carry record of the thread; never carried
IDENTITY = ("-c", "user.name=tempergraph", "-c", "user.email=tempergraph@localhost")
TEXT_SUFFIXES = frozenset({".json", ".jsonl", ".md", ".txt", ".log", ".yaml", ".yml", ".toml"})
SESSION_KEPT = frozenset({"meta.json", "activity.jsonl", "digest.json"})
RUN_SKIPPED_DIRS = frozenset({"output", "checks", "hooks"})
CHECKPOINT_TABLES = ("checkpoints", "writes")


class CarryRefused(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CarryFailed(Exception):
    """The network or the remote failed; nothing local was lost."""


def branch_name(workflow: str, task_id: str) -> str:
    from tempergraph.workspace import flat_part

    name = f"{BRANCH_ROOT}/{flat_part(workflow)}/{flat_part(task_id)}"
    if not gitmod.is_safe_ref(name):
        raise CarryRefused("branch_invalid", f"derived state branch {name!r} is not a valid ref")
    return name


def remote_of(repo: Path, remote: str | None = None) -> str:
    """CAR-B6: `--remote`, else the work branch's upstream remote, else `origin`; none is a refusal."""
    remotes = gitmod.git(["remote"], repo, check=False).split()
    if remote:
        if remote not in remotes:
            raise CarryRefused("carry_no_remote", f"this repository has no remote {remote!r}")
        return remote
    cur = gitmod.branch(repo)
    up = gitmod.git(["config", "--get", f"branch.{cur}.remote"], repo, check=False).strip() if cur else ""
    if up in remotes:
        return up
    if "origin" in remotes:
        return "origin"
    raise CarryRefused("carry_no_remote", "carrying needs a git remote: add one, or name it with --remote")


# -- this machine's record of a carried thread -------------------------------------------------------------------


def marker_path(root: Path, workflow: str, task_id: str) -> Path:
    return run_dir(root, workflow, task_id) / MARKER


def marker(root: Path, workflow: str, task_id: str) -> dict[str, Any]:
    try:
        doc = json.loads(marker_path(root, workflow, task_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def set_marker(root: Path, workflow: str, task_id: str, **fields: Any) -> dict[str, Any]:
    doc = {"schema_version": 1, **marker(root, workflow, task_id), **fields}
    path = marker_path(root, workflow, task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return doc


def is_on(root: Path, workflow: str, task_id: str) -> bool:
    return bool(marker(root, workflow, task_id).get("on"))


# -- what is carried (CAR-B7, CAR-B2) ----------------------------------------------------------------------------------


def _carried_run_file(rel: PurePosixPath) -> bool:
    parts = rel.parts
    if rel.name in (MARKER, "stderr.log") or RUN_SKIPPED_DIRS & set(parts[:-1]):
        return False
    if parts[0] == "sessions":
        return len(parts) == 3 and parts[2] in SESSION_KEPT
    return not (len(parts) >= 2 and parts[0] == "evidence" and parts[1] == "prompts")


def _scrubbed(data: bytes, rel: str, hits: dict[str, int]) -> bytes:
    if PurePosixPath(rel).suffix not in TEXT_SUFFIXES:
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    clean = scrub(text)
    if clean != text:
        hits[rel] = hits.get(rel, 0) + 1
    return clean.encode("utf-8")


def _thread_checkpoint(src: Path, tid: str, dest: Path) -> None:
    """Only this thread's rows of the workflow's checkpoint store, in a store of the same shape.

    A row is chosen by its thread alone, so the checkpoint namespaces of a sub-workflow child, which runs under the
    parent's thread (SWF-B8), travel with the parent's own rows (CAR-B1)."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    out = sqlite3.connect(str(dest))
    try:
        SqliteSaver(out).setup()
        if src.exists():
            out.execute("ATTACH DATABASE ? AS src", (str(src),))
            for table in CHECKPOINT_TABLES:
                out.execute(f"INSERT INTO main.{table} SELECT * FROM src.{table} WHERE thread_id = ?", (tid,))  # noqa: S608
            out.commit()
            out.execute("DETACH DATABASE src")
        out.execute("PRAGMA journal_mode=DELETE")
        out.commit()
    finally:
        out.close()


def _ledger_rows(root: Path, tid: str) -> list[str]:
    try:
        lines = (root / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict) and tid in (r.get("thread_id"), r.get("thread")):
            out.append(ln)
    return out


def _workspace(root: Path, workflow: str, task_id: str, repo: Path) -> dict[str, Any]:
    """The workspace of the thread with the branch and base; the path is left to the root rule (WTR-B18)."""
    from tempergraph.run.events import records

    rec: dict[str, Any] = {}
    for r in records(run_dir(root, workflow, task_id) / "run.jsonl"):
        if r.get("kind") == "workspace":
            rec = r
    mode = rec.get("mode") or "in_place"
    return {"mode": mode, "branch": rec.get("branch") or gitmod.branch(repo), "base_commit": rec.get("base_commit"),
            "root_kind": "sibling" if mode == "worktree" else "main"}


def collect(root: Path, repo: Path, workflow: str, task_id: str, *, workflow_version: str | None,
            lease: Mapping[str, Any] | None, staging: Path) -> dict[str, Path]:
    """The carried files, written under `staging`; returns carried path → file. Scrubbed where text."""
    from tempergraph.release import release
    from tempergraph.run.log import last_seq

    tid = f"{workflow}/{task_id}"
    files: dict[str, Path] = {}
    hits: dict[str, int] = {}

    def put(rel: str, data: bytes) -> None:
        path = staging / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_scrubbed(data, rel, hits))
        files[rel] = path

    base = run_dir(root, workflow, task_id)
    for p in sorted(base.rglob("*")) if base.is_dir() else []:
        rel = PurePosixPath(p.relative_to(base).as_posix())
        if p.is_file() and not p.is_symlink() and _carried_run_file(rel):
            put(f"run/{rel}", p.read_bytes())
    cp = staging / "checkpoint.sqlite"
    _thread_checkpoint(engine_file.checkpoint_of(root, workflow, task_id), tid, cp)
    files["checkpoint.sqlite"] = cp
    put("ledger.jsonl", "".join(ln + "\n" for ln in _ledger_rows(root, tid)).encode("utf-8"))
    put("workspace.json", json.dumps(_workspace(root, workflow, task_id, repo), indent=2).encode("utf-8"))
    rel_doc = release()
    manifest = {"schema_version": 1, "engine_version": ENGINE_VERSION, "store_layout": STORE_LAYOUT,
                "checkpoint_format": rel_doc.get("checkpoint_format"), "workflow": workflow, "task_id": task_id,
                "workflow_version": workflow_version, "seq": last_seq(base / "run.jsonl"),
                "lease": dict(lease) if lease else None, "pushed_at": now_iso(), "scrubbed": hits,
                "files": {rel: hashlib.sha256(path.read_bytes()).hexdigest() for rel, path in sorted(files.items())}}
    put("carry.json", json.dumps(manifest, indent=2).encode("utf-8"))
    return files


# -- the state branch (CAR-B6) ---------------------------------------------------------------------------------


def _tree(repo: Path, files: Mapping[str, Path]) -> str:
    """One tree holding `.tempergraph-carry/` and nothing else, built without the index."""
    nested: dict[str, Any] = {}
    for rel, path in files.items():
        parts = PurePosixPath(rel).parts
        if not parts or ".." in parts or PurePosixPath(rel).is_absolute():
            raise CarryRefused("carry_path", f"{rel!r} is not a path inside {PREFIX}/")
        node = nested
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = gitmod.git(["hash-object", "-w", "--", str(path)], repo).strip()

    def write(node: Mapping[str, Any]) -> str:
        lines = []
        for name, v in sorted(node.items()):
            lines.append(f"040000 tree {write(v)}\t{name}" if isinstance(v, dict) else f"100644 blob {v}\t{name}")
        return gitmod.git(["mktree"], repo, stdin="".join(ln + "\n" for ln in lines)).strip()

    root = gitmod.git(["mktree"], repo, stdin=f"040000 tree {write(nested)}\t{PREFIX}\n").strip()
    listed = gitmod.git(["ls-tree", "-r", "--name-only", root], repo).splitlines()
    if not listed or any(not p.startswith(PREFIX + "/") for p in listed):
        raise CarryRefused("carry_path", f"a state commit holds only {PREFIX}/")
    return root


def _local_ref(branch: str) -> str:
    return f"refs/heads/{branch}"


def _tracking_ref(remote: str, branch: str) -> str:
    return f"refs/remotes/{remote}/{branch}"


def _rev(repo: Path, ref: str) -> str:
    return gitmod.git(["rev-parse", "--verify", "--quiet", ref], repo, check=False).strip()


def fetch(repo: Path, remote: str, branch: str) -> str | None:
    """The remote state branch's tip, fetched; None when the remote has no such branch. Raises `CarryFailed`
    when the remote cannot be reached."""
    try:
        heads = gitmod.git(["ls-remote", "--heads", remote, _local_ref(branch)], repo)
    except gitmod.GitError as exc:
        raise CarryFailed(str(exc)) from exc
    if not heads.strip():
        return None
    try:
        gitmod.git(["fetch", "--no-tags", remote, f"+{_local_ref(branch)}:{_tracking_ref(remote, branch)}"], repo)
    except gitmod.GitError as exc:
        raise CarryFailed(str(exc)) from exc
    return _rev(repo, _tracking_ref(remote, branch)) or None


def manifest_at(repo: Path, commit: str) -> dict[str, Any]:
    try:
        doc = json.loads(gitmod.git(["show", f"{commit}:{PREFIX}/carry.json"], repo))
    except (gitmod.GitError, ValueError) as exc:
        raise CarryRefused("carry_manifest", f"the state branch's carry.json does not parse: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("files"), dict):
        raise CarryRefused("carry_manifest", "the state branch's carry.json does not parse")
    return doc


def _held_by_other(lease: Any, machine: str | None) -> bool:
    return isinstance(lease, Mapping) and bool(lease.get("machine")) and lease.get("machine") != machine


def _lease_text(lease: Mapping[str, Any]) -> str:
    return f"machine {lease.get('machine')} holds the lease since {lease.get('since')}"


@dataclass(kw_only=True)
class Pushed:
    branch: str
    remote: str
    commit: str
    seq: int
    lease: dict[str, Any] | None


def push(root: Path, repo: Path, workflow: str, task_id: str, *, remote: str | None = None,
         workflow_version: str | None = None, lease: Mapping[str, Any] | None = None,
         machine: str | None = None, force: bool = False) -> Pushed:
    """One new commit on the state branch, pushed. Refused when the remote holds a newer state or another
    machine's lease; a non-fast-forward rejection keeps the local state and pushes nothing (CAR-B9, CAR-B4)."""
    from tempergraph.run.log import last_seq

    remote = remote_of(repo, remote or marker(root, workflow, task_id).get("remote"))
    branch = branch_name(workflow, task_id)
    tip = fetch(repo, remote, branch)
    seq = last_seq(run_dir(root, workflow, task_id) / "run.jsonl")
    if tip:
        theirs = manifest_at(repo, tip)
        if int(theirs.get("seq") or 0) > seq:
            raise CarryRefused("carry_behind", f"the state branch holds seq {theirs.get('seq')}, newer than this "
                                               f"machine's {seq}: `tempergraph carry pull {workflow} {task_id}` first")
        if _held_by_other(theirs.get("lease"), machine) and not force:
            raise CarryRefused("carry_leased", _lease_text(theirs["lease"]) + "; `carry pull --force` takes it")
    with tempfile.TemporaryDirectory(prefix="tg-carry-") as tmp:
        files = collect(root, repo, workflow, task_id, workflow_version=workflow_version, lease=lease,
                        staging=Path(tmp))
        tree = _tree(repo, files)
    parent = ["-p", tip] if tip else []
    subject = f"tempergraph state {workflow}/{task_id} seq {seq}"
    commit = gitmod.git([*IDENTITY, "commit-tree", tree, *parent, "-m", subject], repo).strip()
    try:
        gitmod.git(["push", remote, f"{commit}:{_local_ref(branch)}"], repo)
    except gitmod.GitError as exc:
        if "non-fast-forward" in str(exc) or "fetch first" in str(exc) or "rejected" in str(exc):
            raise CarryRefused("carry_behind", "another machine pushed this thread's state first; nothing was "
                                               f"pushed: `tempergraph carry pull {workflow} {task_id}`") from exc
        raise CarryFailed(str(exc)) from exc
    gitmod.git(["update-ref", _local_ref(branch), commit], repo)
    gitmod.git(["update-ref", _tracking_ref(remote, branch), commit], repo, check=False)
    set_marker(root, workflow, task_id, on=True, remote=remote, branch=branch, state="pushed", seq=seq,
               commit=commit, lease=dict(lease) if lease else None, error=None, takeover=False)
    return Pushed(branch=branch, remote=remote, commit=commit, seq=seq, lease=dict(lease) if lease else None)


def drop(root: Path, repo: Path, workflow: str, task_id: str, *, remote: str | None = None) -> dict[str, Any]:
    """Delete the state branch locally and on the remote (CAR-B8, CAR-B3)."""
    remote = remote_of(repo, remote or marker(root, workflow, task_id).get("remote"))
    branch = branch_name(workflow, task_id)
    try:
        on_remote = bool(gitmod.git(["ls-remote", "--heads", remote, _local_ref(branch)], repo).strip())
        if on_remote:
            gitmod.git(["push", remote, "--delete", _local_ref(branch)], repo)
    except gitmod.GitError as exc:
        if is_on(root, workflow, task_id) or marker(root, workflow, task_id):
            set_marker(root, workflow, task_id, state="delete_failed", error=str(exc)[:200])
        raise CarryFailed(str(exc)) from exc
    for ref in (_local_ref(branch), _tracking_ref(remote, branch)):
        gitmod.git(["update-ref", "-d", ref], repo, check=False)
    if marker_path(root, workflow, task_id).parent.is_dir():
        set_marker(root, workflow, task_id, on=False, state="dropped", lease=None, error=None)
    return {"branch": branch, "remote": remote, "deleted": True, "was_on_remote": on_remote}


# -- pull (CAR-B8, CAR-B3, CAR-B10) ----------------------------------------------------------------------------------------


def _read_tree(repo: Path, commit: str, into: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for rel in gitmod.git(["ls-tree", "-r", "--name-only", commit], repo).splitlines():
        if not rel.startswith(PREFIX + "/"):
            raise CarryRefused("carry_path", f"the state branch holds {rel!r}, outside {PREFIX}/")
        inner = rel[len(PREFIX) + 1:]
        dest = into / inner
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = gitmod.git_bytes(["cat-file", "blob", f"{commit}:{rel}"], repo)
        except gitmod.GitError as exc:
            raise CarryRefused("carry_manifest", f"{rel} cannot be read from the state branch") from exc
        dest.write_bytes(data)
        out[inner] = dest
    return out


def checks(repo: Path, remote: str, manifest: Mapping[str, Any], files: Mapping[str, Path], *,
           current_version: str | None, force: bool = False) -> None:
    """CAR-B10: each row refuses before anything is imported."""
    from tempergraph.release import release

    listed = dict(manifest.get("files") or {})
    have = {rel: hashlib.sha256(p.read_bytes()).hexdigest() for rel, p in files.items() if rel != "carry.json"}
    if have != listed:
        bad = sorted(set(have) ^ set(listed)) or sorted(k for k in have if have[k] != listed.get(k))
        raise CarryRefused("carry_digest", f"carried files do not match carry.json: {', '.join(bad[:5])}")
    rel_doc = release()
    if int(manifest.get("store_layout") or 0) > STORE_LAYOUT or \
            int(manifest.get("checkpoint_format") or 0) > int(rel_doc.get("checkpoint_format") or 0):
        raise CarryRefused("carry_newer", "the carried state was written by a newer engine: it needs engine "
                                          f"{manifest.get('engine_version')} or later")
    if current_version is None:
        raise CarryRefused("carry_workflow", f"workflow {manifest.get('workflow')!r} is not registered here")
    carried = manifest.get("workflow_version")
    if carried and carried != current_version and not force:
        raise CarryRefused("carry_workflow", f"the thread ran workflow version {carried}; this machine has "
                                             f"{current_version}. Install that version, or pass --force")
    try:
        ws = json.loads(files["workspace.json"].read_text(encoding="utf-8"))
    except (KeyError, OSError, ValueError) as exc:
        raise CarryRefused("carry_manifest", "the carried workspace.json does not parse") from exc
    br = str(ws.get("branch") or "")
    if not br or not gitmod.is_safe_ref(br) or \
            not gitmod.git(["ls-remote", "--heads", remote, f"refs/heads/{br}"], repo, check=False).strip():
        raise CarryRefused("carry_no_work_branch", f"the work branch {br or '?'} is not on {remote}: there is "
                                                   "nothing to resume on")


def _import_checkpoint(src: Path, dest: Path, tid: str) -> None:
    """Replace this thread's rows in `dest` by the carried ones, a sub-workflow child's namespaces included."""
    from tempergraph.durability.checkpoint import open_saver

    saver = open_saver(dest)
    try:
        conn = saver.conn
        conn.execute("ATTACH DATABASE ? AS carried", (str(src),))
        for table in CHECKPOINT_TABLES:
            conn.execute(f"DELETE FROM main.{table} WHERE thread_id = ?", (tid,))  # noqa: S608
            conn.execute(f"INSERT INTO main.{table} SELECT * FROM carried.{table} WHERE thread_id = ?", (tid,))  # noqa: S608
        conn.commit()
        conn.execute("DETACH DATABASE carried")
    finally:
        saver.conn.close()


def _backup(root: Path, workflow: str, task_id: str) -> str | None:
    base = run_dir(root, workflow, task_id)
    if not base.is_dir():
        return None
    from tempergraph.workspace import flat_name

    dest = root / "backups" / f"carry-{flat_name(workflow, task_id)}-{now_iso().replace(':', '')}"
    dest.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copytree(base, dest / "run")
    cp = dest / "checkpoint.sqlite"
    _thread_checkpoint(engine_file.checkpoint_of(root, workflow, task_id), f"{workflow}/{task_id}", cp)
    (dest / "ledger.jsonl").write_text("".join(ln + "\n" for ln in _ledger_rows(root, f"{workflow}/{task_id}")),
                                       encoding="utf-8")
    return str(dest)


def pull(root: Path, repo: Path, workflow: str, task_id: str, *, remote: str | None = None,
         current_version: str | None, machine: str | None = None, force: bool = False,
         caller: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Fetch the state branch, check it and import the thread; a held lease of another machine refuses
    unless forced, and a forced pull is recorded as a `steer` touch (CAR-B9, CAR-B4)."""
    from tempergraph.run.log import Ledger, last_seq
    from tempergraph.store.layout import ensure_state_root

    remote = remote_of(repo, remote or marker(root, workflow, task_id).get("remote"))
    branch = branch_name(workflow, task_id)
    tid = f"{workflow}/{task_id}"
    tip = fetch(repo, remote, branch)
    if not tip:
        raise CarryRefused("carry_none", f"{remote} has no state branch {branch}")
    manifest = manifest_at(repo, tip)
    base = run_dir(root, workflow, task_id)
    had = (base / "run.jsonl").exists()
    local_seq = last_seq(base / "run.jsonl") if had else 0
    if had and int(manifest.get("seq") or 0) <= local_seq:
        raise CarryRefused("carry_not_newer", f"this machine already has {tid} at seq {local_seq}; the state "
                                              f"branch holds seq {manifest.get('seq')}")
    lease = manifest.get("lease")
    takeover = _held_by_other(lease, machine)
    if takeover and not force:
        raise CarryRefused("carry_leased", _lease_text(lease or {}) + "; pass --force to take it")
    with tempfile.TemporaryDirectory(prefix="tg-carry-") as tmp:
        files = _read_tree(repo, tip, Path(tmp))
        checks(repo, remote, manifest, files, current_version=current_version, force=force)
        ensure_state_root(root)
        backup = _backup(root, workflow, task_id) if had else None
        keep = marker(root, workflow, task_id)
        if base.is_dir():
            shutil.rmtree(base)
        for rel, src in files.items():
            if rel.startswith("run/"):
                dest = base / rel[4:]
                dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copyfile(src, dest)
                os.chmod(dest, 0o600)
        _import_checkpoint(files["checkpoint.sqlite"], engine_file.checkpoint_of(root, workflow, task_id), tid)
        carried_rows = files["ledger.jsonl"].read_text(encoding="utf-8").splitlines()
        ledger = root / "ledger.jsonl"
        kept = [ln for ln in (ledger.read_text(encoding="utf-8").splitlines() if ledger.exists() else [])
                if ln not in set(_ledger_rows(root, tid))]
        ledger.write_text("".join(ln + "\n" for ln in [*kept, *carried_rows]), encoding="utf-8")
        ws = json.loads(files["workspace.json"].read_text(encoding="utf-8"))
    br = str(ws["branch"])
    if not _rev(repo, f"refs/heads/{br}"):  # the work branch, for the worktree a resume re-attaches
        gitmod.git(["fetch", "--no-tags", remote, f"refs/heads/{br}:refs/heads/{br}"], repo, check=False)
    gitmod.git(["update-ref", _local_ref(branch), tip], repo, check=False)
    set_marker(root, workflow, task_id, **{**keep, "on": True, "remote": remote, "branch": branch,
                                           "state": "pulled", "seq": manifest.get("seq"), "commit": tip,
                                           "relocate": True, "takeover": bool(takeover), "lease": lease,
                                           "error": None, "work_branch": br})
    if takeover:
        Ledger(path=root / "ledger.jsonl").append({
            "kind": "intervention", "thread_id": tid, "workflow": workflow, "unit": None,
            "caller": dict(caller or {}), "touches": [{"class": "steer", "action": "carry_takeover"}],
            "pause_kind": "carry", "decision": "carry_pull:force", "cause": "carry_takeover",
            "taken_from": {"machine": (lease or {}).get("machine"), "since": (lease or {}).get("since")}})
    return {"branch": branch, "remote": remote, "seq": manifest.get("seq"), "imported": len(files),
            "takeover": bool(takeover), "backup": backup, "work_branch": br, "workspace": ws.get("mode"),
            **({"note": f"check out {br} before resuming: the run works in your checkout"}
               if ws.get("mode") == "in_place" else {})}


# -- the run's hooks (CAR-B8, CAR-B3, CAR-B9, CAR-B4) -----------------------------------------------------------------------------


def lease_of(machine: str | None) -> dict[str, Any]:
    return {"machine": machine or "unknown", "process": os.getpid(), "since": now_iso()}


def before_resume(root: Path, repo: Path, workflow: str, task_id: str, *, workflow_version: str | None,
                  machine: str | None) -> list[str]:
    """Take the lease on the state branch before the first attempt. Refuses behind a newer remote state or
    another machine's lease; an unreachable remote is a warning, and the push is left for later."""
    m = marker(root, workflow, task_id)
    try:
        push(root, repo, workflow, task_id, workflow_version=workflow_version, lease=lease_of(machine),
             machine=machine, force=bool(m.get("takeover")))
    except CarryFailed as exc:
        set_marker(root, workflow, task_id, state="unpushed", error=str(exc)[:200])
        return ["carry: unpushed (the lease could not be written)"]
    return []


def relocate(root: Path, repo: Path, workflow: str, task_id: str, ws: Mapping[str, Any]) -> dict[str, Any]:
    """After a pull, the workspace record's path under this machine's root rule (WTR-B18)."""
    if not marker(root, workflow, task_id).get("relocate"):
        return dict(ws)
    from tempergraph.workspace import flat_name, sibling_root

    main = gitmod.main_checkout(repo) or repo
    path = main if ws.get("mode") == "in_place" else sibling_root(main) / flat_name(workflow, task_id)
    set_marker(root, workflow, task_id, relocate=False)
    return {**ws, "path": str(path), "last_head": ""}


def after_exit(root: Path, repo: Path, workflow: str, task_id: str, *, exit_code: int,
               workflow_version: str | None, machine: str | None) -> str | None:
    """A finished thread deletes its state branch; any other exit pushes the new state and clears the lease.
    Returns a warning when the remote could not be reached or refused; never raises (OVR-B4)."""
    if not is_on(root, workflow, task_id):
        return None
    try:
        if exit_code == 0:
            drop(root, repo, workflow, task_id)
            set_marker(root, workflow, task_id, on=False, state="finished")
            return None
        push(root, repo, workflow, task_id, workflow_version=workflow_version, lease=None, machine=machine)
        return None
    except CarryRefused as exc:
        set_marker(root, workflow, task_id, state="unpushed", error=f"{exc.code}: {exc}"[:200])
        return f"carry: unpushed ({exc.code})"
    except (CarryFailed, gitmod.GitError, OSError, sqlite3.Error) as exc:
        state = "delete_failed" if exit_code == 0 else "unpushed"
        set_marker(root, workflow, task_id, state=state, error=str(exc)[:200])
        return f"carry: {state}"


def status(root: Path, repo: Path, workflow: str, task_id: str, *, remote: str | None = None,
           online: bool = True) -> dict[str, Any]:
    from tempergraph.run.log import last_seq

    m = marker(root, workflow, task_id)
    out: dict[str, Any] = {"thread_id": f"{workflow}/{task_id}", "on": bool(m.get("on")),
                           "state": m.get("state"), "branch": branch_name(workflow, task_id),
                           "local_seq": last_seq(run_dir(root, workflow, task_id) / "run.jsonl"),
                           "error": m.get("error")}
    if not online:
        return out
    try:
        out["remote"] = remote_of(repo, remote or m.get("remote"))
        tip = fetch(repo, out["remote"], out["branch"])
    except (CarryRefused, CarryFailed) as exc:
        return {**out, "remote_error": str(exc)[:200]}
    if tip:
        man = manifest_at(repo, tip)
        out.update(remote_seq=man.get("seq"), lease=man.get("lease"), pushed_at=man.get("pushed_at"))
    else:
        out["remote_seq"] = None
    return out
