"""Run state: JSON one level deep, merged by reducers (CMP-B17, DUR OVR-B9).

Channels written by units that can run in one superstep are keyed by unit. One reducer deletes: a key
written as ``None`` is removed, which is how a trip back clears artifacts, values, facts and judgements.
"""

from __future__ import annotations

from collections.abc import Mapping
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


# A sub-workflow's child (SWF-B1, SWF-B8) runs on a run state of its own: the same channels, keyed by the child's own
# unit names, so a child `work` never meets the parent's `work`. The parent sees only what its unit exposes.


def child_input(parent: Mapping[str, Any], inputs: Mapping[str, str], options: Mapping[str, Any] | None = None
                ) -> dict[str, Any]:
    """The first state of a child: the parent's task and workspace, the inputs the unit mapped, the operator layers as
    the child reads them (for a child of its own), and the parent's cost so far, so one run cost cap holds across both
    (SWF-B4)."""
    req = parent.get("request") or {}
    out: dict[str, Any] = {"request": {"task_id": req.get("task_id"), "inputs": dict(inputs)},
                           "workspace": dict(parent.get("workspace") or {})}
    run: dict[str, Any] = {}
    cost = (parent.get("run") or {}).get("cost")
    if cost:
        run["cost"] = {k: v for k, v in cost.items() if k != "_base"}
    if options:
        run["options"] = dict(options)
    if run:
        out["run"] = run
    return out


def flat(channel: Mapping[str, Any] | None) -> dict[str, Any]:
    """Every unit's keys of one channel as one mapping, a later unit's key replacing an earlier one's."""
    out: dict[str, Any] = {}
    for vals in (channel or {}).values():
        if isinstance(vals, dict):
            out.update(vals)
    return out


class RunState(TypedDict, total=False):
    request: Annotated[dict[str, Any], replace]  # {task_id, inputs, text_ref, chars}
    # WorkspaceRecord, writer worktrees included (its `children`). Written by the fork and by the join, each alone in
    # its superstep, never by a branch node, so `replace` is the reducer CMP-AC9 asks of every channel.
    workspace: Annotated[dict[str, Any], replace]
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
    maps: Annotated[dict[str, Any], merge_units]  # map unit -> {visit, items, passed, attempts} (MAP-B8, MAP-B9, MAP-B10)
    rulings: Annotated[dict[str, Any], merge_units]  # id -> ruling (own reducer, never cleared by a trip back)
    finalized: Annotated[dict[str, Any], replace]
    run: Annotated[dict[str, Any], merge_run]  # run-level facts: {"stopped": {...}, "path": [...]}
