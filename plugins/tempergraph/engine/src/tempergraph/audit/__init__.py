"""`tempergraph audit` (AUD, ARC, PRA): advisory, read-only, model-free (contract C13).

Release 1 runs the `definition` and `host` layers and the prompt audit; the `history` layer (X2-9) and the
tool-surface audit (TSA, X2-10) are release 2, so their rules are listed as skipped, never as passed.
Owned checks (validation, prompt lint, the readiness report, executor compatibility) are run through
their component and rendered under `<owner>:<code>` (ADR-0054, AUD-B8).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.audit.catalog import RULES, Layer
from tempergraph.audit.definition import Definition
from tempergraph.audit.host import Host, HostInputs, ShellTiming, shell_timing
from tempergraph.audit.report import AuditFinding, AuditReport, Ignore, apply_ignores, order, parse_ignores
from tempergraph.constants import ENGINE_VERSION
from tempergraph.contracts import Capabilities, WorkflowSpec
from tempergraph.model.validate import Finding, validate

BUILT_LAYERS: frozenset[Layer] = frozenset({"definition", "host"})
CONFIDENCE = {"lint-vague-word": "medium", "lint-rule-branching": "medium", "lint-human-wait": "medium",
              "lint-self-grading": "medium", "lint-accepting-brief": "medium"}


@dataclass(kw_only=True)
class AuditContext:
    target: Path
    caps: Mapping[str, Capabilities]
    probe: Callable[[str], str | None] = lambda name: None
    timing: Callable[[float], ShellTiming | None] = shell_timing
    which: Callable[[str], str | None] | None = None
    plugin_cache: Path | None = None
    window_days: int = 30
    version: str = "current"
    executor: str | None = None
    steps: tuple[str, ...] = ()
    show_all: bool = False
    today: dt.date = field(default_factory=dt.date.today)


def _decl_file(spec: WorkflowSpec, manifest: Any) -> str:
    root = spec.package_root
    if root is None or manifest is None:
        return "workflow"
    mod = str(manifest.entry).partition(":")[0]
    for rel in (f"workflow/{mod}/__init__.py", f"workflow/{mod}.py"):
        if (root / rel).is_file():
            return rel
    return f"workflow/{mod}"


def _owned(found: list[Finding]) -> list[AuditFinding]:
    out = []
    for f in found:
        lint = f.code.startswith("lint-")
        owner = "prompt-lint" if lint else "validate"
        where, _, message = f.message.partition(": ") if lint else ("", "", f.message)
        file, _, line = where.partition(":")
        loc: dict[str, Any] = {}
        if file and not file.startswith("inline"):
            loc["file"] = file
            if line.isdigit():
                loc["line"] = int(line)
        out.append(AuditFinding(rule=f"{owner}:{f.code}", layer="definition", severity=f.severity,
                                confidence=CONFIDENCE.get(f.code, "high"), unit=f.unit, owner=owner,
                                statement=message or f.message, location=loc,
                                remedy="See the owning check's rule" + (" (LIF §2.1)" if lint else " (WFM §2.2)")))
    return out


def _readiness(spec: WorkflowSpec, already: set[str | None]) -> list[AuditFinding]:
    from tempergraph.package.readiness import readiness

    out = []
    for g in readiness(spec):
        if g.grade == "ready" or g.gate in already:  # stable mode: validation's `gate-not-ready` stands
            continue
        sev = "warning" if g.grade == "needs work" else "info"
        out.append(AuditFinding(rule=f"readiness:{g.grade.replace(' ', '-')}", layer="definition", severity=sev,
                                confidence="high", unit=g.gate, owner="readiness",
                                statement=f"judge readiness of {g.gate}: {g.grade}"
                                + (f" ({'; '.join(g.findings)})" if g.findings else ""),
                                evidence={"criteria": g.criteria, "blockers": g.blockers,
                                          "calibration_cases": g.calibration_cases, "acceptance": g.acceptance},
                                remedy="Fix the criteria the report names; calibrate the judge (LIF §2.2, JCL)"))
    return out


def audit(spec: WorkflowSpec, layers: set[Layer], ctx: AuditContext, *, manifest: Any = None,
          stamp: dict[str, Any] | None = None) -> AuditReport:
    """AUD §2.1: pure over its inputs, apart from the host layer's read-only probes."""
    rep = AuditReport(workflow=spec.name, version=spec.version, engine_version=ENGINE_VERSION,
                      window_days=ctx.window_days, show_all=ctx.show_all)
    found = validate(spec, ctx.caps)
    broken = any(f.severity == "error" for f in found)
    owned = _owned(found)
    owned += _readiness(spec, {f.unit for f in found if f.code == "gate-not-ready"})
    findings = list(owned)
    decl = _decl_file(spec, manifest)
    run: list[Layer] = []
    for layer in ("definition", "host", "history"):
        if layer not in layers:
            rep.layers_skipped.append({"layer": layer, "reason": "--layer not given"})
        elif layer not in BUILT_LAYERS:
            rep.layers_skipped.append({"layer": layer, "reason": "not in release 1 (release 2)"})
        elif broken and layer != "definition":
            rep.layers_skipped.append({"layer": layer, "reason": "the workflow does not validate"})
        else:
            run.append(layer)
    rep.layers_run = list(run)
    if "definition" in run:
        findings += _guarded(rep, "definition", lambda: Definition(spec, decl, dict(getattr(manifest, "surfaces", {})
                                                                                   or {})).run())
    if "host" in run:
        inputs = HostInputs(target=ctx.target, probe=ctx.probe, timing=ctx.timing, plugin_cache=ctx.plugin_cache,
                            stamp=stamp)
        if ctx.which is not None:
            inputs.which = ctx.which
        findings += _guarded(rep, "host", lambda: Host(spec, decl, inputs).run())
        rep.rules_skipped += inputs.skipped
    for r in RULES:
        if r.layer not in run:
            reason = ("not in release 1" if r.layer not in BUILT_LAYERS else
                      "the workflow does not validate" if broken else "--layer not given")
            entry: dict[str, Any] = {"rule": r.id, "reason": reason}
            if r.min_n is not None:
                entry["min_n"] = r.min_n
            rep.rules_skipped.append(entry)
        elif r.built > 1:
            rep.rules_skipped.append({"rule": r.id, "reason": _NOT_BUILT.get(r.id, f"release {r.built}")})
    findings = _narrow(spec, findings, ctx)
    findings = _dedupe(findings)
    ignores, _problems = parse_ignores(dict(getattr(manifest, "audit", {}) or {}).get("ignore"))
    findings += apply_ignores(findings, ignores, ctx.today)
    rep.findings = order(findings, spec.order)
    rep.owned = _owned_counts(owned)
    return rep


