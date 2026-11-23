"""`tempergraph audit` (AUD, ARC, TSA, PRA): advisory, read-only, model-free (OVR-B15).

Release 3 runs the `definition`, `host` and `history` layers, the tool-surface audit and the prompt audit. The
`history` layer reads the workflow's local run records once (`audit.history`) and every history rule reads those
facts only; a rule with fewer runs than its `min_n` is listed as skipped with `n=<runs> of <min>`, a layer with no
runs as skipped with `no runs in window`, never as passed (AUD-B1, AUD-B5). Owned checks (validation, prompt lint,
the readiness report, executor compatibility, the cost lens and the engine's own findings) are run through their
component and rendered under `<owner>:<code>` (ADR-0054, AUD-B8).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.audit.catalog import RULES, Layer
from tempergraph.audit.definition import Definition
from tempergraph.audit.history import HistoryFacts
from tempergraph.audit.history_rules import HISTORY_C1_C3, RuleSkipped, hot_spots
from tempergraph.audit.history_rules_more import HISTORY_C5_C8, SAMPLE_N
from tempergraph.audit.host import Host, HostInputs, ShellTiming, shell_timing
from tempergraph.audit.owned import HISTORY_OWNED
from tempergraph.audit.report import AuditFinding, AuditReport, Ignore, apply_ignores, order, parse_ignores
from tempergraph.audit.surface import build_surface
from tempergraph.audit.tools import TOOL_HISTORY, ToolRules, run_history
from tempergraph.constants import ENGINE_VERSION
from tempergraph.contracts import Capabilities, WorkflowSpec
from tempergraph.model.validate import Finding, validate

BUILT_LAYERS: frozenset[Layer] = frozenset({"definition", "host", "history"})
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
    history: HistoryFacts | None = None  # the facts of the runs in the window and version (AUD-B3, AUD-B11)
    tool_executor: str | None = None  # show every session on this executor's tool map (`audit tools --executor`)
    mcp_servers: Callable[[], set[str] | None] | None = None  # the MCP servers of the operator's own configuration
    ambient_tools: Callable[[str], list[str] | None] | None = None  # plugin tools a probe lists for an executor


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
                                remedy="See the owning check's rule" + (" (LIF-B12)" if lint else " (WFM-B12)")))
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
                                remedy="Fix the criteria the report names; calibrate the judge (LIF-B13, JCL)"))
    return out


def audit(spec: WorkflowSpec, layers: set[Layer], ctx: AuditContext, *, manifest: Any = None,
          stamp: dict[str, Any] | None = None) -> AuditReport:
    """AUD-B11, AUD-B6, AUD-B9: pure over its inputs, apart from the host layer's read-only probes."""
    rep = AuditReport(workflow=spec.name, version=spec.version, engine_version=ENGINE_VERSION,
                      window_days=ctx.window_days, show_all=ctx.show_all)
    found = validate(spec, ctx.caps)
    broken = any(f.severity == "error" for f in found)
    owned = _owned(found)
    owned += _readiness(spec, {f.unit for f in found if f.code == "gate-not-ready"})
    findings = list(owned)
    decl = _decl_file(spec, manifest)
    run: list[Layer] = []
    why: dict[str, str] = {}
    facts = ctx.history
    if facts is not None:
        rep.runs, rep.unreadable_runs = facts.runs, facts.unreadable
    for layer in ("definition", "host", "history"):
        if layer not in layers:
            why[layer] = "--layer not given"
        elif layer not in BUILT_LAYERS:
            why[layer] = "not in this release"
        elif broken and layer != "definition":
            why[layer] = "the workflow does not validate"
        elif layer == "history" and (facts is None or facts.runs == 0):
            why[layer] = "no runs in window"
        else:
            run.append(layer)
            continue
        rep.layers_skipped.append({"layer": layer, "reason": why[layer]})
    rep.layers_run = list(run)
    tools = _tools(spec, ctx, rep, run, manifest, decl, stamp)  # the session surface, built once per audit
    if "definition" in run:
        findings += _guarded(rep, "definition", lambda: Definition(spec, decl, dict(getattr(manifest, "surfaces", {})
                                                                                   or {})).run())
        if tools is not None:
            findings += _guarded(rep, "tools definition", tools.definition)
    if "host" in run:
        inputs = HostInputs(target=ctx.target, probe=ctx.probe, timing=ctx.timing, plugin_cache=ctx.plugin_cache,
                            stamp=stamp)
        if ctx.which is not None:
            inputs.which = ctx.which
        findings += _guarded(rep, "host", lambda: Host(spec, decl, inputs).run())
        rep.rules_skipped += inputs.skipped
        if tools is not None:
            findings += _guarded(rep, "tools host", tools.host)
            rep.rules_skipped += tools.skipped
    if "history" in run and facts is not None:
        hist = _history_layer(spec, ctx, rep, facts, tools)
        findings += hist
        owned += [f for f in hist if f.owner != "audit"]
    for r in RULES:
        if r.layer not in run:
            entry: dict[str, Any] = {"rule": r.id, "reason": why.get(r.layer, "--layer not given")}
            if r.min_n is not None:
                entry["min_n"] = r.min_n
            rep.rules_skipped.append(entry)
        elif r.id in _NOT_BUILT:
            rep.rules_skipped.append({"rule": r.id, "reason": _NOT_BUILT[r.id]})
    findings = _narrow(spec, findings, ctx)
    findings = _dedupe(findings)
    ignores, _problems = parse_ignores(dict(getattr(manifest, "audit", {}) or {}).get("ignore"))
    findings += apply_ignores(findings, ignores, ctx.today)
    rep.findings = order(findings, spec.order)
    rep.owned = _owned_counts(owned)
    return rep


