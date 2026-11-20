"""Records on every exit, both modes, no model call (SIL §2.1, IMD §2.2, §2.3).

Findings are metadata only (`runs/<workflow>/<task>/findings.json`, LOS §2.1). The evidence file
(`runs/<workflow>/<task>/evidence/record.json`) holds the request, the outputs and scrubbed feedback, stays on the
machine, and is never opened by filing code.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tempergraph import identity
from tempergraph.contracts import WorkflowSpec
from tempergraph.improve import causes as causemod
from tempergraph.improve import lenses
from tempergraph.model import flow
from tempergraph.security.scrub import clip, scrub
from tempergraph.store.layout import run_dir

FINAL_EXITS = frozenset({0, 4, 5})  # not a pause (exit 3)
OUTCOME_FAILED = frozenset({"UNMET", "PARTIAL"})  # a judge's grade; a person's `declined` is pushback
EVIDENCE_CHARS = 32_000


def findings_path(root: Path, workflow: str, task_id: str) -> Path:
    return run_dir(root, workflow, task_id) / "findings.json"


def evidence_path(root: Path, workflow: str, task_id: str) -> Path:
    return run_dir(root, workflow, task_id) / "evidence" / "record.json"


def read_evidence(root: Path, workflow: str, task_id: str) -> dict[str, Any]:
    """A run's local evidence record, or {} when absent or unreadable (the proposer's reading set, PRP §5)."""
    try:
        doc = json.loads(evidence_path(root, workflow, task_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def read_findings(root: Path, workflow: str, task_id: str) -> list[dict[str, Any]]:
    try:
        doc = json.loads(findings_path(root, workflow, task_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [f for f in doc.get("findings") or [] if isinstance(f, dict)] if isinstance(doc, dict) else []


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict):
            out.append(r)
    return out


def segment(records: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The records of the last segment: from the last `run_started` on."""
    start = max((i for i, r in enumerate(records) if r.get("kind") == "run_started"), default=0)
    return list(records[start:])


def fingerprint(side: str, workflow: str, cause: str, unit: str) -> str:
    return hashlib.sha256(f"{side}|{workflow}|{cause}|{unit}".encode()).hexdigest()[:16]


def _side(code: str, executor: str | None) -> str:
    side = causemod.cause_of(code).side
    return f"executor:{executor or 'unknown'}" if side == "executor" else side


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    if os.name == "posix":
        os.chmod(path, 0o600)


def evidence(values: Mapping[str, Any]) -> dict[str, Any]:
    """Request, outputs and feedback, scrubbed and clipped; local only."""
    req = values.get("request") or {}
    fb = [str(v.get("text")) for v in (values.get("feedback") or {}).values() if isinstance(v, Mapping) and v.get("text")]
    fb += [str(r.get("text")) for r in (values.get("rulings") or {}).values() if isinstance(r, Mapping) and r.get("text")]
    return {"schema_version": 1,
            "request": {k: clip(scrub(str(v)), EVIDENCE_CHARS) for k, v in (req.get("inputs") or {}).items()},
            "artifacts": clip(scrub(json.dumps(values.get("artifacts") or {}, default=str)), EVIDENCE_CHARS),
            "values": clip(scrub(json.dumps(values.get("values") or {}, default=str)), EVIDENCE_CHARS),
            "feedback": [clip(scrub(t), 8000) for t in fb]}


def record_exit(root: Path, spec: WorkflowSpec, task_id: str, log_path: Path, values: Mapping[str, Any],
                row: Mapping[str, Any]) -> dict[str, Any]:
    """Findings and evidence of the segment that just ended; the lenses at a final exit. Returns the summary."""
    thread = str(row.get("thread_id"))
    records = _jsonl(log_path)
    seg = segment(records)
    seg_start = str((seg[0] if seg else {}).get("ts") or "")
    ledger = _jsonl(root / "ledger.jsonl")
    exits = [str(r.get("ts")) for r in ledger if r.get("kind") == "run_segment" and r.get("thread_id") == thread]
    since = exits[-2] if len(exits) >= 2 else ""  # interventions after the previous segment ended
    ivs = [r for r in ledger if r.get("kind") == "intervention" and r.get("thread_id") == thread
           and str(r.get("ts") or "") >= since and (not seg_start or str(r.get("ts") or "") <= seg_start)]
    found = causemod.derive(seg, ivs, row.get("grants") or ())
    if int(row.get("exit_code") or 0) in FINAL_EXITS:  # the outcome lens's candidates (SIL §2.2, B3, B7)
        for c in (row.get("outcome") or {}).get("criteria") or ():
            if c.get("class") == "judge" and c.get("status") in OUTCOME_FAILED:
                found.append({"unit": flow.OUTCOME_UNIT, "cause": f"outcome_unmet:{c.get('id')}", "count": 1,
                              "lens": "outcome"})
    keys = {k: row.get(k) for k in ("workflow", "workflow_version", "machine", "repo", "settings_digest",
                                    "overridden_keys")}
    req = str(((values.get("request") or {}).get("inputs") or {}).get("request") or "")
    digest = identity.request_digest(req) if req else None
    at = datetime.now(UTC).isoformat(timespec="seconds")
    rerun_of = next((r.get("rerun_of") for r in seg if r.get("kind") == "run_started" and r.get("rerun_of")), None)
    lines = []
    for f in found:
        c = causemod.cause_of(f["cause"])
        side = _side(f["cause"], f.get("executor"))
        lines.append({"kind": "finding", "thread": thread, **keys, "segment_exit": row.get("exit_code"),
                      "unit": f["unit"], "cause": f["cause"], "class": c.klass, "side": side, "count": f["count"],
                      "remedy": c.remedy, "fingerprint": fingerprint(side, spec.name, f["cause"], f["unit"]),
                      "at": at, "request_digest": digest,
                      **({"executor_version": f["executor_version"]} if f.get("executor_version") else {}),
                      **({"lens": f["lens"]} if f.get("lens") else {}),
                      **({"rerun_of": rerun_of} if rerun_of else {})})
    if lines:  # one document per thread; each segment appends its findings (SIL §2.1)
        doc = {"schema_version": 1, "thread": thread,
               "findings": read_findings(root, spec.name, task_id) + lines}
        _write_private(findings_path(root, spec.name, task_id), json.dumps(doc, default=str))
    _write_private(evidence_path(root, spec.name, task_id), json.dumps(evidence(values), default=str))
    summary: dict[str, Any] = {"causes": sorted({x["cause"] for x in lines}),
                               "sides": sorted({x["side"] for x in lines if x["class"] == "fault"}),
                               "count": len(lines),
                               "fingerprints": sorted({x["fingerprint"] for x in lines}),
                               "fault_fingerprints": sorted({x["fingerprint"] for x in lines
                                                             if x["class"] == "fault" and x.get("lens") != "outcome"}),
                               "outcome_fingerprints": sorted({x["fingerprint"] for x in lines
                                                               if x.get("lens") == "outcome"})}
    if int(row.get("exit_code") or 0) in FINAL_EXITS:
        summary["lenses"] = lenses.decide(spec, root, thread, [x for x in lines if x.get("lens") != "outcome"],
                                          row, seg)
    return summary
