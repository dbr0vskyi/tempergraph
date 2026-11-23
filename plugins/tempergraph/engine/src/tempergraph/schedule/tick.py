"""The tick: one OS-agnostic, deterministic, model-free routine that decides what is due and starts it (TCK-B16, TCK-B12,
TCK-B2; ADR-0095).

Every edge is injected (clock, run launcher, credential resolver, thread-status reader, repository check), so the tick
is tested with a fake clock and a scripted launcher and starts no model. The decisions are the pure functions of
`policies`; this module only reads the fire log, calls them, appends what they return and launches.

Exactly once (SCH-B7): a slot is handled by one event (`started`, `skipped`, `missed` or `refused`) appended under the
schedule's own lock after the log is read again under it, so two ticks, a loop and an external call, or a tick killed
at any step and run again never handle a slot twice. `started` is appended before the run is launched; a tick killed
between the two leaves a started fire whose thread never appears, which a later tick settles as lost.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tempergraph.constants import ENGINE_VERSION
from tempergraph.docs import write_json
from tempergraph.durability.lock import LockHeld, RunLock
from tempergraph.schedule import credentials, ledger, policies, store
from tempergraph.schedule.model import floor_minute
from tempergraph.store.layout import ensure_home

MAX_RUNS = 4  # TCK-B16: runs started in one tick
BUDGET_S = 20.0  # TCK-B16: seconds one tick spends
LOST_AFTER_S = 600  # a started fire whose thread never appeared this long after is settled as lost
HEARTBEAT = "tick.json"
LOCK = "tick.lock"
FINISHED_STATES = ("finished", "stopped", "unfinished")
KILLED = {"stopped": 4, "unfinished": 5, "lost": 5}

Launcher = Callable[[dict[str, Any], dict[str, Any]], bool]  # (entry, start) -> the run was started
Resolver = Callable[[dict[str, Any]], credentials.Check]
StatusOf = Callable[[dict[str, Any], str], dict[str, Any] | None]  # (entry, thread id) -> state, exit_code, cost, alive


def _noop(*_a: Any) -> None:
    return None


@dataclass
class Edges:
    clock: Callable[[], datetime]
    launcher: Launcher
    resolver: Resolver
    status_of: StatusOf = lambda entry, thread: None
    state_root_of: Callable[[dict[str, Any]], Path | None] = lambda entry: None
    repo_ok: Callable[[str], bool] = lambda repo: Path(repo).is_dir()
    preflight: Callable[[dict[str, Any]], tuple[str, str] | None] = lambda entry: None  # `run --check`: (reason, message)
    monotonic: Callable[[], float] = time.monotonic
    on_hook: Callable[[str, dict[str, Any], dict[str, Any]], None] = lambda event, entry, facts: None
    log_error: Callable[[BaseException], None] = lambda exc: logging.getLogger("tempergraph").error(
        "schedule_tick_error", exc_info=exc)
    checkpoint: Callable[[str], None] = _noop  # tests kill the tick at a named step: lock, settle, decide, started, launch, ended


@dataclass
class Result:
    exit_code: int = 0
    locked: bool = False
    started: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)
    settled: list[str] = field(default_factory=list)
    skipped: int = 0
    missed: int = 0
    deferred: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None

    def summary(self) -> str:
        if self.locked:
            return "tick: another tick holds the lock"
        if self.exit_code:
            return f"tick: the home store is not writable ({self.error})"
        text = (f"tick: started {len(self.started)}, refused {len(self.refused)}, skipped {self.skipped}, missed "
                f"{self.missed}, settled {len(self.settled)}, deferred {len(self.deferred)}")
        return text + (f"; error {self.error}" if self.error else "")

    def to_doc(self) -> dict[str, Any]:
        return {"schema_version": 1, "locked": self.locked, "exit_code": self.exit_code, "started": self.started,
                "refused": self.refused, "settled": self.settled, "skipped": self.skipped, "missed": self.missed,
                "deferred": self.deferred, "error": self.error, "summary": self.summary()}


def _iso(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def entry_resolver(environment: Mapping[str, str], profile: Mapping[str, str], user_home: Path | None = None) -> Resolver:
    """TCK-B19 at a fire: the executors recorded at `add` and `edit`, resolved in the tick's own environment."""

    def resolve(entry: dict[str, Any]) -> credentials.Check:
        return credentials.check_fire(entry, environment, profile, user_home)

    return resolve


