"""`attention` (CLI-B6, AC-5): everything waiting on a person, oldest first, with the command that answers it.

Built from the status document of each state root and the last `pause` record of each paused thread, and from the
schedules of the home store (the items of TCK-B24 and `trigger_stale`, TCK-B7); reads only and calls no model (OVR-B15).
Orchestration items join with orchestration (release 4).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tempergraph.contracts import WorkflowSpec
from tempergraph.durability import carry as carrymod
from tempergraph.durability.status import status
from tempergraph.run.events import records
from tempergraph.store.layout import run_dir


def _since(text: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def items(state_root: Path, specs: Mapping[str, WorkflowSpec], now: float | None = None) -> list[dict[str, Any]]:
    now = datetime.now(UTC).timestamp() if now is None else now
    out: list[dict[str, Any]] = []
    for row in status(state_root, specs)["threads"]:
        gates = row.get("pending_gates") or []
        if row.get("state") == "paused" and gates:
            wf, _, task = str(row["thread_id"]).partition("/")
            pauses: dict[str, dict[str, Any]] = {}
            for r in records(run_dir(state_root, wf, task) / "run.jsonl"):
                if r.get("kind") == "pause" and r.get("unit"):
                    pauses[str(r["unit"])] = r
            for g in gates:
                p = pauses.get(str(g.get("unit"))) or {}
                since = _since(p.get("ts"))
                reason = p.get("question") or p.get("reason") or g.get("kind")
                out.append({"thread_id": row["thread_id"], "workflow": row.get("workflow"), "alias": row.get("alias"),
                            "unit": g.get("unit"), "item": g.get("item"), "kind": g.get("kind"),
                            "waiting_since": p.get("ts"), "age_s": round(now - since, 1) if since else None,
                            "reason": reason, "decisions": p.get("decisions"), "command": g.get("resume"),
                            "state_root": str(state_root),
                            **({"schedule": row["schedule"]} if row.get("schedule") else {})})  # TCK-B4: a scheduled run's pause
        elif row.get("carry") == "delete_failed":  # CAR-B11: remote refused the state-branch deletion at finish
            wf, _, task = str(row["thread_id"]).partition("/")
            branch = carrymod.branch_name(wf, task)
            out.append({"thread_id": row["thread_id"], "workflow": row.get("workflow"), "alias": row.get("alias"),
                        "unit": None, "item": None, "kind": "carry_delete_failed",
                        "waiting_since": None, "age_s": None,
                        "reason": f"remote refused deletion of {branch}",
                        "decisions": None, "command": f"tempergraph carry drop {wf} {task}",
                        "state_root": str(state_root)})
    return out


STALE_INTERVALS = 3  # TCK-B7: a heartbeat older than this many tick intervals is stale
BLOCKING_AT = 3  # SCH-B22: overlap skips behind one unfinished fire


def _item(kind: str, sid: str, reason: str, command: str, at: Any, now: float, **extra: Any) -> dict[str, Any]:
    since = _since(at)
    return {"thread_id": None, "workflow": None, "alias": None, "unit": None, "item": None, "kind": kind,
            "schedule_id": sid, "waiting_since": at, "age_s": round(now - since, 1) if since else None, "reason": reason,
            "decisions": None, "command": command, "state_root": None, **extra}


def _last(log: list[dict[str, Any]], kind: str, reason: str | None = None) -> dict[str, Any] | None:
    return next((e for e in reversed(log) if e.get("kind") == kind and (reason is None or e.get("reason") == reason)), None)


def trigger_stale(home: Path | None = None, now: float | None = None) -> dict[str, Any] | None:
    """TCK-B7: active schedules and a `last_tick_at` older than three intervals; reads only."""
    from tempergraph.schedule import store, tick

    now = datetime.now(UTC).timestamp() if now is None else now
    beat = tick.read_heartbeat(home)
    if not beat or not any(e.get("state") == "active" for e in store.list_entries(home)):
        return None
    last = _since(beat.get("last_tick_at"))
    interval = int(beat.get("interval_s") or 60)
    if last is None or now - last <= STALE_INTERVALS * interval:
        return None
    return {"kind": "trigger_stale", "age_s": round(now - last, 1), "interval_s": interval, "last_tick_at": beat.get("last_tick_at"),
            "command": "tempergraph schedule trigger status"}


def schedule_items(home: Path | None = None, now: float | None = None) -> list[dict[str, Any]]:
    """TCK-B24: `schedule_missed`, `schedule_paused`, `schedule_budget`, `schedule_refused` and `blocking_schedule`,
    read from the schedules' entries and fire logs; each names its schedule and the command that answers it."""
    from tempergraph.schedule import store

    now = datetime.now(UTC).timestamp() if now is None else now
    out: list[dict[str, Any]] = []
    for entry in store.list_entries(home):
        sid, state = str(entry["schedule_id"]), entry.get("state")
        if state == "removed":
            continue
        log = store.read_log(sid, home)
        if state == "paused" and (p := _last(log, "paused", "failures")):
            out.append(_item("schedule_paused", sid, f"paused after {p.get('failures')} failures",
                             f"tempergraph schedule resume {sid}", p.get("at"), now))
        if (entry.get("when") or {}).get("kind") == "once" and (m := _last(log, "missed")):
            out.append(_item("schedule_missed", sid, f"the one-time slot {m.get('slot')} passed unstarted",
                             f"tempergraph schedule fire {sid}", m.get("at"), now))
        if b := _last(log, "skipped", "budget"):
            out.append(_item("schedule_budget", sid, f"the {(entry.get('budget') or {}).get('period')} budget is spent",
                             f"tempergraph schedule edit {sid} --budget <period>:<usd>", b.get("at"), now))
        handled = [e for e in log if e.get("kind") in ("started", "skipped", "missed", "refused")]
        if handled and handled[-1].get("kind") == "refused":
            r = handled[-1]
            who = f" ({r['executor']})" if r.get("executor") else ""
            out.append(_item("schedule_refused", sid, f"{r.get('reason')}{who}: {r.get('message') or 'the fire was refused'}",
                             f"tempergraph schedule show {sid}", r.get("at"), now, executor=r.get("executor")))
        ended = {e.get("fire_id") for e in log if e.get("kind") == "ended"}
        open_fire = next((e for e in reversed(log) if e.get("kind") == "started" and e.get("fire_id") not in ended), None)
        if open_fire is not None:
            n = sum(1 for e in log if e.get("kind") == "skipped" and e.get("reason") == "overlap"
                    and str(e.get("at") or "") >= str(open_fire.get("at") or ""))
            if n >= BLOCKING_AT:
                out.append(_item("blocking_schedule", sid, f"{n} slots were skipped behind {open_fire.get('thread')}",
                                 f"tempergraph status {open_fire.get('thread')}", open_fire.get("at"), now,
                                 blocking_schedule=n))
    return out


