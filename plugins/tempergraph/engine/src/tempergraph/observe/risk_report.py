"""`report --risk <workflow>`: judge attempts per gate and risk level (JRK-B10). Figures only.

Reads the run logs: a `judge_risk` record names the level that graded an attempt, the gate's decision on the
same attempt gives PROCEED (no blocker) or RETRY, and the judge's sessions give its cost. In shadow mode the same figures
are also shown by the level the rule would have chosen.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from tempergraph.observe.report import Money


def _records(root: Path, workflow: str) -> Iterator[list[dict[str, Any]]]:
    for log in sorted((root / "runs" / workflow).glob("*/run.jsonl")):
        try:
            lines = log.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        rows = []
        for ln in lines:
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if isinstance(r, dict):
                rows.append(r)
        yield rows


def _usd(m: dict[str, Any]) -> float | None:
    """Reported money when every session reported it, else the estimate; never a sum of the two (OBS-B10 to OBS-B13)."""
    if m["sessions"] and m["reported_sessions"] == m["sessions"]:
        return float(m["reported_usd"])
    if m["sessions"] and m["estimated_sessions"] == m["sessions"]:
        return float(m["estimated_usd"])
    return None


class _Cell:
    def __init__(self) -> None:
        self.attempts = self.proceed = self.retry = 0
        self.money = Money()
        self.by: dict[str, int] = defaultdict(int)

    def row(self, gate: str, level: str) -> dict[str, Any]:
        decided = self.proceed + self.retry
        return {"gate": gate, "level": level, "attempts": self.attempts,
                "proceed_rate": round(self.proceed / decided, 4) if decided else None,
                "retry_rate": round(self.retry / decided, 4) if decided else None,
                "judge_cost_usd": _usd(self.money.to_json()), "chosen_by": dict(self.by)}


def report(root: Path, workflow: str) -> dict[str, Any]:
    cells: dict[tuple[str, str], _Cell] = defaultdict(_Cell)
    would: dict[tuple[str, str], _Cell] = defaultdict(_Cell)
    shadow = False
    for rows in _records(root, workflow):
        level_of: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
        latest: dict[str, dict[str, Any]] = {}  # the level a unit's judge sessions belong to
        for r in rows:
            kind, key = r.get("kind"), (r.get("unit"), r.get("item"), r.get("attempt"))
            if kind == "judge_risk":
                level_of[key] = latest[str(r.get("unit"))] = r
                shadow = shadow or r.get("chosen_by") == "shadow"
                for table, name in ((cells, r.get("level")), (would, r.get("would_choose"))):
                    c = table[(str(r.get("unit")), str(name))]
                    c.attempts += 1
                    c.by[str(r.get("chosen_by"))] += 1
            elif kind == "judgement" and key in level_of:
                risk, blocked = level_of[key], bool(r.get("blockers"))
                for table, name in ((cells, risk.get("level")), (would, risk.get("would_choose"))):
                    c = table[(str(r.get("unit")), str(name))]
                    c.proceed += 0 if blocked else 1
                    c.retry += 1 if blocked else 0
            elif kind == "agent_run" and ".judge" in str(r.get("session_key")):
                unit = next((u for u in latest if str(r.get("session_key")).startswith(u + ".")), None)
                if unit is not None:
                    risk = latest[unit]
                    for table, name in ((cells, risk.get("level")), (would, risk.get("would_choose"))):
                        table[(unit, str(name))].money.add(r.get("usage") or {})
    doc: dict[str, Any] = {"schema_version": 1, "workflow": workflow,
                           "rows": [c.row(g, lv) for (g, lv), c in sorted(cells.items())]}
    if shadow:
        doc["would_choose"] = [c.row(g, lv) for (g, lv), c in sorted(would.items())]
    return doc


def _table(rows: list[dict[str, Any]]) -> list[str]:
    out = [f"{'gate':<20} {'level':<12} {'attempts':>8} {'proceed':>8} {'retry':>8} {'judge cost':>11}"]
    for r in rows:
        rate = lambda v: "-" if v is None else f"{v:.0%}"  # noqa: E731
        cost = "-" if r["judge_cost_usd"] is None else f"${r['judge_cost_usd']:.2f}"
        out.append(f"{r['gate']:<20} {r['level']:<12} {r['attempts']:>8} {rate(r['proceed_rate']):>8} "
                   f"{rate(r['retry_rate']):>8} {cost:>11}")
    return out


def text(doc: dict[str, Any]) -> str:
    if not doc["rows"]:
        return f"{doc['workflow']}: no judge ran under a risk rule\n"
    lines = [f"Judge risk levels of {doc['workflow']}", *_table(doc["rows"])]
    if doc.get("would_choose"):
        lines += ["", "By the level the rule would choose (shadow mode)", *_table(doc["would_choose"])]
    return "\n".join(lines) + "\n"