def schedule_lock_path(schedule_id: str, home: Path | None = None) -> Path:
    return store.entry_path(schedule_id, home).parent / "fire.lock"


# --- the fire log under the schedule's lock ----------------------------------------------------------------------------


class _Fires:
    """One schedule's fire log written through `commit_events` and mirrored into the ledger."""

    def __init__(self, entry: dict[str, Any], home: Path, edges: Edges, now: datetime, trigger: str, result: Result) -> None:
        self.entry, self.home, self.edges, self.now, self.trigger, self.result = entry, home, edges, now, trigger, result
        self.sid = str(entry["schedule_id"])
        self.log = store.read_log(self.sid, home)

    def append(self, event: dict[str, Any]) -> bool:
        """Append one event unless its slot is already handled (SCH-B7); mirror a handled one into the ledger."""
        if not policies.commit_events(list(self.log), [event]):
            return False
        meta = {k: v for k, v in event.items() if k not in ("kind", "slot", "fire_id", "at")}
        rec = store.append_event(self.sid, str(event["kind"]), now=self.now, slot=event.get("slot"),
                                 fire_id=event.get("fire_id"), home=self.home, **meta)
        if rec is None:
            return False
        self.log.append(rec)
        if event["kind"] in policies.HANDLED:
            root = self.edges.state_root_of(self.entry) if event["kind"] == "started" else None
            ledger.append(ledger.fire_row(self.entry, fire_id=str(event.get("fire_id")), slot=event.get("slot"),
                                          outcome=str(event["kind"]), at=self.now, reason=event.get("reason"),
                                          thread_id=event.get("thread"), state_root=root, trigger=self.trigger), self.home)
            if event["kind"] == "skipped":
                self.result.skipped += 1
            elif event["kind"] == "missed":
                self.result.missed += 1
        return True

    def after(self) -> None:
        """SCH-B23: the failure count reaches the limit: pause the schedule and fire `schedule_paused`."""
        d = policies.decide_after(self.entry, self.log, self.now)
        if d.state != "paused":
            return
        for e in d.events:
            self.append(e)
        self.entry = dict(self.entry, state="paused")
        store.write_entry(self.entry, self.home)
        for a in d.attention:
            self.edges.on_hook("schedule_paused", self.entry, a)


def _live(log: list[dict[str, Any]], entry: dict[str, Any], edges: Edges) -> list[policies.LiveRun]:
    ended = {e.get("fire_id") for e in log if e.get("kind") == "ended"}
    out: list[policies.LiveRun] = []
    for e in log:
        if e.get("kind") == "started" and e.get("fire_id") not in ended:
            st = edges.status_of(entry, str(e.get("thread"))) if e.get("thread") else None
            state = "paused" if st and st.get("state") == "paused" else "running"
            out.append(policies.LiveRun(str(e["fire_id"]), str(e["slot"]), str(e.get("thread")), state, e.get("at")))
    return out


def _cost(raw: Any) -> dict[str, Any]:
    c = raw if isinstance(raw, dict) else {}
    reported = float(c.get("reported") or 0.0)
    estimated = reported + float(c.get("estimated_only") or 0.0)
    return {"reported": reported, "estimated": estimated if (c or reported) else None,
            "incomplete": bool(c.get("incomplete") or c.get("unmeasured") or not c)}


def _settle(f: _Fires) -> None:
    """Every `started` fire with no `ended`: from its thread's status, append `ended` and update the failure count."""
    ended = {e.get("fire_id") for e in f.log if e.get("kind") == "ended"}
    for e in [x for x in f.log if x.get("kind") == "started" and x.get("fire_id") not in ended]:
        st = f.edges.status_of(f.entry, str(e.get("thread"))) if e.get("thread") else None
        age = (f.now - datetime.fromisoformat(str(e.get("at") or e["slot"]).replace("Z", "+00:00"))).total_seconds()
        state = str((st or {}).get("state") or "none")
        if state in ("running", "paused") or (state == "none" and age < LOST_AFTER_S):
            continue
        outcome = "lost" if state == "none" else state
        code = (st or {}).get("exit_code")
        if code is None:
            code = 0 if outcome == "finished" else KILLED.get(outcome, 5)
        meta: dict[str, Any] = {"exit": int(code), "outcome": outcome, "cost": _cost((st or {}).get("cost")),
                                "thread": e.get("thread")}
        if f.append({"kind": "ended", "slot": None, "fire_id": e["fire_id"], **meta}):
            ledger.settle(str(e["fire_id"]), {k: meta[k] for k in ("exit", "outcome", "cost")}, at=f.now, home=f.home)
            f.result.settled.append(str(e["fire_id"]))
            f.edges.checkpoint("ended")
            f.after()


