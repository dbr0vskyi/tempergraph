"""Refuse before spend (EXI-B1, OVR-B17).

Runs with no model call. Validation already refuses unknown executors, unbound tier aliases, unmapped
tools and unsupported options against the registered capability sets; the preflight adds what needs the
registry and the machine: each executor's probe, executor-qualified aliases against the binding table,
judge executor selection (EXI-B24), tool enforcement (EXI-B12) and deferred judge MCP views.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from tempergraph import executor_compat
from tempergraph.contracts import Deferred, JudgeSpec, ProbeReport, UnitSpec, WorkflowSpec
from tempergraph.executors.registry import NoJudgeExecutor, Registry, UnknownExecutor
from tempergraph.model.validate import Finding, validate


@dataclass(kw_only=True)
class PreflightReport:
    refusals: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    authoring_warnings: list[Finding] = field(default_factory=list)
    judges: dict[str, str] = field(default_factory=dict)  # unit -> judge executor
    step_executors: dict[str, str] = field(default_factory=dict)
    probes: dict[str, ProbeReport] = field(default_factory=dict)
    deferred: dict[str, list[Deferred]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.refusals

    def first(self) -> Finding | None:
        return self.refusals[0] if self.refusals else None


def observer_warnings(missing: Sequence[str]) -> list[Finding]:
    """EVT-B23: an observer the operator config names that is not installed is a warning, never a refusal."""
    return [Finding("observer-missing", None,
                    f"observer {name!r} is named in the operator config but not installed under the "
                    "`tempergraph.observers` entry-point group; the run starts without it", "warning")
            for name in missing]


def _aliases(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]  # type: ignore[attr-defined]


def _slot_overrides(rep: PreflightReport, caps: dict, probe: Callable[[str, str], bool], unit: str, u: UnitSpec,
                    base: str) -> None:
    """CTS-B10: a slot override whose executor cannot bind its model alias or map the step's tools is refused, each with a
    code of its own; an executor that is not registered is refused as well."""
    assert u.contest is not None and u.step is not None and not isinstance(u.contest.slots, int)
    for slot in u.contest.slots:
        name = slot.executor or base
        if name not in caps:
            rep.refusals.append(Finding("contest-slot-executor-unknown", unit,
                                        f"slot {slot.name!r} of {unit!r} names executor {name!r}, which is not registered"))
            continue
        if slot.executor is not None and not probe(name, unit):
            continue
        c = caps[name]
        if slot.model and slot.model != "inherit":
            alias = slot.model
            if alias not in c.binds_aliases:
                rep.refusals.append(Finding("contest-slot-alias-unbound", unit,
                                            f"slot {slot.name!r} of {unit!r}: executor {name!r} binds no {alias!r}"))
        for tool in u.step.tools:
            if not c.maps(tool):
                rep.refusals.append(Finding("contest-slot-tool-unmapped", unit,
                                            f"slot {slot.name!r} of {unit!r}: executor {name!r} maps no tool for {tool!r}"))


def preflight(spec: WorkflowSpec, registry: Registry, *, judge_override: str | None = None,
              enforce_tools: bool = False, strict_permissions: bool = False) -> PreflightReport:
    rep = PreflightReport()
    caps = {n: registry.get(n).capabilities() for n in registry.available()}
    for f in validate(spec, caps):
        if f.severity == "error":
            rep.refusals.append(f)
        else:
            rep.authoring_warnings.append(f)

    def probe(name: str, unit: str) -> bool:
        if name not in rep.probes:
            try:
                rep.probes[name] = registry.get(name).probe()
            except UnknownExecutor:
                return False
            caps[name] = registry.get(name).capabilities()  # now carries the probed version
        p = rep.probes[name]
        untested = executor_compat.finding(name, p.version) if p.ok else None  # LIF-AC4
        if untested is not None and untested not in rep.warnings:
            rep.warnings.append(untested)
        if not p.ok:
            rep.refusals.append(Finding("executor-probe-failed", unit, f"executor {name!r}: {p.reason}"))
        return p.ok

    def judge_of(unit: str, ex: str, j: JudgeSpec, tools: Sequence[str]) -> None:
        """The judge of a unit's gate on its own layer: its executor, its alias and the MCP views it cannot reach."""
        try:
            judge_ex = registry.judge_executor(ex, j.executor, judge_override)
        except (NoJudgeExecutor, UnknownExecutor) as exc:
            rep.refusals.append(Finding("judge-executor-none", unit, str(exc)))
            return
        if not probe(judge_ex, unit):
            return
        jc = caps[judge_ex]
        if not (jc.restricts_judge_tools and jc.prompt_off_argv):
            rep.refusals.append(Finding("judge-executor-unrestricted", unit,
                                        f"judge executor {judge_ex!r} cannot hold a judge to read-only tools"))
            return
        rep.judges[unit] = judge_ex
        if j.model and j.model not in jc.binds_aliases:
            rep.refusals.append(Finding("alias-unbound", unit, f"judge executor {judge_ex!r} binds no {j.model!r}"))
        mcp = [t for t in tools if t.startswith("mcp:")]
        if mcp and not jc.judge_mcp:
            rep.deferred[unit] = [Deferred(capability=t, reason="judge_mcp") for t in mcp]
            rep.warnings.append(Finding("judge-view-deferred", unit,
                                        f"judge views of {', '.join(mcp)} are out of reach on {judge_ex!r}",
                                        "warning"))

    def council(unit: str, u: UnitSpec) -> None:
        """CNL-B6: each member's alias and tools are checked against its own executor (validation reports a tool the
        executor maps no name for, this adds the probe, the binding table and enforcement), the chair on its own layer
        and the judge on the gate's; a gap is a refusal, and the run starts nothing."""
        c = u.council
        assert c is not None
        sessions = [(f"member {m.name!r}", f"{unit}.member:{m.name}", m.executor, m.model, m.tools) for m in c.members]
        if c.chair is not None:
            sessions.append(("the chair", f"{unit}.chair", c.chair.executor, c.chair.model, ()))
        for who, key, named, alias, tools in sessions:
            ex = named or spec.default_executor
            rep.step_executors[key] = ex
            if ex not in caps or not probe(ex, unit):
                continue
            cap = caps[ex]
            if alias and alias.startswith(ex + ":") and alias not in cap.binds_aliases:
                rep.refusals.append(Finding("alias-unbound", unit, f"{who}: the binding table has no {alias!r}"))
            if tools and (enforce_tools or strict_permissions) and not cap.enforces_step_tools:
                rep.refusals.append(Finding("enforcement-unsupported", unit,
                                            f"{who}: executor {ex!r} cannot enforce the member's declared tools"))
        if u.gate.judge is not None:
            judge_of(unit, spec.default_executor, u.gate.judge, ())

    for unit in spec.order:
        u = spec.units[unit]
        st = u.step
        if u.kind == "council" and u.council is not None:
            council(unit, u)
            continue
        if u.kind not in ("step", "map", "contest") or st is None:
            continue
        ex = st.executor or spec.default_executor
        rep.step_executors[unit] = ex
        if u.contest is not None and not isinstance(u.contest.slots, int):
            _slot_overrides(rep, caps, probe, unit, u, ex)  # CTS-B10: each slot's own executor and model
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
        if u.gate.judge is not None:
            judge_of(unit, ex, u.gate.judge, st.tools)
    return rep
