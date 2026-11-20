"""The blueprint (SCF §2.1): a strict JSON document of the decided shape; `blueprint check` turns it into a
throwaway spec with stub prompts and gates, validates it, and checks it against the draft outcome.
Model-free and read-only (C13)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.api import Criterion, Gate, Judge, Route, Routing, Script, Step, Switch, Workflow
from tempergraph.contracts import (
    Capabilities,
    InputDeclaration,
    OutcomeSpec,
    Param,
    ProducesKind,
    WorkflowSpec,
)
from tempergraph.model.validate import LATER_KINDS, SLUG_RE, Finding, validate

BLUEPRINT_FILE = "blueprint.json"
TOP_KEYS = frozenset({"schema_version", "name", "units", "flow", "outcome_ref", "input"})
UNIT_KEYS = frozenset({"name", "kind", "summary", "produces", "reads", "gate", "on_fail", "on_budget_spent",
                       "approval", "back_targets", "executor"})
GATE_KEYS = frozenset({"check", "judge", "signoff"})
RELEASE_KINDS = frozenset({"step", "script", "route", "switch"})
FLOW_KINDS = frozenset({"route", "switch", "parallel", "map", "wait"})
MAX_UNITS = 20
SUMMARY_CHARS = 60
# Validation findings that are a reference problem of the shape; a blueprint check fails on them (SCF-B2).
REFERENCE_WARNINGS = frozenset({"template-key-not-on-every-path"})


def stub_check(ctx: Any) -> Any:  # pragma: no cover - never run; only referenced by the throwaway spec
    raise RuntimeError("blueprint stub")


def stub_select(view: Any) -> str:  # pragma: no cover
    raise RuntimeError("blueprint stub")


@dataclass(frozen=True, kw_only=True)
class BlueprintUnit:
    name: str
    kind: str
    summary: str = ""
    produces: tuple[str, ...] = ()
    reads: tuple[str, ...] = ()
    check: bool = False
    judge: bool = False
    signoff: bool = False
    on_fail: str | None = None
    on_budget_spent: str | None = None
    approval: bool | None = None
    back_targets: tuple[str, ...] = ()
    executor: str | None = None


@dataclass(frozen=True, kw_only=True)
class Blueprint:
    name: str
    units: tuple[BlueprintUnit, ...]
    flow: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    outcome_ref: Mapping[str, Any] | None = None
    input: Mapping[str, Any] = field(default_factory=dict)
    raw: Mapping[str, Any] = field(default_factory=dict)

    def unit(self, name: str) -> BlueprintUnit | None:
        return next((u for u in self.units if u.name == name), None)


def digest(doc: Any) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


def _f(code: str, unit: str | None, message: str) -> Finding:
    return Finding(code, unit, message, "error")


def _strs(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) and x for x in v)


def parse(data: Any) -> Blueprint | list[Finding]:
    """SCF §2.1: an unknown key is an error, so a misspelt field is reported, never drawn (SCF-B1)."""
    out: list[Finding] = []
    if not isinstance(data, dict):
        return [_f("blueprint-invalid", None, "the blueprint must be a JSON object")]
    for k in sorted(set(data) - TOP_KEYS):
        out.append(_f("unknown_key", None, f"$.{k} is not a blueprint field"))
    if data.get("schema_version") != 1:
        out.append(_f("blueprint-invalid", None, f"$.schema_version {data.get('schema_version')!r} is unknown"))
    name = data.get("name")
    if not isinstance(name, str) or not SLUG_RE.match(name):
        out.append(_f("blueprint-invalid", None, f"$.name {name!r} is not a slug"))
    raw_units = data.get("units")
    units: list[BlueprintUnit] = []
    if not isinstance(raw_units, list) or not (1 <= len(raw_units) <= MAX_UNITS):
        out.append(_f("blueprint-invalid", None, f"$.units must list 1 to {MAX_UNITS} units"))
        raw_units = raw_units if isinstance(raw_units, list) else []
    for i, u in enumerate(raw_units):
        at = f"$.units[{i}]"
        if not isinstance(u, dict):
            out.append(_f("blueprint-invalid", None, f"{at} must be an object"))
            continue
        uname = u.get("name") if isinstance(u.get("name"), str) else None
        for k in sorted(set(u) - UNIT_KEYS):
            out.append(_f("unknown_key", uname, f"{at}.{k} is not a unit field"))
        if not uname or not SLUG_RE.match(uname):
            out.append(_f("blueprint-invalid", uname, f"{at}.name {u.get('name')!r} is not a slug"))
            continue
        kind = u.get("kind", "step")
        if kind in LATER_KINDS:
            out.append(_f("not_in_release", uname, f"{at}.kind {kind!r} is built in release {LATER_KINDS[kind]}"))
        elif kind not in RELEASE_KINDS:
            out.append(_f("blueprint-invalid", uname, f"{at}.kind {kind!r} is not a unit kind"))
        summary = u.get("summary", "")
        if not isinstance(summary, str) or len(summary) > SUMMARY_CHARS:
            out.append(_f("summary-too-long", uname, f"{at}.summary is over {SUMMARY_CHARS} characters"))
        for key in ("produces", "reads", "back_targets"):
            if key in u and not _strs(u[key]):
                out.append(_f("blueprint-invalid", uname, f"{at}.{key} must be a list of names"))
        gate = u.get("gate", {})
        if not isinstance(gate, dict):
            out.append(_f("blueprint-invalid", uname, f"{at}.gate must be an object"))
            gate = {}
        for k in sorted(set(gate) - GATE_KEYS):
            out.append(_f("unknown_key", uname, f"{at}.gate.{k} is not a gate field"))
        units.append(BlueprintUnit(
            name=uname, kind=str(kind), summary=str(summary or ""),
            produces=tuple(u.get("produces") or ()) if _strs(u.get("produces") or []) else (),
            reads=tuple(u.get("reads") or ()) if _strs(u.get("reads") or []) else (),
            check=bool(gate.get("check")), judge=bool(gate.get("judge")), signoff=bool(gate.get("signoff")),
            on_fail=u.get("on_fail"), on_budget_spent=u.get("on_budget_spent"), approval=u.get("approval"),
            back_targets=tuple(u.get("back_targets") or ()) if _strs(u.get("back_targets") or []) else (),
            executor=u.get("executor")))
    flow = data.get("flow", {})
    if not isinstance(flow, dict):
        out.append(_f("blueprint-invalid", None, "$.flow must map a unit to its shape"))
        flow = {}
    for unit, shape in flow.items():
        if not isinstance(shape, dict) or len(shape) != 1 or next(iter(shape)) not in FLOW_KINDS:
            out.append(_f("blueprint-invalid", unit, f"$.flow.{unit} must be one of {sorted(FLOW_KINDS)}"))
            continue
        kind = next(iter(shape))
        if kind in ("parallel", "map", "wait"):
            out.append(_f("not_in_release", unit, f"$.flow.{unit}.{kind} is built in release 2"))
    for key in ("outcome_ref", "input"):
        if key in data and not isinstance(data[key], dict):
            out.append(_f("blueprint-invalid", None, f"$.{key} must be an object"))
    if out:
        return out
    return Blueprint(name=str(name), units=tuple(units), flow=dict(flow), outcome_ref=data.get("outcome_ref"),
                     input=dict(data.get("input") or {}), raw=data)


def read(path: Path) -> Blueprint | list[Finding]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [_f("blueprint-invalid", None, f"{path.name}: {type(exc).__name__}")]
    return parse(data)


def to_spec(bp: Blueprint) -> WorkflowSpec:
    """The throwaway spec: stub prompts that name each read, stub gates, the blueprint's policies."""
    units: dict[str, Any] = {}
    for u in bp.units:
        shape = dict(bp.flow.get(u.name) or {})
        gate_kw: dict[str, Any] = {"check": stub_check if u.check else None,
                                   "judge": Judge(stance="stub", brief="stub", references=list(u.reads))
                                   if u.judge else None,
                                   "criteria": [Criterion(id=f"{u.name}-stub", text="stub", check_method="stub")]
                                   if u.judge else [],
                                   "approval": bool(u.approval) or u.signoff, "back_targets": list(u.back_targets)}
        if u.on_fail:
            gate_kw["on_fail"] = u.on_fail
        if u.on_budget_spent:
            gate_kw["on_budget_spent"] = u.on_budget_spent
        gate = Gate(**gate_kw)
        prompt = f"Stub for {u.name}." + "".join(f" {{{r}}}" for r in u.reads)
        produces: dict[str, ProducesKind] = {k: "file" for k in u.produces}
        if u.kind == "script":
            units[u.name] = Script(call=stub_check, produces=produces, inputs=list(u.reads), gate=gate)
        elif u.kind == "route":
            units[u.name] = Route(select=stub_select, targets=list(shape.get("route") or ()), gate=gate)
        elif u.kind == "switch":
            sw = shape.get("switch") or {}
            units[u.name] = Switch(predicate=stub_select, arms=dict(sw.get("arms") or {}),
                                   default=str(sw.get("default") or ""), gate=gate)
        else:
            route = list(shape.get("route") or ())
            units[u.name] = Step(prompt=prompt, tools=["read", "write"], produces=produces, executor=u.executor,
                                 summary=u.summary, gate=gate, route=stub_select if route else None,
                                 route_targets=route)
    inp = bp.input
    spec = Workflow(order=[u.name for u in bp.units], units=units,
                    routing=Routing(description=f"Blueprint of {bp.name}"), issue_repository="blueprint/check",
                    input=InputDeclaration(kind=inp.get("kind", "text"),
                                           parameters=tuple(Param(name=str(p)) for p in inp.get("parameters") or ())))
    import dataclasses

    return dataclasses.replace(spec, name=bp.name, version="0.0.0")