# --- one start -----------------------------------------------------------------------------------------------------------


def _refuse(f: _Fires, start: dict[str, Any], reason: str, message: str, executor: str | None = None) -> None:
    extra: dict[str, Any] = {"message": message[:200]}
    if executor:
        extra["executor"] = executor
    if f.append({"kind": "refused", "slot": start["slot"], "fire_id": start["fire_id"], "reason": reason, **extra}):
        f.result.refused.append(str(start["fire_id"]))
        f.after()


def start_one(f: _Fires, start: dict[str, Any]) -> bool:
    """The refusals of TCK-B16 (a moved repository, the preflight, the credential check), then `started` and the launch."""
    repo = str((f.entry.get("target") or {}).get("repo") or "")
    if not repo or not f.edges.repo_ok(repo):
        _refuse(f, start, "repo_missing", f"the repository {repo!r} was moved or deleted")
        return False
    problem = f.edges.preflight(f.entry)
    if problem is not None:
        _refuse(f, start, problem[0], problem[1])
        return False
    verdict = f.edges.resolver(f.entry)
    if verdict.refusal is not None:
        code, message = verdict.refusal
        _refuse(f, start, code, message, next((r["executor"] for r in verdict.checked if r.get("result") in ("refused", "none")),
                                              None))
        return False
    if not f.append(policies.started_event(start)):  # the slot was handled under the lock: nothing to launch
        return False
    f.result.started.append(str(start["fire_id"]))
    f.edges.checkpoint("started")
    ok = f.edges.launcher(f.entry, start)
    f.edges.checkpoint("launch")
    if not ok:  # the run could not be started: an `ended` that counts as a failure (SCH-B23)
        meta = {"exit": 5, "outcome": "launch_failed", "cost": {"reported": 0.0, "estimated": 0.0, "incomplete": False},
                "thread": start.get("thread")}
        if f.append({"kind": "ended", "slot": None, "fire_id": start["fire_id"], **meta}):
            ledger.settle(str(start["fire_id"]), {k: meta[k] for k in ("exit", "outcome", "cost")}, at=f.now, home=f.home)
            f.after()
    return ok


# --- the tick ----------------------------------------------------------------------------------------------------------------


def heartbeat_path(home: Path) -> Path:
    return store.schedules_root(home) / HEARTBEAT


