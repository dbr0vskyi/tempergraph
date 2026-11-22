"""The per-thread result cache of model-free scripts (SCR-B9, SCR-B3, ADR-0067).

A script with `cache: thread` is keyed by a digest of what decides its result; a hit restores the recorded
`produces` files and result from `<thread folder>/cache/` and runs nothing. Only a run that finished and
succeeded is recorded. A folder or an entry that cannot be read raises :class:`CacheError`, which the caller
logs and treats as a miss.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from tempergraph import git as gitmod
from tempergraph.store import manifest

SCHEMA = 1
ABSENT = "absent"
REFUSED = "refused"
WORKSPACE = "workspace"


class CacheError(Exception):
    """The cache folder or an entry in it cannot be read or written: a logged miss (SCR-B9)."""


@dataclass(frozen=True, kw_only=True)
class Result:
    """What a succeeded script left: its exit code, its artifacts and the kind of each artifact's key."""

    exit_code: int | None = None
    artifacts: Mapping[str, str] = field(default_factory=dict)
    kinds: Mapping[str, str] = field(default_factory=dict)


def key(*, argv: tuple[str, ...], reference: str | None, workflow: str, arguments: tuple[str, ...],
        inputs: Mapping[str, str]) -> str:
    """The digest of the resolved argv or callable reference, the workflow's content digest, the rendered
    arguments and the content digest of each declared input."""
    doc = {"argv": list(argv), "reference": reference, "workflow": workflow, "arguments": list(arguments),
           "inputs": {k: inputs[k] for k in sorted(inputs)}}
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    return manifest.file_hash(path) or ABSENT


def _under(path: Path, root: Path) -> bool:
    with contextlib.suppress(OSError, ValueError):
        path.resolve().relative_to(root.resolve())
        return True
    return False


def tree_hash(workdir: Path, state_root: Path, exclude: Collection[str] = ()) -> str:
    """The hash of the tracked and untracked files of the workspace outside the state root (and outside
    `exclude`, workspace-relative paths such as the script's own earlier outputs)."""
    if gitmod.toplevel(workdir) is None:
        return "manifest:" + manifest.status(workdir)
    try:
        listed = gitmod.git_bytes(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], workdir)
    except gitmod.GitError:
        return "manifest:" + manifest.status(workdir)
    skip = set(exclude)
    h = hashlib.sha256()
    for rel in sorted(p for p in listed.decode("utf-8", "replace").split("\0") if p):
        path = workdir / rel
        if rel in skip or ".tempergraph/" in rel or _under(path, state_root):
            continue
        h.update(f"{rel}\0{_file_digest(path)}\n".encode())
    return h.hexdigest()


def _dir_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(f"{p.relative_to(root).as_posix()}\0{_file_digest(p)}\n".encode())
    return h.hexdigest()


def safe_relative(value: str) -> Path | None:
    """A workspace-relative path with no `..` and no root, or nothing."""
    p = Path(value)
    return None if not value or p.is_absolute() or ".." in p.parts else p


def input_digest(name: str, workdir: Path, state_root: Path, artifacts: Mapping[str, str],
                 exclude: Collection[str] = ()) -> str:
    """The content digest of one declared input: `workspace` is the tree hash; an artifact or value key is the
    content of the file it names (else the text); anything else is a path of the workspace."""
    if name == WORKSPACE:
        return "tree:" + tree_hash(workdir, state_root, exclude)
    if name in artifacts:
        value = str(artifacts[name])
        rel = safe_relative(value)
        if rel is not None and (workdir / rel).is_file():
            return "file:" + _file_digest(workdir / rel)
        return "value:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
    rel = safe_relative(name)
    if rel is None:
        return REFUSED
    path = workdir / rel
    if path.is_dir():
        return "dir:" + _dir_hash(path)
    return "file:" + _file_digest(path)


def _entry(folder: Path, key_: str) -> Path:
    return folder / f"{key_}.json"


def _blobs(folder: Path, key_: str) -> Path:
    return folder / f"{key_}.files"


def store(folder: Path, key_: str, result: Result, workdir: Path) -> None:
    """Record a succeeded run: its result and a copy of each `file` artifact it left in the workspace."""
    files: dict[str, dict[str, str]] = {}
    try:
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        for name, value in result.artifacts.items():
            rel = safe_relative(str(value))
            if result.kinds.get(name) != "file" or rel is None or not (workdir / rel).is_file():
                continue
            blob = hashlib.sha256(rel.as_posix().encode("utf-8")).hexdigest()[:24]
            dest = _blobs(folder, key_) / blob
            dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(workdir / rel, dest)
            files[name] = {"path": rel.as_posix(), "blob": blob}
        doc = {"schema": SCHEMA, "exit_code": result.exit_code, "artifacts": dict(result.artifacts),
               "kinds": dict(result.kinds), "files": files}
        tmp = folder / f"{key_}.tmp"
        tmp.write_text(json.dumps(doc, sort_keys=True), encoding="utf-8")
        os.replace(tmp, _entry(folder, key_))
    except OSError as exc:
        raise CacheError(type(exc).__name__) from None


def lookup(folder: Path, key_: str, workdir: Path) -> Result | None:
    """The recorded result of a hit, with its files put back in the workspace; nothing on a miss; a
    :class:`CacheError` when the folder or the entry cannot be read."""
    if folder.exists() and not folder.is_dir():
        raise CacheError("NotADirectoryError")
    try:
        raw = _entry(folder, key_).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise CacheError(type(exc).__name__) from None
    try:
        doc = json.loads(raw)
        if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
            raise ValueError("schema")
        files = {str(k): dict(v) for k, v in dict(doc.get("files") or {}).items()}
        arts = {str(k): str(v) for k, v in dict(doc.get("artifacts") or {}).items()}
        kinds = {str(k): str(v) for k, v in dict(doc.get("kinds") or {}).items()}
        code = doc.get("exit_code")
        restores: list[tuple[Path, Path]] = []
        for info in files.values():
            rel = safe_relative(str(info["path"]))
            blob = _blobs(folder, key_) / str(info["blob"])
            if rel is None or not blob.is_file():
                raise ValueError("entry")
            restores.append((blob, workdir / rel))
        for blob, dest in restores:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(blob, dest)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise CacheError(type(exc).__name__) from None
    return Result(exit_code=code if isinstance(code, int) else None, artifacts=arts, kinds=kinds)
