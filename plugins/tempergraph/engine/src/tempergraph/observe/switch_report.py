"""`report --switch <workflow>/<switch>`: finished runs per arm and zone (CXR-B13, SWM-B5). Figures only.

Re-armed runs are shown apart and never enter a cell's figures; a cell under five runs is marked.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from tempergraph.observe.report import Money, Thread, threads

MIN_RUNS = 5
TOO_FEW = "too few to compare"


def _seconds(t: Thread) -> float | None:
    try:
        a = datetime.fromisoformat(str(t.started_at).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str((t.exit or {}).get("ts")).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (b - a).total_seconds()


def _usd(m: dict[str, Any]) -> float | None:
    """Reported money when every session reported it, else the estimate; never a sum of the two (OBS-B10 to OBS-B13)."""
    if m["sessions"] and m["reported_sessions"] == m["sessions"]:
        return float(m["reported_usd"])
    if m["sessions"] and m["estimated_sessions"] == m["sessions"]:
        return float(m["estimated_usd"])
    return None


def _first_pass(t: Thread, units: set[str] | None) -> tuple[int, int]:
    """Gates that passed on their first decision, of the gates between the switch and `joins_at`."""
    first: dict[tuple[str, Any], str] = {}
    for g in t.gates:
        key = (str(g.get("unit")), g.get("item"))
        if (units is None or key[0] in units) and key not in first:
            first[key] = str(g.get("verdict"))
    return sum(1 for v in first.values() if v == "PROCEED"), len(first)


def _cell(ts: list[Thread], units: set[str] | None, size: str | None, first: dict[str, dict[str, Any]]
          ) -> dict[str, Any]:
    money = Money()
    passed = gates = 0
    sized = 0.0
    walls: list[float] = []
    outcomes: dict[str, int] = defaultdict(int)
    for t in ts:
        for s in t.sessions:
            money.add(s.usage)
        p, n = _first_pass(t, units)
        passed, gates = passed + p, gates + n
        v = (first[t.thread_id].get("measures") or {}).get(size) if size else None
        if isinstance(v, int | float) and not isinstance(v, bool):
            sized += float(v)
        w = _seconds(t)
        if w is not None:
            walls.append(w)
        outcomes[str((t.outcome or {}).get("verdict") or f"exit:{(t.exit or {}).get('reason')}")] += 1
    m = money.to_json()
    usd = _usd(m)
    done = sum(1 for t in ts if (t.exit or {}).get("exit_code") == 0)
    return {"runs": len(ts), "completed": done, "comparable": len(ts) >= MIN_RUNS,
            "first_pass_yield": round(passed / gates, 3) if gates else None, "cost": m,
            "cost_per_completed_run_usd": round(usd / done, 6) if usd is not None and done else None,
            "cost_per_size_usd": round(usd / sized, 6) if usd is not None and sized else None,
            "wall_s": round(sum(walls) / len(walls), 3) if walls else None, "outcomes": dict(sorted(outcomes.items()))}


def report(root: Path, workflow: str, switch: str, since: datetime | None = None, *,
           units: Iterable[str] | None = None, size: str | None = None, version: str | None = None
           ) -> dict[str, Any]:
    """Per arm and zone, for finished runs of one workflow version (the latest seen unless `version` is given).
    `units` are the units between the switch and `joins_at`; without them every gate counts."""
    finished = [t for t in threads(root, since) if t.workflow == workflow and t.exit is not None
                and any(r.get("unit") == switch for r in t.routes)]
    versions = sorted({str(t.version) for t in finished if t.version is not None})
    if version is None and versions:
        version = max(versions, key=lambda v: max(str(t.started_at) for t in finished if str(t.version) == v))
    if version is not None:
        finished = [t for t in finished if str(t.version) == version]
    between = set(units) if units is not None else None
    first = {t.thread_id: next(r for r in t.routes if r.get("unit") == switch) for t in finished}
    rearmed = {t.thread_id for t in finished
               if any(r.get("unit") == switch and r.get("chosen_by") == "rearm" for r in t.routes)}
    cells: dict[tuple[str, str, str, bool], list[Thread]] = defaultdict(list)
    started: dict[str, int] = defaultdict(int)
    for t in finished:
        r = first[t.thread_id]
        started[str(r.get("arm"))] += 1
        if t.thread_id not in rearmed:
            cells[(str(r.get("arm")), str(r.get("zone") or "-"), str(r.get("would_choose") or "-"),
                   bool(r.get("shadow")))].append(t)
    rows = [{"arm": arm, "zone": zone, "would_choose": would, "shadow": shadow, **_cell(ts, between, size, first)}
            for (arm, zone, would, shadow), ts in sorted(cells.items())]
    apart: dict[str, list[Thread]] = defaultdict(list)
    for t in finished:
        if t.thread_id in rearmed:
            apart[str(first[t.thread_id].get("arm"))].append(t)
    return {"schema_version": 1, "workflow": workflow, "switch": switch, "version": version, "versions": versions,
            "runs": len(finished), "size": size, "min_runs": MIN_RUNS, "cells": rows,
            "rearmed": [{"from_arm": arm, **_cell(ts, between, size, first),
                         "rearm_rate": round(len(ts) / started[arm], 3)} for arm, ts in sorted(apart.items())],
            "rearm_rate": {arm: round(len(apart.get(arm, [])) / n, 3) for arm, n in sorted(started.items())}}


def _figures(c: dict[str, Any]) -> str:
    if not c["comparable"]:
        return f"{c['runs']} runs, {TOO_FEW}"
    parts = [f"{c['runs']} runs"]
    if c["first_pass_yield"] is not None:
        parts.append(f"first pass {c['first_pass_yield']:.0%}")
    if c["cost_per_completed_run_usd"] is not None:
        parts.append(f"${c['cost_per_completed_run_usd']:.2f} per completed run")
    if c["cost_per_size_usd"] is not None:
        parts.append(f"${c['cost_per_size_usd']:.2f} per unit of size")
    if c["wall_s"] is not None:
        parts.append(f"{c['wall_s']:.0f} s")
    parts.append("outcome " + ", ".join(f"{k} {n}" for k, n in c["outcomes"].items()))
    return ", ".join(parts)


def text(doc: dict[str, Any]) -> str:
    lines = [f"Switch {doc['workflow']}/{doc['switch']}, version {doc['version'] or 'unknown'}: "
             f"{doc['runs']} finished runs"]
    for c in doc["cells"]:
        would = f", would choose {c['would_choose']}" if c["shadow"] else ""
        lines.append(f"  {c['arm']} / {c['zone']}{would}: {_figures(c)}")
    for c in doc["rearmed"]:
        lines.append(f"  re-armed from {c['from_arm']} ({c['rearm_rate']:.0%} of its runs): {_figures(c)}")
    if not doc["cells"] and not doc["rearmed"]:
        lines.append("  no finished run reached this switch")
    return "\n".join(lines) + "\n"
