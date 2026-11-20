"""Refuse before spend (EXI-B1, contract C15).

Runs with no model call. Validation already refuses unknown executors, unbound tier aliases, unmapped
tools and unsupported options against the registered capability sets; the preflight adds what needs the
registry and the machine: each executor's probe, executor-qualified aliases against the binding table,
judge executor selection (EXI §2.4), tool enforcement (EXI-B12) and deferred judge MCP views.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tempergraph import executor_compat
from tempergraph.contracts import Deferred, ProbeReport, WorkflowSpec
from tempergraph.executors.registry import NoJudgeExecutor, Registry, UnknownExecutor
from tempergraph.model.validate import Finding, validate


@dataclass(kw_only=True)
class PreflightReport:
    refusals: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    judges: dict[str, str] = field(default_factory=dict)  # unit -> judge executor
    step_executors: dict[str, str] = field(default_factory=dict)
    probes: dict[str, ProbeReport] = field(default_factory=dict)
    deferred: dict[str, list[Deferred]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.refusals

    def first(self) -> Finding | None:
        return self.refusals[0] if self.refusals else None


def _aliases(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]  # type: ignore[attr-defined]


def preflight(spec: WorkflowSpec, registry: Registry, *, judge_override: str | None = None,
              enforce_tools: bool = False, strict_permissions: bool = False) -> PreflightReport:
    rep = PreflightReport()
    caps = {n: registry.get(n).capabilities() for n in registry.available()}
    for f in validate(spec, caps):
        (rep.refusals if f.severity == "error" else rep.warnings).append(f)

    def probe(name: str, unit: str) -> bool:
        if name not in rep.probes:
            try:
                rep.probes[name] = registry.get(name).probe()
            except UnknownExecutor:
                return False
            caps[name] = registry.get(name).capabilities()  # now carries the probed version
        p = rep.probes[name]
        untested = executor_compat.finding(name, p.version) if p.ok else None  # LIF-AC-4
        if untested is not None and untested not in rep.warnings:
            rep.warnings.append(untested)
        if not p.ok:
            rep.refusals.append(Finding("executor-probe-failed", unit, f"executor {name!r}: {p.reason}"))
        return p.ok

    for unit in spec.order:
        u = spec.units[unit]
        st = u.step
        if u.kind != "step" or st is None:
            continue
        ex = st.executor or spec.default_executor
        rep.step_executors[unit] = ex
        if ex not in caps or not probe(ex, unit):
            continue
        c = caps[ex]
        for alias in _aliases(st.model) + _aliases(spec.model_profile.get(unit)):
            if alias.startswith(ex + ":") and alias not in c.binds_aliases:
                rep.refusals.append(Finding("alias-unbound", unit, f"the binding table has no {alias!r}"))
        if (enforce_tools or strict_permissions) and not c.enforces_step_tools:
            rep.refusals.append(Finding("enforcement-unsupported", unit,
                                        f"executor {ex!r} cannot enforce the step's declared tools"))
        if any(t.startswith("skill:") for t in st.tools) and not c.hosts_authoring_surface:
            rep.warnings.append(Finding("authoring-surface-missing", unit,
                                        f"executor {ex!r} loads no skills", "warning"))
        j = u.gate.judge
        if j is None:
            continue
        try:
            judge_ex = registry.judge_executor(ex, j.executor, judge_override)
        except (NoJudgeExecutor, UnknownExecutor) as exc:
            rep.refusals.append(Finding("judge-executor-none", unit, str(exc)))
            continue
        if not probe(judge_ex, unit):
            continue
        jc = caps[judge_ex]
        if not (jc.restricts_judge_tools and jc.prompt_off_argv):
            rep.refusals.append(Finding("judge-executor-unrestricted", unit,
                                        f"judge executor {judge_ex!r} cannot hold a judge to read-only tools"))
            continue
        rep.judges[unit] = judge_ex
        if j.model and j.model not in jc.binds_aliases:
            rep.refusals.append(Finding("alias-unbound", unit, f"judge executor {judge_ex!r} binds no {j.model!r}"))
        mcp = [t for t in st.tools if t.startswith("mcp:")]
        if mcp and not jc.judge_mcp:
            rep.deferred[unit] = [Deferred(capability=t, reason="judge_mcp") for t in mcp]
            rep.warnings.append(Finding("judge-view-deferred", unit,
                                        f"judge views of {', '.join(mcp)} are out of reach on {judge_ex!r}",
                                        "warning"))
    return rep