def read_heartbeat(home: Path | None = None) -> dict[str, Any] | None:
    """The heartbeat `tick.json`, or None; read-only."""
    try:
        doc = json.loads((store.schedules_root(home) / HEARTBEAT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def _due_key(entry: dict[str, Any], log: list[dict[str, Any]], now: datetime) -> str:
    passed = policies.passed_slots(entry, log, now) if entry.get("state") == "active" else []
    return _iso(min(passed)) if passed else "9999"


def run_tick(home: Path, edges: Edges, *, trigger: str = "external", interval_s: int = policies.DEFAULT_TICK_S) -> Result:
    """TCK-B16. Never raises for a schedule's own trouble: an unhandled error goes to the code log and the heartbeat."""
    result = Result()
    try:
        ensure_home(home)
        store.schedules_root(home).mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = RunLock(store.schedules_root(home) / LOCK).acquire()
    except LockHeld:
        result.locked = True  # TCK-B2: exit 0 at once, nothing read
        return result
    except OSError as exc:
        result.exit_code, result.error = 1, type(exc).__name__  # an unwritable home store: nothing started
        return result
    now = edges.clock()
    kinds: dict[str, list[str]] = {}
    try:
        edges.checkpoint("lock")
        entries = store.list_entries(home)
        for entry in entries:
            if entry.get("state") != "removed":
                _locked(entry, home, edges, now, trigger, result, lambda f: _settle(f))
        edges.checkpoint("settle")
        order = sorted((e for e in store.list_entries(home) if e.get("state") == "active"),
                       key=lambda e: _due_key(e, store.read_log(str(e["schedule_id"]), home), now))
        started = [0]
        t0 = edges.monotonic()
        for entry in order:
            _locked(entry, home, edges, now, trigger, result,
                    lambda f: _decide(f, interval_s, started, t0, kinds))
    except Exception as exc:  # noqa: BLE001 - the tick ends with exit 0 and says what failed (TCK-B16)
        result.error = f"{type(exc).__name__}: {exc}"[:200]
        edges.log_error(exc)
    finally:
        try:
            _heartbeat(home, edges, now, trigger, interval_s, result, kinds)
        finally:
            lock.release()
    return result


def _locked(entry: dict[str, Any], home: Path, edges: Edges, now: datetime, trigger: str, result: Result,
            body: Callable[[_Fires], None]) -> None:
    """Run `body` under the schedule's own lock; a schedule another process is handling is left for the next tick."""
    sid = str(entry["schedule_id"])
    lock = RunLock(schedule_lock_path(sid, home))
    try:
        lock.acquire()
    except LockHeld:
        return
    try:
        fresh = store.read_entry(sid, home)  # read again under the lock: a `fire` or an edit may have just changed it
        body(_Fires(fresh, home, edges, now, trigger, result))
    finally:
        lock.release()


def _decide(f: _Fires, interval_s: int, started: list[int], t0: float, kinds: dict[str, list[str]]) -> None:
    if f.entry.get("state") != "active":
        return
    live = _live(f.log, f.entry, f.edges)
    d = policies.decide_tick(f.entry, f.log, live, f.now, tick_s=interval_s)
    f.edges.checkpoint("decide")
    for e in d.events:
        f.append(e)
    for row in f.edges.resolver(f.entry).checked:
        kinds[str(row["executor"])] = list(row["kinds"])
    waiting = False
    for start in sorted(d.start, key=lambda s: s["slot"]):
        if started[0] >= MAX_RUNS or f.edges.monotonic() - t0 >= BUDGET_S:
            f.result.deferred.append({"schedule_id": f.sid, "slot": str(start["slot"])})
            waiting = True
            continue
        started[0] += 1
        start_one(f, start)
    if d.state == "done" and not waiting and f.entry.get("state") == "active":
        f.entry = dict(f.entry, state=d.state)
        store.write_entry(f.entry, f.home)


def _heartbeat(home: Path, edges: Edges, now: datetime, trigger: str, interval_s: int, result: Result,
               kinds: dict[str, list[str]]) -> None:
    doc = {"schema_version": 1, "last_tick_at": _iso(now), "engine_version": ENGINE_VERSION, "trigger": trigger,
           "interval_s": interval_s, "credentials": kinds, "deferred": result.deferred,
           "started": len(result.started), "last_error": result.error}
    try:
        write_json(heartbeat_path(home), doc)
    except OSError as exc:
        edges.log_error(exc)


# --- `schedule fire` (SCH-B26): one manual slot through the same path, no catch-up -------------------------------------------


def manual_start(entry: dict[str, Any], now: datetime, log: list[dict[str, Any]]) -> dict[str, Any]:
    """The start of a manual fire: id `<schedule_id>@manual-<yyyymmddThhmmssZ>`, its slot the second it was asked."""
    sid, workflow = str(entry["schedule_id"]), str((entry.get("target") or {}).get("workflow"))
    at = now.astimezone(UTC).replace(microsecond=0)
    start = policies.plan_start(entry, floor_minute(at), log)
    start.update(slot=_iso(at), fire_id=policies.fire_id(sid, at, manual_at=at),
                 thread=f"{workflow}/s-{sid}-manual-{at:%Y%m%dT%H%M%S}")
    return start


def fire_now(entry: dict[str, Any], edges: Edges, home: Path, *, trigger: str = "manual") -> tuple[Result, dict[str, Any]]:
    now = edges.clock()
    result = Result()
    holder: dict[str, Any] = {}

    def body(f: _Fires) -> None:
        start = manual_start(f.entry, now, f.log)
        holder.update(start)
        start_one(f, start)

    _locked(entry, home, edges, now, trigger, result, body)
    return result, holder


def stale_after(interval_s: int) -> timedelta:
    return timedelta(seconds=3 * interval_s)
