"""What answered a pause, for the friction judge (SIL-B37): six facts read from ids and enums, never from text.

The pause's reason, the decision word that answered it, the kind of caller, whether feedback was given, whether the
workspace changed and the verdict of the unit's next gate. They come from the run log (`pause`, `workspace` and
`gate` records) and the ledger's `intervention` rows; no feedback text, answer value, path or file content is read
or returned (SIL-B38). A fact that cannot be read is `not recorded`, never a guess.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from tempergraph.improve.record import _jsonl, _when
from tempergraph.store.layout import run_dir

UNKNOWN = "not recorded"
WORKSPACE_ACTIONS = {"prepared": "unchanged", "reused": "unchanged", "attached": "unchanged",
                     "external_change": "changed"}


def _second(ts: Any) -> datetime | None:
    got = _when(ts)
    return got.replace(microsecond=0) if got else None


def _word(value: Any) -> str:
    """An id or enum word of a record; anything else (empty, not a string) is not recorded."""
    return value if isinstance(value, str) and value and len(value) <= 80 and "\n" not in value else UNKNOWN


def _facts(finding: Mapping[str, Any], records: Sequence[Mapping[str, Any]],
           ledger: Sequence[Mapping[str, Any]], thread: str) -> dict[str, str]:
    unit, kid = str(finding.get("unit") or ""), str(finding.get("child") or "")
    made = _second(finding.get("at"))
    pauses = [(i, r) for i, r in enumerate(records) if r.get("kind") == "pause" and str(r.get("unit") or "") == unit
              and str(r.get("child") or "") == kid
              and (made is None or (_second(r.get("ts")) or made) <= made)]
    out = dict.fromkeys(("reason", "decision", "caller", "feedback", "workspace", "next_gate"), UNKNOWN)
    if not pauses:
        return out
    at, pause = pauses[-1]
    out["reason"] = _word(pause.get("reason") or pause.get("pause_kind"))
    when, owner = _when(pause.get("ts")), f"{kid}/{unit}" if kid else unit
    answers = [r for r in ledger if r.get("kind") == "intervention" and r.get("thread_id") == thread
               and str(r.get("unit") or "") == owner
               and (when is None or (_when(r.get("ts")) or when) >= when)]
    if answers:
        row = answers[0]
        out["decision"] = _word(row.get("decision"))
        out["caller"] = _word((row.get("caller") or {}).get("kind") if isinstance(row.get("caller"), Mapping) else None)
        out["feedback"] = "given" if row.get("feedback") is True else "not given"
    after = records[at + 1:]
    ws = next((r for r in after if r.get("kind") == "workspace" and r.get("action") in WORKSPACE_ACTIONS), None)
    if ws is not None and ws.get("mode") != "in_place":  # WTR-B22: a run in place is compared with nothing
        out["workspace"] = WORKSPACE_ACTIONS[str(ws["action"])]
    gate = next((r for r in after if r.get("kind") == "gate" and str(r.get("unit") or "") == unit
                 and str(r.get("child") or "") == kid), None)
    out["next_gate"] = "none" if gate is None or not gate.get("verdict") else _word(gate.get("verdict"))
    return out


def of(root: Path, workflow: str, task_id: str, findings: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    """The facts of each finding of a segment that ended in a pause (`segment_exit` 3), by fingerprint."""
    paused = [f for f in findings if f.get("segment_exit") == 3 and f.get("fingerprint")]
    if not paused:
        return {}
    records = _jsonl(run_dir(root, workflow, task_id) / "run.jsonl")
    ledger = _jsonl(root / "ledger.jsonl")
    return {str(f["fingerprint"]): _facts(f, records, ledger, str(f.get("thread") or f"{workflow}/{task_id}"))
            for f in paused}
