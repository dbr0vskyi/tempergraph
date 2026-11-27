"""Records on every exit, both modes, no model call (SIL-B8, IMD-B20, IMD-B21).

Findings are metadata only (`runs/<workflow>/<task>/findings.json`, LOS-B7, LOS-B8, LOS-B9). The evidence file
(`runs/<workflow>/<task>/evidence/record.json`) holds the request, the outputs and scrubbed feedback, stays on the
machine, and is never opened by filing code.
"""

from __future__ import annotations

import contextlib
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
from tempergraph.improve import digest as digestmod
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


def prompt_path(root: Path, workflow: str, task_id: str, session_key: str) -> Path:
    return run_dir(root, workflow, task_id) / "evidence" / "prompts" / f"{session_key}.txt"


def write_prompt(root: Path, workflow: str, task_id: str, session_key: str, text: str) -> None:
    """A step session's rendered prompt, scrubbed, local only: the session review's intent (SRV-B17)."""
    with contextlib.suppress(OSError):  # OVR-B4
        _write_private(prompt_path(root, workflow, task_id, session_key), clip(scrub(text), EVIDENCE_CHARS))


def read_prompt(root: Path, workflow: str, task_id: str, session_key: str) -> str:
    try:
        return prompt_path(root, workflow, task_id, session_key).read_text(encoding="utf-8")
    except OSError:
        return ""


def unit_decls(spec: WorkflowSpec) -> dict[str, dict[str, Any]]:
    """What each unit declares, for the digest and the review header: tools, criteria, the judge's brief."""
    from tempergraph.contracts import TextRef
    from tempergraph.model.text import TextUnreadable, load_text, split_judge_file

    out: dict[str, dict[str, Any]] = {}
    for name, u in spec.units.items():
        j = u.gate.judge
        brief = (j.brief if j else "") or ""
        if j is not None and j.file:
            with contextlib.suppress(TextUnreadable):
                brief = split_judge_file(load_text(spec, TextRef(path=j.file)))[1] or brief
        out[name] = {"tools": list(u.step.tools) if u.step else [],
                     "criteria": [{"id": c.id, "text": c.text} for c in u.gate.criteria],
                     "brief": clip(brief, 4000)}
    return out
def read_evidence(root: Path, workflow: str, task_id: str) -> dict[str, Any]:
    """A run's local evidence record, or {} when absent or unreadable (the proposer's reading set, PRP-B23)."""
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


def append_findings(root: Path, workflow: str, task_id: str, thread: str, lines: Sequence[Mapping[str, Any]]) -> None:
    """Appends finding lines to the thread's findings document, in one private write (SIL-B8, SRV-B26)."""
    if not lines:
        return
    doc = {"schema_version": 1, "thread": thread, "findings": read_findings(root, workflow, task_id) + list(lines)}
    _write_private(findings_path(root, workflow, task_id), json.dumps(doc, default=str))


def write_findings(root: Path, workflow: str, task_id: str, thread: str, findings: Sequence[Mapping[str, Any]]) -> None:
    """Rewrites the thread's findings document with `findings`, in one private write (SRV-B7)."""
    doc = {"schema_version": 1, "thread": thread, "findings": list(findings)}
    _write_private(findings_path(root, workflow, task_id), json.dumps(doc, default=str))


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


def _child_owner(spec: WorkflowSpec, path: Any, kids: Mapping[str, Any]) -> dict[str, Any]:
    """SWF-B9: the fields that make a finding about a sub-workflow child's unit the child workflow's: its name and
    version as the run started it (`run_started.children`), the parent, the unit's path, and the child's own
    `issue_repository` (none when the child declares none: a child's finding never files to its parent's repository).
    Empty for a unit of the run's own workflow."""
    if not path:
        return {}
    held = kids.get(str(path)) or {}
    name = str(held.get("workflow") or "")
    if not name:
        return {}
    from tempergraph.model import subworkflow

    got = subworkflow.read_child(name)
    repo = got.spec.issue_repository if isinstance(got, subworkflow.Child) else None
    labels = None  # ISS-B1: the child's own `improvement.issue_labels`; a bad or missing document gives none
    if isinstance(got, subworkflow.Child) and got.spec.package_root is not None:
        try:
            doc = json.loads((got.spec.package_root / "tempergraph.json").read_text(encoding="utf-8"))
            declared = (doc.get("improvement") or {}).get("issue_labels") if isinstance(doc, dict) else None
            labels = declared if isinstance(declared, list) else None
        except (OSError, ValueError, AttributeError):
            labels = None
    return {"workflow": name, "workflow_version": held.get("workflow_version"), "parent": spec.name,
            "child": str(path), "issue_repository": repo, "issue_labels": labels}


