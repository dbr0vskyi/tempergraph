"""The loop's summary (SIL-B22): what one loop child left, short enough to show beside what waits on a person.

One `loop_summary` record per ticket in the thread's `loop.jsonl`: the findings the thread holds, the issues this
child opened or commented on, and the three kept review observations with the highest confidence, as category, unit
and confidence and never a note. `attention` and the detail document read it (CLI-B20, RDD-B7).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tempergraph.improve import digest as digestmod
from tempergraph.improve.record import _jsonl, read_findings
from tempergraph.store.layout import now_iso, run_dir

TOP = 3
FILED_OPS = frozenset({"filed", "commented"})


def _top(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for r in records:  # plan order: the order the reviews ran in
        if r.get("kind") != "review_done":
            continue
        unit = digestmod.parse_key(str(r.get("session_key")))[0]
        for o in r.get("observations") or []:
            if o.get("check") == "kept":
                conf = o.get("confidence")
                kept.append({"category": o.get("category"), "unit": unit,
                             "confidence": float(conf) if isinstance(conf, int | float) else None})
    kept.sort(key=lambda o: -(o["confidence"] if o["confidence"] is not None else -1.0))  # stable: ties keep plan order
    return kept[:TOP]


def build(root: Path, workflow: str, task_id: str, results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The `loop_summary` record of the child that has just handled the thread's ticket."""
    records = _jsonl(run_dir(root, workflow, task_id) / "loop.jsonl")
    return {"ts": now_iso(), "kind": "loop_summary", "thread": f"{workflow}/{task_id}",
            "recorded": len(read_findings(root, workflow, task_id)),
            "filed": sum(1 for r in results if r.get("op") in FILED_OPS), "top": _top(records)}


def thread_newest(root: Path, workflow: str, task_id: str) -> dict[str, Any] | None:
    """The newest `loop_summary` record of one thread, or None until a loop child has ended."""
    found = [r for r in _jsonl(run_dir(root, workflow, task_id) / "loop.jsonl") if r.get("kind") == "loop_summary"]
    return max(found, key=lambda r: str(r.get("ts") or "")) if found else None


def newest(root: Path, workflow: str, task_id: str | None = None) -> dict[str, Any] | None:
    """The newest summary of a thread, or of the workflow when no thread is named (the latest of its threads)."""
    if task_id is not None:
        return thread_newest(root, workflow, task_id)
    base = root / "runs" / workflow
    found = [s for d in (sorted(base.iterdir()) if base.is_dir() else ()) if d.is_dir()
             for s in [thread_newest(root, workflow, d.name)] if s is not None]
    return max(found, key=lambda r: str(r.get("ts") or "")) if found else None
