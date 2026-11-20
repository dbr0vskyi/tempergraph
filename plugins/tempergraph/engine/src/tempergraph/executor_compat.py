"""The executor compatibility table (LIF §2, LIF-AC-4): per executor, the versions its probe facts or contract
tests were recorded for. Outside the range: a warning, and capabilities are projected (EAG-B7)."""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Any

from tempergraph.model.validate import Finding

TABLE = Path(__file__).parent / "data" / "executor_compat.json"


@cache
def table() -> dict[str, Any]:
    doc = json.loads(TABLE.read_text(encoding="utf-8"))
    return dict(doc.get("executors") or {})


def _v(text: str) -> tuple[int, ...]:
    m = re.search(r"(\d+(?:\.\d+)*)", text)
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def in_range(version: str, spec_range: str) -> bool:
    v = _v(version)
    for part in (p.strip() for p in spec_range.split(",") if p.strip()):
        m = re.match(r"^(>=|<=|==|<|>)\s*(\S+)$", part)
        if m is None or not v:
            return False
        b = _v(m.group(2))
        if not {">=": v >= b, "<=": v <= b, "==": v == b, "<": v < b, ">": v > b}[m.group(1)]:
            return False
    return True


def row(executor: str, version: str | None) -> dict[str, Any]:
    """What `executors` shows: the recorded versions, the range, and whether this version is inside it."""
    t = table().get(executor)
    if t is None:
        return {"executor": executor, "state": "no_table"}
    state = "unknown_version" if not version or not _v(version) else ("recorded" if in_range(version, t["range"]) else "outside")
    return {"executor": executor, "version": version, "range": t["range"], "recorded": t.get("recorded", []),
            "state": state}


def finding(executor: str, version: str | None) -> Finding | None:
    """For preflight: a warning when the probed version lies outside the recorded range."""
    r = row(executor, version)
    if r["state"] == "outside":
        return Finding("executor-version-untested", None, f"{executor} {version} is outside the versions its facts "
                       f"were recorded for ({r['range']}); capabilities are projected", "warning")
    return None
