"""The map unit's list and item bookkeeping (MAP §2.2). Model-free.

A map's items run through the unit's own four nodes, one item at a time. The `maps` state channel holds, per
map unit, the list read at the start of the visit, the ids that passed and each item's attempt count. The
attempt, judgement and counter channels of the unit hold the item in hand.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tempergraph.contracts import ExtractContext, MapItem, MapSpec, WorkflowSpec

ITEM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
ITEM_TEXT = 4_000
MAX_ITEMS = 50
WHOLE = "all"  # the id of the one item `on_empty: one_item` runs (MAP-B2)


class MapFault(Exception):
    """The list cannot be read, holds a bad or duplicate id, or is too long: the run stops before any item."""

    def __init__(self, code: str, message: str, count: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.count = count


def _items(raw: Any) -> list[MapItem]:
    if not isinstance(raw, (list, tuple)):
        raise MapFault("map_list_unreadable", "the list is not an array")
    out: list[MapItem] = []
    for x in raw:
        if isinstance(x, MapItem):
            out.append(x)
        elif isinstance(x, str):
            out.append(MapItem(id=x, text=x))
        elif isinstance(x, Mapping) and isinstance(x.get("id"), str):
            out.append(MapItem(id=x["id"], text=str(x.get("text") or "")))
        else:
            raise MapFault("map_list_unreadable", "an item is neither a string nor an object with an id")
    return out


def read_items(spec: WorkflowSpec, unit: str, state: Mapping[str, Any], workdir: Path) -> list[MapItem]:
    """The list of one visit, read once (MAP §2.2 row 1). Raises `MapFault`."""
    m: MapSpec | None = spec.units[unit].map
    assert m is not None
    src, key = m.items_from
    pointer = ((state.get("artifacts") or {}).get(src) or {}).get(key)
    if not pointer:
        raise MapFault("map_list_missing", f"{src} produced no {key!r}")
    path = (workdir / str(pointer)).resolve()
    if not path.is_relative_to(workdir.resolve()) or not path.is_file():
        raise MapFault("map_list_unreadable", f"{pointer} is not a file in the workspace")
    values = {str(k): str(v) for vals in (state.get("values") or {}).values() if isinstance(vals, dict)
              for k, v in vals.items()}
    if m.extract is not None:
        try:
            raw = m.extract.resolve()(ExtractContext(artifact=path, workdir=workdir, values=values))
        except Exception as exc:  # noqa: BLE001 - the extractor's fault stops the run, its type recorded
            raise MapFault("map_extract_raised", f"extract raised {type(exc).__name__}") from None
    else:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise MapFault("map_list_unreadable", f"{pointer} is not a JSON array") from None
    items = _items(raw)
    if not items:
        if m.on_empty == "one_item":
            text = path.read_text(encoding="utf-8", errors="replace")
            return [MapItem(id=WHOLE, text=text[:ITEM_TEXT])]
        if m.on_empty == "skip":
            return []
        raise MapFault("map_empty", "the list is empty", 0)
    if len(items) > min(m.max_items, MAX_ITEMS):
        raise MapFault("map_too_many", f"{len(items)} items, more than max_items {min(m.max_items, MAX_ITEMS)}",
                       len(items))
    seen: set[str] = set()
    for it in items:
        if not ITEM_ID.match(it.id):
            raise MapFault("map_item_id", f"item id {it.id[:40]!r} is not a slug", len(items))
        if it.id in seen:
            raise MapFault("map_duplicate_id", f"item id {it.id!r} appears twice", len(items))
        seen.add(it.id)
    return [MapItem(id=it.id, text=it.text[:ITEM_TEXT]) for it in items]


def record(state: Mapping[str, Any], unit: str) -> dict[str, Any]:
    return dict((state.get("maps") or {}).get(unit) or {})


def pending(m: Mapping[str, Any]) -> dict[str, Any] | None:
    """The first item of the list that has not passed in this visit, with its 1-based index."""
    passed = set(m.get("passed") or [])
    for i, it in enumerate(m.get("items") or [], start=1):
        if it["id"] not in passed:
            return {**it, "index": i, "count": len(m["items"])}
    return None


def item_key(key: str, item: str) -> str:
    """`<key>[<item id>]`: how an item's artifacts, values and facts are keyed (MAP §2.2)."""
    return f"{key}[{item}]"


def advance(spec: WorkflowSpec, unit: str, state: Mapping[str, Any]) -> dict[str, Any] | None:
    """The state write that marks the item in hand passed. Returns the write that moves on to the next
    item, or None when every item has passed (the caller then proceeds to the join). The `maps` write is in
    `passed_write` either way."""
    m = record(state, unit)
    att = (state.get("attempts") or {}).get(unit) or {}
    item = att.get("item")
    if spec.units[unit].map is None or not item:
        return None
    passed = list(dict.fromkeys(list(m.get("passed") or []) + [item]))
    m["passed"] = passed
    if pending(m) is None:
        return None
    return {"maps": {unit: m}, "judgements": {unit: None}, "feedback": {unit: None},
            "counters": {unit: {"retries": 0, "infra": 0, "human": 0}}}


def passed_write(spec: WorkflowSpec, unit: str, state: Mapping[str, Any]) -> dict[str, Any]:
    m = record(state, unit)
    item = ((state.get("attempts") or {}).get(unit) or {}).get("item")
    if spec.units[unit].map is None or not item:
        return {}
    m["passed"] = list(dict.fromkeys(list(m.get("passed") or []) + [item]))
    return {"maps": {unit: m}}
