"""Fire-decision policies as pure functions (SCH-B5 to SCH-B9, SCH-B11, SCH-B21 to SCH-B26; ADR-0098, ADR-0099).

Every function reads an entry (the dict of SCH-B14), its fire log (the lines of SCH-B28), the live runs (each a fire
with its thread's state) and a clock the caller passes in, and returns what to record and raise. Nothing here reads
the clock, a file or a process, writes, or starts anything: the tick of the next phase (TCK) only calls these.

A slot with a `started`, `skipped`, `missed` or `refused` event is handled, and no function decides it again.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from tempergraph.render.template import TemplateError, render
from tempergraph.schedule.model import (
    Rule,
    When,
    floor_minute,
    next_slots,
    parse_rule,
    slots_between,
    wall_to_utc,
    zone_of,
)

HANDLED = frozenset({"started", "skipped", "missed", "refused"})
DEFAULT_TICK_S = 60  # the interval the portable loop declares (TCK)
MAX_ALL_PER_TICK = 3  # SCH-B21: under `all`, at most 3 slots a tick
BLOCKING_AT = 3  # SCH-B22: after 3 slots skipped behind one paused run
MAX_PASSED = 1000  # the most recent passed slots a decision reads
DAY_S = 86400
FIRE_KEYS = ("slot", "date", "previous_slot", "schedule")


@dataclass(frozen=True)
class LiveRun:
    """A fire's run that counts as live: its thread is `running` or `paused` (SCH-B13)."""

    fire_id: str
    slot: str
    thread: str
    state: str  # "running" | "paused"
    started_at: str | None = None


@dataclass
class Decision:
    events: list[dict[str, Any]] = field(default_factory=list)  # fire-log lines to record (without `seq` and `at`)
    start: list[dict[str, Any]] = field(default_factory=list)  # slots to start now, with identity, keys and label
    attention: list[dict[str, Any]] = field(default_factory=list)  # items to raise
    hooks: list[str] = field(default_factory=list)  # lifecycle hook events to fire
    state: str | None = None  # the schedule's new state, when it changes


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _when(entry: dict[str, Any]) -> When:
    return When.from_doc(entry["when"])


def _event(kind: str, slot: datetime | str | None, sid: str, **meta: Any) -> dict[str, Any]:
    text = _iso(slot) if isinstance(slot, datetime) else slot
    return {"kind": kind, "slot": text, "fire_id": fire_id(sid, _dt(text)) if text else None, **meta}


# --- identity and keys (SCH-B26, SCH-B11) ------------------------------------------------------------------------


def fire_id(schedule_id: str, slot: datetime, manual_at: datetime | None = None) -> str:
    """`<schedule_id>@<slot as yyyymmddThhmmZ>`, or `@manual-<yyyymmddThhmmssZ>` for `schedule fire`."""
    if manual_at is not None:
        return f"{schedule_id}@manual-{manual_at.astimezone(UTC):%Y%m%dT%H%M%S}Z"
    return f"{schedule_id}@{slot.astimezone(UTC):%Y%m%dT%H%M}Z"


def thread_id(workflow: str, schedule_id: str, slot: datetime) -> str:
    """`<workflow>/s-<schedule_id>-<slot as yyyymmddThhmm>` (UTC): a second start of a slot is refused by DUR-B1."""
    return f"{workflow}/s-{schedule_id}-{slot.astimezone(UTC):%Y%m%dT%H%M}"


def orchestration_id(name: str, slot: datetime, hex4: str) -> str:
    return f"{name}-s{slot.astimezone(UTC):%Y%m%dT%H%M}-{hex4}"


