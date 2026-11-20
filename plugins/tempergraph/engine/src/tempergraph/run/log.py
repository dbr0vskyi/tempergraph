"""The run log, cost rules and the live progress file (OBS §2.1–§2.3, EVT §2.2; contract C2).

Every write is best effort: a failing write is counted and never changes the run.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.constants import SCHEMA
from tempergraph.contracts import Event, EventSink, Usage
from tempergraph.docs import append_jsonl, write_json
from tempergraph.security.scrub import clip, scrub
from tempergraph.store.layout import now_iso

# Engine default prices, USD per million tokens, by model family, for the current generation that the tier
# aliases resolve to (first-party list prices as of 2026-11; OBS §2.2). The binding table overrides per model.
# A row without `cache_read` prices cache reads at CACHE_READ_FACTOR of input.
DEFAULT_PRICES: dict[str, dict[str, float]] = {
    "haiku": {"input": 0.10, "output": 0.50},
    "sonnet": {"input": 2.0, "output": 10.0, "cache_read": 0.10},
    "opus": {"input": 4.0, "output": 20.0, "cache_read": 0.20},
}
CACHE_READ_FACTOR = 0.1
CACHE_WRITE_FACTOR = 1.25


def family(model: str | None) -> str | None:
    m = (model or "").lower()
    return next((f for f in DEFAULT_PRICES if f in m), None)


def estimate(usage: Usage, model: str | None, prices: Mapping[str, Mapping[str, float]] | None = None
             ) -> float | None:
    """The engine's own estimate for a session with tokens; None when unmeasured (OBS §2.2)."""
    if not usage.has_tokens():
        return None
    row = (prices or {}).get(model or "") or DEFAULT_PRICES.get(family(model) or "")
    if row is None:
        return None
    pin, pout = row["input"], row["output"]
    total = (usage.input_tokens or 0) * pin + (usage.output_tokens or 0) * pout
    total += (usage.cache_read_tokens or 0) * row.get("cache_read", pin * CACHE_READ_FACTOR)
    total += (usage.cache_write_tokens or 0) * pin * CACHE_WRITE_FACTOR
    return round(total / 1_000_000, 6)


@dataclass(kw_only=True)
class CostTotals:
    """Run cost so far: reported and estimated kept apart (OBS §2.2)."""

    reported: float = 0.0
    estimated: float = 0.0
    estimated_only: float = 0.0  # estimates of sessions that reported nothing
    sessions: int = 0
    reported_sessions: int = 0
    estimated_sessions: int = 0
    unmeasured: int = 0

    def add(self, usage: Usage) -> None:
        self.sessions += 1
        if usage.reported_cost_usd is not None:
            self.reported += usage.reported_cost_usd
            self.reported_sessions += 1
        if usage.estimated_cost_usd is not None:
            self.estimated += usage.estimated_cost_usd
            self.estimated_sessions += 1
            if usage.reported_cost_usd is None:
                self.estimated_only += usage.estimated_cost_usd
        if usage.reported_cost_usd is None and usage.estimated_cost_usd is None:
            self.unmeasured += 1

    @property
    def completeness(self) -> str:
        if self.unmeasured:
            return "incomplete"
        return "complete" if self.reported_sessions == self.sessions else "estimated"

    def figure(self) -> float:
        """The run line's figure: reported where present, else estimated, per session (BUD §2)."""
        return round(self.reported + self.estimated_only, 6)

    def to_json(self) -> dict[str, Any]:
        return {"reported": round(self.reported, 6) if self.reported_sessions else None,
                "estimated": round(self.estimated, 6) if self.estimated_sessions else None,
                "incomplete": self.completeness == "incomplete", "completeness": self.completeness,
                "counters": {k: getattr(self, k) for k in ("reported", "estimated", "estimated_only", "sessions",
                                                          "reported_sessions", "estimated_sessions", "unmeasured")}}

    @classmethod
    def from_json(cls, d: Mapping[str, Any] | None) -> CostTotals:
        t = cls()
        for k, v in ((d or {}).get("counters") or {}).items():
            if k in cls.__dataclass_fields__ and isinstance(v, int | float):
                setattr(t, k, v)
        return t


ENVELOPE_OPTIONAL = ("unit", "item", "attempt", "session_key")


def cost_so_far(cost: Mapping[str, Any] | None) -> dict[str, Any]:
    """EVT §2.2 `cost_so_far`: reported, estimated and the completeness flag for the thread so far."""
    t = CostTotals.from_json(cost)
    j = t.to_json()
    return {"reported": j["reported"], "estimated": j["estimated"], "completeness": t.completeness}


