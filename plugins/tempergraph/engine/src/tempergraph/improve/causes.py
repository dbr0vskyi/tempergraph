"""Cause codes from run-log names and numbers only, each classed and given a side (SIL §2.3, §2.4).

No model call and no text: a cause is derived from record kinds, enums, counts and criterion ids. A code may
carry one `:<detail>` part (a refusal class, a criterion id, an infra cause, a pause cause).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from tempergraph.improve import params

Klass = Literal["fault", "infra", "designed"]


@dataclass(frozen=True, kw_only=True)
class Cause:
    klass: Klass
    side: str  # engine, workflow, executor, host; `executor` becomes `executor:<name>` on the finding
    remedy: str


# The base code (before any `:`) decides the class, the side and the fixed remedy text.
CAUSES: dict[str, Cause] = {
    "tool_access": Cause(klass="fault", side="workflow",
                         remedy="Declare the tool or command the step needed in the unit's tools or allow-list"),
    "grant_missing": Cause(klass="fault", side="workflow",
                           remedy="Declare the granted capability on the unit; the grant stood in for it"),
    "grant_unused": Cause(klass="designed", side="workflow", remedy="Recorded only: the grant was never called"),
    "retries_spent": Cause(klass="fault", side="workflow",
                           remedy="Tighten the prompt or the check named by the blockers; the retry budget ran out"),
    "loop_budget_spent": Cause(klass="fault", side="workflow",
                               remedy="Strengthen the serving criterion upstream; trips back ran out"),
    "retry_burst": Cause(klass="fault", side="workflow",
                         remedy="Three or more retries in one visit: the prompt or check of the unit misses a rule"),
    "judge_blocked": Cause(klass="fault", side="workflow",
                           remedy="The step keeps missing this criterion: state it in the prompt or add a check"),
    "check_fail": Cause(klass="fault", side="workflow",
                        remedy="The step's output fails the deterministic check; say what it checks in the prompt"),
    "gap_escalation": Cause(klass="fault", side="workflow",
                            remedy="The judge could not grade a criterion: give it a reference or a check"),
    "blocked_without_check": Cause(klass="fault", side="workflow",
                                   remedy="A BLOCKED pause with an empty check: add a check that tests the blocker"),
    "blocked": Cause(klass="designed", side="workflow", remedy="Recorded only: a designed BLOCKED pause"),
    "no_change": Cause(klass="fault", side="workflow",
                       remedy="The judge found no change since the last attempt: the step cannot fix this alone"),
    "escalation": Cause(klass="fault", side="workflow", remedy="An escalation with an unlisted reason"),
    "refused": Cause(klass="fault", side="workflow", remedy="A permission was refused: declare it or narrow the step"),
    "step_timeout": Cause(klass="fault", side="workflow",
                          remedy="The step ran out of time: split it or raise its timeout"),
    "agent_decided": Cause(klass="fault", side="workflow",
                           remedy="An agent answered this pause on its own: add a check or an environmental cause"),
    "pushback": Cause(klass="fault", side="workflow",
                      remedy="A person rewound, ruled or declined: the gate let this through"),
    "judge_unparsed": Cause(klass="fault", side="engine", remedy="The judge's answer could not be parsed twice"),
    "guard": Cause(klass="fault", side="engine", remedy="The independence guard discarded a judgement"),
    "engine_error": Cause(klass="fault", side="engine", remedy="The engine recorded an internal error"),
    "unknown_tool_name": Cause(klass="fault", side="executor",
                               remedy="The executor reported a tool name outside the view catalog"),
    "executor_error": Cause(klass="fault", side="executor", remedy="The executor reported an error kind it should not"),
    "infra": Cause(klass="infra", side="engine", remedy="Recorded only: an infrastructure failure"),
    "slow_host": Cause(klass="infra", side="host", remedy="Recorded only: the host is slow"),
    "auth": Cause(klass="infra", side="host", remedy="Recorded only: the executor is not signed in"),
    "environmental": Cause(klass="infra", side="host", remedy="Recorded only: the environment failed a check"),
    "approval": Cause(klass="designed", side="workflow", remedy="Recorded only: a designed approval"),
    "upstream": Cause(klass="designed", side="workflow", remedy="Recorded only: an upstream dependency paused it"),
    "person_stop": Cause(klass="designed", side="workflow", remedy="Recorded only: a person stopped the run"),
    "cost_cap": Cause(klass="designed", side="workflow", remedy="Recorded only: the run cost cap drained the run"),
}


def cause_of(code: str) -> Cause:
    return CAUSES.get(code.split(":", 1)[0], Cause(klass="fault", side="engine", remedy="Unclassified cause"))


def _unit(session_key: str) -> str:
    return str(session_key).split(".", 1)[0]


def derive(records: Sequence[Mapping[str, Any]], interventions: Iterable[Mapping[str, Any]] = (),
           grants: Iterable[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    """Causes of one segment: `{unit, cause, count, executor?}` with no text."""
    out: dict[tuple[str, str, str], int] = {}
    versions: dict[tuple[str, str, str], str] = {}  # executor causes carry the CLI version (SIL-AC-4)

    def add(unit: str, code: str, executor: str = "", version: str = "") -> None:
        key = (unit, code, executor)
        out[key] = out.get(key, 0) + 1
        if version:
            versions[key] = version

    retries: dict[str, int] = {}
    checks: dict[str, Mapping[str, Any]] = {}
    for r in records:
        kind = r.get("kind")
        unit = str(r.get("unit") or _unit(str(r.get("session_key") or "")))
        if kind == "unit_entered":
            retries[unit] = 0
        elif kind == "attempt_start" and r.get("session_kind") == "retry":
            retries[unit] = retries.get(unit, 0) + 1
            if retries[unit] == int(params.value("retry_burst.min_retries")):
                add(unit, "retry_burst")
        elif kind == "agent_run":
            if r.get("infra_cause"):
                code = "slow_host" if r["infra_cause"] == "slow_host" else f"infra:{r['infra_cause']}"
                add(unit, code)
            if r.get("timed_out") and not r.get("infra_cause") and r.get("session_kind") in ("step", "retry"):
                add(unit, "step_timeout")
            if r.get("error_kind") == "unknown":
                add(unit, "executor_error:unknown", str(r.get("executor") or ""), str(r.get("cli_version") or ""))
            for name in r.get("unknown_tools") or ():
                add(unit, f"unknown_tool_name:{name}", str(r.get("executor") or ""),
                    str(r.get("cli_version") or ""))
        elif kind == "check":
            checks[unit] = r
            if r.get("result") == "FAIL" and not r.get("environmental"):
                add(unit, f"check_fail:{unit}")
        elif kind == "judgement":
            for cid in r.get("blockers") or ():
                add(unit, f"judge_blocked:{cid}")
            if r.get("guard") == "discarded":
                add(unit, "guard:discarded")
        elif kind == "gate" and r.get("verdict") is None and r.get("token") == "ESCALATE":
            add(unit, "judge_unparsed")
        elif kind == "engine_error":
            add(unit, "engine_error")
        elif kind == "pause":
            pk, reason = str(r.get("pause_kind") or ""), str(r.get("reason") or "")
            if pk == "tool_access":
                for t in r.get("tool_access") or [{"class": "unclassified"}]:
                    add(unit, f"tool_access:{t.get('class') or 'unclassified'}")
            elif pk == "budget":
                add(unit, "loop_budget_spent" if reason == "loop_budget" else "retries_spent")
            elif pk == "approval":
                add(unit, "approval")
            elif reason == "blocked":
                c = checks.get(unit)
                empty = c is None or not str(c.get("evidence") or "").strip()
                add(unit, "blocked_without_check" if empty else "blocked")
            elif reason in ("unresolved_gap", "gap"):
                add(unit, "gap_escalation")
            elif reason == "no_change":
                add(unit, "no_change")
            elif reason.startswith("guard:") or reason in ("refused", "auth", "environmental", "upstream"):
                add(unit, reason)
            elif reason == "unparsed":
                add(unit, "judge_unparsed")
            else:
                add(unit, "gap_escalation" if "gap" in reason else f"escalation:{reason or 'unknown'}")
        elif kind == "run_exit":
            reason = str(r.get("reason") or "")
            if reason == "budget":
                add("", "retries_spent")
            elif reason == "person":
                add("", "person_stop")
            elif reason == "cost_cap":
                add("", "cost_cap")
    for iv in interventions:
        c = iv.get("caller") or {}
        rescue = any(t.get("class") == "rescue" for t in iv.get("touches") or [])
        steer = [t for t in iv.get("touches") or [] if t.get("class") == "steer"]
        if rescue and c.get("decided_by") == "agent":
            add(str(iv.get("unit") or ""), f"agent_decided:{iv.get('pause_kind') or 'escalation'}")
        if c.get("decided_by") == "person" and (iv.get("ruling") or any(t.get("action") in ("rewind", "rerun")
                                                                          for t in steer)):
            add(str(iv.get("unit") or ""), "pushback")
    for g in grants:
        add(str(g.get("unit") or ""), f"grant_missing:{g.get('capability') or g.get('prefix')}" if g.get("used")
            else f"grant_unused:{g.get('capability') or g.get('prefix')}")
    return [{"unit": u, "cause": code, "count": n, **({"executor": ex} if ex else {}),
             **({"executor_version": versions[(u, code, ex)]} if (u, code, ex) in versions else {})}
            for (u, code, ex), n in out.items()]
