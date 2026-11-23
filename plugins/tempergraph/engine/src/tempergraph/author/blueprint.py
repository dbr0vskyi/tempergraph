"""The blueprint (SCF-B9, SCF-B11): a strict JSON document of the decided shape; `blueprint check` turns it into a
throwaway spec with stub prompts and gates, validates it, and checks it against the draft outcome.
Model-free and read-only (OVR-B15)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.api import (
    Ask,
    Criterion,
    Gate,
    Judge,
    Map,
    Parallel,
    Question,
    Route,
    Routing,
    Script,
    Step,
    Switch,
    Wait,
    Workflow,
)
from tempergraph.contracts import (
    EFFORTS,
    Capabilities,
    InputDeclaration,
    OutcomeSpec,
    Param,
    ProducesKind,
    WorkflowSpec,
)
from tempergraph.model.validate import LATER_KINDS, SLUG_RE, Finding, validate
from tempergraph.package.manifest import name_problem

# The authoring blueprint states no sub-workflow, no contest and no council (SCF-B9): it cannot state slots or members,
# though the engine builds these kinds, so a blueprint keeps its `not_in_release` refusal of them.
BLUEPRINT_LATER_KINDS: dict[str, int] = {**LATER_KINDS, "subworkflow": 3, "contest": 3, "council": 3}
BLUEPRINT_FILE = "blueprint.json"
TOP_KEYS = frozenset({"schema_version", "name", "units", "flow", "outcome_ref", "input"})
UNIT_KEYS = frozenset({"name", "kind", "summary", "produces", "reads", "gate", "on_fail", "on_budget_spent",
                       "approval", "back_targets", "executor", "sizing", "judge_sizing"})
SIZING_KEYS = frozenset({"model", "effort", "why"})
SIZING_MIN_WORDS = 4
TIERS = ("small", "medium", "large")
GATE_KEYS = frozenset({"check", "judge", "signoff"})
RELEASE_KINDS = frozenset({"step", "script", "route", "switch", "map", "parallel", "ask", "wait"})
SESSION_UNIT_KINDS = frozenset({"step", "map"})  # kinds whose units run model sessions and so carry `sizing`
# A flow shape that belongs to one unit kind (SCF-B9, SCF-B11): the shape states that kind's parameters.
SHAPE_KIND = {"map": "map", "parallel": "parallel", "wait": "wait"}
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
    sizing: Mapping[str, str] | None = None  # the step's model, effort and why (SCF-B9, SCF-B11, SCF-B10)
    judge_sizing: Mapping[str, str] | None = None


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


def outcome_digest(doc: Any) -> str:
    """`outcome_ref.digest`: the outcome as canonical JSON without its `revisions` history, which records how
    the outcome changed rather than what it says (scaffold adds the `authored` entry; SCF-B11, SCF-B13, SCF-B15, SCF-B16, SCF-B17, SCF-B18, SCF-B19, SCF-B20, SCF-B22)."""
    if isinstance(doc, dict):
        doc = {k: v for k, v in doc.items() if k != "revisions"}
    return digest(doc)


def _f(code: str, unit: str | None, message: str) -> Finding:
    return Finding(code, unit, message, "error")


def _strs(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) and x for x in v)


def _sizing(unit: str, at: str, got: Any, needed: bool) -> list[Finding]:
    """SCF-B9, SCF-B11: every model step and every judge states its model tier, its effort and why (SCF-B10)."""
    if got is None:
        return [_f("sizing-missing", unit, f"{at} is missing: state the model, the effort and why")] if needed else []
    if not needed:
        return [_f("sizing-invalid", unit, f"{at} is set on a unit that runs no such session")]
    if not isinstance(got, dict) or set(got) != SIZING_KEYS or not all(isinstance(v, str) for v in got.values()):
        return [_f("sizing-invalid", unit, f"{at} takes exactly {sorted(SIZING_KEYS)} as text")]
    out = []
    tier = got["model"].rsplit(":", 1)[-1]
    if got["model"] == "inherit" or not tier or (":" not in got["model"] and tier not in TIERS):
        out.append(_f("sizing-invalid", unit, f"{at}.model {got['model']!r} is not a tier of {sorted(TIERS)} or "
                                              "a qualified alias"))
    if got["effort"] not in EFFORTS:
        out.append(_f("sizing-invalid", unit, f"{at}.effort {got['effort']!r} is not one of {list(EFFORTS)}"))
    if len(got["why"].split()) < SIZING_MIN_WORDS:
        out.append(_f("sizing-invalid", unit, f"{at}.why must say in a sentence why this model and effort fit"))
    return out


def _shape(unit: str, kind: str, body: Any, kinds: Mapping[str, str]) -> list[Finding]:
    """SCF-B9, SCF-B11: `map`, `parallel` and `wait` shapes sit on a unit of that kind and state its parameters."""
    at = f"$.flow.{unit}.{kind}"
    if kind in SHAPE_KIND and kinds.get(unit, SHAPE_KIND[kind]) != SHAPE_KIND[kind]:
        return [_f("blueprint-invalid", unit, f"{at} belongs on a `{SHAPE_KIND[kind]}` unit; {unit} is a "
                   f"{kinds[unit]}")]
    if kind == "map" and not (isinstance(body, dict) and set(body) <= {"over"} and isinstance(body.get("over"), str)
                              and body["over"].count(".") == 1):
        return [_f("blueprint-invalid", unit, f"{at} takes {{over: \"<unit>.<key>\"}}, the list it runs over")]
    if kind == "parallel" and not (_strs(body) and len(body) >= 2):
        return [_f("blueprint-invalid", unit, f"{at} lists two or more branch units")]
    if kind == "wait" and not (isinstance(body, dict) and set(body) <= {"event"}
                               and isinstance(body.get("event", unit), str)):
        return [_f("blueprint-invalid", unit, f"{at} takes {{}} or {{event: <name>}}")]
    return []


def parse(data: Any) -> Blueprint | list[Finding]:
    """SCF-B9, SCF-B11: an unknown key is an error, so a misspelt field is reported, never drawn (SCF-B1)."""
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
    elif (problem := name_problem(name)) is not None:
        out.append(_f("blueprint-invalid", None, f"$.name: {problem}"))
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
        if kind in BLUEPRINT_LATER_KINDS:
            out.append(_f("not_in_release", uname, f"{at}.kind {kind!r} is built in release {BLUEPRINT_LATER_KINDS[kind]}"))
        elif kind not in RELEASE_KINDS:
            out.append(_f("blueprint-invalid", uname, f"{at}.kind {kind!r} is not a unit kind"))
        if kind == "ask" and list(u.get("produces") or ["answers"]) != ["answers"]:
            out.append(_f("blueprint-invalid", uname, f"{at}.produces: an ask unit produces `answers` only (ASK-B5, ASK-B6)"))
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
        session = kind in SESSION_UNIT_KINDS
        for key, needed in (("sizing", session), ("judge_sizing", session and bool(gate.get("judge")))):
            out.extend(_sizing(uname, f"{at}.{key}", u.get(key), needed))
        units.append(BlueprintUnit(
            sizing=u.get("sizing") if isinstance(u.get("sizing"), dict) else None,
            judge_sizing=u.get("judge_sizing") if isinstance(u.get("judge_sizing"), dict) else None,
            name=uname, kind=str(kind), summary=str(summary or ""),
            produces=(("answers",) if kind == "ask" else
                      tuple(u.get("produces") or ()) if _strs(u.get("produces") or []) else ()),
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
        out.extend(_shape(unit, kind, shape[kind], {u.name: u.kind for u in units}))
    for u in units:
        if u.kind in ("map", "parallel") and u.kind not in dict(flow.get(u.name) or {}):
            out.append(_f("blueprint-invalid", u.name, f"$.flow.{u.name} must state the {u.kind}'s shape"))
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


def branch_units(bp: Blueprint) -> set[str]:
    """The units a `parallel` shape names as its branches."""
    return {b for shape in bp.flow.values() if isinstance(shape, dict) for b in (shape.get("parallel") or ())}


def to_spec(bp: Blueprint) -> WorkflowSpec:
    """The throwaway spec: stub prompts that name each read, stub gates, the blueprint's policies."""
    units: dict[str, Any] = {}
    branches = branch_units(bp)
    for u in bp.units:
        shape = dict(bp.flow.get(u.name) or {})
        tools = ["read"] if u.name in branches else ["read", "write"]  # FLX-B6: a branch reads only
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
        elif u.kind == "map":
            src, key = str((shape.get("map") or {}).get("over") or ".").split(".", 1)
            units[u.name] = Map(items_from=(src, key), step=Step(prompt=prompt + " {item}", tools=["read", "write"],
                                                                 produces=produces, executor=u.executor,
                                                                 summary=u.summary, gate=gate))
        elif u.kind == "parallel":
            units[u.name] = Parallel(branches=list(shape.get("parallel") or ()), gate=gate)
        elif u.kind == "ask":
            units[u.name] = Ask(questions=[Question("answer", u.summary or f"Answer for {u.name}?")],
                                context=list(u.reads), gate=gate)
        elif u.kind == "wait":
            units[u.name] = Wait(event=str((shape.get("wait") or {}).get("event") or u.name), check=stub_select,
                                 gate=gate)
        elif u.kind == "route":
            units[u.name] = Route(select=stub_select, targets=list(shape.get("route") or ()), gate=gate)
        elif u.kind == "switch":
            sw = shape.get("switch") or {}
            units[u.name] = Switch(predicate=stub_select, arms=dict(sw.get("arms") or {}),
                                   default=str(sw.get("default") or ""), gate=gate)
        else:
            route = list(shape.get("route") or ())
            units[u.name] = Step(prompt=prompt, tools=tools, produces=produces, executor=u.executor,
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
    """`blueprint check` (SCF-B9, SCF-B11): WFM validation of the throwaway spec, then the outcome cross-check."""
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
        if ref.get("digest") != outcome_digest(outcome_doc) or ref.get("revision") != outcome.revision:
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