ANSWER_FIELDS = ("criteria", "items", "reasons", "decisions", "wait_s_median", "from_unit")


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


def _when(ts: Any) -> datetime | None:
    try:
        got = datetime.fromisoformat(str(ts))
    except ValueError:
        return None
    return got if got.tzinfo else got.replace(tzinfo=UTC)


def unjudged_pause_findings(root: Path, workflow: str, task_id: str, thread: str,
                            home: Path | None = None) -> list[dict[str, Any]]:
    """SIL-B28, SIL-B47, SIL-B48: the findings of the thread's segments that ended in a pause (exit 3) that no loop of
    the thread has dealt with. A waiting or claimed ticket of the thread that holds the fingerprint covers it. A
    `loop_started` record covers it when it names the fingerprint at or after the finding was made, was not held
    (autonomy `record`, a dry run) and, for a friction fault, the loop log holds a judge answer for the fingerprint.
    Read at every final exit of the thread."""
    from tempergraph.improve import child

    held = [f for f in read_findings(root, workflow, task_id) if f.get("segment_exit") == 3
            and str(f.get("thread")) == thread]
    if not held:
        return []
    in_tickets = child.held_by_tickets(root, thread, home)
    log = _jsonl(child.loop_log(root, workflow, task_id))
    started = [(_when(r.get("ts")), set(r.get("fingerprints") or ())) for r in log
               if r.get("kind") == "loop_started" and r.get("held") is not True]
    answered = {str(a.get("fingerprint")) for r in log if r.get("kind") == "loop_judged"
                for a in r.get("answers") or () if isinstance(a, dict)}
    out = []
    for f in held:
        fp = f.get("fingerprint")
        if fp in in_tickets:
            continue
        made = _when(f.get("at"))
        friction = f.get("class") == "fault" and f.get("lens") not in ("outcome", "review")
        covered = any(fps and fp in fps and (made is None or ts is None or ts >= made)
                      for ts, fps in started) and (not friction or str(fp) in answered)
        if not covered:
            out.append(f)
    return out


