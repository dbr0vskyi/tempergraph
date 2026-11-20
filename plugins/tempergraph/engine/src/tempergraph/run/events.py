"""Reading run events: the run log in `seq` order, the activity journal, `--follow`, narrator lines and the
in-process observers (EVT §2.1–§2.3, §2.6; ADR-0022, ADR-0027).

Readers here create nothing and call no model (contract C13); they skip unknown kinds and fields (C12).
Observers never change a run or its exit code (contract C2, EVT-B5).
"""

from __future__ import annotations

import contextlib
import json
import queue
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

QUEUE_SIZE = 1_000
NARRATED = frozenset({"unit_entered", "check", "gate", "route", "pause", "human", "budget", "stop_requested"})


# -- reading ----------------------------------------------------------------------------------------


def _lines(path: Path, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    """Complete JSON lines from byte `offset`; a partial last line is left for the next read."""
    try:
        with open(path, "rb") as fh:
            fh.seek(offset)
            data = fh.read()
    except OSError:
        return [], offset
    out: list[dict[str, Any]] = []
    end = data.rfind(b"\n")
    if end < 0:
        return out, offset
    for line in data[: end + 1].splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out, offset + end + 1


def records(path: Path, since: int | None = None) -> list[dict[str, Any]]:
    """Every run-log record after `since`, in `seq` order; the schema line is not a record."""
    recs, _ = _lines(path)
    return [r for r in recs if isinstance(r.get("seq"), int) and (since is None or r["seq"] > since)]


def follow(path: Path, held: Callable[[], bool], since: int | None = None, *, poll_s: float = 0.25,
           timeout_s: float | None = None, sleep: Callable[[float], None] = time.sleep) -> Iterator[dict[str, Any]]:
    """Records after `since` as they are written; ends once the newest segment's `run_exit` is read and no
    lock is held (EVT §2.6, EVT-B3). Each record is yielded once."""
    offset, last, ended = 0, since, False
    start = time.monotonic()
    while True:
        recs, offset = _lines(path, offset)
        for r in recs:
            seq = r.get("seq")
            if not isinstance(seq, int):
                continue
            if r.get("kind") == "run_started":
                ended = False
            elif r.get("kind") == "run_exit":
                ended = True
            if last is not None and seq <= last:
                continue
            last = seq
            yield r
        if not held() and (ended or not recs):
            return  # the segment exited, or the process is gone without a `run_exit` (orphaned)
        if timeout_s is not None and time.monotonic() - start >= timeout_s:
            return
        sleep(poll_s)


def activity(path: Path, since: int | None = None) -> list[dict[str, Any]]:
    """One session's activity journal lines after line number `since`."""
    lines, _ = _lines(path)
    return [ln for ln in lines if since is None or (isinstance(ln.get("n"), int) and ln["n"] > since)]


def follow_activity(path: Path, live: Path, held: Callable[[], bool], since: int | None = None, *,
                    poll_s: float = 0.25, timeout_s: float | None = None,
                    sleep: Callable[[float], None] = time.sleep) -> Iterator[dict[str, Any]]:
    """Journal lines as they are flushed; ends at the session's `result` or `truncated` line, when its live
    file is removed at session end, or when no lock is held."""
    offset, last, seen_live, done = 0, since, False, False
    start = time.monotonic()
    while True:
        lines, offset = _lines(path, offset)
        seen_live = seen_live or live.exists()
        for ln in lines:
            if ln.get("ev") in ("result", "truncated"):
                done = True
            n = ln.get("n")
            if last is not None and isinstance(n, int) and n <= last:
                continue
            if isinstance(n, int):
                last = n
            yield ln
        if not lines and (done or (seen_live and not live.exists()) or not held()):
            return
        if timeout_s is not None and time.monotonic() - start >= timeout_s:
            return
        sleep(poll_s)


# -- narrator lines ---------------------------------------------------------------------------------


def route_unit(node: Any) -> str | None:
    """A graph node by its unit: `draft.step` is `draft`, a human node is `human`, the end is `end`."""
    if not isinstance(node, str) or not node:
        return None
    if node.endswith(".human"):
        return "human"
    if node == "__end__":
        return "end"
    return node.split(".", 1)[0]


def narrate(r: Mapping[str, Any]) -> str:
    """One line for a run-log record, as a monitor's narrator shows it (RDD §2.1 `events_tail`)."""
    kind = str(r.get("kind"))
    where = r.get("unit") or ""
    if r.get("item"):
        where = f"{where}[{r['item']}]"
    if r.get("attempt") is not None and kind not in ("unit_entered",):
        where = f"{where}#{r['attempt']}" if where else ""
    text: str
    if kind == "unit_entered":
        text = f"entered {where} (visit {r.get('visit')}, from {r.get('entered_from')})"
    elif kind == "check":
        env = " environmental" if r.get("environmental") else ""
        text = f"check {where}: {r.get('result')}{env}"
    elif kind == "judgement":
        text = f"judge {where}: {r.get('met', '?')}/{r.get('total', '?')} met"
    elif kind == "gate":
        target = route_unit(r.get("route_target"))
        text = f"gate {where}: {r.get('verdict')}" + (f" -> {target}" if target else "")
    elif kind == "pause":
        text = f"paused at {where} ({r.get('pause_kind') or r.get('session_kind')}): {r.get('resume') or ''}".rstrip()
    elif kind == "human":
        text = f"decision at {where}: {r.get('decision')}"
    elif kind == "budget":
        text = f"budget {r.get('counter')}: {r.get('used')}/{r.get('limit')} ({r.get('cause')})"
    elif kind == "stop_requested":
        text = f"stop requested ({r.get('mode')})"
    elif kind == "route":
        text = f"route {where} -> {route_unit(r.get('target') or r.get('route_target'))}"
    elif kind == "session_opened":
        text = f"session {r.get('session_key')} on {r.get('executor')} ({r.get('model') or r.get('alias')})"
    elif kind == "run_started":
        text = f"segment {r.get('segment')} started ({r.get('origin')})"
    elif kind == "run_exit":
        text = f"segment {r.get('segment')} exited {r.get('exit_code')} ({r.get('reason')})"
    else:
        text = f"{kind} {where}".rstrip()
    return f"{r.get('seq')} {r.get('ts')} {text}"


def tail(recs: list[dict[str, Any]], n: int = 20) -> list[str]:
    return [narrate(r) for r in recs if r.get("kind") in NARRATED][-n:]


# -- in-process observers (EVT §2.6) ----------------------------------------------------------------


@runtime_checkable
class RunObserver(Protocol):
    name: str

    def on_record(self, record: dict[str, Any]) -> None: ...

    def on_activity(self, session_key: str, line: dict[str, Any]) -> None: ...


def register_observers(entry_point_group: str = "tempergraph.observers",
                       names: tuple[str, ...] | None = None) -> tuple[list[RunObserver], list[str]]:
    """Observers installed under the entry-point group; only those named (operator config) are loaded.
    Returns the observers and the names that are not installed (a preflight warning, EVT §4)."""
    wanted = set(names or ())
    found: dict[str, RunObserver] = {}
    for ep in entry_points(group=entry_point_group):
        if ep.name not in wanted:
            continue
        try:
            obj = ep.load()
            inst = obj() if isinstance(obj, type) else obj
        except Exception:  # noqa: BLE001 - a broken observer never stops a run
            continue
        if isinstance(inst, RunObserver):
            found[ep.name] = inst
    missing = sorted(wanted - set(found))
    return list(found.values()), missing


@dataclass
class _Lane:
    observer: RunObserver
    q: queue.Queue[tuple[str, Any] | None] = field(default_factory=lambda: queue.Queue(QUEUE_SIZE))
    dropped: int = 0
    disabled: bool = False
    error: str | None = None
    thread: threading.Thread | None = None


class ObserverHub:
    """Each observer on its own thread behind a bounded queue: a full queue drops and counts, an exception
    disables that observer for the segment and is recorded once as an `engine_error` of scope `observer`."""

    def __init__(self, observers: list[RunObserver]) -> None:
        self.lanes = [_Lane(o) for o in observers]
        self._errors: queue.Queue[tuple[str, str]] = queue.Queue()
        for lane in self.lanes:
            lane.thread = threading.Thread(target=self._pump, args=(lane,), daemon=True,
                                           name=f"observer-{lane.observer.name}")
            lane.thread.start()

    def _pump(self, lane: _Lane) -> None:
        while True:
            item = lane.q.get()
            if item is None:
                return
            if lane.disabled:
                continue
            what, payload = item
            try:
                if what == "record":
                    lane.observer.on_record(payload)
                else:
                    lane.observer.on_activity(payload[0], payload[1])
            except Exception as exc:  # noqa: BLE001 - EVT-B5
                lane.disabled = True
                lane.error = type(exc).__name__
                self._errors.put((lane.observer.name, lane.error))

    def _put(self, item: tuple[str, Any]) -> None:
        for lane in self.lanes:
            if lane.disabled:
                continue
            try:
                lane.q.put_nowait(item)
            except queue.Full:
                lane.dropped += 1

    def on_record(self, record: dict[str, Any]) -> None:
        self._put(("record", dict(record)))

    def on_activity(self, session_key: str, line: dict[str, Any]) -> None:
        self._put(("activity", (session_key, dict(line))))

    def take_errors(self) -> list[tuple[str, str]]:
        out = []
        while True:
            try:
                out.append(self._errors.get_nowait())
            except queue.Empty:
                return out

    def close(self, timeout_s: float = 5.0) -> dict[str, dict[str, Any]]:
        """Drain and stop every lane; returns per observer its dropped count and whether it was disabled."""
        for lane in self.lanes:
            with contextlib.suppress(queue.Full):
                lane.q.put(None, timeout=timeout_s)
        for lane in self.lanes:
            if lane.thread is not None:
                lane.thread.join(timeout_s)
        return {lane.observer.name: {"dropped": lane.dropped, "disabled": lane.disabled, "error": lane.error}
                for lane in self.lanes}
