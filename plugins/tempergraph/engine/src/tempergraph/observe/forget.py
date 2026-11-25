"""`stats forget`: state roots whose folder is gone leave the machine index and this month's stats rows
(CST-B17 to CST-B24).

The index is read and written only through :mod:`tempergraph.observe.rows` (its lock, `read_index`,
`index_roots`, `stats_path`); this module decides what goes and rewrites the month's two stats files. The stats
are rewritten before the index (CST-B22), and each file is replaced while the verb holds the lock that the
engine's stats writers take (CST-B23).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from tempergraph.docs import write_json
from tempergraph.observe import rows


class IndexInUse(Exception):
    """The index lock was not had in :data:`rows.INDEX_LOCK_S` (CST-B21)."""


def _month_files(home: Path, month: str) -> list[Path]:
    return [rows.stats_path(home, month), home / "stats" / "sessions" / f"{month}.jsonl"]


def _outbox_ids(home: Path) -> set[str]:
    """The `row_id`s that an outbox still lists (CST-B12): their rows stay until a flush has delivered them."""
    ids: set[str] = set()
    for box in sorted((home / "outbox").glob("*.jsonl")) if (home / "outbox").is_dir() else []:
        try:
            lines = box.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for ln in lines:
            try:
                ref = json.loads(ln)
            except ValueError:
                continue
            if isinstance(ref, dict) and ref.get("row_id"):
                ids.add(str(ref["row_id"]))
    return ids


def _split(data: bytes, gone: set[str], keep: set[str]) -> tuple[bytes, dict[str, int]]:
    """`data` without the rows of a gone root that no outbox lists, and the count removed for each root. Every
    other line, one that is not JSON included, stays byte for byte."""
    kept: list[bytes] = []
    removed: dict[str, int] = {}
    for line in data.splitlines(keepends=True):
        try:
            row = json.loads(line)
        except ValueError:
            row = None
        root = row.get("state_root") if isinstance(row, dict) else None
        if isinstance(root, str) and root in gone and str(row.get("row_id")) not in keep:
            removed[root] = removed.get(root, 0) + 1
            continue
        kept.append(line)
    return b"".join(kept), removed


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _counts(home: Path, month: str, gone: list[str]) -> dict[str, int]:
    keep = _outbox_ids(home)
    total = dict.fromkeys(gone, 0)
    for path in _month_files(home, month):
        data = _read(path)
        if data is None:
            continue
        for root, n in _split(data, set(gone), keep)[1].items():
            total[root] += n
    return total


def _rewrite(path: Path, gone: set[str], keep: set[str]) -> None:
    """Replace `path` by its kept lines through a temporary file, holding the lock that the stats writers take
    (:func:`rows.append_stats_row`) from the read to the replace, so a row a writer appends meanwhile waits and is
    kept (CST-B23). Raises :class:`OSError` when the lock is not had or the replace fails. A writer that did not
    get the lock is not protected."""
    with rows._locked(path) as got:
        if not got:
            raise OSError(f"{path} is in use; try again")
        data = _read(path)
        if data is None:
            return
        out, removed = _split(data, gone, keep)
        if not removed:
            return
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(out)
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        finally:
            Path(tmp).unlink(missing_ok=True)


def _result(check: bool, month: str, counts: dict[str, int]) -> dict[str, Any]:
    return {"schema_version": 1, "check": check, "month": month,
            "roots": [{"state_root": root, "rows": n} for root, n in counts.items()]}


def forget(home: Path, check: bool) -> dict[str, Any]:
    """Remove the gone entries of the machine index and their rows from this month's stats (UTC), or with `check`
    only count them. Raises :class:`IndexInUse` when the index lock is not had (never with `check`)."""
    month = rows.month_now()
    gone = [str(r["path"]) for r in rows.index_roots(home) if r["missing"]]
    if check:
        return _result(True, month, _counts(home, month, gone))
    if not gone:
        return _result(False, month, {})
    with rows._locked(home / "index.json") as got:
        if not got:
            raise IndexInUse("the machine index is in use")
        gone = [str(r["path"]) for r in rows.index_roots(home) if r["missing"]]  # again, under the lock
        counts = _counts(home, month, gone)
        if gone:
            drop = set(gone)
            keep = _outbox_ids(home)
            for path in _month_files(home, month):  # the stats first: a failure leaves every entry in the index
                _rewrite(path, drop, keep)
            write_json(home / "index.json",
                       {"schema_version": 1, "roots": [r for r in rows.read_index(home) if str(r["path"]) not in drop]})
    return _result(False, month, counts)
