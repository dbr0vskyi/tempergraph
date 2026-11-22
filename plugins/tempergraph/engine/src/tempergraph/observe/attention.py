"""`attention` (CLI-B6, AC-5): everything waiting on a person, oldest first, with the command that answers it.

Built from the status document of each state root and the last `pause` record of each paused thread; reads only
and calls no model (OVR-B15). Orchestration and schedule items join when those features ship (release 2).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tempergraph.contracts import WorkflowSpec
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
        if row.get("state") != "paused" or not gates:
            continue
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
                        "state_root": str(state_root)})
    return out


def attention(roots: list[Path], specs: Mapping[str, WorkflowSpec], now: float | None = None) -> dict[str, Any]:
    found: list[dict[str, Any]] = []
    missing = []
    for root in roots:
        if not root.is_dir():
            missing.append(str(root))
            continue
        found += items(root, specs, now)
    found.sort(key=lambda i: (i["waiting_since"] is None, i["waiting_since"] or ""))
    return {"schema_version": 1, "items": found, "missing_roots": missing}


def line(i: dict[str, Any]) -> str:
    age = i.get("age_s")
    when = "?" if age is None else f"{int(age // 3600)}h{int(age % 3600 // 60):02d}m" if age >= 3600 \
        else f"{int(age // 60)}m"
    where = f"{i['unit']}" + (f"[{i['item']}]" if i.get("item") else "")
    return f"{when:>6}  {i.get('alias') or i['thread_id']}  {where}  {i['kind']}: {i['reason']}\n        {i['command']}"