def judged_units(seg: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """SRV-B12, SRV-B31, SRV-B44: per `unit.item` (the bare unit when the record has no `item`) with a `judgement`
    record, `passed` (its last record has no blockers) and `gave` (the attempts with a record whose
    `confidence_source` is not `engine_placeholder`: a real judgement)."""
    passed: dict[str, bool] = {}
    gave: dict[str, set[int]] = {}
    for r in seg:
        if r.get("kind") != "judgement" or not r.get("unit"):
            continue
        unit = f"{r['unit']}.{r['item']}" if r.get("item") else str(r["unit"])
        passed[unit] = not (r.get("blockers") or [])
        held = gave.setdefault(unit, set())
        if r.get("confidence_source") != "engine_placeholder":
            held.add(int(r.get("attempt") or 1))
    return {u: {"passed": passed[u], "gave": sorted(gave[u])} for u in passed}


def record_exit(root: Path, spec: WorkflowSpec, task_id: str, log_path: Path, values: Mapping[str, Any],
                row: Mapping[str, Any], seg: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Findings and evidence of the segment that just ended; the lenses at a final exit. Returns the summary.

    `seg` is the records the exit covers when they are not the last segment's (SIL-B27: a stop before a unit has
    no segment of its own)."""
    thread = str(row.get("thread_id"))
    records = _jsonl(log_path)
    seg = segment(records) if seg is None else list(seg)
    seg_start = str((seg[0] if seg else {}).get("ts") or "")
    ledger = _jsonl(root / "ledger.jsonl")
    exits = [str(r.get("ts")) for r in ledger if r.get("kind") == "run_segment" and r.get("thread_id") == thread]
    since = exits[-2] if len(exits) >= 2 else ""  # interventions after the previous segment ended
    ivs = [r for r in ledger if r.get("kind") == "intervention" and r.get("thread_id") == thread
           and str(r.get("ts") or "") >= since and (not seg_start or str(r.get("ts") or "") <= seg_start)]
    starter = next((r.get("caller") or {} for r in records if r.get("kind") == "run_started"), {})
    found = causemod.derive(seg, ivs, row.get("grants") or (), starter=starter)
    decls = unit_decls(spec)
    try:  # SRV-B11, SRV-B12: digests first, their causes join the findings; never changes the exit (OVR-B4)
        digests = digestmod.write_segment(root, spec.name, task_id, seg, decls)
        found += digestmod.causes(digests, root=root, workflow=spec.name, version=row.get("workflow_version"),
                                  units=decls, judged=judged_units(seg))
    except Exception:  # noqa: BLE001
        digests = []
    if int(row.get("exit_code") or 0) in FINAL_EXITS:  # the outcome lens's candidates (SIL-B10, B3, B7)
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
    kids = next((r.get("children") or {} for r in seg if r.get("kind") == "run_started"), {})
    lines = []
    for f in found:
        c = causemod.cause_of(f["cause"])
        side = _side(f["cause"], f.get("executor"))
        owner = _child_owner(spec, f.get("child"), kids)  # SWF-B9: a child's unit is the child workflow's
        lines.append({"kind": "finding", "thread": thread, **keys, **owner, "segment_exit": row.get("exit_code"),
                      "segment_started": seg_start,
                      "unit": f["unit"], "cause": f["cause"], "class": f.get("class") or c.klass, "side": side, "count": f["count"],
                      "remedy": c.remedy,
                      "fingerprint": fingerprint(side, str(owner.get("workflow") or spec.name), f["cause"], f["unit"]),
                      "at": at, "request_digest": digest,
                      **({"executor_version": f["executor_version"]} if f.get("executor_version") else {}),
                      **({"lens": f["lens"]} if f.get("lens") else {}),
                      **{k: f[k] for k in ANSWER_FIELDS if k in f},  # FRC-B8, FRC-B9, FRC-B13: ids, enums, numbers
                      **({"rerun_of": rerun_of} if rerun_of else {})})
    final = int(row.get("exit_code") or 0) in FINAL_EXITS
    stop = int(row.get("exit_code") or 0) == 4 and row.get("reason") == "person"
    earlier = unjudged_pause_findings(root, spec.name, task_id, thread) if final else []  # SIL-B28
    append_findings(root, spec.name, task_id, thread, lines)  # one document per thread; each segment appends (SIL-B8)
    _write_private(evidence_path(root, spec.name, task_id), json.dumps(evidence(values), default=str))
    summary: dict[str, Any] = {"digests": len(digests), "causes": sorted({x["cause"] for x in lines}),
                               "sides": sorted({x["side"] for x in lines if x["class"] == "fault"}),
                               "count": len(lines),
                               "fingerprints": sorted({x["fingerprint"] for x in lines}),
                               "fault_fingerprints": sorted({x["fingerprint"] for x in lines
                                                             if x["class"] == "fault" and x.get("lens") != "outcome"}),
                               "outcome_fingerprints": sorted({x["fingerprint"] for x in lines
                                                               if x.get("lens") == "outcome"})}
    covered = [x for x in earlier if x.get("lens") not in ("outcome", "review")]  # their lines are already written
    if covered:
        # SIL-B28, SIL-AC45: the session review plans from `fingerprints`, so only a person's stop adds the pauses there
        key = "fingerprints" if stop else "pause_fingerprints"
        summary[key] = sorted({*summary.get(key, ()), *(str(x["fingerprint"]) for x in covered)})
        summary["fault_fingerprints"] = sorted({*summary["fault_fingerprints"],
                                                *(str(x["fingerprint"]) for x in covered if x.get("class") == "fault")})
    if final:
        summary["lenses"] = lenses.decide(spec, root, thread,
                                          [x for x in lines if x.get("lens") != "outcome"] + covered, row, seg)
    return summary