def loop_summaries(state_root: Path) -> list[dict[str, Any]]:
    """CLI-B20: for each workflow, its newest `loop_summary` when it holds a finding, an observation or a failed review
    (`review_failed`, the failed reviews by error class; `{}` in an older summary). Reads only."""
    from tempergraph.improve import loop_summary

    out: list[dict[str, Any]] = []
    base = state_root / "runs"
    for wdir in sorted(base.iterdir()) if base.is_dir() else ():
        s = loop_summary.newest(state_root, wdir.name) if wdir.is_dir() else None
        held = s.get("review_failed") if s is not None else None
        failed = {str(k): int(v) for k, v in held.items()} if isinstance(held, dict) else {}
        if s is None or not (s.get("recorded") or s.get("top") or failed):
            continue
        thread = str(s.get("thread") or "")
        out.append({"workflow": wdir.name, "thread": thread, "at": s.get("ts"), "recorded": int(s.get("recorded") or 0),
                    "filed": int(s.get("filed") or 0), "top": list(s.get("top") or []), "review_failed": failed,
                    "command": f"tempergraph improve review show {thread}", "state_root": str(state_root)})
    return out


def attention(roots: list[Path], specs: Mapping[str, WorkflowSpec], now: float | None = None,
              home: Path | None = None) -> dict[str, Any]:
    found: list[dict[str, Any]] = []
    loop: list[dict[str, Any]] = []
    missing = []
    for root in roots:
        if not root.is_dir():
            missing.append(str(root))
            continue
        found += items(root, specs, now)
        loop += loop_summaries(root)
    found += schedule_items(home, now)
    found.sort(key=lambda i: (i["waiting_since"] is None, i["waiting_since"] or ""))
    loop.sort(key=lambda s: str(s.get("at") or ""), reverse=True)  # newest first
    doc: dict[str, Any] = {"schema_version": 1, "items": found, "loop": loop, "missing_roots": missing}
    stale = trigger_stale(home, now)
    if stale:
        doc["trigger_stale"] = stale  # TCK-B7
    return doc


def loop_line(s: dict[str, Any]) -> str:
    """The text form of one summary: the counts, the failed reviews by error class when any (`16 reviews failed:
    usage_limit 16`), then each observation, then the command (no note text)."""
    rows = "".join(f"\n        {o.get('category')}  {o.get('unit')}  {o.get('confidence')}" for o in s.get("top") or [])
    failed = s.get("review_failed") or {}
    lost = f", {sum(failed.values())} reviews failed: " + ", ".join(f"{k} {n}" for k, n in sorted(failed.items())) \
        if failed else ""
    return f"  loop  {s['thread']}: {s['recorded']} recorded, {s['filed']} filed{lost}{rows}\n        {s['command']}"


def stale_line(s: dict[str, Any]) -> str:
    return (f"  trigger_stale  no tick for {int(s['age_s'] // 60)}m (interval {s['interval_s']}s)\n"
            f"        {s['command']}")


def line(i: dict[str, Any]) -> str:
    age = i.get("age_s")
    when = "?" if age is None else f"{int(age // 3600)}h{int(age % 3600 // 60):02d}m" if age >= 3600 \
        else f"{int(age // 60)}m"
    if i.get("schedule_id") and not i.get("unit"):  # a schedule item (TCK-B24)
        return f"{when:>6}  {i['kind']}  {i['schedule_id']}: {i['reason']}\n        {i['command']}"
    where = f"{i['unit']}" + (f"[{i['item']}]" if i.get("item") else "")
    sched = f"  (schedule {i['schedule']['schedule_id']})" if i.get("schedule") else ""
    return f"{when:>6}  {i.get('alias') or i['thread_id']}  {where}  {i['kind']}: {i['reason']}{sched}\n        {i['command']}"