class RunLog:
    """`runs/<workflow>/<task_id>/run.jsonl`; the first line carries the schema.

    Every record carries the envelope of EVT §2.1: `seq` continues across instances and segments,
    `segment` counts process lifetimes (0 at the start, +1 per resume), `thread_id` comes from the path,
    and `unit`, `item`, `attempt` and `session_key` are present, null when the record has no unit.
    """

    def __init__(self, path: Path, observers: Any = None) -> None:
        self.path = path
        self.failures = 0
        self.seq = last_seq(path)  # seq continues across segments (EVT-B2)
        self.thread_id = f"{path.parent.parent.name}/{path.parent.name}"
        self.segment: int | None = None
        self.checked_tail = False
        self.observers = observers  # an ObserverHub (run/events.py) or None; enabled in operator config only

    def _segment(self) -> int:
        """This process's segment: the one after the log's last `run_started`, or 0 for a new thread."""
        if self.segment is None:
            prev = last_record(self.path, "run_started")
            last = (prev or {}).get("segment")
            self.segment = 0 if prev is None else (last + 1 if isinstance(last, int) else 1)
        return self.segment

    def write(self, record: str, /, **fields: Any) -> int:
        self.seq += 1
        try:
            segment = self._segment()
        except Exception:  # noqa: BLE001 - C2
            segment = 0
        rec = {**fields, "kind": record, "ts": now_iso(), "seq": self.seq, "thread_id": self.thread_id,
               "segment": segment}
        if "kind" in fields:
            rec["session_kind"] = fields["kind"]
        for key in ENVELOPE_OPTIONAL:
            rec.setdefault(key, None)
        if rec["session_key"] and (rec["unit"] is None or rec["attempt"] is None):
            unit, item, attempt = split_session_key(str(rec["session_key"]))
            for k, v in (("unit", unit), ("item", item), ("attempt", attempt)):
                if rec[k] is None:
                    rec[k] = v
        out = _jsonable(rec)
        try:
            if not self.path.exists():
                append_jsonl(self.path, {"kind": "schema", "schema": SCHEMA["run_log"]})
            elif not self.checked_tail:
                _end_cut_line(self.path)
            self.checked_tail = True
            append_jsonl(self.path, out)
        except Exception:  # noqa: BLE001 - observability never changes the run (C2)
            self.failures += 1
            return self.seq
        if self.observers is not None:
            self.observers.on_record(out)
            for name, error in self.observers.take_errors():  # EVT-B5: recorded once, the run goes on
                self.write("engine_error", scope="observer", observer=name, error=error)
        if record in ("run_started", "run_exit"):
            self._rows(record, segment)
        return self.seq

    def _rows(self, record: str, segment: int) -> None:
        """The machine index at `run_started` and the stats row at `run_exit` (CST §2.1, §2.2); best effort (C2)."""
        try:
            from tempergraph.observe import rows

            if record == "run_started":
                rows.on_run_started(self.path)
            else:
                rows.on_run_exit(self.path, segment)
        except Exception:  # noqa: BLE001
            self.failures += 1


def _end_cut_line(path: Path) -> None:
    """A process that died mid-line leaves a partial last line; end it so the next record is whole."""
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        if fh.tell() == 0:
            return
        fh.seek(-1, os.SEEK_END)
        last = fh.read(1)
    if last != b"\n":
        with open(path, "ab") as fh:
            fh.write(b"\n")


def split_session_key(key: str) -> tuple[str | None, str | None, int | None]:
    """`<unit>[.<item>].<attempt>.<kind>[.<n>]` back into unit, item and attempt (EVT §2.1)."""
    parts = key.split(".")
    for i in range(len(parts) - 2, 0, -1):
        if parts[i].isdigit() and not parts[i + 1].isdigit():
            head = parts[:i]
            unit = head[0] if head else None
            item = ".".join(head[1:]) or None
            return unit, item, int(parts[i])
    return None, None, None