def fire_keys(entry: dict[str, Any], slot: datetime, log: Sequence[dict[str, Any]]) -> dict[str, str]:
    """`{fire.slot}` (local ISO date-time), `{fire.date}`, `{fire.previous_slot}` (the last slot that started a run, or
    empty) and `{fire.schedule}`."""
    zone = zone_of(entry["when"]["zone"])
    local = slot.astimezone(zone)
    prev = [e["slot"] for e in log if e.get("kind") == "started" and e.get("slot") and e["slot"] != _iso(slot)]
    return {"fire.slot": local.strftime("%Y-%m-%dT%H:%M"), "fire.date": local.date().isoformat(),
            "fire.previous_slot": _dt(max(prev)).astimezone(zone).strftime("%Y-%m-%dT%H:%M") if prev else "",
            "fire.schedule": str(entry["schedule_id"])}


def render_fire_text(text: str, keys: dict[str, str]) -> str:
    """Render the fire keys in a request, an input or an argument by the template grammar (CON-B8). The grammar's
    field names have no dot, so `{fire.date}` is read as the field `fire_date`; any other `{fire.x}` is invalid."""
    for m in re.finditer(r"(?<!\{)\{fire\.([A-Za-z0-9_]+)\}(?!\})", text):
        if m.group(1) not in FIRE_KEYS:  # the grammar reads any dotted pair (SWF-B12): a mistyped fire key is refused here
            raise TemplateError(f"unknown fire key fire.{m.group(1)}", m.start())
    translated = re.sub(r"(?<!\{)\{fire\.(" + "|".join(FIRE_KEYS) + r")\}(?!\})", r"{fire_\1}", text)
    out, _ = render(translated, {k.replace(".", "_"): v for k, v in keys.items()})
    return out


def run_label(entry: dict[str, Any], slot: datetime) -> str:
    return f"schedule {entry['name']} {fire_keys(entry, slot, [])['fire.date']}"


def plan_start(entry: dict[str, Any], slot: datetime, log: Sequence[dict[str, Any]]) -> dict[str, Any]:
    sid = str(entry["schedule_id"])
    target = entry.get("target") or {}
    workflow = target.get("workflow")
    return {"slot": _iso(slot), "fire_id": fire_id(sid, slot),
            "thread": thread_id(str(workflow), sid, slot) if workflow else None,
            "label": run_label(entry, slot), "keys": fire_keys(entry, slot, log)}


