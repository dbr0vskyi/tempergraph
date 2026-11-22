"""The supervision record of a run, built at every `run_exit` for the thread so far (SUP-B10, SUP-B11).

Read from the thread's intervention rows in the ledger and its `run_started` records. Cost fields and
`observations` come from the supervision journal (SCO-B15, T7.6) and stay null until then: unmeasured is
never zero.
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

DECIDERS = ("person", "agent", "unknown", "pipeline", "orchestrator", "scheduler", "engine")
CLASSES = ("designed", "rescue", "steer", "engine")


def _rows(path: Path, kind: str, **match: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("kind") == kind and all(r.get(k) == v for k, v in match.items()):
            out.append(r)
    return out


def build(ledger: Path, run_log: Path, thread: str, units_reached: Sequence[str]) -> dict[str, Any]:
    rows = _rows(ledger, "intervention", thread_id=thread)
    starts = _rows(run_log, "run_started")
    touches = {c: {d: 0 for d in DECIDERS} for c in CLASSES}
    rescue_by_pause: dict[str, int] = {}
    relayed = {"turn_named": 0, "turn_only": 0, "claimed": 0}
    waits: dict[str, float] = {}
    per_pause: list[float] = []
    undesigned_units: set[str] = set()
    undesigned_by: set[str] = set()
    designed_by: set[str] = set()
    unknown = sum(1 for s in starts if (s.get("caller") or {}).get("kind") == "unknown")
    sessions: set[tuple[str, str]] = set()
    for s in starts:
        c = s.get("caller") or {}
        if c.get("host_session"):
            sessions.add((str(c.get("host")), str(c["host_session"])))
    for r in rows:
        c = r.get("caller") or {}
        by = str(c.get("decided_by") or c.get("kind") or "unknown")
        by = by if by in DECIDERS else "unknown"
        if c.get("kind") == "unknown":
            unknown += 1
        if c.get("relay") in relayed:
            relayed[str(c["relay"])] += 1
        if c.get("host_session"):
            sessions.add((str(c.get("host")), str(c["host_session"])))
        if r.get("wait_s") is not None:
            waits[by] = round(waits.get(by, 0.0) + float(r["wait_s"]), 1)
            per_pause.append(float(r["wait_s"]))
        for t in r.get("touches") or []:
            cls = str(t.get("class"))
            if cls not in touches:
                continue
            touches[cls][by] += 1
            if cls == "rescue":
                kind = str(r.get("pause_kind") or "escalation")
                rescue_by_pause[kind] = rescue_by_pause.get(kind, 0) + 1
            if cls in ("rescue", "steer"):
                undesigned_units.add(str(r.get("unit") or ""))
                undesigned_by.add(by)
            if cls == "designed":
                designed_by.add(by)
    total = {c: sum(v.values()) for c, v in touches.items()}
    undesigned = total["rescue"] + total["steer"]
    reached = [u for u in dict.fromkeys(units_reached) if u]
    if reached and undesigned and len(undesigned_units & set(reached)) * 2 >= len(reached):
        level = "operator"
    elif total["steer"]:
        level = "collaborator"
    elif total["rescue"]:
        level = "consultant"
    elif total["designed"]:
        level = "approver"
    else:
        level = "observer"
    if level in ("observer", "approver"):
        level_by = "none"
    else:
        level_by = next(iter(undesigned_by)) if len(undesigned_by) == 1 else "mixed"
    rec: dict[str, Any] = {
        "touches": {**touches, "rescue_by_pause": rescue_by_pause}, "undesigned": undesigned, "relayed": relayed,
        "agent_own_rescues": touches["rescue"]["agent"], "wait_s": waits, "person_wait_s": waits.get("person", 0.0),
        "latency_s": {"median": statistics.median(per_pause), "max": max(per_pause)} if per_pause else None,
        "observations": None, "supervisors": {"sessions": len(sessions), "hosts": sorted({h for h, _ in sessions})},
        "callers_unknown": unknown, "supervision_cost": None, "supervision_share": None,
        "level": level, "level_by": level_by}
    if level == "approver" and designed_by == {"agent"}:
        rec["designed_by"] = "agent"
    return rec


def path_units(values: Mapping[str, Any]) -> list[str]:
    return list(((values.get("run") or {}).get("path") or {}).get("units") or [])
