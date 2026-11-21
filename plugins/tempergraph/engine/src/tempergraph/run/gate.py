"""The gate node's decision and the human node's decisions (HUM §2, BUD §2, BUD-B3, B4; CMP routing).

`decide` is pure: it reads the unit's attempt record, its judge outcome and its counters, and returns the
state write that routes the run. It never pauses; a pause is the human node's.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from tempergraph.contracts import Decision, RouteView, UnitSpec, Verdict, WorkflowSpec
from tempergraph.model import flow
from tempergraph.run import ladder as laddermod
from tempergraph.run import mapping

ESCALATE_CAUSES = frozenset({"auth", "refused", "tool_access", "environmental", "blocked", "upstream",
                             "workflow_fault"})
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


class RouteFault(Exception):
    """A route function raised or returned a name that is not one of its targets (CMP-B3)."""


def route_view(unit: str, state: Mapping[str, Any]) -> RouteView:
    """What a route or switch function sees: step values, check facts and artifact keys, never prose."""
    values: dict[str, str] = {}
    for vals in (state.get("values") or {}).values():
        if isinstance(vals, dict):
            values.update({str(k): str(v) for k, v in vals.items()})
    facts = {u: {str(k): str(v) for k, v in f.items()} for u, f in (state.get("facts") or {}).items()
             if isinstance(f, dict)}
    keys = sorted({str(k) for arts in (state.get("artifacts") or {}).values() if isinstance(arts, dict) for k in arts})
    visit = int(((state.get("visits") or {}).get(unit) or {}).get("visit", 1))
    return RouteView(unit=unit, visit=visit, values=values, facts=facts, artifact_keys=tuple(keys), settings={})


def pick(spec: WorkflowSpec, unit: str, state: Mapping[str, Any]) -> dict[str, Any] | None:
    """CMP §2.2: the forward target a step's route, a route unit or a switch picks, as the `route` record's
    fields; None when the unit routes by `order`. A route fault raises `RouteFault`; a switch fault takes the
    default arm. A switch's pick is reused within a visit (`sticky: visit`) or for the run (`sticky: run`)."""
    u = spec.units[unit]
    view = route_view(unit, state)
    if u.switch is not None:
        return _switch_pick(spec, unit, state, view)
    if u.route is None:
        return None
    try:
        got = u.route.resolve()(view)
    except Exception as exc:  # noqa: BLE001 - a raise stops the run, never falls back to `order`
        raise RouteFault(f"route {u.route.ref} raised {type(exc).__name__}") from None
    if not isinstance(got, str) or got not in u.route_targets:
        raise RouteFault(f"route {u.route.ref} returned {got!r}, not one of {list(u.route_targets)}")
    return {"arm": got, "target": flow.through_outcome(spec, got), "chosen_by": "predicate", "visit": view.visit}


SIGNALS_MAX, SIGNAL_CHARS = 10, 60
COMPLEXITY_FIELDS = ("zone", "measures", "rules_digest", "rules_source", "rules_error")


def _signals(raw: Any) -> tuple[dict[str, Any], int]:
    """SWM §2.1: at most 10 names to numbers or strings of at most 60 characters; the rest is clipped and counted."""
    if not isinstance(raw, Mapping):
        return {}, 0
    out: dict[str, Any] = {}
    clipped = 0
    for k, v in raw.items():
        if len(out) >= SIGNALS_MAX:
            clipped += 1
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            v = str(v)
            if len(v) > SIGNAL_CHARS:
                v, clipped = v[:SIGNAL_CHARS], clipped + 1
        out[str(k)[:SIGNAL_CHARS]] = v
    return out, clipped


def _switch_pick(spec: WorkflowSpec, unit: str, state: Mapping[str, Any], view: RouteView) -> dict[str, Any]:
    """A switch's pick with what the predicate would choose (SWM §2.2). The operator's arm wins in either mode
    (CMP-B7); shadow mode and any predicate fault take the default; a re-armed pick is never made again."""
    u = spec.units[unit]
    sw = u.switch
    assert sw is not None
    prior = ((state.get("route") or {}).get(unit) or {}).get("pick")
    if prior and (prior.get("chosen_by") == "rearm" or sw.sticky == "run" or prior.get("visit") == view.visit):
        return dict(prior)
    would: str | None = None
    fault: str | None = None
    signals: dict[str, Any] = {}
    clipped = 0
    measured: dict[str, Any] = {}
    if sw.complexity is not None:  # CXR §2.4: the step node evaluated the rules once; the gate reads the result
        measured = dict(((state.get("attempts") or {}).get(unit) or {}).get("complexity") or {})
        would = measured.get("arm") if measured.get("arm") in sw.arms else None
        if would is None:
            fault = "not_evaluated"
    else:
        try:
            assert sw.predicate is not None
            got = sw.predicate.resolve()(view)
            if isinstance(got, tuple) and len(got) == 2:
                got, raw = got
                signals, clipped = _signals(raw)
            would = str(got) if str(got) in sw.arms else None
            if would is None:
                fault = "unknown_arm"
        except Exception as exc:  # noqa: BLE001 - a predicate fault takes the default arm
            fault = type(exc).__name__
    shadow = sw.mode == "shadow"
    operator = u.extra.get("arm")
    if operator in sw.arms:
        arm, by = str(operator), "operator"
    elif shadow or would is None:
        arm, by = sw.default, "default"
    else:
        arm, by = would, "predicate"
    p: dict[str, Any] = {"arm": arm, "target": flow.through_outcome(spec, sw.arms[arm]), "chosen_by": by,
                         "visit": view.visit, "shadow": shadow, "would_choose": would}
    if signals:
        p["signals"] = signals
    if clipped:
        p["signals_clipped"] = clipped
    if fault:
        p["fault"] = fault
    p.update({k: measured[k] for k in COMPLEXITY_FIELDS if k in measured})
    return p


