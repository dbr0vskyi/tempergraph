"""The per-thread run lock (WSP-B8, WSP-B9, WSP-B11, DUR-B9 `running`, DUR-B4).

An OS file lock held for the life of the run process. Observers probe it without creating the file and
for an instant only: a shared, non-blocking lock on an existing file that is released at once.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path
from typing import IO, Any

from tempergraph.constants import ENGINE_VERSION
from tempergraph.docs import write_json

if sys.platform != "win32":
    import fcntl

    def _try(fh: IO[Any], exclusive: bool) -> bool:
        try:
            fcntl.flock(fh.fileno(), (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _release(fh: IO[Any]) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
else:  # pragma: no cover - Windows
    import msvcrt

    def _try(fh: IO[Any], exclusive: bool) -> bool:
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _release(fh: IO[Any]) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


class LockHeld(Exception):
    def __init__(self, path: Path, holder: dict[str, Any]) -> None:
        super().__init__(f"run lock held: {path}")
        self.path, self.holder = path, holder


def holder() -> dict[str, Any]:
    """MIG-B8: the process and the engine it runs on, read by `update` and `--prune-engines`."""
    env = Path(sys.prefix)
    managed = env.parent.name == "engines"
    return {"pid": os.getpid(), "engine_version": ENGINE_VERSION, "engine": env.name if managed else None,
            "engine_digest": env.name.rsplit("-", 1)[-1] if managed else None}


class RunLock:
    """Exclusive lock for one thread; use as a context manager."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh: IO[Any] | None = None

    def acquire(self) -> RunLock:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fh = open(self.path, "a+")  # noqa: SIM115 - held for the run's life
        os.chmod(self.path, 0o600)
        if not _try(fh, exclusive=True):
            fh.close()
            raise LockHeld(self.path, read_holder(self.path))
        self._fh = fh
        write_json(self.path.with_suffix(".holder.json"), holder())
        return self

    def release(self) -> None:
        if self._fh is not None:
            with contextlib.suppress(OSError):
                self.path.with_suffix(".holder.json").unlink()
            _release(self._fh)
            self._fh.close()
            self._fh = None

    def __enter__(self) -> RunLock:
        return self.acquire()

    def __exit__(self, *exc: object) -> None:
        self.release()


def read_holder(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.with_suffix(".holder.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def is_held(path: Path) -> bool:
    """Probe the lock without creating it (DUR-B4)."""
    if not path.exists():
        return False
    try:
        fh = open(path)  # noqa: SIM115
    except OSError:
        return False
    try:
        if _try(fh, exclusive=False):
            _release(fh)
            return False
        return True
    finally:
        fh.close()
