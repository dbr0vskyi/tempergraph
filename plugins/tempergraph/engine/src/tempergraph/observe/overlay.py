"""The run overlay on the workflow diagram (OBS-B15, CLI `graph <workflow> --overlay <thread>`).

Counts and engine words only, read from the thread's run log: visits, sessions and repeats per unit, gate
verdicts, money (reported and estimated apart), and how many times each routing edge was taken. No request,
output or feedback text can reach it (SEC-B2). Read-only.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from tempergraph.observe import report as rep
from tempergraph.run.events import records, route_unit
from tempergraph.store.layout import run_dir


def overlay(root: Path, workflow: str, task: str) -> dict[str, Any]:
    recs = records(run_dir(root, workflow, task) / "run.jsonl")
    t = rep.fold(recs)
    units: dict[str, dict[str, Any]] = {}
    visits: dict[str, int] = defaultdict(int)
    verdicts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    edges: dict[tuple[str, str, str], int] = defaultdict(int)
    for r in recs:
        unit = r.get("unit")
        if r.get("kind") == "unit_entered" and unit:
            visits[unit] = max(visits[unit], int(r.get("visit") or 1))
        elif r.get("kind") == "gate" and unit:
            if r.get("verdict"):
                verdicts[unit][str(r["verdict"])] += 1
            dst = route_unit(r.get("route_target"))
            if dst is not None:
                edges[(unit, dst, str(r.get("token") or ""))] += 1
    by_unit: dict[str, list[rep.Session]] = defaultdict(list)
    for s in (t.sessions if t else []):
        by_unit[s.unit].append(s)
    for name in sorted(set(visits) | set(by_unit) | set(verdicts)):
        ss = by_unit.get(name, [])
        units[name] = {"visits": visits.get(name, 0), "sessions": len(ss),
                       "repeats": sum(1 for s in ss if s.cause is not None),
                       "verdicts": dict(sorted(verdicts[name].items())), "cost": rep._money(ss)}
    return {"thread_id": f"{workflow}/{task}", "units": units,
            "edges": [[a, b, tok, n] for (a, b, tok), n in sorted(edges.items())],
            "exit_code": (t.exit or {}).get("exit_code") if t else None}