def started_event(start: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    out = {"kind": "started", "slot": start["slot"], "fire_id": start["fire_id"], "thread": start["thread"]}
    if now is not None:
        out["at"] = _iso(now)
    return out


def commit_events(shared: list[dict[str, Any]], events: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append events to a shared fire log, dropping one for a slot that is already handled there: two decisions made over
    one log never give a slot two `started` events (SCH-B7; the slot's thread id is the second guard, DUR-B1)."""
    handled = handled_slots(shared)
    committed: list[dict[str, Any]] = []
    for e in events:
        if e.get("kind") in HANDLED and e.get("slot"):
            if e["slot"] in handled:
                continue
            handled.add(e["slot"])
        shared.append(e)
        committed.append(e)
    return committed


# --- reading the fire log ----------------------------------------------------------------------------------------


def handled_slots(log: Sequence[dict[str, Any]]) -> set[str]:
    return {str(e["slot"]) for e in log if e.get("kind") in HANDLED and e.get("slot")}


def pending_slot(log: Sequence[dict[str, Any]]) -> str | None:
    """The slot held under `queue`: the latest `queued` event whose slot has no handling event since."""
    handled = handled_slots(log)
    for e in reversed(log):
        if e.get("kind") == "queued" and e.get("slot") and e["slot"] not in handled:
            return str(e["slot"])
    return None


def since(entry: dict[str, Any], log: Sequence[dict[str, Any]]) -> datetime:
    """Slots before the schedule was created, or last edited, are nobody's (SCH-B12: `next_slot` from now)."""
    marks = [_dt(entry["created"]["at"])]
    marks += [_dt(e["at"]) for e in log if e.get("kind") == "edited" and e.get("at")]
    return max(marks)


def default_window_s(entry: dict[str, Any]) -> int:
    """The recurrence's period capped at 24 hours; 24 hours for a `once` (SCH-B21)."""
    when = entry["when"]
    if when.get("kind") == "once":
        return DAY_S
    rule: Rule = parse_rule(str(when["rule"]))
    return int(min(rule.period.total_seconds(), DAY_S))


def passed_slots(entry: dict[str, Any], log: Sequence[dict[str, Any]], now: datetime) -> list[datetime]:
    """The slots at or before `now`, since the schedule began, that nothing has handled and nothing holds pending."""
    handled, pending = handled_slots(log), pending_slot(log)
    found = slots_between(_when(entry), floor_minute(since(entry, log)), floor_minute(now))
    out = [s.utc for s in found if _iso(s.utc) not in handled and _iso(s.utc) != pending]
    return out[-MAX_PASSED:]


def classify_catch_up(entry: dict[str, Any], passed: Sequence[datetime], now: datetime, tick_s: int = DEFAULT_TICK_S
                      ) -> tuple[list[datetime], list[datetime]]:
    """(slots to fire in order, slots to record `missed`) under `latest`, `none` or `all` (SCH-B21).

    A slot found no later than one tick interval after its instant is on time and fires under every policy (an
    inference from SCH-B21, so that `none` still fires a slot the loop found on time)."""
    policy = entry.get("catch_up") or "latest"
    window = int(entry.get("catch_up_window_s") or default_window_s(entry))
    age = {s: (now - s).total_seconds() for s in passed}
    in_window = [s for s in passed if age[s] <= window]
    if policy == "none":
        fire = [s for s in passed if age[s] <= tick_s]
    elif policy == "all":
        fire = in_window[:MAX_ALL_PER_TICK]
    else:
        fire = [max(in_window)] if in_window else []
    left = set(in_window[MAX_ALL_PER_TICK:]) if policy == "all" else set()  # still pending for the next tick
    return fire, [s for s in passed if s not in fire and s not in left]


# --- spend (SCH-B24, SCH-B8) -------------------------------------------------------------------------------------


def period_bounds(entry: dict[str, Any], now: datetime) -> tuple[datetime, datetime]:
    """The calendar day, ISO week (from Monday) or month in the schedule's zone that holds `now`, as UTC."""
    zone = zone_of(entry["when"]["zone"])
    local = now.astimezone(zone)
    period = entry["budget"]["period"]
    if period == "day":
        a: date = local.date()
        b = a + timedelta(days=1)
    elif period == "week":
        a = local.date() - timedelta(days=local.weekday())
        b = a + timedelta(days=7)
    else:
        a = local.date().replace(day=1)
        b = (a + timedelta(days=32)).replace(day=1)
    return (wall_to_utc(datetime.combine(a, time(0)), zone), wall_to_utc(datetime.combine(b, time(0)), zone))


def period_spend(entry: dict[str, Any], log: Sequence[dict[str, Any]], now: datetime) -> float:
    """The spend of this schedule's fires that started in the current period: an ended fire counts its estimated cost,
    and a fire whose cost is `incomplete`, or that has not ended, counts at the run cap, so an unmeasured run never
    makes the budget look unspent (C1)."""
    start, end = period_bounds(entry, now)
    cap = float(entry.get("run_cost_cap_usd") or 0.0)
    ended = {}
    for e in log:
        if e.get("kind") == "ended" and e.get("fire_id") not in ended:
            ended[e.get("fire_id")] = e
    total = 0.0
    for e in log:
        if e.get("kind") != "started" or not e.get("at") or not start <= _dt(e["at"]) < end:
            continue
        cost = (ended.get(e.get("fire_id")) or {}).get("cost") or {}
        estimated = cost.get("estimated")
        total += cap if cost.get("incomplete") or estimated is None else float(estimated)
    return total


def _budget_skip_raised(entry: dict[str, Any], log: Sequence[dict[str, Any]], now: datetime) -> bool:
    start, end = period_bounds(entry, now)
    return any(e.get("kind") == "skipped" and e.get("reason") == "budget" and e.get("at") and start <= _dt(e["at"]) < end
               for e in log)


# --- failures (SCH-B23, SCH-B9) ----------------------------------------------------------------------------------


def failure_count(log: Sequence[dict[str, Any]]) -> int:
    """Failures in a row: an `ended` with exit 4 or 5 and a `refused` count, an `ended` with exit 0 and a `resumed` reset;
    everything else changes nothing."""
    n = 0
    for e in log:
        kind = e.get("kind")
        if kind == "ended":
            code = e.get("exit")
            if code == 0:
                n = 0
            elif code in (4, 5):
                n += 1
        elif kind == "refused":
            n += 1
        elif kind == "resumed":
            n = 0
    return n


def decide_after(entry: dict[str, Any], log: Sequence[dict[str, Any]], now: datetime) -> Decision:
    """After an `ended` or `refused` event is in the log: pause the schedule when the count reaches the limit."""
    if entry.get("state") != "active":
        return Decision()
    n = failure_count(log)
    if n < int(entry.get("pause_after_failures") or 3):
        return Decision()
    last = next(e for e in reversed(log) if e.get("kind") in ("ended", "refused"))
    cause = f"exit {last.get('exit')} {last.get('outcome') or ''}".strip() if last["kind"] == "ended" else (
        f"refused {last.get('reason') or ''}".strip())
    sid = str(entry["schedule_id"])
    return Decision(events=[{"kind": "paused", "slot": None, "fire_id": None, "reason": "failures", "failures": n}],
                    attention=[{"kind": "schedule_paused", "schedule_id": sid, "thread": last.get("thread"),
                                "cause": cause}], hooks=["schedule_paused"], state="paused")


# --- one tick's decisions (SCH-B21, SCH-B22, SCH-B5) -------------------------------------------------------------


def blocking_count(log: Sequence[dict[str, Any]], live: Sequence[LiveRun], planned: int = 0
                   ) -> tuple[int, LiveRun | None]:
    """The `overlap` skips recorded since the oldest paused live run started, and that run."""
    paused = [r for r in live if r.state == "paused"]
    if not paused:
        return 0, None
    oldest = min(paused, key=lambda r: r.started_at or r.slot)
    mark = _dt(oldest.started_at or oldest.slot)
    n = sum(1 for e in log if e.get("kind") == "skipped" and e.get("reason") == "overlap" and e.get("at")
            and _dt(e["at"]) >= mark)
    return n + planned, oldest


@dataclass
class _State:
    live: int
    pending: str | None
    planned_spend: float = 0.0
    overlap_skips: int = 0


def _route(entry: dict[str, Any], log: Sequence[dict[str, Any]], live: Sequence[LiveRun], slot: datetime,
           now: datetime, st: _State, d: Decision) -> None:
    """Overlap, then budget, then start (a slot skipped behind a live run spends nothing)."""
    sid = str(entry["schedule_id"])
    policy = entry.get("overlap") or "skip"
    limit = int(entry.get("max_live") or 1) if policy == "parallel" else 1
    if st.live >= limit:
        if policy == "queue":
            if st.pending:
                d.events.append(_event("skipped", st.pending, sid, reason="overlap"))
            d.events.append(_event("queued", slot, sid))
            st.pending = _iso(slot)
            return
        d.events.append(_event("skipped", slot, sid, reason="overlap"))
        st.overlap_skips += 1
        count, run = blocking_count(log, live, st.overlap_skips)
        if run is not None and count >= BLOCKING_AT:
            d.attention = [a for a in d.attention if a["kind"] != "blocking_schedule"] + [
                {"kind": "blocking_schedule", "schedule_id": sid, "thread": run.thread, "blocking_schedule": count}]
        return
    budget = entry.get("budget")
    cap = float(entry.get("run_cost_cap_usd") or 0.0)
    if budget and period_spend(entry, log, now) + st.planned_spend + cap > float(budget["cap_usd"]):
        d.events.append(_event("skipped", slot, sid, reason="budget"))
        if not _budget_skip_raised(entry, log, now) and not any(e.get("reason") == "budget" for e in d.events[:-1]):
            d.attention.append({"kind": "schedule_budget", "schedule_id": sid, "period": budget["period"],
                                "cap_usd": budget["cap_usd"]})
        return
    d.start.append(plan_start(entry, slot, log))
    st.live += 1
    st.planned_spend += cap


def decide_slot(entry: dict[str, Any], log: Sequence[dict[str, Any]], live: Sequence[LiveRun], slot: datetime,
                now: datetime) -> Decision:
    """One slot: `skipped` with `paused` when the schedule is not active, else overlap, budget, start."""
    d = Decision()
    if entry.get("state") != "active":
        d.events.append(_event("skipped", slot, str(entry["schedule_id"]), reason="paused"))
        return d
    _route(entry, log, live, slot, now, _State(live=len(live), pending=pending_slot(log)), d)
    return d


def decide_tick(entry: dict[str, Any], log: Sequence[dict[str, Any]], live: Sequence[LiveRun], now: datetime, *,
                tick_s: int = DEFAULT_TICK_S) -> Decision:
    """What one tick does for one schedule: catch-up, then overlap and budget for each slot to fire. A paused, done or
    removed schedule decides nothing (the slots passed while paused are `resume_events`)."""
    d = Decision()
    if entry.get("state") != "active":
        return d
    sid = str(entry["schedule_id"])
    when = _when(entry)
    st = _State(live=len(live), pending=pending_slot(log))
    if entry.get("overlap") == "queue" and st.pending and st.live == 0:  # the run ended: the pending slot starts
        pending = _dt(st.pending)
        st.pending = None
        _route(entry, log, live, pending, now, st, d)
    fire, missed = classify_catch_up(entry, passed_slots(entry, log, now), now, tick_s)
    for s in missed:
        d.events.append(_event("missed", s, sid, reason="catch_up"))
    if when.kind == "once" and missed:
        d.attention.append({"kind": "schedule_missed", "schedule_id": sid, "slot": _iso(missed[0]),
                            "answer": f"schedule fire {sid}"})
    for s in fire:
        _route(entry, log, live, s, now, st, d)
    if when.kind == "once":
        slot = when_slot(when)
        done = _iso(slot) in handled_slots(log) | {e["slot"] for e in d.events if e["kind"] in HANDLED} | {
            s["slot"] for s in d.start}
        if done:
            d.state = "done"
    elif st.pending is None and not next_slots(when, floor_minute(now) + timedelta(minutes=1), 1):
        d.state = "done"  # the recurrence has ended
    return d


def when_slot(when: When) -> datetime:
    """The one slot of a `once`."""
    return wall_to_utc(datetime.fromisoformat(str(when.at)), zone_of(when.zone))


def resume_events(entry: dict[str, Any], log: Sequence[dict[str, Any]], now: datetime, *, catch_up: bool
                  ) -> list[dict[str, Any]]:
    """`schedule resume`: the slots passed while paused are `missed` unless `--catch-up`; `resumed` resets the failures."""
    sid = str(entry["schedule_id"])
    out: list[dict[str, Any]] = []
    paused = [_dt(e["at"]) for e in log if e.get("kind") == "paused" and e.get("at")]
    if not catch_up and paused:
        handled = handled_slots(log)
        for s in slots_between(_when(entry), floor_minute(paused[-1]), floor_minute(now)):
            if s.utc > paused[-1] and _iso(s.utc) not in handled:
                out.append(_event("missed", s.utc, sid, reason="paused"))
    out.append({"kind": "resumed", "slot": None, "fire_id": None, "catch_up": catch_up})
    return out
