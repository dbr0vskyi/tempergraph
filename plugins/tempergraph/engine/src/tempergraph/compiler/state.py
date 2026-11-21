"""Run state: JSON one level deep, merged by reducers (CMP §2.3, DUR contract C7).

Channels written by units that can run in one superstep are keyed by unit. One reducer deletes: a key
written as ``None`` is removed, which is how a trip back clears artifacts, values, facts and judgements.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict


def merge_units(old: dict[str, Any] | None, new: dict[str, Any] | None) -> dict[str, Any]:
    """Two-level merge: ``{unit: None}`` deletes a unit; ``{unit: {key: None}}`` deletes a key."""
    out: dict[str, Any] = dict(old or {})
    for unit, val in (new or {}).items():
        if val is None:
            out.pop(unit, None)
        elif isinstance(val, dict) and isinstance(out.get(unit), dict):
            merged = dict(out[unit])
            for k, v in val.items():
                if v is None:
                    merged.pop(k, None)
                else:
                    merged[k] = v
            out[unit] = merged
        else:
            out[unit] = val
    return out


def merge_run(old: dict[str, Any] | None, new: dict[str, Any] | None) -> dict[str, Any]:
    """`merge_units` for the run-level facts, safe for two branches of a parallel block writing in one superstep:
    the path's units are a union in arrival order, and a cost total is added as the delta its writer made on
    the total it read (`_base`), so neither branch's sessions are lost."""
    new = dict(new or {})
    out = dict(old or {})
    path, cost = new.pop("path", None), new.pop("cost", None)
    if isinstance(path, dict) and isinstance(path.get("units"), list):
        have = list((out.get("path") or {}).get("units") or [])
        out["path"] = {**(out.get("path") or {}), **path, "units": have + [u for u in path["units"] if u not in have]}
    elif path is not None:
        new["path"] = path
    if isinstance(cost, dict):
        base = cost.get("_base")
        cost = {k: v for k, v in cost.items() if k != "_base"}
        held = (out.get("cost") or {}).get("counters")
        if isinstance(base, dict) and isinstance(held, dict) and held != base:
            from tempergraph.run.log import CostTotals

            t = CostTotals.from_json(out.get("cost"))
            for k, v in (cost.get("counters") or {}).items():
                setattr(t, k, getattr(t, k) + v - (base.get(k) or 0))
            cost = t.to_json()
        out["cost"] = {k: v for k, v in cost.items() if v is not None}  # an absent figure is an absent key
    return merge_units(out, new)


def replace(old: Any, new: Any) -> Any:
    return new if new is not None else old


class RunState(TypedDict, total=False):
    request: Annotated[dict[str, Any], replace]  # {task_id, inputs, text_ref, chars}
    workspace: Annotated[dict[str, Any], replace]  # WorkspaceRecord
    artifacts: Annotated[dict[str, Any], merge_units]  # unit -> key -> pointer
    values: Annotated[dict[str, Any], merge_units]  # unit -> key -> value
    facts: Annotated[dict[str, Any], merge_units]  # unit -> key -> str
    attempts: Annotated[dict[str, Any], merge_units]  # unit -> {attempt, visit, last result summary}
    judgements: Annotated[dict[str, Any], merge_units]  # unit -> outcome of the judge node
    route: Annotated[dict[str, Any], merge_units]  # unit -> {token, node, ...}
    pause: Annotated[dict[str, Any], merge_units]  # unit -> pause payload
    feedback: Annotated[dict[str, Any], merge_units]  # unit -> one-time feedback for the next attempt
    counters: Annotated[dict[str, Any], merge_units]  # unit -> budget counters
    visits: Annotated[dict[str, Any], merge_units]  # unit -> {visit, reason, from}
    maps: Annotated[dict[str, Any], merge_units]  # map unit -> {visit, items, passed, attempts} (MAP §2.2)
    rulings: Annotated[dict[str, Any], merge_units]  # id -> ruling (own reducer, never cleared by a trip back)
    finalized: Annotated[dict[str, Any], replace]
    run: Annotated[dict[str, Any], merge_run]  # run-level facts: {"stopped": {...}, "path": [...]}
