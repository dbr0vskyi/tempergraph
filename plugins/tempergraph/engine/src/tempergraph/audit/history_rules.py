"""The history rules of C1, C2 and C3 (ARC-B9, ARC-B10, ARC-B11) and the hot spots per unit (AUD-B3).

Every function reads `HistoryFacts` only: no file, no executor, no model. A rule returns findings with the catalog's
severity, confidence, cause and remedy; the evidence names the counts, `n` (the runs read) and the window. A rule is
called only with at least its `min_n` runs (`audit.__init__`); the smaller sample counts a rule states inside itself
(5 RETRYs, 5 visits, 20 attempts) keep it quiet when the runs hold too few of them.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import Any

from tempergraph.audit.catalog import PARAMS, rule
from tempergraph.audit.history import STEP_KINDS, Attempt, HistoryFacts, p90
from tempergraph.audit.report import AuditFinding, order
from tempergraph.contracts import WorkflowSpec

P = {k: v.default for k, v in PARAMS.items()}
Rule = Callable[[WorkflowSpec, HistoryFacts], list[AuditFinding]]


class RuleSkipped(Exception):  # noqa: N818 - a signal, not an error: the rule's input is missing (ARC-B7)
    """A rule that cannot judge on the facts it was given: it is listed as skipped with this reason, never passed."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def finding(rule_id: str, facts: HistoryFacts, unit: str | None, statement: str, *, item: str | None = None,
            evidence: dict[str, Any] | None = None, session: str | None = None) -> AuditFinding:
    """A history finding: the catalog's record, the evidence counts, `n` and the window (AUD-B3)."""
    r = rule(rule_id)
    return AuditFinding(rule=r.id, layer=r.layer, severity=r.severity, confidence=r.confidence,
                        cause=r.cause, unit=unit, item=item, session=session, statement=statement,
                        evidence={**(evidence or {}), "n": facts.runs, "window_days": facts.window_days},
                        remedy=r.remedy)


def step_attempts(facts: HistoryFacts, unit: str) -> list[Attempt]:
    return [a for a in facts.attempts if a.unit == unit and a.kind in STEP_KINDS]


def total_spend(facts: HistoryFacts) -> float:
    return sum(a.cost or 0.0 for a in facts.attempts)


def repeat_share(facts: HistoryFacts, unit: str) -> tuple[float, str]:
    """The gate's repeats (retry sessions) as a share of the workflow's spend, else of its sessions."""
    spend = total_spend(facts)
    if spend > 0:
        return sum(a.cost or 0.0 for a in facts.attempts if a.unit == unit and a.kind == "retry") / spend, "cost"
    total = len(facts.attempts)
    return (sum(1 for a in facts.attempts if a.unit == unit and a.kind == "retry") / total if total else 0.0,
            "attempts")


def _visits(facts: HistoryFacts, unit: str) -> list[Any]:
    return [v for v in facts.visits if v.unit == unit and v.tokens]


# -- C1 ---------------------------------------------------------------------------------------------------------