_NOT_BUILT = {  # definition rules whose unit kinds the engine does not build yet (ARC-B15)
    "unbounded-wait": "kind not in release 1 (wait and ask are release 2)",
    "council-one-family": "the council unit is not built yet",
    "council-even-majority": "the council unit is not built yet",
}


def _tools(spec: WorkflowSpec, ctx: AuditContext, rep: AuditReport, run: list[Layer], manifest: Any, decl: str,
           stamp: dict[str, Any] | None) -> ToolRules | None:
    """TSA-B6: the session surface, built once from the tool maps, the manifest and (with history) the recorded use,
    shared by the C4 rules and by `audit tools`."""
    if not run:
        return None
    try:
        surface = build_surface(spec, ctx.caps, manifest, ctx.history if "history" in run else None,
                                executor=ctx.tool_executor)
    except Exception as exc:  # noqa: BLE001 - AUD-B15: the rules that need the surface are skipped
        import logging

        logging.getLogger("tempergraph").warning("audit surface error: %s", type(exc).__name__)
        rep.rules_skipped.append({"rule": "tool surface", "reason": f"rule error ({type(exc).__name__})"})
        return None
    rep.surface = surface
    return ToolRules(spec, surface, ctx.caps, decl, stamp=stamp, plugin_cache=ctx.plugin_cache,
                     mcp_servers=ctx.mcp_servers, ambient_tools=ctx.ambient_tools)

HistoryRule = Callable[[WorkflowSpec, HistoryFacts], list[AuditFinding] | None]
# rule id -> its function; None back means the owner is not present
HISTORY_RULES: dict[str, HistoryRule] = {**HISTORY_C1_C3, **HISTORY_C5_C8, **HISTORY_OWNED}


def sample_n(rule_id: str, facts: HistoryFacts) -> int:
    """The sample a history rule counts: the runs in the window, or the records of its own shape (AUD-B5)."""
    count = SAMPLE_N.get(rule_id)
    return count(facts) if count is not None else facts.runs


def _history_layer(spec: WorkflowSpec, ctx: AuditContext, rep: AuditReport, facts: HistoryFacts,
                   tools: ToolRules | None = None) -> list[AuditFinding]:
    """AUD-B3, AUD-B5, ARC-B7: every history rule on the facts; below `min_n` it is skipped with `n=<runs> of <min>`."""
    out: list[AuditFinding] = []
    for r in RULES:
        if r.layer != "history":
            continue
        n, need = sample_n(r.id, facts), r.min_n or 1
        if n < need:
            rep.rules_skipped.append({"rule": r.id, "reason": f"n={n} of {need}", "min_n": need})
            continue
        fn: HistoryRule | None = HISTORY_RULES.get(r.id)
        if r.id in TOOL_HISTORY:
            if tools is None:
                rep.rules_skipped.append({"rule": r.id, "reason": "tool surface not built", "min_n": need})
                continue
            fn = lambda _s, f, rid=r.id: run_history(tools, rid, f)  # noqa: E731
        if fn is None:
            rep.rules_skipped.append({"rule": r.id, "reason": "not built", "min_n": need})
            continue
        try:
            got = fn(spec, facts)
        except RuleSkipped as why:
            rep.rules_skipped.append({"rule": r.id, "reason": why.reason, "min_n": need})
            continue
        except Exception as exc:  # noqa: BLE001 - AUD-B15: a rule that raises is skipped, the report continues
            import logging

            logging.getLogger("tempergraph").warning("audit rule error in %s: %s", r.id, type(exc).__name__)
            rep.rules_skipped.append({"rule": r.id, "reason": f"rule error ({type(exc).__name__})", "min_n": need})
            continue
        if got is None:
            rep.rules_skipped.append({"rule": r.id, "reason": "owner not present", "min_n": need})
            continue
        out += got
    rep.hot_spots = hot_spots(facts, out)
    return out


def _guarded(rep: AuditReport, layer: str, fn: Callable[[], list[AuditFinding]]) -> list[AuditFinding]:
    """AUD-B15, AUD-B9, AUD-B2: a rule that raises is skipped with reason `rule error`; the report continues."""
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
    """One finding per (rule, unit, item) (AUD-B7, AUD-B12)."""
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
    """`--layer` given: those; otherwise every layer whose inputs exist (AUD-B11, AUD-B6, AUD-B9)."""
    return set(given) if given else {"definition", "host", "history"}  # type: ignore[arg-type]


__all__ = ["AuditContext", "AuditFinding", "AuditReport", "Ignore", "audit", "audit_layers", "parse_ignores"]
