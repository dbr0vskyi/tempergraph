"""`label <thread> <gate> [--criterion id] --value agree|disagree` (FBK-B8, FBK-B9 `explicit`).

One `label` record appended to the state root's ledger: what it is about, its value, its source from the
caller's decider (PRV-B14) and the judge binding that made the judgement. Metadata only: the verb takes no
text, so no request, output or feedback text can reach a label (FBK-AC3, IMD-AC1). The derived kinds of
FBK-B9 and `labels queue` are `improve/reliability.py` (T12.3).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from tempergraph.run.events import records
from tempergraph.store.layout import home_path, now_iso, run_dir

VALUES = ("agree", "disagree")


class LabelRefused(ValueError):
    pass


def _ts(text: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def binding(recs: list[dict[str, Any]], unit: str, attempt: Any, before_seq: int | None = None) -> dict[str, Any]:
    """FBK-B8 `binding` from the judge session that made the judgement and its `judgement` record (which
    carries the brief and criteria digests, EVT-B10 to EVT-B16); a field not recorded is null."""
    judge = next((r for r in reversed(recs) if r.get("kind") == "agent_run" and r.get("unit") == unit
                  and r.get("attempt") == attempt and r.get("session_kind") == "judge"), None) or {}
    judged = next((r for r in reversed(recs) if r.get("kind") == "judgement" and r.get("unit") == unit
                   and (before_seq is None or r.get("seq", 0) < before_seq)), None) or {}
    models = sorted(((judge.get("usage") or {}).get("by_model") or {}).keys())
    return {"executor": judge.get("executor"), "executor_version": judge.get("cli_version"),
            "alias": judge.get("alias"), "model_slug": models[0] if len(models) == 1 else judge.get("model"),
            "brief_digest": judged.get("brief_digest"), "criteria_digest": judged.get("criteria_digest")}


def label(root: Path, thread: str, gate: str, value: str, caller: dict[str, Any], *,
          criterion: str | None = None, attempt: int | None = None, relayed: bool = False) -> dict[str, Any]:
    if value not in VALUES:
        raise LabelRefused(f"--value must be one of {', '.join(VALUES)}")
    workflow, _, task = thread.partition("/")
    recs = list(records(run_dir(root, workflow, task) / "run.jsonl"))
    def attempt_of(g: dict[str, Any]) -> Any:
        """A gate record has no attempt of its own; it closes the unit's latest attempt before it."""
        if g.get("attempt") is not None:
            return g["attempt"]
        starts = [r for r in recs if r.get("kind") == "attempt_start" and r.get("unit") == gate
                  and r.get("session_kind") in ("step", "retry") and r.get("seq", 0) < g.get("seq", 0)]
        return starts[-1].get("attempt") if starts else None

    gates = [r for r in recs if r.get("kind") == "gate" and r.get("unit") == gate
             and (attempt is None or attempt_of(r) == attempt)]
    if not gates:
        raise LabelRefused(f"{thread} has no gate judgement at {gate!r}" + (f" attempt {attempt}" if attempt else ""))
    g = dict(gates[-1])
    g["attempt"] = attempt_of(g)
    judged = next((r for r in reversed(recs) if r.get("kind") == "judgement" and r.get("unit") == gate
                   and r.get("seq", 0) < g.get("seq", 0)), None)
    if criterion is not None:
        ids = {str(s.get("id")) for s in (judged or {}).get("statuses") or []}
        if criterion not in ids:
            raise LabelRefused(f"{criterion!r} is not a criterion of that judgement ({', '.join(sorted(ids)) or 'none'})")
    started = next((r for r in reversed(recs) if r.get("kind") == "run_started" and r.get("seq", 0) < g.get("seq", 0)),
                   None) or {}
    from tempergraph.provenance import decide

    decided = decide(caller, relayed=relayed, words=("label", value), since=g.get("ts"), home=home_path())
    by = decided.get("decided_by")
    source = "person" if by == "person" else "agent"  # unknown callers and unproven relays never grade (FBK-B2)
    now = now_iso()
    t0, t1 = _ts(g.get("ts")), _ts(now)
    from tempergraph import identity
    from tempergraph.git import main_checkout

    machine = identity.machine_id(home_path())
    repo = identity.repo_id(main_checkout(root.parent))  # the ledger's join keys (IMD-B5), as the runner writes them
    return {"kind": "label", "schema_version": 1, "label_id": uuid.uuid4().hex, "thread": thread,
            "run_id": f"{thread}#{g.get('segment')}", "workflow": workflow,
            "workflow_version": started.get("workflow_version"), "machine": machine, "repo": repo,
            "unit": gate, "attempt": g.get("attempt"), "gate_record": g.get("seq"), "gate_verdict": g.get("verdict"),
            "criterion_id": criterion, "label_kind": "explicit", "value": value, "source": source,
            "origin": "run", "at": now,
            "observed_after_s": round(t1 - t0, 1) if t0 is not None and t1 is not None else None,
            "binding": binding(recs, gate, g.get("attempt"), g.get("seq")),
            "confidence": (judged or {}).get("confidence"), "confidence_source": (judged or {}).get("confidence_source"),
            "caller": {k: decided.get(k) for k in ("kind", "confidence", "decided_by", "relay", "host", "call_id")}}
