"""The outcome file and each gate's criteria from it (OUT §2.1–2.3, §4; PKG §2.3 step 5).

Reading is model-free and read-only. The outcome gate, sign-off and the outcome record are T5.8.2 and T5.8.3.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from tempergraph.contracts import (
    CallableRef,
    CheckFinding,
    CheckResult,
    Criterion,
    GateSpec,
    IntermediateOutcome,
    JudgeSpec,
    OutcomeSpec,
    StepSpec,
    UnitSpec,
    WorkflowSpec,
)
from tempergraph.model import flow
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
        if u.kind in ("step", "map") and name not in outcome.intermediate:
            out.append(Finding(code="outcome-unit-missing", unit=name, message=f"{name} has no intermediate outcome"))
    for name, io in outcome.intermediate.items():
        found = spec.units.get(name)
        if found is not None and found.gate.check is None and any(c.verified_by == "check" for c in io.criteria):
            out.append(Finding(code="mechanical-without-check", unit=name,
                               message="a `check` criterion needs the unit's gate to have a check (CHK §4)"))
    return out


# ---------------------------------------------------------------------------------------------
# The outcome gate (OUT §2.4)

OUTCOME_STANCE = "The request and the deliverables are the truth; everything a step said is a claim to verify."
_TIER = {"small": 1, "haiku": 1, "medium": 2, "sonnet": 2, "large": 3, "opus": 3}


def _strongest_judge_model(spec: WorkflowSpec) -> str | None:
    models = [u.gate.judge.model for u in spec.units.values() if u.gate.judge is not None and u.gate.judge.model]
    return max(models, key=lambda m: _TIER.get(str(m).lower(), 0)) if models else None


def outcome_unit(spec: WorkflowSpec) -> UnitSpec | None:
    """The reserved `outcome` unit compiled from `outcome.json` with no declaration (PKG §2.7, OUT §2.4)."""
    o = spec.outcome
    if o is None or not o.final:
        return None
    graded = tuple(c for c in o.final if c.verified_by in ("judge", "check"))
    sign_off = [{"id": c.id, "text": c.text, "role": (c.verifier or {}).get("role", ""),
                 "question": (c.verifier or {}).get("question", "")} for c in o.final if c.verified_by == "person"]
    unverified = [{"id": c.id, "reason": (c.verifier or {}).get("reason", "")} for c in o.final
                  if c.verified_by == "none"]
    jcfg = dict(o.judge or {})
    made = deliverable_producers(spec)
    every = _on_every_path(spec)
    # a deliverable some path does not produce is an optional reference for the outcome judge (OUT §2.4)
    refs: dict[str, Literal["required", "optional"]] = {
        str(d.get("key")): "required" if not made.get(str(d.get("key"))) or set(made[str(d.get("key"))]) & every
        else "optional" for d in o.deliverables if d.get("key")}
    refs.update({str(r): "required" for r in jcfg.get("references") or ()})
    judge = None
    if any(c.verified_by == "judge" for c in graded):
        judge = JudgeSpec(stance=str(jcfg.get("stance") or OUTCOME_STANCE), references=refs,
                          executor=jcfg.get("executor"),
                          model=jcfg.get("model") or _strongest_judge_model(spec))
    gate = GateSpec(check=CallableRef(module=__name__, qualname="outcome_check"), judge=judge, criteria=graded,
                    approval=bool(sign_off), back_targets=tuple(flow.outcome_back_targets(spec)), loop_budget=1,
                    retry_budget=0)
    return UnitSpec(kind="step", gate=gate, step=StepSpec(tools=("read",)),
                    extra={"outcome": True, "sign_off": sign_off, "unverified": unverified})


def with_outcome(spec: WorkflowSpec) -> WorkflowSpec:
    """The run-time spec: the declared units plus the compiled outcome unit, if the workflow has one."""
    u = outcome_unit(spec)
    if u is None or flow.OUTCOME_UNIT in spec.units:
        return spec
    return dataclasses.replace(spec, units={**spec.units, flow.OUTCOME_UNIT: u})


def deliverable_producers(spec: WorkflowSpec) -> dict[str, list[str]]:
    """Each deliverable key and the units that declare they produce it."""
    o = spec.outcome
    out: dict[str, list[str]] = {}
    for d in (o.deliverables if o else ()):
        key = str(d.get("key") or "")
        for name in spec.order:
            u = spec.units[name]
            keys = set(u.step.produces) if u.step else set()
            for sc in ((u.step.before + u.step.after) if u.step else ()) + ((u.script,) if u.script else ()):
                keys |= set(sc.produces)
            if u.kind == "ask":
                keys.add("answers")
            if key in keys:
                out.setdefault(key, []).append(name)
    return out


def _on_every_path(spec: WorkflowSpec) -> set[str]:
    """Units no route, switch, fallback or deadline can skip: a workflow with none of them runs all its units."""
    skipping = any(u.route is not None or u.switch is not None or u.gate.fallback or name in spec.flow
                   or flow.deadline_node(spec, name) for name, u in spec.units.items())
    return set() if skipping else set(spec.order)


def outcome_check(ctx: Any) -> CheckResult:
    """The built-in check: every deliverable exists; then the workflow's own outcome check, if any."""
    findings: list[CheckFinding] = []
    deliverables = (ctx.settings or {}).get("deliverables") or []
    arts = {k: v for vs in (ctx.artifacts or {}).values() if isinstance(vs, Mapping) for k, v in vs.items()}
    vals = {k: v for vs in (ctx.values or {}).values() if isinstance(vs, Mapping) for k, v in vs.items()}
    producers = (ctx.settings or {}).get("deliverable_producers") or {}
    path = set((ctx.settings or {}).get("path_units") or ())
    off_path = 0
    for d in deliverables:
        key, kind = str(d.get("key") or ""), str(d.get("kind") or "file")
        made_by = producers.get(key) or []
        if made_by and path and not path & set(made_by):  # OUT §2.4: required only on a path that produces it
            off_path += 1
            continue
        present = key in arts or key in vals
        if present and kind == "file" and key in arts:
            present = (ctx.workdir / str(arts[key])).exists()
        if not present:
            findings.append(CheckFinding(status="fail", criterion=None, place=str(d.get("where") or key),
                                         message=f"deliverable {key} is missing", fix=f"produce {key}"))
    result: CheckResult = CheckResult(result="FAIL" if findings else "PASS", findings=findings,
                                      evidence=f"{len(deliverables) - len(findings) - off_path} of "
                                               f"{len(deliverables) - off_path} deliverables present"
                                               + (f"; {off_path} not produced on this path" if off_path else ""))
    ref = (ctx.settings or {}).get("outcome_check")
    if ref and not findings:
        mod, _, qual = str(ref).partition(":")
        own = CallableRef(module=mod, qualname=qual).resolve()(ctx)
        if isinstance(own, CheckResult):
            own.evidence = (result.evidence + "\n" + own.evidence).strip()
            return own
    return result


def derived_back(spec: WorkflowSpec, failing: list[str], path: list[str]) -> str | None:
    """OUT §2.4: the earliest unit on the path whose criterion serves a failing final criterion."""
    o = spec.outcome
    if o is None:
        return None
    for unit in flow.effective_order(spec):
        if unit not in path:
            continue
        io = o.intermediate.get(unit)
        if io and any(set(c.serves) & set(failing) for c in io.criteria):
            return unit
    return None
