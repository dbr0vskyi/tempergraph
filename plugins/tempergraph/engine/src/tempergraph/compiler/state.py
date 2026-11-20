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
    rulings: Annotated[dict[str, Any], merge_units]  # id -> ruling (own reducer, never cleared by a trip back)
    finalized: Annotated[dict[str, Any], replace]
    run: Annotated[dict[str, Any], merge_units]  # run-level facts: {"stopped": {...}, "path": [...]}
