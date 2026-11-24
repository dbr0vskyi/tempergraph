"""The calls a step session made, read from its activity journal for the attempt's check (CHK-B24, CHK-B25).

The record is `None` wherever it cannot be trusted: no journal, a journal with no call, a session whose
executor reports tool names only (no capability on any call), and a journal that dropped a tool line. A
check reads `None` as "no session record", never as an empty list.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_session(session_dir: Path) -> list[dict[str, Any]] | None:
    """The calls since the session last started, in call order: `{name, capability, target, ok}` each (CHK-B24).

    `target` is the journal line's `input_summary` (null with `observe.tool_inputs = off`), `ok` is true only for
    a call that finished with `ok` true. Returns `None` for a missing or unreadable journal, no call, no call
    with a capability, a `truncated` line that names a dropped tool line, and any line that cannot be read (CHK-B25).
    """
    try:
        text = (session_dir / "activity.jsonl").read_text(encoding="utf-8")
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        if not all(isinstance(r, dict) for r in rows):
            return None
        starts = [i for i, r in enumerate(rows) if r.get("ev") == "session_started"]
        rows = rows[starts[-1]:] if starts else rows
        calls: list[dict[str, Any]] = []
        by_id: dict[str, dict[str, Any]] = {}
        for r in rows:
            ev = r.get("ev")
            if ev == "truncated":
                dropped = r.get("dropped") or {}
                if any(k in dropped for k in ("tool_started", "tool_finished")):
                    return None
            elif ev == "tool_started":
                call = {"name": r.get("name"), "capability": r.get("capability"),
                        "target": r.get("input_summary"), "ok": False}
                calls.append(call)
                by_id[str(r.get("call_id", ""))] = call
            elif ev == "tool_finished":
                started = by_id.get(str(r.get("call_id", "")))
                if started is not None:
                    started["ok"] = r.get("ok") is True
    except Exception:  # noqa: BLE001 - a record that cannot be read is no record
        return None
    if not calls or not any(c["capability"] for c in calls):
        return None
    return calls
