"""The effort ladder: climbing evidence, held causes and the rung of the next attempt (LAD §2.2, §2.3). Pure.

A ladder never adds an attempt: it only chooses the effort of a retry the budget already allows, and only
the two kinds of evidence of §2.2 ever move it up.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.contracts import EFFORTS, STAGES, EscalationSpec, UnitSpec

TRUSTED_STATES = {"local-dev": ("accepted", "provisional"), "local-stable": ("accepted",), "pipeline": ("accepted",)}
PIN_KEYS = ("effort", "model")
TIER_UP = {"small": "medium", "medium": "large"}  # LAD §2.1: exactly one tier above
TIER_RANK = {"small": 0, "medium": 1, "large": 2}
TIER_FAMILY = {"small": "haiku", "medium": "sonnet", "large": "opus"}  # the price row of a tier (OBS §2.2)
MODES = ("off", "offer", "auto")
DEFAULT_STAGES = {"local-dev": "offer", "local-stable": "offer", "pipeline": "off"}
RECORD_MIN, RECORD_LB = 5, 0.5  # LAD §2.5: escalated attempts graded by an accepted judge, Wilson lower bound
HELD_ERRORS = {"turn_cap": "turn_cap", "cap_reached": "cost_cap", "model": "model"}


def trusted(judge_state: str, stage: str) -> bool:
    """LAD §2.2: a RETRY counts from an `accepted` binding, or a `provisional` one at stage `local-dev`. A
    binding graded `unreliable` in production is `contradicted` (JCL §2.5), so it is never trusted."""
    return judge_state in TRUSTED_STATES.get(stage, ("accepted",))


@dataclass(frozen=True, kw_only=True)
class Classified:
    evidence: str | None = None  # `judge_blocker`, `check_fail` or None
    held_by: str | None = None  # the held cause of LAD §2.3 when there is no evidence
    criteria: tuple[str, ...] = field(default=())


def _held_attempt(att: Mapping[str, Any]) -> str | None:
    """Why the attempt did not end with a result (LAD §2.3 rows 1 and 2), or None when it did."""
    if att.get("timed_out"):
        return "timeout"
    if att.get("stalled"):
        return "stall"
    if att.get("infra_cause") or att.get("infra_spent"):
        return "infra"
    if att.get("error_kind") in HELD_ERRORS:
        return HELD_ERRORS[str(att["error_kind"])]
    if att.get("cut_off"):
        return "cut_off"
    return None


def classify(att: Mapping[str, Any], judged: Mapping[str, Any]) -> Classified:
    """The failed attempt's climbing evidence, or the cause that holds the rung."""
    held = _held_attempt(att)
    reason = judged.get("reason")
    if reason == "check_fail":
        check = att.get("check") or {}
        failing = [f for f in check.get("findings") or [] if f.get("status") == "fail"]
        if check.get("environmental"):
            return Classified(held_by="environmental")
        if held:
            return Classified(held_by=held)
        if any(f.get("kind") == "output_contract" for f in failing):
            return Classified(held_by="output_contract")
        ids = tuple(dict.fromkeys(str(f["criterion"]) for f in failing
                                  if f.get("criterion") and f.get("kind") == "substance"))
        return Classified(evidence="check_fail", criteria=ids) if ids else Classified(held_by="check_no_substance")
    if reason == "blockers":
        if held:
            return Classified(held_by=held)
        if judged.get("confidence_source") == "engine_placeholder":
            return Classified(held_by="judge_placeholder")
        ids = tuple(dict.fromkeys(str(b.get("criterion")) for b in judged.get("blockers") or []
                                  if not b.get("no_change") and not b.get("defect_in")))
        if not ids:
            return Classified(held_by="no_substantive_blocker")
        if not judged.get("trusted"):
            return Classified(held_by="judge_not_trusted")
        return Classified(evidence="judge_blocker", criteria=ids)
    return Classified(held_by=held or str(reason or "step_failed"))


