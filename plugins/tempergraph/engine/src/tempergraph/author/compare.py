"""`blueprint compare <workflow>` and rung 2 of `author verify` (SCF-B18, SCF-B19, SCF-B20, SCF-B21, SCF-B22): the built spec against the approved
blueprint. Compared: names, order, artifacts and reads, checks, judges, sign-offs, failure and approval
policy, back and route targets, switch arms, map lists, parallel branches, wait events, and the outcome digest. Not compared: summaries, models,
criteria texts and prompts (SCF-AC3). Each difference is said in words, with the two fixes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tempergraph.author.blueprint import Blueprint, outcome_digest
from tempergraph.contracts import TextRef, UnitSpec, WorkflowSpec
from tempergraph.model.text import TextUnreadable, load_text
from tempergraph.render.template import TemplateError, fields

FIXES = "fix the workflow to match the blueprint, or change the blueprint with the person's yes (a decision)"


@dataclass(frozen=True, kw_only=True)
class Difference:
    unit: str | None
    field: str
    blueprint: Any
    built: Any
    statement: str

    def to_json(self) -> dict[str, Any]:
        return {"unit": self.unit, "field": self.field, "blueprint": self.blueprint, "built": self.built,
                "statement": self.statement, "fixes": FIXES}


def _reads(spec: WorkflowSpec, u: UnitSpec, produced: set[str]) -> list[str]:
    if u.script is not None:
        return sorted(set(u.script.inputs) & produced)
    if u.ask is not None:
        return sorted(set(u.ask.context) & produced)  # ASK-B5, ASK-B6: what the person is shown
    if u.step is None or u.step.prompt == "default":
        return []
    try:
        text = load_text(spec, u.step.prompt if isinstance(u.step.prompt, TextRef) else u.step.prompt)
        names = {f.split(".")[0] for f in fields(text)}
    except (TextUnreadable, TemplateError):
        return []
    return sorted(names & produced)


def _produces(u: UnitSpec) -> list[str]:
    if u.step is not None:
        return sorted(u.step.produces)
    if u.script is not None:
        return sorted(u.script.produces)
    if u.ask is not None:
        return ["answers"]  # ASK-B5, ASK-B6: the unit's one artifact
    return []


def compare(bp: Blueprint, spec: WorkflowSpec, outcome_doc: Any = None) -> list[Difference]:
    out: list[Difference] = []

    def diff(unit: str | None, fld: str, a: Any, b: Any, statement: str) -> None:
        if a != b:
            out.append(Difference(unit=unit, field=fld, blueprint=a, built=b, statement=statement))

    names = [u.name for u in bp.units]
    diff(None, "units", sorted(names), sorted(spec.order),
         f"the units differ: blueprint {sorted(names)}, workflow {sorted(spec.order)}")
    if sorted(names) == sorted(spec.order):
        diff(None, "order", names, list(spec.order), f"the order differs: blueprint {names}, workflow {list(spec.order)}")
    produced = {k for u in spec.units.values() for k in _produces(u)}
    for b in bp.units:
        u = spec.units.get(b.name)
        if u is None:
            continue
        diff(b.name, "kind", b.kind, u.kind, f"{b.name} is a {u.kind}; the blueprint says {b.kind}")
        diff(b.name, "produces", sorted(b.produces), _produces(u),
             f"{b.name} produces {_produces(u)}; the blueprint says {sorted(b.produces)}")
        diff(b.name, "reads", sorted(b.reads), _reads(spec, u, produced),
             f"{b.name} reads {_reads(spec, u, produced)}; the blueprint says {sorted(b.reads)}")
        g = u.gate
        diff(b.name, "gate.check", b.check, g.check is not None,
             f"{b.name} {'has' if g.check else 'has no'} check; the blueprint says {'one' if b.check else 'none'}")
        diff(b.name, "gate.judge", b.judge, g.judge is not None,
             f"{b.name} {'has' if g.judge else 'has no'} judge; the blueprint says {'one' if b.judge else 'none'}")
        approval = bool(b.approval) or b.signoff
        diff(b.name, "approval", approval, g.approval,
             f"{b.name} now pauses for approval after a pass; the blueprint does not" if g.approval else
             f"{b.name} no longer pauses for approval after a pass; the blueprint does")
        diff(b.name, "on_fail", b.on_fail or "retry", g.on_fail,
             f"{b.name} on_fail is {g.on_fail}; the blueprint says {b.on_fail or 'retry'}")
        diff(b.name, "on_budget_spent", b.on_budget_spent or "ask", g.on_budget_spent,
             f"{b.name} on_budget_spent is {g.on_budget_spent}; the blueprint says {b.on_budget_spent or 'ask'}")
        diff(b.name, "back_targets", sorted(b.back_targets), sorted(g.back_targets),
             f"{b.name} goes back to {sorted(g.back_targets)}; the blueprint says {sorted(b.back_targets)}")
        shape = dict(bp.flow.get(b.name) or {})
        if u.kind in ("step", "route") or "route" in shape:
            diff(b.name, "route", sorted(shape.get("route") or ()), sorted(u.route_targets),
                 f"{b.name} routes to {sorted(u.route_targets)}; the blueprint says {sorted(shape.get('route') or ())}")
        if u.switch is not None or "switch" in shape:
            sw = shape.get("switch") or {}
            built = {"arms": dict(u.switch.arms), "default": u.switch.default} if u.switch else {}
            diff(b.name, "switch", {"arms": dict(sw.get("arms") or {}), "default": sw.get("default")}, built,
                 f"{b.name}'s switch arms or default differ from the blueprint")
        if u.map is not None or "map" in shape:
            built_over = ".".join(u.map.items_from) if u.map else None
            diff(b.name, "map.over", (shape.get("map") or {}).get("over"), built_over,
                 f"{b.name} maps over {built_over}; the blueprint says {(shape.get('map') or {}).get('over')}")
        if u.kind == "parallel" or "parallel" in shape:
            diff(b.name, "parallel", sorted(shape.get("parallel") or ()), sorted(u.branches),
                 f"{b.name} joins {sorted(u.branches)}; the blueprint says {sorted(shape.get('parallel') or ())}")
        if u.wait is not None or "wait" in shape:
            want = str((shape.get("wait") or {}).get("event") or b.name)
            diff(b.name, "wait.event", want, u.wait.event if u.wait else None,
                 f"{b.name} waits for {u.wait.event if u.wait else None}; the blueprint says {want}")
        if spec.outcome is not None:
            io = spec.outcome.intermediate.get(b.name)
            signs = any(c.verified_by == "person" for c in (io.criteria if io else ()))
            diff(b.name, "signoff", b.signoff, signs, f"{b.name} {'has' if signs else 'has no'} sign-off criteria; "
                 f"the blueprint says {'it has' if b.signoff else 'none'}")
    if bp.outcome_ref is not None and outcome_doc is not None:
        diff(None, "outcome_ref.digest", bp.outcome_ref.get("digest"), outcome_digest(outcome_doc),
             "outcome.json changed since the blueprint was approved")
    return out