_NOT_BUILT = {
    "outcome-unverified-blocker": "owner not present: OUT trust and coverage (plan T5.8.1)",
    "outcome-uncovered": "owner not present: OUT trust and coverage (plan T5.8.1)",
    "unbounded-wait": "kind not in release 1 (wait and ask are release 2)",
}


def _guarded(rep: AuditReport, layer: str, fn: Callable[[], list[AuditFinding]]) -> list[AuditFinding]:
    """AUD §4: a rule that raises is skipped with reason `rule error`; the report continues."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger("tempergraph").warning("audit rule error in %s: %s", layer, type(exc).__name__)
        rep.rules_skipped.append({"rule": f"{layer} layer", "reason": f"rule error ({type(exc).__name__})"})
        return []


def _narrow(spec: WorkflowSpec, findings: list[AuditFinding], ctx: AuditContext) -> list[AuditFinding]:
    keep: set[str] | None = None
    if ctx.steps:
        keep = set(ctx.steps)
    if ctx.executor:
        bound = {n for n, u in spec.units.items() if u.step is not None
                 and (u.step.executor or spec.default_executor) == ctx.executor}
        keep = bound if keep is None else keep & bound
    if keep is None:
        return findings
    return [f for f in findings if f.unit is None or f.unit in keep]


def _dedupe(findings: list[AuditFinding]) -> list[AuditFinding]:
    """One finding per (rule, unit, item) (AUD §2.3)."""
    seen: set[tuple[Any, ...]] = set()
    out = []
    for f in findings:
        key = (*f.key, f.location.get("file"), f.statement if f.owner != "audit" else "")
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def _owned_counts(owned: list[AuditFinding]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for f in owned:
        counts[f.owner] = counts.get(f.owner, 0) + 1
    return [{"owner": k, "count": v} for k, v in sorted(counts.items())]


def audit_layers(given: list[str] | None) -> set[Layer]:
    """`--layer` given: those; otherwise every layer whose inputs exist (AUD §2.1)."""
    return set(given) if given else {"definition", "host", "history"}  # type: ignore[arg-type]


__all__ = ["AuditContext", "AuditFinding", "AuditReport", "Ignore", "audit", "audit_layers", "parse_ignores"]
