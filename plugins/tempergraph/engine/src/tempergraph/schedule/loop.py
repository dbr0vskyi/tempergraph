"""The portable loop: the default trigger (TCK-B1, TCK-B3, TCK-B8, TCK-B14).

One engine process per user, under `schedules/loop.lock`, that runs the tick, sleeps until the earlier of the next slot of
any schedule and 60 s, and runs the tick again. It holds nothing in memory between ticks: each tick and each sleep read the
store afresh. A wall-clock jump (a machine that slept through a slot) ends the sleep, found by comparing the wall clock
with the monotonic one, so the missed slot is ticked at once. When an `update` switches engines it finishes its tick,
lets go of the lock and starts itself again through the shim. `schedule loop --stop` writes a marker the loop sees within
one slice of its sleep; no signal is needed, so it is the same on every OS.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tempergraph.constants import ENGINE_VERSION
from tempergraph.docs import write_json
from tempergraph.durability.lock import LockHeld, RunLock, is_held
from tempergraph.schedule import store
from tempergraph.schedule.model import When, floor_minute, next_slots

LOCK = "loop.lock"
INFO = "loop.json"
STOP = "loop.stop"
MAX_SLEEP_S = 60.0  # TCK-B14
SLICE_S = 5.0  # the sleep is taken in slices, so a stop marker and a clock jump are seen within one
JUMP_S = 10.0  # wall and monotonic time that part further than this are a clock jump (a machine that slept)
STALE_INTERVALS = 3


@dataclass
class Edges:
    clock: Callable[[], datetime]
    monotonic: Callable[[], float]
    sleeper: Callable[[float], None]
    tick: Callable[[], Any]  # one tick, read fresh each time
    switched: Callable[[], bool] = lambda: False  # an `update` installed another engine
    reexec: Callable[[], bool] = lambda: True  # start the loop again through the shim


def lock_path(home: Path) -> Path:
    return store.schedules_root(home) / LOCK


def running(home: Path) -> dict[str, Any] | None:
    """The loop of this user, when its lock is held (read-only); its `loop.json` says its pid."""
    if not is_held(lock_path(home)):
        return None
    try:
        doc = json.loads((store.schedules_root(home) / INFO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {}
    return dict(doc) if isinstance(doc, dict) else {}


def stop(home: Path) -> bool:
    """`schedule loop --stop`: ask the running loop to end. False when none runs."""
    if running(home) is None:
        return False
    (store.schedules_root(home) / STOP).write_text("stop\n", encoding="utf-8")
    return True


def sleep_for(now: datetime, entries: list[dict[str, Any]], *, max_s: float = MAX_SLEEP_S, floor_s: float = 1.0) -> float:
    """Seconds until the earlier of the next slot of any active schedule and `max_s`, never below `floor_s`."""
    best = max_s
    for e in entries:
        if e.get("state") != "active":
            continue
        for s in next_slots(When.from_doc(e["when"]), floor_minute(now), 2):
            if s.utc > now:
                best = min(best, (s.utc - now).total_seconds())
                break
    return max(floor_s, min(best, max_s))


def wait(seconds: float, e: Edges, home: Path) -> str:
    """Sleep `seconds` in slices: `stop` when the marker appears, `jump` when the wall clock parts from the monotonic one,
    else `slept`."""
    wall0, mono0 = e.clock(), e.monotonic()
    marker = store.schedules_root(home) / STOP
    while True:
        if marker.exists():
            return "stop"
        mono = e.monotonic() - mono0
        if abs((e.clock() - wall0).total_seconds() - mono) > JUMP_S:
            return "jump"
        if mono >= seconds:
            return "slept"
        e.sleeper(min(SLICE_S, seconds - mono))


def _info(home: Path, now: datetime, ticks: int) -> None:
    with contextlib.suppress(OSError):
        write_json(store.schedules_root(home) / INFO, {"schema_version": 1, "pid": os.getpid(), "engine_version": ENGINE_VERSION,
                                                       "started_at": now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                       "ticks": ticks})


def run_loop(home: Path, e: Edges, *, max_ticks: int | None = None) -> int:
    """Run until stopped (or `max_ticks`, for tests). A second loop of the same user finds the lock held and ends at once."""
    try:
        store.schedules_root(home).mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = RunLock(lock_path(home)).acquire()
    except LockHeld:
        return 0
    except OSError:
        return 1
    marker = store.schedules_root(home) / STOP
    marker.unlink(missing_ok=True)
    ticks = 0
    try:
        while True:
            e.tick()
            ticks += 1
            _info(home, e.clock(), ticks)
            if e.switched():  # TCK-B8: the tick is finished; the next runs on the new engine
                lock.release()
                e.reexec()
                return 0
            if marker.exists() or (max_ticks is not None and ticks >= max_ticks):
                return 0
            how = wait(sleep_for(e.clock(), store.list_entries(home)), e, home)
            if how == "stop":
                return 0
    finally:
        lock.release()
        marker.unlink(missing_ok=True)
        (store.schedules_root(home) / INFO).unlink(missing_ok=True)


def engine_switched(home: Path) -> bool:
    """`engines/current.json` names another environment than the one this process runs in (read-only)."""
    try:
        doc = json.loads((home / "engines" / "current.json").read_text(encoding="utf-8"))
        current = Path(str(doc["path"])).resolve()
    except (OSError, ValueError, KeyError):
        return False
    return current != Path(sys.prefix).resolve()


def trigger_alive(home: Path, now: datetime, os_entry: Callable[[], bool] = lambda: False) -> bool:
    """TCK-B15: a loop runs, or an `os` entry exists (`os_entry` says), or a tick ran within three of its intervals."""
    if running(home) is not None or os_entry():
        return True
    from tempergraph.schedule import tick

    beat = tick.read_heartbeat(home)
    if not beat:
        return False
    try:
        last = datetime.fromisoformat(str(beat["last_tick_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return False
    return now - last <= timedelta(seconds=STALE_INTERVALS * int(beat.get("interval_s") or 60))


def autostart(home: Path, start: Callable[[], bool]) -> bool:
    """The `host` adapter (TCK-B14): start `schedule loop --detach` only when `schedule.loop_autostart` is on and no loop
    holds the lock. Exits quietly on every failure: a hook never blocks a session."""
    from tempergraph import settings

    try:
        if not settings.schedule_settings(home)["loop_autostart"] or running(home) is not None:
            return False
        return bool(start())
    except Exception:  # noqa: BLE001
        return False
