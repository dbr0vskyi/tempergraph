"""The outcome file and each gate's criteria from it (OUT §2.1–2.3, §4; PKG §2.3 step 5).

Reading is model-free and read-only. The outcome gate, sign-off and the outcome record are T5.8.2 and T5.8.3.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tempergraph.contracts import CallableRef, Criterion, IntermediateOutcome, OutcomeSpec, WorkflowSpec
from tempergraph.model.validate import Finding

OUTCOME_FILE = "outcome.json"
VERIFIED_BY = frozenset({"check", "judge", "person", "none"})
SEVERITIES = frozenset({"blocker", "warning"})


def _criterion(raw: Any, where: str, out: list[Finding]) -> Criterion | None:
    if not isinstance(raw, Mapping) or not raw.get("id") or not raw.get("text"):
        out.append(Finding(code="outcome-criterion-invalid", unit=where, message="a criterion needs `id` and `text`"))
        return None
    by = raw.get("verified_by")
    if by not in VERIFIED_BY:
        out.append(Finding(code="outcome-criterion-invalid", unit=where,
                           message=f"{raw['id']}: `verified_by` must be check, judge, person or none"))
        return None
    sev = raw.get("severity", "blocker")
    if sev not in SEVERITIES:
        out.append(Finding(code="outcome-criterion-invalid", unit=where, message=f"{raw['id']}: severity {sev!r}"))
        return None
    verifier: Mapping[str, Any] = raw["verifier"] if isinstance(raw.get("verifier"), Mapping) else {}
    if by == "none" and not str(verifier.get("reason") or "").strip():
        out.append(Finding(code="outcome-none-unexplained", unit=where,
                           message=f"{raw['id']}: `verified_by: none` needs a reason"))
    policy = raw.get("no_change_policy", "escalate")
    return Criterion(id=str(raw["id"]), text=str(raw["text"]), check_method=str(raw.get("check_method") or ""),
                     severity=sev, no_change_policy=policy if policy in ("escalate", "retry") else "escalate",
                     unverified_system=raw.get("unverified_system"), mechanical=by == "check", verified_by=by,
                     verifier=dict(verifier), source=raw.get("source"),
                     serves=tuple(str(s) for s in raw.get("serves") or ()))


def parse_outcome(data: Any) -> OutcomeSpec | list[Finding]:
    """OUT §2.1 and the file-only rows of OUT §4."""
    out: list[Finding] = []
    if not isinstance(data, Mapping) or data.get("schema_version") != 1:
        return [Finding(code="outcome-missing", unit=None, message="outcome.json is not a version 1 object")]
    final = [c for c in (_criterion(r, "final", out) for r in data.get("final") or []) if c]
    if not final and not out:
        out.append(Finding(code="outcome-missing", unit=None, message="outcome.json has no final criterion"))
    inter: dict[str, IntermediateOutcome] = {}
    raw_inter: Mapping[str, Any] = data["intermediate"] if isinstance(data.get("intermediate"), Mapping) else {}
    for unit, body in raw_inter.items():
        body = body if isinstance(body, Mapping) else {}
        crit = [c for c in (_criterion(r, str(unit), out) for r in body.get("criteria") or []) if c]
        inter[str(unit)] = IntermediateOutcome(statement=str(body.get("statement") or ""), criteria=tuple(crit))
    seen: set[str] = set()
    for c in final + [c for io in inter.values() for c in io.criteria]:
        if c.id in seen:
            out.append(Finding(code="criterion-id-duplicate", unit=None, message=f"criterion id {c.id!r} twice"))
        seen.add(str(c.id))
    final_ids = {c.id for c in final}
    for unit, io in inter.items():
        for c in io.criteria:
            for s in c.serves:
                if s not in final_ids:
                    out.append(Finding(code="outcome-serves-unknown", unit=unit,
                                       message=f"{c.id} serves {s!r}, which is not a final criterion"))
    if out:
        return out
    check = data.get("check")
    ref = None
    if isinstance(check, str) and ":" in check:
        mod, _, qual = check.partition(":")
        ref = CallableRef(module=mod, qualname=qual)
    return OutcomeSpec(schema_version=1, revision=int(data.get("revision") or 1),
                       statement=str(data.get("statement") or ""),
                       deliverables=tuple(dict(d) for d in data.get("deliverables") or () if isinstance(d, Mapping)),
                       final=tuple(final), intermediate=inter,
                       judge=dict(data["judge"]) if isinstance(data.get("judge"), Mapping) else None, check=ref,
                       assumptions=tuple(str(a) for a in data.get("assumptions") or ()),
                       revisions=tuple(dict(r) for r in data.get("revisions") or () if isinstance(r, Mapping)))


def read_outcome(package_path: Path) -> OutcomeSpec | list[Finding]:
    """Read `<package>/outcome.json`; a missing or unreadable file is `outcome-missing`."""
    try:
        data = json.loads((package_path / OUTCOME_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [Finding(code="outcome-missing", unit=None, message=f"outcome.json: {type(exc).__name__}")]
    return parse_outcome(data)


def gate_criteria(outcome: OutcomeSpec, unit: str) -> list[Criterion]:
    """The unit's intermediate criteria, `mechanical` set for `check` ones (OUT-AC-2)."""
    io = outcome.intermediate.get(unit)
    return list(io.criteria) if io else []


def check_against(outcome: OutcomeSpec, spec: WorkflowSpec) -> list[Finding]:
    """The unit rows of OUT §4: an intermediate outcome for an unknown unit, or a model step with none."""
    out: list[Finding] = []
    for unit in outcome.intermediate:
        if unit not in spec.units:
            out.append(Finding(code="outcome-unit-unknown", unit=unit, message=f"{unit} is not in the workflow"))
    for name, u in spec.units.items():
        if u.kind == "step" and name not in outcome.intermediate:
            out.append(Finding(code="outcome-unit-missing", unit=name, message=f"{name} has no intermediate outcome"))
    for name, io in outcome.intermediate.items():
        found = spec.units.get(name)
        if found is not None and found.gate.check is None and any(c.verified_by == "check" for c in io.criteria):
            out.append(Finding(code="mechanical-without-check", unit=name,
                               message="a `check` criterion needs the unit's gate to have a check (CHK §4)"))
    return out