def last_seq(path: Path) -> int:
    """The `seq` of the last record of a run log, 0 when there is none; reads only the file's tail."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 65536))
            lines = fh.read().splitlines()
    except OSError:
        return 0
    for line in reversed(lines):
        try:
            seq = json.loads(line).get("seq")
        except (ValueError, AttributeError):
            continue
        if isinstance(seq, int):
            return seq
    return 0


def last_record(path: Path, kind: str, **match: Any) -> dict[str, Any] | None:
    """The last run-log record of `kind` whose fields match; None when there is none."""
    found = None
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("kind") == kind and all(rec.get(k) == v for k, v in match.items()):
                    found = rec
    except OSError:
        return None
    return found


def _jsonable(v: Any) -> Any:
    if isinstance(v, Usage):
        return v.to_json()
    if isinstance(v, Mapping):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [_jsonable(x) for x in v]
    if isinstance(v, str | int | float | bool) or v is None:
        return v
    return str(v)


JOURNAL_MAX_LINES = 20_000
JOURNAL_MAX_BYTES = 8 * 1024 * 1024
# The journal cap's drop order (EVT §2.3): past half the cap `model_delta` lines are dropped, past three
# quarters `text` lines too, and past 95 % everything but tool lines; the last slot is the `truncated` line.
_DROP_STAGES: tuple[tuple[float, frozenset[str] | None], ...] = (
    (0.95, None), (0.75, frozenset({"model_delta", "text"})), (0.5, frozenset({"model_delta"})))
_TOOL_EVENTS = frozenset({"tool_started", "tool_finished"})


class LiveSink(EventSink):
    """The live progress file (OBS §2.3, RDD §2.2) and the activity journal (EVT §2.3).

    The journal is buffered and flushed at most once a second and at session end; the live file is replaced
    at most once a second. `opened` is called once with the `session_started` data, so the caller writes
    `session_opened`; `observers` get every journal line after it is written. Every write is best effort.
    """

    def __init__(self, session_dir: Path | None, clock: Any = time.monotonic, *,
                 opened: Callable[[dict[str, Any]], None] | None = None, observers: Any = None,
                 session_key: str = "", tool_inputs: bool = True,
                 max_lines: int = JOURNAL_MAX_LINES, max_bytes: int = JOURNAL_MAX_BYTES) -> None:
        super().__init__()
        self.dir = session_dir
        self.clock = clock
        self.opened = opened
        self.observers = observers
        self.session_key = session_key or (session_dir.name if session_dir else "")
        self.tool_inputs = tool_inputs
        self.max_lines, self.max_bytes = max_lines, max_bytes
        self.last_write = float("-inf")
        self.last_flush = float("-inf")
        self.recent: list[dict[str, Any]] = []
        self.open_tool: dict[str, Any] | None = None
        self.open_calls: dict[str, dict[str, Any]] = {}
        self.last_text = ""
        self.last_event_at: str | None = None
        self.tokens_so_far: int | None = None
        self.turns_so_far: int | None = None
        self.pgid: int | None = None
        self.n = 0
        self.lines = 0
        self.bytes = 0
        self.dropped: dict[str, int] = {}
        self.buffer: list[dict[str, Any]] = []
        self.failures = 0
        self.disabled = False
        self.closed = False

    # -- the journal -------------------------------------------------------------------------------

    def _keep(self, ev: str) -> bool:
        used = max(self.lines / self.max_lines, self.bytes / self.max_bytes)
        if self.lines >= self.max_lines - 1 or self.bytes >= self.max_bytes:
            return False
        for threshold, drop in _DROP_STAGES:
            if used >= threshold:
                return ev in _TOOL_EVENTS if drop is None else ev not in drop
        return True

    def _journal(self, row: dict[str, Any]) -> None:
        if self.dir is None or self.disabled:
            return
        ev = str(row.get("ev"))
        if not self._keep(ev):
            self.dropped[ev] = self.dropped.get(ev, 0) + 1
            return
        row = _jsonable(row)
        self.lines += 1
        self.bytes += len(json.dumps(row, ensure_ascii=False)) + 1
        self.buffer.append(row)

    def flush(self) -> None:
        if self.dir is None or not self.buffer or self.disabled:
            self.buffer.clear()
            return
        rows, self.buffer = self.buffer, []
        try:
            path = self.dir / "activity.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with open(path, "a", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            os.chmod(path, 0o600)
        except Exception:  # noqa: BLE001 - EVT §4: journal off for this session, the session goes on
            self.failures += 1
            self.disabled = True
            return
        self.last_flush = self.clock()
        if self.observers is not None:
            for row in rows:
                self.observers.on_activity(self.session_key, row)

    # -- events --------------------------------------------------------------------------------------

    def push(self, event: Event) -> None:
        super().push(event)
        if self.dir is None:
            return
        self.n += 1
        d = {k: v for k, v in dict(event.data).items() if k != "usage"}
        self.last_event_at = now_iso()
        if event.kind == "session_started":
            self._opened(dict(event.data))
        elif event.kind == "tool_started":
            if not self.tool_inputs:
                d["input_summary"] = None
            call: dict[str, Any] = {"name": d.get("name"), "capability": d.get("capability"),
                    "input_summary": d.get("input_summary"), "started_at": self.last_event_at, "t": event.ts}
            self.open_calls[str(d.get("call_id", ""))] = call
            self.open_tool = call
        elif event.kind == "tool_finished":
            done_call = self.open_calls.pop(str(d.get("call_id", "")), None)
            if done_call is not None:
                call = done_call
                d["duration_s"] = round(max(0.0, event.ts - float(call.get("t") or 0.0)), 3)
                done = {"name": call["name"], "input_summary": call["input_summary"], "ok": d.get("ok"),
                        "duration_s": d["duration_s"]}
                self.recent = (self.recent + [done])[-10:]
            self.open_tool = next(reversed(self.open_calls.values()), None)
        elif event.kind == "text":
            self.last_text = clip(scrub(str(d.get("last_line", ""))), 200)
        elif event.kind == "result":
            usage = event.data.get("usage")
            if isinstance(usage, Usage):
                tokens = [x for x in (usage.input_tokens, usage.output_tokens) if x is not None]
                self.tokens_so_far = sum(tokens) if tokens else None
                self.turns_so_far = usage.turns
        if "pgid" in d and isinstance(d.get("pgid"), int):
            self.pgid = d["pgid"]
        self._journal({"t": round(event.ts, 3), "n": self.n, "ev": event.kind, **d})
        now = self.clock()
        if now - self.last_flush >= 1.0 or event.kind == "result":
            self.flush()
        if now - self.last_write >= 1.0 or event.kind == "result":
            self.last_write = now
            self._live()

    def write_meta(self, **fields: Any) -> None:
        """`meta.json` of the session (LOS §2.1), merged field by field; best effort (contract C2)."""
        if self.dir is None or self.disabled:
            return
        path = self.dir / "meta.json"
        try:
            held = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"schema_version": 1}
            held.update(_jsonable(fields))
            write_json(path, held)
        except Exception:  # noqa: BLE001
            self.failures += 1

    def _opened(self, data: dict[str, Any]) -> None:
        if self.opened is None:
            return
        try:
            self.opened(data)
        except Exception:  # noqa: BLE001 - C2
            self.failures += 1
        self.opened = None

    def _live(self) -> None:
        if self.dir is None:
            return
        open_tool = None
        if self.open_tool is not None:
            open_tool = {k: v for k, v in self.open_tool.items() if k != "t"}
        try:
            write_json(self.dir / "live.json", {
                "schema_version": SCHEMA["activity"], "session_key": self.session_key, "open_tool": open_tool,
                "recent": self.recent, "last_text": self.last_text, "tokens_so_far": self.tokens_so_far,
                "turns_so_far": self.turns_so_far, "pgid": self.pgid, "last_event_at": self.last_event_at,
                "updated_at": now_iso(), "pid": os.getpid(), "ended": self.closed})
        except Exception:  # noqa: BLE001
            self.failures += 1

    def close(self) -> None:
        """Session end: the `truncated` line when lines were dropped, the last flush and live file."""
        if self.closed:
            return
        self.closed = True
        if self.dropped and self.dir is not None and not self.disabled:
            self.n += 1
            self.buffer.append({"t": None, "n": self.n, "ev": "truncated", "dropped": dict(self.dropped)})
        self.flush()
        self.open_tool = None
        self.write_meta(ended_at=now_iso())
        if self.dir is not None:  # LOS §2.1: the live file is removed at session end
            try:
                (self.dir / "live.json").unlink(missing_ok=True)
            except OSError:
                self.failures += 1


def session_sink(log: RunLog, req: Any, executor: str, *, tool_inputs: bool = True) -> LiveSink:
    """The sink for one session: journal and live file in its folder, `session_opened` into the run log."""
    raw = (req.session_dir / "raw.jsonl") if req.session_dir is not None else None

    transcript = {"engine": str(raw) if raw else None, "native": None, "native_kind": None}

    def opened(data: dict[str, Any]) -> None:
        log.write("session_opened", session_key=req.session_key, kind=req.kind, executor=executor,
                  alias=req.alias, model=data.get("model"), session_id=data.get("session_id"),
                  transcript=transcript, pgid=data.get("pgid"))
        sink.write_meta(session_id=data.get("session_id"), model=data.get("model"), pgid=data.get("pgid"),
                        cli_version=data.get("cli_version"))

    sink = LiveSink(req.session_dir, opened=opened, observers=log.observers, session_key=req.session_key,
                    tool_inputs=tool_inputs)
    sink.write_meta(session_key=req.session_key, kind=req.kind, executor=executor, alias=req.alias,
                    transcript=transcript, started_at=now_iso(), ended_at=None)
    return sink


@dataclass(kw_only=True)
class Ledger:
    """`<state root>/ledger.jsonl`: one metadata-only row per run segment and per intervention."""

    path: Path
    failures: int = 0
    rows: list[dict[str, Any]] = field(default_factory=list)

    def append(self, row: dict[str, Any]) -> None:
        try:
            append_jsonl(self.path, _jsonable({"ts": now_iso(), **row}))
        except Exception:  # noqa: BLE001
            self.failures += 1


def dumps(v: Any) -> str:
    return json.dumps(_jsonable(v), ensure_ascii=False)
