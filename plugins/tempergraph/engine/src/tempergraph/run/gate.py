"""The gate node's decision and the human node's decisions (HUM §2, BUD §2, BUD-B3, B4; CMP routing).

`decide` is pure: it reads the unit's attempt record, its judge outcome and its counters, and returns the
state write that routes the run. It never pauses; a pause is the human node's.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tempergraph.contracts import Decision, UnitSpec, Verdict, WorkflowSpec
from tempergraph.model import flow

ESCALATE_CAUSES = frozenset({"auth", "refused", "tool_access", "environmental", "blocked", "upstream"})
HUMAN_CAP = 100


def clear_from(spec: WorkflowSpec, unit: str, state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """BUD-B4: delete verdicts, judgements, artifacts, values and facts of ``unit`` and every later unit.

    Every later unit that already ran gets a new visit, so its next entry is recorded as one (EVT §2.2)."""
    order = flow.effective_order(spec)
    later = order[order.index(unit):] if unit in order else [unit]
    out: dict[str, Any] = {k: {u: None for u in later} for k in ("artifacts", "values", "facts", "judgements")}
    out["counters"] = {u: {"retries": 0, "infra": 0} for u in later}
    attempts = (state or {}).get("attempts") or {}
    visits = (state or {}).get("visits") or {}
    out["visits"] = {u: {"visit": int((visits.get(u) or {}).get("visit", 1)) + 1, "entered_from": "proceed"}
                     for u in later[1:] if attempts.get(u)}
    return out


def _merge(*writes: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for w in writes:
        for ch, val in w.items():
            if isinstance(val, dict) and isinstance(out.get(ch), dict):
                out[ch] = {**out[ch], **val}
            else:
                out[ch] = val
    return out


def resume_command(spec: WorkflowSpec, task_id: str, decisions: list[str]) -> str:
    return f"tempergraph resume {spec.name} {task_id} --decision <{'|'.join(decisions)}>"


def pause_payload(spec: WorkflowSpec, unit: str, kind: str, reason: str, state: Mapping[str, Any],
                  task_id: str, blockers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    u = spec.units[unit]
    s = flow.successors(spec, unit)
    words = ["proceed", "retry"] + [f"back:{t}" for t in u.gate.back_targets] + ["stop"]
    if kind == "approval":
        words = ["proceed", "retry", "stop"]
    arts = sorted(((state.get("artifacts") or {}).get(unit) or {}).keys())
    rubric = [{"n": i, "id": c.id, "text": c.text, "severity": c.severity} for i, c in enumerate(u.gate.criteria, 1)]
    ws = state.get("workspace") or {}
    del s
    out = {"kind": kind, "unit": unit, "item": None, "reason": reason, "artifacts": arts, "rubric": rubric,
           "blockers": blockers or [], "decisions": words, "workspace": ws.get("path"),
           "resume": resume_command(spec, task_id, words)}
    if reason == "tool_access":  # each refused or missing name and what fixes it (RST §2.8)
        out["tool_access"] = list((((state.get("attempts") or {}).get(unit) or {}).get("tool_access")) or [])
    if kind == "approval" and u.extra.get("sign_off"):
        out["sign_off"] = list(u.extra["sign_off"])  # person criteria to sign (OUT §2.4, OUT-B4)
    return out


def decide(spec: WorkflowSpec, unit: str, state: Mapping[str, Any], task_id: str) -> dict[str, Any]:
    u: UnitSpec = spec.units[unit]
    g = u.gate
    s = flow.successors(spec, unit)
    att = (state.get("attempts") or {}).get(unit) or {}
    judged = (state.get("judgements") or {}).get(unit) or {}
    counters = dict((state.get("counters") or {}).get(unit) or {})
    retries = int(counters.get("retries", 0))
    loops = dict(counters.get("loops") or {})

    def route(token: str, node: str, **extra: Any) -> dict[str, Any]:
        return {"route": {unit: {"token": token, "node": node, **extra}}}

    def to_human(kind: str, reason: str) -> dict[str, Any]:
        payload = pause_payload(spec, unit, kind, reason, state, task_id, judged.get("blockers"))
        return _merge(route("ESCALATE", s.escalate[0], kind=kind), {"pause": {unit: payload}})

    def spent(reason: str) -> dict[str, Any]:
        if g.on_budget_spent == "stop":
            return _merge(route("STOP", s.stop[0]), {"run": {"stopped": {"reason": "budget", "unit": unit,
                                                                         "detail": reason}}})
        return to_human("budget", reason)

    if att.get("infra_spent"):
        return _merge(route("STOP", s.stop[0]), {"run": {"stopped": {"reason": "infra", "unit": unit,
                                                                     "detail": att.get("infra_cause")}}})
    cause = att.get("escalate")
    if cause in ESCALATE_CAUSES:
        return to_human("escalation", str(cause))
    verdict = judged.get("verdict", str(Verdict.ESCALATE))
    if verdict == Verdict.RETRY:
        if retries < g.retry_budget:
            counters["retries"] = retries + 1
            return _merge(route("RETRY", s.retry[0]), {"counters": {unit: counters}})
        return spent("retry_budget")
    if verdict == Verdict.BACK:
        target = judged.get("back_to")
        if not target or target not in g.back_targets:
            return to_human("escalation", "back_target_not_allowed")
        if int(loops.get(target, 0)) >= g.loop_budget:
            return spent("loop_budget")
        loops[target] = int(loops.get(target, 0)) + 1
        visits = (state.get("visits") or {}).get(target) or {}
        reason = "; ".join(b.get("problem", "") for b in judged.get("blockers") or []) or "sent back"
        return _merge(clear_from(spec, target, state),
                      route("BACK", flow.step_node(target)),
                      {"counters": {unit: {**counters, "retries": 0, "infra": 0, "loops": loops}},
                       "visits": {target: {"visit": int(visits.get("visit", 1)) + 1, "reason": reason, "from": unit,
                                           "entered_from": f"back:{unit}"}}})
    if verdict == Verdict.PROCEED:
        if g.approval:
            return to_human("approval", "approval")
        return route("PROCEED", s.proceed[0])
    return to_human("escalation", judged.get("reason") or "escalate")


# ---------------------------------------------------------------------------------------------
# Human decisions (HUM §2.2)


class DecisionRefused(ValueError):
    pass


def check_decision(spec: WorkflowSpec, unit: str, state: Mapping[str, Any], d: Decision, *,
                   human_cap: int = HUMAN_CAP) -> None:
    """HUM §4: refuse before anything is written."""
    g = spec.units[unit].gate
    path = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
    if d.word in ("event", "answer"):
        raise DecisionRefused(f"{d.word}: is only accepted at a wait or an ask")
    if d.word == "back" and d.unit not in g.back_targets:
        raise DecisionRefused(f"back:{d.unit} is not a back target of {unit}")
    if d.word == "rewind" and d.unit not in path:
        raise DecisionRefused(f"rewind:{d.unit}: {d.unit} was not completed on this path")
    human = int(((state.get("counters") or {}).get(unit) or {}).get("human", 0))
    if d.word in ("retry", "rewind") and human >= human_cap:
        raise DecisionRefused(f"the human cap of {human_cap} is spent on {unit}")


def apply_decision(spec: WorkflowSpec, unit: str, state: Mapping[str, Any], payload: Mapping[str, Any]
                   ) -> dict[str, Any]:
    d = Decision.parse(str(payload.get("decision", "")))
    s = flow.successors(spec, unit)
    feedback = payload.get("feedback") or None
    counters = dict((state.get("counters") or {}).get(unit) or {})

    def route(token: str, node: str) -> dict[str, Any]:
        return {"route": {unit: {"token": token, "node": node, "by": "person"}}, "pause": {unit: None}}

    if d.word == "proceed":
        nxt = s.proceed[0]
        w = route("PROCEED", nxt)
        nxt_unit = nxt.rsplit(".", 1)[0] if nxt.endswith(".step") else None
        if feedback and nxt_unit:
            w["feedback"] = {nxt_unit: {"text": feedback, "as": "notes"}}
        return w
    if d.word == "retry":
        counters.update(retries=0, human=int(counters.get("human", 0)) + 1, infra=0)
        w = _merge(route("RETRY", s.retry[0]), {"counters": {unit: counters}})
        if feedback:
            w["feedback"] = {unit: {"text": feedback, "as": "feedback"}}
        return w
    if d.word in ("back", "rewind") and d.unit:
        visits = (state.get("visits") or {}).get(d.unit) or {}
        human = int(counters.get("human", 0)) + (1 if d.word == "rewind" else 0)
        w = _merge(clear_from(spec, d.unit, state), route(d.word.upper(), flow.step_node(d.unit)),
                   {"visits": {d.unit: {"visit": int(visits.get("visit", 1)) + 1,
                                        "reason": feedback or f"{d.word} by a person", "from": unit,
                                        "entered_from": f"{d.word}:{unit}"}}})
        w["counters"] = {**w.get("counters", {}), unit: {**counters, "human": human, "loops": {}}}
        return w
    return _merge(route("STOP", s.stop[0]), {"run": {"stopped": {"reason": "person", "unit": unit,
                                                                 "detail": "stop"}}})
