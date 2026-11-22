"""Store layout migration (MIG-B9, MIG-B10, MIG-B5): one step per layout number, run under a lock, with a backup before a
breaking step and the backup restored when a step raises. Standard library only, so `update` can run it.

This release writes layout 1 and ships no step; the machinery is here for the first release that does.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tempergraph.docs import write_json
from tempergraph.store.layout import now_iso

LOCK_WAIT_S = 60.0


class MigrationRefused(RuntimeError):
    """Exit 2: a lock held too long, or a breaking step while an older engine runs in the root."""


class MigrationFailed(RuntimeError):
    """Exit 1: a step raised; its backup was restored and the manifest is unchanged."""


@dataclass(frozen=True, kw_only=True)
class Step:
    """`from_layout` → `from_layout + 1`. `touches` lists the files (relative) a breaking step moves or
    rewrites, so they are backed up first; append-only logs are never rewritten."""

    from_layout: int
    kind: str  # `additive` or `breaking`
    apply: Callable[[Path], None]
    touches: Callable[[Path], Sequence[str]] = lambda root: ()


STEPS: dict[int, Step] = {}


def _manifest(root: Path) -> dict[str, Any]:
    try:
        doc = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def layout_of(root: Path) -> int | None:
    v = _manifest(root).get("layout")
    return v if isinstance(v, int) else None


def _lock(root: Path, wait_s: float) -> Path:
    path = root / "locks" / ".migrate"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    deadline = time.monotonic() + wait_s
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return path
        except FileExistsError:
            if time.monotonic() >= deadline:
                try:
                    holder = path.read_text(encoding="utf-8").strip()
                except OSError:
                    holder = "?"
                raise MigrationRefused(f"the store at {root} is being migrated by pid {holder}") from None
            time.sleep(0.1)


def _backup(root: Path, step: Step) -> Path:
    dest = root / "backups" / f"layout-{step.from_layout}-{now_iso().replace(':', '').replace('-', '')}"
    dest.mkdir(parents=True, exist_ok=False, mode=0o700)
    for rel in ("manifest.json", *step.touches(root)):
        src = root / rel
        if src.is_file():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / rel)
    write_json(dest / "backup.json", {"schema_version": 1, "from_layout": step.from_layout,
                                      "files": [r for r in ("manifest.json", *step.touches(root))
                                                if (root / r).is_file()], "taken_at": now_iso()})
    return dest


def _restore_from(root: Path, backup: Path) -> None:
    try:
        files = json.loads((backup / "backup.json").read_text(encoding="utf-8")).get("files") or []
    except (OSError, ValueError):
        files = []
    for rel in files:
        if (backup / rel).is_file():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup / rel, root / rel)


def migrate(root: Path, *, target: int, engine: str, steps: Mapping[int, Step] | None = None,
            older_live: Callable[[Path], Sequence[str]] | None = None, wait_s: float = LOCK_WAIT_S) -> list[int]:
    """Move the store at `root` forward to layout `target`. Returns the layouts stepped from; a store already
    there, or one with no manifest yet, is left alone. Idempotent."""
    steps = STEPS if steps is None else steps
    cur = layout_of(root)
    if cur is None or cur >= target:
        return []
    lock = _lock(root, wait_s)
    done: list[int] = []
    try:
        got = layout_of(root)  # another process may have moved it while this one waited
        cur = target if got is None else got
        while cur < target:
            step = steps.get(cur)
            if step is None:
                raise MigrationFailed(f"no migration step from layout {cur}")
            backup: Path | None = None
            if step.kind == "breaking":
                live = list(older_live(root)) if older_live else []
                if live:
                    raise MigrationRefused(f"{', '.join(live)} is running on an older engine in {root}: wait "
                                           "for it or run `tempergraph stop --drain`")
                backup = _backup(root, step)
            before = _manifest(root)
            try:
                step.apply(root)
            except Exception as exc:  # noqa: BLE001
                if backup is not None:
                    _restore_from(root, backup)
                write_json(root / "manifest.json", before, mode=0o644)
                raise MigrationFailed(f"layout step {cur} failed ({type(exc).__name__}); the store is unchanged") \
                    from exc
            cur += 1
            write_json(root / "manifest.json", {**before, "layout": cur, "moved_by": engine, "moved_at": now_iso(),
                                                "backup": str(backup) if backup else before.get("backup")},
                       mode=0o644)
            done.append(cur - 1)
    finally:
        lock.unlink(missing_ok=True)
    return done


def older_live(root: Path, engine: str | None = None) -> list[str]:
    """The threads whose run lock is held by a live process of another engine version (MIG-B9, MIG-B10, MIG-B5)."""
    if engine is None:
        from tempergraph.constants import ENGINE_VERSION as engine  # noqa: N811
    out = []
    for holder in sorted((root / "locks").glob("*/*.holder.json")) if (root / "locks").is_dir() else []:
        try:
            doc = json.loads(holder.read_text(encoding="utf-8"))
            pid = int(doc.get("pid"))
            os.kill(pid, 0)
        except (OSError, ValueError, TypeError):
            continue
        if doc.get("engine_version") and doc.get("engine_version") != engine and pid != os.getpid():
            out.append(f"{holder.parent.name}/{holder.name[:-len('.holder.json')]}")
    return out


def _written_since(root: Path, moved_at: str) -> bool:
    """Whether a run has written to the root since the migration (its run logs are newer)."""
    from datetime import datetime

    try:
        t = datetime.fromisoformat(moved_at.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return True
    return any(p.stat().st_mtime > t + 1 for p in (root / "runs").glob("*/*/run.jsonl")) if (root / "runs").is_dir() \
        else False


def restorable(root: Path) -> bool:
    """MIG-B9, MIG-B10, MIG-B5 rollback: a backup restores only while no run has written to the root since the step."""
    man = _manifest(root)
    backup = Path(str(man.get("backup") or ""))
    return bool(man.get("backup")) and (backup / "backup.json").is_file() \
        and not _written_since(root, str(man.get("moved_at") or ""))


def restore(root: Path) -> bool:
    if not restorable(root):
        return False
    _restore_from(root, Path(str(_manifest(root)["backup"])))
    return True
