"""The workspace manifest of a folder outside git (WSP-B15 to WSP-B18, ADR-0127).

Where git cannot say what changed, the engine lists every file under the workspace but the state root, with
its size and modification time. Two manifests that differ mean something wrote the workspace, which is what the
independence guard asks (GRD). A file whose size or time changed is hashed, so a report can say whether its
content changed too. The manifest stops at `MAX_FILES`; a start with a read-only session to guard is refused
above it.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path

from tempergraph.store.layout import ROOT_VAR, STATE_DIR

MAX_FILES = 20_000
Entry = tuple[int, int]  # size, mtime_ns


class TooManyFiles(Exception):
    """The workspace holds more files than a manifest takes."""


def scan(workdir: Path, limit: int | None = None) -> dict[str, Entry]:
    """`{relative path: (size, mtime_ns)}` of every file under `workdir`, the state root left out."""
    limit = MAX_FILES if limit is None else limit
    out: dict[str, Entry] = {}
    declared = os.environ.get(ROOT_VAR)  # a declared state root inside the workspace is left out too
    skip = Path(declared).resolve() if declared else None
    stack = [workdir]
    while stack:
        folder = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    if e.name != STATE_DIR and (skip is None or Path(e.path).resolve() != skip):
                        stack.append(Path(e.path))
                    continue
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            out[Path(e.path).relative_to(workdir).as_posix()] = (st.st_size, st.st_mtime_ns)
            if len(out) > limit:
                raise TooManyFiles(f"{workdir} holds more than {limit} files")
    return out


def count_over(workdir: Path, limit: int | None = None) -> bool:
    try:
        scan(workdir, limit)
    except TooManyFiles:
        return True
    return False


def digest(entries: Mapping[str, Entry]) -> str:
    """One line for a manifest: the count and a hash over its sorted entries; equal manifests, equal lines."""
    h = hashlib.sha256()
    for path in sorted(entries):
        size, mtime = entries[path]
        h.update(f"{path}\0{size}\0{mtime}\n".encode("utf-8", "surrogateescape"))
    return f"manifest:{len(entries)}:{h.hexdigest()}"


def status(workdir: Path) -> str:
    """The fingerprint's status outside git; `manifest:over` when the folder is past the limit (no guard)."""
    try:
        return digest(scan(workdir))
    except TooManyFiles:
        return "manifest:over"


def file_hash(path: Path) -> str | None:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
    except OSError:
        return None
    return h.hexdigest()


def changed(workdir: Path, base: Mapping[str, object], limit: int = 500) -> list[str]:
    """Paths added, removed or with another size or time than in `base` (a stored scan), sorted."""
    try:
        now = scan(workdir)
    except TooManyFiles:
        return []
    old = {k: tuple(v) for k, v in base.items() if isinstance(v, list | tuple)}
    paths = [p for p in now if old.get(p) != now[p]] + [p for p in old if p not in now]
    return sorted(paths)[:limit]
