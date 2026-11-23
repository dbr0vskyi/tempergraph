"""Run state: JSON one level deep, merged by reducers (CMP-B17, DUR OVR-B9).

Channels written by units that can run in one superstep are keyed by unit. One reducer deletes: a key
written as ``None`` is removed, which is how a trip back clears artifacts, values, facts and judgements.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping
from dataclasses import dataclass, field
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


def merge_maps(old: dict[str, Any] | None, new: dict[str, Any] | None) -> dict[str, Any]:
    """The reducer of the `maps` channel (MAP-B9, MAP-B10, CMP-AC9): `merge_units`, safe for two items of a concurrent map
    ending in one superstep. Each item writes keys of its own (`n:<id>`, `st:<id>`), which merge by item id, and the
    ids that passed are a union; a write that carries a list (it starts a visit, or rewrites the record whole) is
    taken as it is, so a new visit forgets the passed ids of the last."""
    out: dict[str, Any] = dict(old or {})
    for unit, val in (new or {}).items():
        held = out.get(unit)
        if isinstance(val, dict) and isinstance(held, dict) and "items" not in val and isinstance(val.get("passed"), list):
            union = list(dict.fromkeys(list(held.get("passed") or []) + val["passed"]))
            out.update(merge_units({unit: held}, {unit: {**val, "passed": union}}))
        else:
            out.update(merge_units({unit: held} if unit in out else {}, {unit: val}))
            if val is None:
                out.pop(unit, None)
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


def fold(state: Mapping[str, Any], writes: Mapping[str, Any]) -> dict[str, Any]:
    """`state` as it reads once `writes` are applied through each channel's own reducer: what a node of a concurrent
    map's item hands to the next node of the same item (a `Send` carries a state of its own, not the channels)."""
    out = dict(state)
    for channel, value in writes.items():
        reducer = _reducers().get(channel)
        out[channel] = reducer(out.get(channel), value) if reducer is not None else value
    return out


ITEM = "__item"  # the key a node of a concurrent map's item finds in the state it is sent: `{unit, id, slot}`
SLOT_CHANNELS = ("attempts", "judgements", "feedback", "counters", "route", "pause")  # an item's are keyed by its slot


def slot(unit: str, item: str) -> str:
    """`<unit>.<item id>`: how an item of a concurrent map, or a slot of a contest, is addressed (an item id holds no dot;
    a slot name is a slug, which holds none either)."""
    return f"{unit}.{item}"


def item_view(state: Mapping[str, Any], unit: str, item: str) -> dict[str, Any]:
    """`state` as an item's node reads it: the slot's own record in the place the unit's own would be, so the step,
    judge, gate and human bodies run on an item as they run on a unit."""
    at = slot(unit, item)
    view = dict(state)
    for channel in SLOT_CHANNELS:
        held = dict(state.get(channel) or {})
        if at in held:
            held[unit] = held[at]
        else:
            held.pop(unit, None)
        view[channel] = held
    view[ITEM] = {"unit": unit, "id": item, "slot": at}
    return view


def slot_writes(writes: Mapping[str, Any], unit: str, item: str) -> dict[str, Any]:
    """What a body wrote for the unit, moved to the item's slot so that items finishing in one superstep never share a key."""
    out = dict(writes)
    at = slot(unit, item)
    for channel in SLOT_CHANNELS:
        got = out.get(channel)
        if isinstance(got, dict) and unit in got:
            out[channel] = {(at if k == unit else k): v for k, v in got.items()}
    return out


def own_keys(held: Mapping[str, Any] | None, item: str) -> dict[str, Any]:
    """One item's keys of a unit's artifacts, values or facts as plain keys: `<key>[<item>]` read as `<key>`. A contest's
    judge sees these only, so one slot's judge holds no other slot's artifact (CTS-B3)."""
    tail = f"[{item}]"
    return {k[: -len(tail)]: v for k, v in (held or {}).items() if k.endswith(tail)}


def item_end(unit: str, item: str, token: str, node: str) -> dict[str, Any]:
    """The `maps` write of an item's turn: it goes on (a retry), has passed, waits for a person (parked) or has stopped
    the map, naming where the map then goes (a stop, a fallback or a person's rewind)."""
    key = f"st:{item}"
    if token == "RETRY":
        return {"maps": {unit: {key: "started"}}}
    if token in ("NEXT", "PROCEED"):
        return {"maps": {unit: {key: "passed"}}}
    if token == "ESCALATE":
        return {"maps": {unit: {key: "parked"}}}
    return {"maps": {unit: {key: "stopped", "exit": {"token": token, "node": node, "item": item}}}}


@dataclass
class Move:
    """What a concurrent map's own step node does next: the state it writes, the items it sends to an item node (`kind`
    is `step` or `human`), or the node it goes to; with none of these it waits for the items that are running."""

    writes: dict[str, Any]
    items: list[str] = field(default_factory=list)
    kind: str = "step"
    goto: str | None = None


@functools.lru_cache(maxsize=1)
def _reducers() -> dict[str, Any]:
    from typing import get_type_hints

    return {name: m for name, hint in get_type_hints(RunState, include_extras=True).items()
            for m in getattr(hint, "__metadata__", ()) if callable(m)}


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
    maps: Annotated[dict[str, Any], merge_maps]  # map unit -> {visit, items, passed, n:<id>, st:<id>} (MAP-B8 to MAP-B10)
    rulings: Annotated[dict[str, Any], merge_units]  # id -> ruling (own reducer, never cleared by a trip back)
    finalized: Annotated[dict[str, Any], replace]
    run: Annotated[dict[str, Any], merge_run]  # run-level facts: {"stopped": {...}, "path": [...]}
