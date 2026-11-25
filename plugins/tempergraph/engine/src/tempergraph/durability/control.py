"""Run control: the stop request file (RCT-B6, RCT-B7, RCT-B3, RCT-B8, RCT-B9, RCT-B10).

The `stop` verb writes `runs/<workflow>/<task_id>/control/stop.json`; the engine holding the thread's
lock picks it up between records and at least once a second while a session runs, removes it and acts.
A file, not a signal: it carries a mode and is safe after process-id reuse (ADR `stop-verb-as-the-only-observer-control`).
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from tempergraph.docs import write_json
from tempergraph.durability.lock import is_held
from tempergraph.executors.launcher import StopRequest
from tempergraph.store.layout import lock_path, now_iso, run_dir

StopMode = Literal["drain", "now"]
POLL_S = 1.0


class NotLive(Exception):
    """RCT-B3: the thread's lock is not held; nothing was written."""


def stop_file(state_root: Path, workflow: str, task_id: str) -> Path:
    return run_dir(state_root, workflow, task_id) / "control" / "stop.json"


def request_stop(state_root: Path, workflow: str, task_id: str, mode: StopMode = "drain",
                 caller: dict[str, Any] | None = None) -> StopMode:
    """Write (or strengthen) a stop request for a live thread; returns the mode now on file."""
    if not is_held(lock_path(state_root, workflow, task_id)):
        raise NotLive(f"{workflow}/{task_id} is not running")
    path = stop_file(state_root, workflow, task_id)
    current = _read(path)
    if current is not None and current[0] == "now":
        return "now"  # the stronger mode wins (RCT-B8, RCT-B9, RCT-B10)
    write_json(path, {"schema_version": 1, "mode": mode, "requested_at": now_iso(), "caller": caller or {}})
    return mode


def _read(path: Path) -> tuple[StopMode, dict[str, Any]] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        mode = data.get("mode")
        return ("now" if mode == "now" else "drain"), data
    except (OSError, ValueError, AttributeError):
        return "drain", {"unparsable": True}  # a request that does not parse is a drain, recorded


@dataclass(frozen=True, kw_only=True)
class TakenStop:
    mode: StopMode
    caller: dict[str, Any]
    unparsable: bool = False
    stale: bool = False


def take_stop(state_root: Path, workflow: str, task_id: str, *, stale: bool = False) -> TakenStop | None:
    """Read and remove a pending request. ``stale``: called by a resume for a request nobody acted on."""
    path = stop_file(state_root, workflow, task_id)
    got = _read(path)
    if got is None:
        return None
    path.unlink(missing_ok=True)
    mode, data = got
    return TakenStop(mode=mode, caller=dict(data.get("caller") or {}), unparsable=bool(data.get("unparsable")),
                     stale=stale)


class StopWatcher:
    """Polls the request file while a run holds its lock; ``now`` fires the launcher's stop contract.

    ``drain`` is only remembered: the run stops at its next boundary (RCT-B1)."""

    def __init__(self, state_root: Path, workflow: str, task_id: str, session_stop: StopRequest,
                 poll_s: float = POLL_S) -> None:
        self.args = (state_root, workflow, task_id)
        self.session_stop = session_stop
        self.poll_s = poll_s
        self.taken: TakenStop | None = None
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="stop-watcher", daemon=True)

    def check(self) -> TakenStop | None:
        got = take_stop(*self.args)
        if got is not None and (self.taken is None or got.mode == "now"):
            self.taken = got
        if self.taken is not None and self.taken.mode == "now":
            self.session_stop.request("stop")
        return self.taken

    def _loop(self) -> None:
        while not self._done.wait(self.poll_s):
            self.check()

    def __enter__(self) -> StopWatcher:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._done.set()
        self._thread.join(timeout=self.poll_s * 2)