def arm_overrides(spec: WorkflowSpec, unit: str, state: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    """SWM §2.3: the override values of the arm in force that names `unit`, and their layer `arm:<switch>.<arm>`."""
    for name, other in spec.units.items():
        sw = other.switch
        if sw is None or not sw.arm_overrides:
            continue
        p = ((state.get("route") or {}).get(name) or {}).get("pick") or {}
        values = (sw.arm_overrides.get(str(p.get("arm"))) or {}).get(unit)
        if values:
            return dict(values), f"arm:{name}.{p.get('arm')}"
    return {}, ""


def _rearm(spec: WorkflowSpec, unit: str, state: Mapping[str, Any], cause: str) -> tuple[str, Any] | None:
    """The switch and re-arm entry that apply to `unit` ending on `cause`, once per switch and run (SWM §2.4)."""
    for name, other in spec.units.items():
        sw = other.switch
        stored = (state.get("route") or {}).get(name) or {}
        p = stored.get("pick") or {}
        if sw is None or not p or stored.get("rearmed"):
            continue
        for r in sw.rearm:
            if r.from_arm == p.get("arm") and unit in r.units and cause in r.on:
                return name, r
    return None


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
    item = ((state.get("attempts") or {}).get(unit) or {}).get("item")  # a map's item in hand (MAP §2.2)
    out = {"kind": kind, "unit": unit, "item": item, "reason": reason, "artifacts": arts, "rubric": rubric,
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

    def to_human(kind: str, reason: str, **extra: Any) -> dict[str, Any]:
        payload = pause_payload(spec, unit, kind, reason, state, task_id, judged.get("blockers"))
        return _merge(route("ESCALATE", s.escalate[0], kind=kind, **extra), {"pause": {unit: payload}})

    def rearm(cause: str) -> dict[str, Any] | None:
        """A trip back to the entry of the safer arm in place of the gate's own policy (SWM §2.4)."""
        found = _rearm(spec, unit, state, cause)
        if found is None:
            return None
        name, r = found
        sw = spec.units[name].switch
        assert sw is not None
        if sw.complexity is not None and cause == "budget_spent" and laddermod.classify(att, judged).evidence is None:
            return None  # CXR §2.5: a budget spent on held causes keeps the gate's own policy
        entry = sw.arms[r.to]
        prior = ((state.get("route") or {}).get(name) or {}).get("pick") or {}
        visits = (state.get("visits") or {}).get(entry) or {}
        loops[entry] = int(loops.get(entry, 0)) + 1
        p = {"arm": r.to, "target": entry, "chosen_by": "rearm", "visit": prior.get("visit", 1),
             "shadow": False, "would_choose": prior.get("would_choose"), "rearmed_from": r.from_arm,
             "rearm_unit": unit, "rearm_cause": cause, **{k: prior[k] for k in COMPLEXITY_FIELDS if k in prior}}
        return _merge(clear_from(spec, entry, state), route("BACK", flow.step_node(entry), rearm=name),
                      {"route": {name: {"pick": p, "rearmed": True}},
                       "counters": {unit: {**counters, "retries": 0, "infra": 0, "loops": loops}},
                       "visits": {entry: {"visit": int(visits.get("visit", 1)) + 1,
                                          "reason": f"re-armed from {r.from_arm} to {r.to} ({cause})", "from": unit,
                                          "entered_from": f"rearm:{unit}"}}})

    def spent(reason: str) -> dict[str, Any]:
        if reason == "retry_budget":
            w = rearm("budget_spent")
            if w is not None:
                return w
        if g.on_budget_spent == "stop":
            return _merge(route("STOP", s.stop[0]), {"run": {"stopped": {"reason": "budget", "unit": unit,
                                                                         "detail": reason}}})
        return to_human("budget", reason)

    if att.get("map_fault"):  # the list could not be used: stop before any item (MAP §2.2 row 1, MAP-B5)
        return _merge(route("STOP", s.stop[0]), {"run": {"stopped": {"reason": "map", "unit": unit,
                                                                     "detail": att.get("map_fault")}}})
    if att.get("infra_spent"):
        return _merge(route("STOP", s.stop[0]), {"run": {"stopped": {"reason": "infra", "unit": unit,
                                                                     "detail": att.get("infra_cause")}}})
    cause = att.get("escalate")
    if cause in ESCALATE_CAUSES:
        return to_human("escalation", str(cause))
    if att.get("timed_out") and not att.get("slow_host"):  # a step timeout re-arms at once (SWM §2.4)
        w = rearm("timeout")
        if w is not None:
            return w
    verdict = judged.get("verdict", str(Verdict.ESCALATE))
    if verdict == Verdict.RETRY and att.get("escalated"):  # LAD §2.4: a failed escalated attempt ends it
        return spent("escalation")
    if verdict == Verdict.RETRY:
        if retries < g.retry_budget:
            counters["retries"] = retries + 1
            ov = arm_overrides(spec, unit, state)[0]
            step = laddermod.decide(u, att, judged, counters, ov)
            if step is None:
                return _merge(route("RETRY", s.retry[0]), {"counters": {unit: counters}})
            counters["ladder"] = {k: step[k] for k in ("visit", "item", "rung", "evidence", "held_by", "trail",
                                                       "escalated")}
            esc = laddermod.escalation(u, step, judged, retry_left=True, overrides=ov,
                                       rearm_available=_rearm(spec, unit, state, "budget_spent") is not None)
            shown = {k: v for k, v in step.items() if k not in ("trail", "escalated")}
            if esc is not None:
                shown["escalation"] = esc
            if esc and esc["take"] == "offer":  # LAD §2.4: a person chooses; no retry is spent yet
                counters["retries"] = retries
                counters["ladder"]["offer"] = {k: esc[k] for k in ("to", "effort", "criteria")}
                w = to_human("budget", "escalation_offer", ladder=shown)
                w["pause"][unit]["escalation"] = {**counters["ladder"]["offer"], "judge_state": esc["judge_state"],
                                                  "command": f"tempergraph resume {spec.name} {task_id} --escalate"}
                return _merge(w, {"counters": {unit: counters}})
            if esc and esc["take"] == "auto":
                counters["ladder"].update(escalate={"to": esc["to"], "effort": esc["effort"], "taken_by": "auto"},
                                          escalated=True)
            return _merge(route("RETRY", s.retry[0], ladder=shown), {"counters": {unit: counters}})
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
        try:  # the route is picked before any approval pause (CMP §2.2)
            p = pick(spec, unit, state)
        except RouteFault as exc:
            return _merge(route("STOP", s.stop[0]), {"run": {"stopped": {"reason": "route", "unit": unit,
                                                                         "detail": str(exc)}}})
        extra = {"pick": p} if p else {}
        if g.approval:
            return to_human("approval", "approval", **extra)
        nxt = mapping.advance(spec, unit, state)
        if nxt is not None:  # a map's next item runs the unit's own step node again (MAP §2.2)
            return _merge(route("NEXT", s.retry[0], item=att.get("item")), nxt)
        return _merge(route("PROCEED", flow.target_node(p["target"]) if p else s.proceed[0], **extra),
                      mapping.passed_write(spec, unit, state))
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


FEEDBACK_LIMIT = 8_000
RULINGS_ACTIVE = 10
RULINGS_CHARS = 16_000


def active_rulings(spec: WorkflowSpec, state: Mapping[str, Any], unit: str) -> list[str]:
    """RRN §2.2: rulings in force for `unit`: named by `applies_to`, else given at it or an earlier unit."""
    order = flow.effective_order(spec)
    out = []
    for r in (state.get("rulings") or {}).values():
        if not isinstance(r, dict) or r.get("revoked_at"):
            continue
        applies = list(r.get("applies_to") or [])
        if applies:
            hit = unit in applies
        else:
            at = str(r.get("given_at") or "")
            hit = unit == at or (at in order and unit in order and order.index(unit) >= order.index(at))
        if hit:
            out.append(str(r.get("text") or ""))
    return out


def decision_target(spec: WorkflowSpec, unit: str, d: Decision) -> str:
    """The unit a decision's feedback reaches (RRN §2.2)."""
    if d.word == "proceed":
        nxt = flow.successors(spec, unit).proceed[0]
        return nxt.rsplit(".", 1)[0] if nxt.endswith(".step") else unit
    if d.word in ("back", "rewind") and d.unit:
        return d.unit
    return unit


def check_rulings(state: Mapping[str, Any], new_text: str | None, revoke: Sequence[str]) -> None:
    """RRN §4: unknown revoke ids, and the limits of 10 active rulings and 16 000 characters."""
    rulings = {k: v for k, v in (state.get("rulings") or {}).items() if isinstance(v, dict)}
    for rid in revoke:
        if rid not in rulings or rulings[rid].get("revoked_at"):
            raise DecisionRefused(f"--revoke-ruling {rid}: no active ruling with that id")
    active = [(k, v) for k, v in rulings.items() if not v.get("revoked_at") and k not in revoke]
    if new_text is None:
        return
    chars = sum(len(str(v.get("text") or "")) for _, v in active) + len(new_text)
    if len(active) + 1 > RULINGS_ACTIVE or chars > RULINGS_CHARS:
        oldest = min(active, key=lambda kv: str(kv[1].get("at") or ""))[0] if active else "-"
        raise DecisionRefused(f"rulings over their limit ({RULINGS_ACTIVE} active, {RULINGS_CHARS} characters); "
                              f"revoke one first, the oldest is {oldest}")


def ruling_writes(state: Mapping[str, Any], payload: Mapping[str, Any], given_at: str) -> dict[str, Any]:
    """The `rulings` channel write of one resume: a new ruling and any revocations (CON §2.12 `Ruling`)."""
    now = datetime.now(UTC).isoformat(timespec="seconds")
    w: dict[str, Any] = {rid: {"revoked_at": now, "revoked_by": payload.get("caller")}
                         for rid in payload.get("revoke") or []}
    r = payload.get("ruling")
    if r and payload.get("feedback"):
        rid = f"r{len(state.get('rulings') or {}) + 1}"
        w[rid] = {"id": rid, "text": str(payload["feedback"]), "given_at": given_at,
                  "applies_to": list(r.get("applies_to") or []), "by": payload.get("caller"), "at": now}
    return w


def apply_decision(spec: WorkflowSpec, unit: str, state: Mapping[str, Any], payload: Mapping[str, Any]
                   ) -> dict[str, Any]:
    w = _apply(spec, unit, state, payload)
    d = Decision.parse(str(payload.get("decision", "")))
    rulings = ruling_writes(state, payload, decision_target(spec, unit, d))
    if rulings:
        w["rulings"] = rulings
    return w


def _apply(spec: WorkflowSpec, unit: str, state: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    d = Decision.parse(str(payload.get("decision", "")))
    s = flow.successors(spec, unit)
    # `--ruling` makes the text a ruling instead of one-time feedback; a rewind's text is still its visit reason
    feedback = payload.get("feedback") or None
    one_time = None if payload.get("ruling") else feedback
    counters = dict((state.get("counters") or {}).get(unit) or {})

    def route(token: str, node: str) -> dict[str, Any]:
        return {"route": {unit: {"token": token, "node": node, "by": "person"}}, "pause": {unit: None}}

    if d.word == "proceed":
        more = mapping.advance(spec, unit, state)
        if more is not None:  # a person passed one item of a map; the next item runs
            return _merge(route("NEXT", s.retry[0]), more)
        picked = ((state.get("route") or {}).get(unit) or {}).get("pick")  # made before the approval pause
        nxt = flow.target_node(picked["target"]) if picked else s.proceed[0]
        w = _merge(route("PROCEED", nxt), mapping.passed_write(spec, unit, state))
        if picked:
            w["route"][unit]["pick"] = picked
        nxt_unit = nxt.rsplit(".", 1)[0] if nxt.endswith(".step") else None
        if one_time and nxt_unit:
            w["feedback"] = {nxt_unit: {"text": one_time, "as": "notes"}}
        return w
    if d.word == "retry":
        held = counters.get("ladder") or {}
        if payload.get("escalate") and held.get("offer"):  # the person took the offer: it spends a retry (E5)
            counters.update(retries=int(counters.get("retries", 0)) + 1, human=int(counters.get("human", 0)) + 1)
            counters["ladder"] = {**{k: v for k, v in held.items() if k != "offer"}, "escalated": True,
                                  "escalate": {**held["offer"], "taken_by": "person"}}
            return _merge(route("RETRY", s.retry[0]), {"counters": {unit: counters}},
                          {"feedback": {unit: {"text": one_time, "as": "feedback"}}} if one_time else {})
        counters.update(retries=0, human=int(counters.get("human", 0)) + 1, infra=0)
        # a person's retry starts the visit at rung 0 (LAD §2.3); an escalation of this visit stays spent (E9)
        counters["ladder"] = {"visit": held.get("visit"), "item": held.get("item"), "rung": 0,
                              "escalated": True} if held.get("escalated") else None
        w = _merge(route("RETRY", s.retry[0]), {"counters": {unit: counters}})
        if one_time:
            w["feedback"] = {unit: {"text": one_time, "as": "feedback"}}
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
