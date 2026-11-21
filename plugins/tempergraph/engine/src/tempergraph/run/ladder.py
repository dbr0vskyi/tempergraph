"""The effort ladder: climbing evidence, held causes and the rung of the next attempt (LAD §2.2, §2.3). Pure.

A ladder never adds an attempt: it only chooses the effort of a retry the budget already allows, and only
the two kinds of evidence of §2.2 ever move it up.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from tempergraph.contracts import EFFORTS, UnitSpec

TRUSTED_STATES = {"local-dev": ("accepted", "provisional"), "local-stable": ("accepted",), "pipeline": ("accepted",)}
PIN_KEYS = ("effort", "model")
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
    None when the unit has no ladder."""
    rungs, pinned = rungs_of(u, overrides)
    if not rungs:
        return None
    visit, item = int(att.get("visit", 1)), att.get("item")
    rung = held_rung(counters, visit, item)
    got = Classified(held_by="operator_pin") if pinned else classify(att, judged)
    nxt = min(rung + 1, len(rungs) - 1) if got.evidence else rung
    return {"visit": visit, "item": item, "from_rung": rung, "rung": nxt, "effort": None if pinned else rungs[nxt],
            "evidence": got.evidence, "held_by": got.held_by if not got.evidence else None,
            "criteria": list(got.criteria), "judge_state": judged.get("judge_state")}


def ascending(rungs: tuple[str, ...]) -> bool:
    return all(r in EFFORTS for r in rungs) and all(
        EFFORTS.index(a) < EFFORTS.index(b) for a, b in zip(rungs, rungs[1:], strict=False))
