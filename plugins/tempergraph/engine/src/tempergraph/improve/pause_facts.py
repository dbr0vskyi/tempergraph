"""What answered a pause, for the friction judge (SIL-B37): facts read from ids and enums, never from text.

Each finding is told the pause that ended its own segment (`segment_of`: from `segment_started`, else the segment of the latest `run_exit` at
or before the finding's time): the paused unit and item,
the pause's reason, the decision word that answered it, the kind of caller, whether a ruling and whether feedback was
given (never their words), the operator reason of the decision (one of six words, else `not given`), the classes of the decision's touches, whether the workspace changed and the verdict of the
next gate of the paused unit, child and item. They come from the run log (`pause`, `workspace` and `gate` records)
and the ledger's `intervention` rows; no feedback or ruling text, answer value, path or file content is read or
returned (SIL-B38). A fact that cannot be read is `not recorded`, never a guess; a finding with no pause gets no row.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from tempergraph.improve.record import _jsonl, _when
from tempergraph.store.layout import run_dir

UNKNOWN = "not recorded"
OPERATOR_REASONS = ("engine_defect", "judge_error", "environment", "plan", "request", "other")  # CLI-B24
TOUCH_ORDER = ("designed", "rescue", "steer", "engine")
WORKSPACE_ACTIONS = {"prepared": "unchanged", "reused": "unchanged", "attached": "unchanged",
                     "external_change": "changed"}


def _second(ts: Any) -> datetime | None:
    got = _when(ts)
    return got.replace(microsecond=0) if got else None


def _word(value: Any) -> str:
    """An id or enum word of a record; anything else (empty, not a string) is not recorded."""
    return value if isinstance(value, str) and value and len(value) <= 80 and "\n" not in value else UNKNOWN


def segment_of(finding: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> tuple[int, int] | None:
    """SIL-B51: the index range of the finding's own segment: from the `run_started` at `segment_started` to the next
    one; for a line without it, the segment whose `run_exit` is the latest at or before the finding's time, both read
    to the whole second. None when no such segment is found or the finding's time cannot be read."""
    starts = [i for i, r in enumerate(records) if r.get("kind") == "run_started"]
    bounds = list(zip(starts, [*starts[1:], len(records)], strict=False))
    marked = str(finding.get("segment_started") or "")
    if marked:
        return next((b for b in bounds if str(records[b[0]].get("ts") or "") == marked), None)
    made = _second(finding.get("at"))
    if made is None:
        return None
    found: tuple[int, int] | None = None
    latest: datetime | None = None
    for b in bounds:
        for r in records[b[0]:b[1]]:
            if r.get("kind") != "run_exit":
                continue
            ended = _second(r.get("ts"))
            if ended is not None and ended <= made and (latest is None or ended >= latest):
                found, latest = b, ended
    return found


def pause_reason(seg_records: Sequence[Mapping[str, Any]], findings: Sequence[Mapping[str, Any]]) -> str:
    """The reason of the pause that ended a segment (SIL-B45): the pause at a listed finding's unit, else the segment's
    last pause, read from the pause record's own `reason` (its kind when it has none), never the `run_exit` reason.
    `findings` are those already bound to the segment; `-` when the segment has no pause."""
    pauses = [r for r in seg_records if r.get("kind") == "pause"]
    if not pauses:
        return "-"
    pick = next((p for f in findings for p in reversed(pauses)
                 if str(p.get("unit") or "") == str(f.get("unit") or "")
                 and str(p.get("child") or "") == str(f.get("child") or "")), pauses[-1])
    return re.sub(r"[^A-Za-z0-9_.:-]", "", str(pick.get("reason") or pick.get("pause_kind") or "-")) or "-"


def _touch(row: Mapping[str, Any]) -> str:
    """SIL-B43: every class the decision touched, each once, in `TOUCH_ORDER`, joined by `,`; none is not recorded."""
    classes = {t.get("class") for t in row.get("touches") or () if isinstance(t, Mapping)}
    return ",".join(c for c in TOUCH_ORDER if c in classes) or UNKNOWN


def _facts(finding: Mapping[str, Any], records: Sequence[Mapping[str, Any]],
           ledger: Sequence[Mapping[str, Any]], thread: str) -> dict[str, str] | None:
    """The row of one finding, or None when no pause, no decision and no gate is recorded for it."""
    unit, kid = str(finding.get("unit") or ""), str(finding.get("child") or "")
    own = segment_of(finding, records)
    if own is None:
        return None
    pauses = [(i, r) for i, r in enumerate(records[own[0]:own[1]], own[0]) if r.get("kind") == "pause"]
    if not pauses:
        return None
    at, pause = next(((i, r) for i, r in reversed(pauses)
                      if str(r.get("unit") or "") == unit and str(r.get("child") or "") == kid), pauses[-1])
    out = dict.fromkeys(("reason", "decision", "caller", "feedback", "workspace", "next_gate", "ruling", "touch"),
                        UNKNOWN)
    out["operator_reason"] = "not given"
    p_unit, p_kid, p_item = str(pause.get("unit") or ""), str(pause.get("child") or ""), str(pause.get("item") or "")
    out["unit"] = _word(p_unit) if p_unit else "-"
    out["item"] = _word(p_item) if p_item else "-"
    out["reason"] = _word(pause.get("reason") or pause.get("pause_kind"))
    when, owner = _when(pause.get("ts")), f"{p_kid}/{p_unit}" if p_kid else p_unit
    answers = [r for r in ledger if r.get("kind") == "intervention" and r.get("thread_id") == thread
               and str(r.get("unit") or "") == owner
               and (when is None or (_when(r.get("ts")) or when) >= when)]
    if answers:
        row = answers[0]
        out["decision"] = _word(row.get("decision"))
        out["caller"] = _word((row.get("caller") or {}).get("kind") if isinstance(row.get("caller"), Mapping) else None)
        out["ruling"] = "given" if row.get("ruling") else "not given"  # whether, never the words (SIL-B38)
        out["feedback"] = "given" if row.get("feedback") is True and not row.get("ruling") else "not given"
        out["touch"] = _touch(row)
        given = row.get("operator_reason")
        out["operator_reason"] = given if given in OPERATOR_REASONS else "not given"
    after = records[at + 1:]
    ws = next((r for r in after if r.get("kind") == "workspace" and r.get("action") in WORKSPACE_ACTIONS), None)
    if ws is not None and ws.get("mode") != "in_place":  # WTR-B22: a run in place is compared with nothing
        out["workspace"] = WORKSPACE_ACTIONS[str(ws["action"])]
    gate = next((r for r in after if r.get("kind") == "gate" and str(r.get("unit") or "") == p_unit
                 and str(r.get("child") or "") == p_kid and str(r.get("item") or "") == p_item), None)
    out["next_gate"] = "none" if gate is None or not gate.get("verdict") else _word(gate.get("verdict"))
    return out


def of(root: Path, workflow: str, task_id: str, findings: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    """The facts of each finding of a segment that ended in a pause (`segment_exit` 3), by fingerprint."""
    paused = [f for f in findings if f.get("segment_exit") == 3 and f.get("fingerprint")]
    if not paused:
        return {}
    records = _jsonl(run_dir(root, workflow, task_id) / "run.jsonl")
    ledger = _jsonl(root / "ledger.jsonl")
    rows = {str(f["fingerprint"]): _facts(f, records, ledger, str(f.get("thread") or f"{workflow}/{task_id}"))
            for f in paused}
    return {fp: row for fp, row in rows.items() if row is not None}