def check(bp: Blueprint, caps: Mapping[str, Capabilities], outcome: OutcomeSpec | None = None,
          outcome_doc: Any = None) -> list[Finding]:
    """`blueprint check` (SCF §2.1): WFM validation of the throwaway spec, then the outcome cross-check."""
    from tempergraph.run.outcome import check_against

    spec = to_spec(bp)
    found = [f for f in validate(spec, caps) if not f.code.startswith("lint-")]
    out = [f if f.severity == "error" else _f(f.code, f.unit, f.message) for f in found
           if f.severity == "error" or f.code in REFERENCE_WARNINGS]
    if outcome is None:
        return out
    out += [f for f in check_against(outcome, spec) if f.severity == "error"]
    if bp.outcome_ref is not None and outcome_doc is not None:
        ref = bp.outcome_ref
        if ref.get("digest") != digest(outcome_doc) or ref.get("revision") != outcome.revision:
            out.append(_f("blueprint_outcome_mismatch", None, "outcome_ref does not match the outcome draft "
                          f"(revision {outcome.revision}); the approval is cleared"))
    for u in bp.units:
        io = outcome.intermediate.get(u.name)
        crits = io.criteria if io else ()
        has_check = any(c.verified_by == "check" for c in crits)
        if u.check and not has_check:
            out.append(_f("blueprint-check-without-criterion", u.name, f"{u.name}'s gate has a check but no "
                          "`check` criterion"))
        if has_check and not u.check:
            out.append(_f("blueprint-criterion-without-check", u.name, f"{u.name} has a `check` criterion but its "
                          "gate has no check"))
        if u.signoff != any(c.verified_by == "person" for c in crits):
            out.append(_f("blueprint-signoff-mismatch", u.name, f"{u.name}: the blueprint's sign-off and the "
                          "outcome's `person` criteria disagree"))
    return out