def rungs_of(u: UnitSpec, overrides: Mapping[str, Any] | None = None) -> tuple[tuple[str, ...], bool]:
    """The ladder in force for a unit, and whether an operator pin switches it off (LAD §2.3 last row). An arm
    in force may give its own ladder, or a fixed effort that replaces the step's ladder (SWM §2.3)."""
    st = u.step
    if st is None:
        return (), False
    ov = overrides or {}
    rungs = tuple(ov["effort_ladder"]) if ov.get("effort_ladder") else () if "effort" in ov else tuple(st.effort_ladder)
    pinned = bool(rungs) and any(k in (u.extra.get("operator_set") or ()) for k in PIN_KEYS)
    return rungs, pinned


def held_rung(counters: Mapping[str, Any], visit: int, item: Any) -> int:
    """The rung this visit (and item) stands on; any other visit starts at rung 0 (LAD §2.3)."""
    held = counters.get("ladder") or {}
    return int(held.get("rung", 0)) if held.get("visit") == visit and held.get("item") == item else 0


def decide(u: UnitSpec, att: Mapping[str, Any], judged: Mapping[str, Any], counters: Mapping[str, Any],
           overrides: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """The `ladder_decision` of a gate that sends the unit to a retry: the rung of the next attempt and why.
    None when the unit has neither a ladder nor an escalation."""
    rungs, pinned = rungs_of(u, overrides)
    esc = escalation_of(u, overrides)
    if not rungs and esc is None:
        return None
    visit, item = int(att.get("visit", 1)), att.get("item")
    rung = held_rung(counters, visit, item) if rungs else 0
    got = Classified(held_by="operator_pin") if pinned else classify(att, judged)
    nxt = min(rung + 1, len(rungs) - 1) if got.evidence and rungs else rung
    prev = counters.get("ladder") or {}
    same = prev if prev.get("visit") == visit and prev.get("item") == item else {}
    trail = [*(same.get("trail") or []), {"rung": rung, "top": rung >= len(rungs) - 1, "evidence": got.evidence,
                                          "criteria": list(got.criteria)}][-2:]
    return {"visit": visit, "item": item, "from_rung": rung, "rung": nxt,
            "effort": rungs[nxt] if rungs and not pinned else None,
            "evidence": got.evidence, "held_by": got.held_by if not got.evidence else None,
            "criteria": list(got.criteria), "judge_state": judged.get("judge_state"), "trail": trail,
            "escalated": bool(same.get("escalated"))}


def escalation_of(u: UnitSpec, overrides: Mapping[str, Any] | None = None) -> EscalationSpec | None:
    """The escalation in force: the arm's when it gives one (SWM §2.3), else the step's; none under a pin."""
    st = u.step
    if st is None or any(k in (u.extra.get("operator_set") or ()) for k in PIN_KEYS):
        return None
    got = (overrides or {}).get("escalation")
    if isinstance(got, Mapping):
        return EscalationSpec(to=str(got.get("to")), stages=dict(got.get("stages") or {}), effort=got.get("effort"))
    return got if isinstance(got, EscalationSpec) else st.escalation


def mode(esc: EscalationSpec, stage: str, record_met: bool) -> str:
    """LAD §2.5: what the stage allows. `auto` is an offer in local-dev and, without a met escalation record,
    in local-stable; a pipeline never waits on an offer, and its `auto` needs a promotion stamp (PRO §2.4)."""
    m = {**DEFAULT_STAGES, **dict(esc.stages)}.get(stage, "off")
    if stage == "pipeline":
        return "off"
    if m == "auto" and (stage == "local-dev" or not record_met):
        return "offer"
    return m if m in MODES else "off"


def tier(alias: object) -> str:
    return str(alias or "").rsplit(":", 1)[-1]


def _judge_rank(judge: Any) -> int:
    """The strongest tier the gate's judge can grade on: its own, or its highest risk level's (JRK §2.3 floor)."""
    from tempergraph.run.risk import top_rank

    return top_rank(judge)


def escalation(u: UnitSpec, step: Mapping[str, Any], judged: Mapping[str, Any], *, retry_left: bool,
               rearm_available: bool, overrides: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """LAD §2.4: whether the next attempt is escalated. None when the unit declares no escalation or the failed
    attempt carried no `judge_blocker` evidence; else `take` (`auto`, `offer` or None) and, when not taken,
    `held_by` naming the first condition that failed."""
    esc = escalation_of(u, overrides)
    if esc is None or step.get("evidence") != "judge_blocker":
        return None
    facts = judged.get("escalation") or {}
    trail = list(step.get("trail") or [])
    rungs, _ = rungs_of(u, overrides)
    st = u.step
    assert st is not None
    effort = esc.effort or (rungs[-1] if rungs else (st.session_options.effort if st.session_options else None))
    out: dict[str, Any] = {"to": esc.to, "effort": effort, "take": None, "held_by": None,
                           "criteria": [], "judge_state": judged.get("judge_state")}
    allowed = mode(esc, str(facts.get("stage") or "local-dev"), bool(facts.get("record_met")))
    last = trail[-2:]
    shared = sorted(set(last[0]["criteria"]) & set(last[1]["criteria"])) if len(last) == 2 else []
    judge = u.gate.judge
    estimate, left = facts.get("estimate_usd"), facts.get("cap_left_usd")
    failed = next((name for name, bad in (
        ("E1", allowed == "off"),
        ("E2", len(last) < 2 or not all(t["top"] for t in last)),
        ("E3", len(last) < 2 or any(t["evidence"] != "judge_blocker" for t in last) or not shared),
        ("E4", _judge_rank(judge) < TIER_RANK.get(tier(esc.to), 9) or judged.get("judge_state") != "accepted"),
        ("E5", not retry_left),
        ("E6_unmeasured", estimate is None),
        ("E6", estimate is not None and left is not None and float(estimate) > float(left)),
        ("E7", facts.get("bound") is False),
        ("E8", rearm_available),
        ("E9", bool(step.get("escalated"))),
    ) if bad), None)
    if failed:
        return {**out, "held_by": failed}
    return {**out, "take": allowed, "criteria": shared}


def record_escalation(root: Path, *, workflow: str, version: str | None, unit: str, thread: str, passed: bool,
                      judge_state: str | None, to: str) -> None:
    """One row of the escalation record (LAD §2.7): an escalated attempt, how it ended and who graded it."""
    from tempergraph.run.log import Ledger

    Ledger(path=root / "ledger.jsonl").append({"kind": "escalation", "workflow": workflow, "version": version,
                                               "unit": unit, "thread_id": thread, "passed": bool(passed),
                                               "judge_state": judge_state, "to": to})


def record_met(root: Path, workflow: str, version: str | None, unit: str) -> bool:
    """LAD §2.5: at least five escalated attempts of this step and workflow version graded by an `accepted`
    judge, with a pass rate whose Wilson lower bound is at least 0.5. An unreadable record is not met."""
    from tempergraph.improve.calibration import wilson_lb

    try:
        rows = [json.loads(ln) for ln in (root / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if ln]
    except (OSError, ValueError):
        return False
    mine = [r for r in rows if isinstance(r, dict) and r.get("kind") == "escalation" and r.get("workflow") == workflow
            and r.get("version") == version and r.get("unit") == unit and r.get("judge_state") == "accepted"]
    n, x = len(mine), sum(1 for r in mine if r.get("passed"))
    return n >= RECORD_MIN and wilson_lb(x, n) >= RECORD_LB


def stages_ok(esc: EscalationSpec) -> bool:
    return all(k in STAGES and v in MODES for k, v in dict(esc.stages).items())


def ascending(rungs: tuple[str, ...]) -> bool:
    return all(r in EFFORTS for r in rungs) and all(
        EFFORTS.index(a) < EFFORTS.index(b) for a, b in zip(rungs, rungs[1:], strict=False))
