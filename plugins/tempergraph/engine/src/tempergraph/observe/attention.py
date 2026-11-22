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


def loop_summaries(state_root: Path) -> list[dict[str, Any]]:
    """CLI-B20: for each workflow, its newest `loop_summary` when it holds a finding or an observation. Reads only."""
    from tempergraph.improve import loop_summary

    out: list[dict[str, Any]] = []
    base = state_root / "runs"
    for wdir in sorted(base.iterdir()) if base.is_dir() else ():
        s = loop_summary.newest(state_root, wdir.name) if wdir.is_dir() else None
        if s is None or not (s.get("recorded") or s.get("top")):
            continue
        thread = str(s.get("thread") or "")
        out.append({"workflow": wdir.name, "thread": thread, "at": s.get("ts"), "recorded": int(s.get("recorded") or 0),
                    "filed": int(s.get("filed") or 0), "top": list(s.get("top") or []),
                    "command": f"tempergraph improve review show {thread}", "state_root": str(state_root)})
    return out


def attention(roots: list[Path], specs: Mapping[str, WorkflowSpec], now: float | None = None) -> dict[str, Any]:
    found: list[dict[str, Any]] = []
    loop: list[dict[str, Any]] = []
    missing = []
    for root in roots:
        if not root.is_dir():
            missing.append(str(root))
            continue
        found += items(root, specs, now)
        loop += loop_summaries(root)
    found.sort(key=lambda i: (i["waiting_since"] is None, i["waiting_since"] or ""))
    loop.sort(key=lambda s: str(s.get("at") or ""), reverse=True)  # newest first
    return {"schema_version": 1, "items": found, "loop": loop, "missing_roots": missing}


def loop_line(s: dict[str, Any]) -> str:
    """The text form of one summary: the counts, then each observation, then the command (no note text)."""
    rows = "".join(f"\n        {o.get('category')}  {o.get('unit')}  {o.get('confidence')}" for o in s.get("top") or [])
    return f"  loop  {s['thread']}: {s['recorded']} recorded, {s['filed']} filed{rows}\n        {s['command']}"


def line(i: dict[str, Any]) -> str:
    age = i.get("age_s")
    when = "?" if age is None else f"{int(age // 3600)}h{int(age % 3600 // 60):02d}m" if age >= 3600 \
        else f"{int(age // 60)}m"
    where = f"{i['unit']}" + (f"[{i['item']}]" if i.get("item") else "")
    return f"{when:>6}  {i.get('alias') or i['thread_id']}  {where}  {i['kind']}: {i['reason']}\n        {i['command']}"