def loop_driver_criterion(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    out = []
    for unit in dict.fromkeys(r.unit for r in facts.retries):
        retries = [r for r in facts.retries if r.unit == unit]
        if len(retries) < P["loop_min_retries"]:
            continue
        leads = Counter(r.blockers[0] for r in retries if r.blockers)
        if not leads:
            continue
        crit, led = leads.most_common(1)[0]
        share, basis = repeat_share(facts, unit)
        if led / len(retries) >= P["loop_lead_share"] and share >= P["loop_repeat_share"]:
            out.append(finding("loop-driver-criterion", facts, unit,
                               f"criterion {crit!r} leads {led} of {len(retries)} RETRY verdicts of {unit} and its "
                               f"repeats are {share:.0%} of spend", item=crit,
                               evidence={"criterion": crit, "retries": len(retries), "led": led,
                                         "repeat_share": round(share, 3), "basis": basis}))
    return out


def low_first_pass(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    out = []
    for unit in dict.fromkeys(v.unit for v in facts.visits):
        visits = _visits(facts, unit)
        passed = sum(1 for v in visits if v.first_pass)
        if len(visits) >= P["min_visits"] and passed / len(visits) < P["first_pass_floor"]:
            out.append(finding("low-first-pass", facts, unit, f"{unit} passes first time in {passed} of "
                               f"{len(visits)} visits", evidence={"visits": len(visits), "first_pass": passed,
                                                                  "yield": round(passed / len(visits), 3)}))
    return out


def no_change_retried(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    out = []
    for unit in dict.fromkeys(r.unit for r in facts.retries):
        hits = [r for r in facts.retries if r.unit == unit and r.blockers and set(r.blockers) <= set(r.no_change)]
        if hits:
            out.append(finding("no-change-retried", facts, unit, f"{len(hits)} RETRYs of {unit} had only "
                               "`no_change` blockers, which a retry cannot fix",
                               evidence={"retries": len(hits), "criteria": sorted({b for r in hits for b in r.blockers})}))
    return out


def repeated_check_evidence(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    out = []
    for unit in dict.fromkeys(c.unit for c in facts.checks):
        hits = {(c.run, c.visit) for c in facts.checks if c.unit == unit and c.attempts_after}
        if hits:
            out.append(finding("repeated-check-evidence", facts, unit, f"{len(hits)} visits of {unit} failed the "
                               "check twice with the same evidence and ran a new attempt",
                               evidence={"visits": len(hits)}))
    return out


def missing_field_rendered(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    out = []
    for unit in dict.fromkeys(m[1] for m in facts.missing):
        hits = [m for m in facts.missing if m[1] == unit]
        for marker in dict.fromkeys(m[2] for m in hits):
            out.append(finding("missing-field-rendered", facts, unit, f"a step record of {unit} shows {marker}",
                               item=marker, evidence={"records": sum(1 for m in hits if m[2] == marker),
                                                      "runs": len({m[0] for m in hits if m[2] == marker})}))
    return out


def fallback_rate(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    out = []
    for unit in dict.fromkeys(v.unit for v in facts.visits):
        visits = _visits(facts, unit)
        took = sum(1 for v in visits if v.fallback)
        if len(visits) >= P["min_visits"] and took / len(visits) >= P["fallback_share"]:
            out.append(finding("fallback-rate", facts, unit, f"{unit} took its fallback in {took} of {len(visits)} "
                               "visits", evidence={"visits": len(visits), "fallbacks": took,
                                                   "share": round(took / len(visits), 3)}))
    return out


# -- C2 ---------------------------------------------------------------------------------------------------------


def check_ran_nothing(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    out = []
    for unit in dict.fromkeys(c.unit for c in facts.checks):
        hits = [c for c in facts.checks if c.unit == unit and c.ran_nothing]
        if hits:
            out.append(finding("check-ran-nothing", facts, unit, f"the check of {unit} ran none of its declared "
                               f"commands in {len(hits)} records", evidence={"checks": len(hits),
                                                                             "runs": len({c.run for c in hits})}))
    return out


def infra_heavy(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    out = []
    for unit in dict.fromkeys(a.unit for a in facts.attempts):
        attempts = step_attempts(facts, unit)
        infra = [a for a in attempts if a.infra_cause]
        if len(attempts) >= P["infra_min_attempts"] and len(infra) / len(attempts) >= P["infra_share"]:
            lead = Counter(str(a.infra_cause) for a in infra).most_common(1)[0][0]
            out.append(finding("infra-heavy", facts, unit, f"{len(infra)} of {len(attempts)} attempts of {unit} "
                               f"ended on an infrastructure cause, most often {lead}",
                               evidence={"attempts": len(attempts), "infra": len(infra), "leading_cause": lead,
                                         "share": round(len(infra) / len(attempts), 3)}))
    return out


# -- C3 ---------------------------------------------------------------------------------------------------------


def _passing(facts: HistoryFacts, unit: str) -> list[Attempt]:
    return [a for a in step_attempts(facts, unit) if a.ok and not a.timed_out and not a.stalled
            and a.duration_s is not None]


def _limit(facts: HistoryFacts, unit: str) -> float | None:
    limits = [a.timeout_s for a in step_attempts(facts, unit) if a.timeout_s]
    return max(limits) if limits else None


def timeout_below_pass_p90(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    out = []
    for unit in dict.fromkeys(a.unit for a in facts.attempts):
        passing, limit = _passing(facts, unit), _limit(facts, unit)
        if len(passing) < P["min_passing_attempts"] or limit is None:
            continue
        q = p90([float(a.duration_s or 0) for a in passing])
        if limit < P["timeout_fit_ratio"] * q:
            rec = round(P["timeout_recommend_ratio"] * q)
            out.append(finding("timeout-below-pass-p90", facts, unit, f"the {int(limit)} s limit of {unit} is below "
                               f"{P['timeout_fit_ratio']} x the p90 of passing attempts ({round(q)} s); about {rec} s "
                               "would fit", evidence={"limit_s": int(limit), "p90_s": round(q),
                                                      "recommended_s": rec, "passing": len(passing)}))
    return out


def attempts_at_limit(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    out = []
    for unit in dict.fromkeys(a.unit for a in facts.attempts):
        attempts = step_attempts(facts, unit)
        bad = [a for a in attempts if a.timed_out or a.stalled]
        if len(attempts) >= P["min_visits"] and bad and len(bad) / len(attempts) >= P["timeout_share"]:
            shapes = Counter(a.end_shape or ("slow_host" if a.tool_wall_share >= P["slow_tool_share"]
                                             else "model_silent") for a in bad)
            out.append(finding("attempts-at-limit", facts, unit, f"{len(bad)} of {len(attempts)} attempts of {unit} "
                               "timed out or stalled", evidence={"attempts": len(attempts), "at_limit": len(bad),
                                                                 "shapes": dict(shapes)}))
    return out


def limit_far_above_p90(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    out = []
    for unit in dict.fromkeys(a.unit for a in facts.attempts):
        passing, limit = _passing(facts, unit), _limit(facts, unit)
        if len(passing) < P["min_passing_attempts"] or limit is None:
            continue
        q = p90([float(a.duration_s or 0) for a in passing])
        if q > 0 and limit > P["timeout_loose_ratio"] * q:
            out.append(finding("limit-far-above-p90", facts, unit, f"the {int(limit)} s limit of {unit} is over "
                               f"{P['timeout_loose_ratio']:g} x the p90 of passing attempts ({round(q)} s)",
                               evidence={"limit_s": int(limit), "p90_s": round(q), "passing": len(passing)}))
    return out


def request_timed_out(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    out = []
    for unit in dict.fromkeys(a.unit for a in facts.attempts):
        attempts = step_attempts(facts, unit)
        hits = [a for a in attempts if a.infra_cause == "request_timed_out"]
        if hits:
            largest = max((a.output_tokens or 0 for a in attempts), default=0)
            out.append(finding("request-timed-out", facts, unit, f"{len(hits)} requests of {unit} timed out; its "
                               f"largest single response was {largest} tokens",
                               evidence={"requests": len(hits), "largest_response_tokens": largest}))
    return out


HISTORY_C1_C3: dict[str, Rule] = {
    "loop-driver-criterion": loop_driver_criterion, "low-first-pass": low_first_pass,
    "no-change-retried": no_change_retried, "repeated-check-evidence": repeated_check_evidence,
    "missing-field-rendered": missing_field_rendered, "fallback-rate": fallback_rate,
    "check-ran-nothing": check_ran_nothing, "infra-heavy": infra_heavy,
    "timeout-below-pass-p90": timeout_below_pass_p90, "attempts-at-limit": attempts_at_limit,
    "limit-far-above-p90": limit_far_above_p90, "request-timed-out": request_timed_out,
}


def hot_spots(facts: HistoryFacts, findings: list[AuditFinding]) -> list[dict[str, Any]]:
    """AUD-B3: per unit the repeat share of spend, first-pass yield, timeouts, refusals and pauses per run."""
    out = []
    for unit in facts.units():
        visits = _visits(facts, unit)
        mine = order([f for f in findings if f.unit == unit], ())
        refusals: int | str = ("unclassified" if facts.runs and facts.journal_runs == 0 else
                               sum(len(s.denied) for s in facts.sessions if s.unit == unit and s.journal))
        out.append({"unit": unit, "findings": len(mine), "leading_rule": mine[0].rule if mine else None,
                    "repeat_share": round(repeat_share(facts, unit)[0], 3),
                    "first_pass_yield": round(sum(1 for v in visits if v.first_pass) / len(visits), 3) if visits
                    else None,
                    "timeouts": sum(1 for a in step_attempts(facts, unit) if a.timed_out or a.stalled),
                    "refusals": refusals,
                    "pauses_per_run": round(sum(1 for p in facts.pauses if p.unit == unit) / facts.runs, 3)
                    if facts.runs else None})
    return out
