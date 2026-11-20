"""The outcome record of a thread and the workflow's uncorrected outcome measures (OUT §2.5, CON §2.14).

Model-free and metadata only: statuses and ids, never criterion text from a session. Trust here is the release 1
default with no calibrated judge (a judge grade is `uncalibrated`); the trust profile and coverage of OUT §2.3
come from `run/outcome_trust.py` (T8) where it is present.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from tempergraph.contracts import WorkflowSpec
from tempergraph.model import flow

TRUST = {"check": "deterministic", "person": "human", "none": "unverified", "judge": "uncalibrated"}
PASSED = frozenset({"MET", "n_a", "signed"})
FAILED = frozenset({"UNMET", "PARTIAL", "declined"})


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


def _status(raw: Any) -> str:
    s = str(raw)
    return "n_a" if s == "N/A" else s


def build(spec: WorkflowSpec, values: Mapping[str, Any], log_path: Path) -> dict[str, Any] | None:
    """The `OutcomeRecord` of a thread so far; None for a workflow with no final criteria."""
    o = spec.outcome
    if o is None or not o.final:
        return None
    unit = flow.OUTCOME_UNIT
    judged = (values.get("judgements") or {}).get(unit)
    att = (values.get("attempts") or {}).get(unit) or {}
    statuses = {s["id"]: _status(s.get("status")) for s in (judged or {}).get("statuses") or [] if s.get("id")}
    check_failed = ((att.get("check") or {}).get("result")) == "FAIL"
    humans = [r for r in _jsonl(log_path) if r.get("kind") == "human" and r.get("unit") == unit]
    reached = bool(att) or judged is not None
    criteria: list[dict[str, Any]] = []
    for c in o.final:
        grader: Any = None
        if not reached:
            status = "not_judged"
        elif c.verified_by in ("none", None):
            status = "not_verified"
        elif c.verified_by == "person":
            last = humans[-1] if humans else None
            word = str((last or {}).get("decision") or "")
            status = "signed" if word == "proceed" else "declined" if word == "stop" else "not_judged"
            grader = (last or {}).get("caller") if status != "not_judged" else None
        else:
            status = statuses.get(c.id) or ("UNMET" if check_failed else "not_judged")
            grader = (c.verifier or {}).get("check") if c.verified_by == "check" else {
                "executor": (judged or {}).get("judge_executor"), "alias": (judged or {}).get("alias")}
        criteria.append({"id": c.id, "class": c.verified_by or "none", "severity": c.severity, "trust": TRUST[c.verified_by or "none"],
                         "status": status, "grader": grader})
    intermediate = []
    for name, io in o.intermediate.items():
        got = {s["id"]: _status(s.get("status")) for s in
               ((values.get("judgements") or {}).get(name) or {}).get("statuses") or [] if s.get("id")}
        for c in io.criteria:
            if c.id in got:
                intermediate.append({"unit": name, "id": c.id, "status": got[c.id]})
    return {"revision": o.revision, "verdict": verdict(criteria, reached), "criteria": criteria,
            "intermediate": intermediate, "later": []}


def verdict(criteria: Iterable[Mapping[str, Any]], reached: bool = True) -> str:
    """OUT §2.5: met, met_with_open, unmet, needs_person or not_reached."""
    if not reached:
        return "not_reached"
    rows = list(criteria)
    blockers = [c for c in rows if c.get("severity", "blocker") == "blocker"]
    if any(c["status"] in FAILED for c in blockers):
        return "unmet"
    if any(c["status"] == "UNVERIFIABLE" or (c["class"] == "person" and c["status"] == "not_judged")
           for c in blockers):
        return "needs_person"
    if all(c["status"] in PASSED for c in rows):
        return "met"
    return "met_with_open"


# ---------------------------------------------------------------------------------------------
# Measures per workflow version and revision (`outcome show --runs`)


def _latest(rows: Iterable[Mapping[str, Any]], workflow: str) -> dict[str, dict[str, Any]]:
    """The last `run_segment` row of each thread of the workflow that carries an outcome."""
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.get("kind") == "run_segment" and r.get("workflow") == workflow and r.get("outcome"):
            out[str(r.get("thread_id"))] = dict(r)
    return out


def measures(spec: WorkflowSpec, ledger: Path, since: str | None = None) -> dict[str, Any]:
    """OUT §2.5 measures, uncorrected, per revision; a revision is never pooled with another (OUT-B7)."""
    rows = _jsonl(ledger)
    if since:
        rows = [r for r in rows if str(r.get("ts", "")) >= since]
    latest = _latest(rows, spec.name)
    reruns = {str(r.get("thread_id")) for r in rows if r.get("kind") == "intervention" and r.get("cause") == "rerun"}
    waits: dict[str, list[float]] = {}
    for r in rows:
        if (r.get("kind") == "intervention" and r.get("unit") == flow.OUTCOME_UNIT and r.get("wait_s") is not None
                and r.get("pause_kind") == "approval"):
            waits.setdefault(str(r.get("thread_id")), []).append(float(r["wait_s"]))
    serving: dict[str, list[tuple[str, str]]] = {}
    if spec.outcome is not None:
        for name, io in spec.outcome.intermediate.items():
            for c in io.criteria:
                for f in c.serves:
                    serving.setdefault(f, []).append((name, str(c.id)))
    by_rev: dict[int, list[tuple[str, dict[str, Any]]]] = {}
    for tid, r in latest.items():
        by_rev.setdefault(int(r["outcome"].get("revision") or 0), []).append((tid, r["outcome"]))
    out = []
    for rev, runs in sorted(by_rev.items()):
        graded = [(t, o) for t, o in runs if o.get("verdict") != "not_reached"]
        met = [(t, o) for t, o in graded if o.get("verdict") in ("met", "met_with_open")]
        escapes = [t for t, _ in met if t in reruns]
        not_verified = [t for t, o in graded if any(c.get("status") == "not_verified" for c in o.get("criteria", []))]
        weak = sorted({c["id"] for _, o in graded for c in o.get("criteria", [])
                       if c.get("severity") == "blocker" and c.get("trust") in ("unverified", "uncalibrated")})
        upstream = {}
        for fid, serves in serving.items():
            passed_up = failed_after = 0
            for _, o in graded:
                inter = {(i["unit"], i["id"]): i["status"] for i in o.get("intermediate", [])}
                if serves and all(inter.get(s) == "MET" for s in serves):
                    passed_up += 1
                    final = next((c for c in o.get("criteria", []) if c["id"] == fid), None)
                    failed_after += bool(final and final["status"] in FAILED)
            upstream[fid] = {"n": passed_up, "failed_after_upstream_passed": failed_after}
        person = [c for _, o in graded for c in o.get("criteria", []) if c.get("class") == "person"]
        out.append({
            "revision": rev, "n": len(runs), "reached": len(graded),
            "met_rate": round(len(met) / len(graded), 3) if graded else None,
            "escape_rate": round(len(escapes) / len(met), 3) if met else None, "escapes": len(escapes),
            "unverified_share": round(len(not_verified) / len(graded), 3) if graded else None,
            "weak_blockers": weak, "upstream_agreement": upstream,
            "sign_off": {"per_run": round(len(person) / len(graded), 2) if graded else None,
                         "wait_s": round(sum(sum(v) for v in waits.values()), 1)},
            "corrected": None})  # judge-error correction waits on calibration (EVS §2.5)
    return {"schema_version": 1, "workflow": spec.name, "revisions": out}


UPSTREAM_LOW = 0.2  # failed after its serving criteria passed on at least this share of runs (release 1 default)
UPSTREAM_MIN_N = 5


def candidates(spec: WorkflowSpec, ledger: Path, since: str | None = None) -> dict[str, Any]:
    """OUT §2.6 revision candidates, model-free: signals with thread ids and counts, never text."""
    rows = _jsonl(ledger)
    if since:
        rows = [r for r in rows if str(r.get("ts", "")) >= since]
    latest = _latest(rows, spec.name)
    graded = {t: r["outcome"] for t, r in latest.items() if r["outcome"].get("verdict") != "not_reached"}
    reruns = {str(r.get("thread_id")) for r in rows if r.get("kind") == "intervention" and r.get("cause") == "rerun"}
    out: list[dict[str, Any]] = []

    def add(signal: str, threads: Iterable[str], **extra: Any) -> None:
        ts = sorted(set(threads))
        out.append({"signal": signal, **extra, "threads": ts, "count": len(ts)})

    rulings: dict[str, set[str]] = {}
    for r in rows:
        if r.get("kind") == "intervention" and r.get("workflow") == spec.name and r.get("ruling"):
            rulings.setdefault(str(r.get("unit")), set()).add(str(r.get("thread_id")))
    for unit, ts in sorted(rulings.items()):
        if len(ts) >= 3:
            add("recurring_ruling", ts, unit=unit)
    esc = [t for t, o in graded.items() if o.get("verdict") in ("met", "met_with_open") and t in reruns]
    if esc:
        add("escape", esc)
    final = spec.outcome.final if spec.outcome else ()
    for c in final:
        def having(pred: Any, cid: str | None = c.id) -> list[str]:
            return [t for t, o in graded.items() if any(x["id"] == cid and pred(x) for x in o.get("criteria", []))]

        declined = having(lambda x: x["status"] == "declined")
        if declined:
            add("declined_sign_off", declined, criterion=c.id)
        weak = having(lambda x: x.get("trust") == "unverified")
        if graded and len(weak) * 2 > len(graded):
            add("unverified", weak, criterion=c.id)
        signed = having(lambda x: x["status"] == "signed")
        if c.verified_by == "person" and len(graded) >= 20 and len(signed) == len(graded):
            add("climb_ladder", signed, criterion=c.id)  # OUT-B6: calibration cases to collect
    for rev in measures(spec, ledger, since)["revisions"]:
        for fid, up in rev["upstream_agreement"].items():
            if up["n"] >= UPSTREAM_MIN_N and up["failed_after_upstream_passed"] / up["n"] >= UPSTREAM_LOW:
                add("low_upstream_agreement", [], criterion=fid, revision=rev["revision"], n=up["n"],
                    failed=up["failed_after_upstream_passed"])
    return {"schema_version": 1, "workflow": spec.name, "candidates": out}
