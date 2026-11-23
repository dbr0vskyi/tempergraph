"""The history rules of C5 to C8 (ARC-B12 to ARC-B15, PRA-B10): pauses and supervision, cost, the escape rate, the
cut prompt, and the council and contest rules (ARC-B15) that read only run records.

Every function reads `HistoryFacts` only. The council and contest rules count records of their own shape and report
their own `n` (`SAMPLE_N`): the council's `rounds` with each member's `choices` and `changed` flag (CNL-B10, CNL-B2,
CNL-B12) and a contest's `slots` and `winner` (CTS-B7). A workflow with none of them is skipped, never passed.
"""

from __future__ import annotations

import statistics
from collections import Counter
from collections.abc import Callable, Iterator
from typing import Any

from tempergraph.audit.history import STEP_KINDS, HistoryFacts
from tempergraph.audit.history_rules import P, Rule, finding
from tempergraph.audit.report import AuditFinding
from tempergraph.contracts import WorkflowSpec

TOUCH_CLASSES = ("designed", "rescue", "steer", "engine")


def _touches(rec: dict[str, Any]) -> Iterator[tuple[str, str, int]]:
    for cls, by in (rec.get("touches") or {}).items():
        if cls in TOUCH_CLASSES and isinstance(by, dict):
            for decider, n in by.items():
                yield cls, str(decider), int(n or 0)


# -- C5 ---------------------------------------------------------------------------------------------------------


def empty_pauses(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    out = []
    for unit in dict.fromkeys(p.unit for p in facts.pauses):
        ended = [p for p in facts.pauses if p.unit == unit and p.decision is not None]
        empty = [p for p in ended if p.decision == "proceed" and not p.feedback and not p.changed]
        if len(ended) >= P["min_pauses"] and len(empty) / len(ended) >= P["empty_pause_share"]:
            out.append(finding("empty-pauses", facts, unit, f"{len(empty)} of {len(ended)} pauses at {unit} ended in "
                               "`proceed` with no feedback and no workspace change",
                               evidence={"pauses": len(ended), "empty": len(empty)}))
    return out


def interventions_per_run(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    total = sum(int(r.get("undesigned") or 0) for r in facts.supervision)
    if not facts.runs or total / facts.runs <= P["interventions_per_run"]:
        return []
    by_class: Counter[str] = Counter()
    by_decider: Counter[str] = Counter()
    for r in facts.supervision:
        for cls, decider, n in _touches(r):
            if cls in ("rescue", "steer") and n:
                by_class[cls] += n
                by_decider[decider] += n
    by_kind: Counter[str] = Counter()
    for r in facts.supervision:
        for kind, n in ((r.get("touches") or {}).get("rescue_by_pause") or {}).items():
            by_kind[str(kind)] += int(n or 0)
    return [finding("interventions-per-run", facts, None, f"{total / facts.runs:.1f} undesigned touches per run "
                    f"over {facts.runs} runs", evidence={"per_run": round(total / facts.runs, 2),
                                                         "by_class": dict(by_class), "by_decider": dict(by_decider),
                                                         "by_pause_kind": dict(by_kind)})]


def agent_rescues_alone(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    rescues = sum(n for r in facts.supervision for cls, _, n in _touches(r) if cls == "rescue")
    alone = sum(int(r.get("agent_own_rescues") or 0) for r in facts.supervision)
    if rescues < P["min_rescues"] or alone / rescues < P["agent_rescue_share"]:
        return []
    return [finding("agent-rescues-alone", facts, None, f"agents made {alone} of {rescues} rescue decisions on "
                    "their own", evidence={"rescues": rescues, "agent_alone": alone,
                                           "share": round(alone / rescues, 3)})]


def supervision_cost_share(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    shares = [float(r["supervision_share"]) for r in facts.supervision if r.get("supervision_share") is not None]
    if len(shares) < P["min_measured_runs"] or statistics.median(shares) <= P["supervision_share"]:
        return []
    return [finding("supervision-cost-share", facts, None, f"supervision is a median {statistics.median(shares):.0%} "
                    f"of run cost over {len(shares)} measured runs",
                    evidence={"median_share": round(statistics.median(shares), 3), "measured_runs": len(shares)})]


def polling_supervisor(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    obs = [float(r["observations"]) for r in facts.supervision if r.get("observations") is not None]
    rewake = [float(r["rewake_share"]) for r in facts.supervision if r.get("rewake_share") is not None]
    polling = len(obs) >= P["min_measured_runs"] and statistics.mean(obs) > P["polling_observations"]
    waking = len(rewake) >= P["min_measured_runs"] and statistics.median(rewake) > P["rewake_share"]
    if not (polling or waking):
        return []
    return [finding("polling-supervisor", facts, None, "the supervisor polls the run instead of waiting on its exit",
                    evidence={"observations_per_run": round(statistics.mean(obs), 1) if obs else None,
                              "rewake_share": round(statistics.median(rewake), 3) if rewake else None})]


def callers_unknown(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    total = unknown = 0
    for r in facts.supervision:
        for _, decider, n in _touches(r):
            total += n
            unknown += n if decider == "unknown" else 0
    if total < P["min_touches"] or unknown / total <= P["unknown_caller_share"]:
        return []
    return [finding("callers-unknown", facts, None, f"{unknown} of {total} touches had caller `unknown`",
                    evidence={"touches": total, "unknown": unknown, "share": round(unknown / total, 3)})]


# -- C6 and C7 --------------------------------------------------------------------------------------------------


def context_heavy_step(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    out = []
    for unit in dict.fromkeys(a.unit for a in facts.attempts):
        peaks = [a.peak_context for a in facts.attempts if a.unit == unit and a.kind in STEP_KINDS and a.peak_context]
        if len(peaks) >= P["min_attempts"] and statistics.median(peaks) > P["context_peak_tokens"]:
            out.append(finding("context-heavy-step", facts, unit, f"the median peak context of {unit} is "
                               f"{int(statistics.median(peaks))} tokens", evidence={
                                   "attempts": len(peaks), "median_peak_tokens": int(statistics.median(peaks))}))
    return out


def outcome_escapes(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    graded = [(run, verdict) for run, verdict in facts.outcomes if verdict and verdict != "not_reached"]
    escapes = [run for run, verdict in graded if verdict in ("met", "met_with_open") and run in facts.rerun_sources]
    if len(graded) < P["min_graded_runs"] or len(escapes) / len(graded) < P["escape_rate"]:
        return []
    return [finding("outcome-escapes", facts, None, f"{len(escapes)} of {len(graded)} graded runs met the outcome "
                    "and were rerun", evidence={"graded": len(graded), "escapes": len(escapes),
                                                "rate": round(len(escapes) / len(graded), 3)})]


def rendered_near_cut(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    out = []
    for unit in dict.fromkeys(u for _, u in facts.cut_prompts):
        runs = {r for r, u in facts.cut_prompts if u == unit}
        out.append(finding("rendered-near-cut", facts, unit, f"the renderer cut the prompt of {unit} in "
                           f"{len(runs)} runs", evidence={"runs": len(runs)}))
    return out


# -- ARC-B15 council and contest -------------------------------------------------------------------------------


def leader(choices: dict[str, Any]) -> Any:
    """The round's majority choice; None on an empty round or a tie."""
    top = Counter(choices.values()).most_common(2)
    if not top or (len(top) > 1 and top[0][1] == top[1][1]):
        return None
    return top[0][0]


def _later(c: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in c.get("rounds") or [] if int(r.get("round") or 0) > 0]


def _round0(c: dict[str, Any]) -> dict[str, Any]:
    return next((r.get("choices") or {} for r in c.get("rounds") or [] if int(r.get("round") or 0) == 0), {})


def _councils(facts: HistoryFacts) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for c in facts.councils:
        if _later(c):
            out.setdefault(str(c.get("unit")), []).append(c)
    return out


def council_rounds_no_gain(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    out = []
    for unit, cs in _councils(facts).items():
        moved = sum(1 for c in cs if c.get("outcome") != leader(_round0(c)))
        if len(cs) >= P["min_picks"] and moved / len(cs) < P["council_gain_floor"]:
            out.append(finding("council-rounds-no-gain", facts, unit, f"later rounds of {unit} changed the outcome "
                               f"in {moved} of {len(cs)} visits", evidence={"visits": len(cs),
                                                                            "changed_outcome": moved}))
    return out


def council_conformity(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    out = []
    for unit, cs in _councils(facts).items():
        rounds = conforming = 0
        for c in cs:
            majority = leader(_round0(c))
            for r in _later(c):
                rounds += 1
                movers = [m for m, did in (r.get("changed") or {}).items() if did]
                if movers and all((r.get("choices") or {}).get(m) == majority for m in movers):
                    conforming += 1
        if rounds >= P["min_picks"] and conforming / rounds >= P["council_conformity_share"]:
            out.append(finding("council-conformity", facts, unit, f"in {conforming} of {rounds} rounds after round 0 "
                               "every member who changed moved to the round-0 majority",
                               evidence={"rounds": rounds, "conforming": conforming}))
    return out


def _place(value: Any) -> int | None:
    """A place in a `contest` record (EVT-B15): an integer counted from 1, as the engine writes it; None for any other."""
    try:
        return int(value) if value is not None and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


def _picked_among_many(record: Any) -> bool:
    """A `contest` record that picked among slots: two or more (a retry that ran the winner's slot alone is no pick)."""
    return len(record.get("slots") or []) >= 2


def contest_no_gain(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding]:
    out = []
    for unit in dict.fromkeys(str(c.get("unit")) for c in facts.contests):
        picks = [c for c in facts.contests if str(c.get("unit")) == unit and _picked_among_many(c)]
        lowest = sum(1 for c in picks if _place(c.get("winner")) == min(_place(s.get("slot")) or 0 for s in c["slots"]))
        if len(picks) >= P["min_picks"] and lowest / len(picks) >= P["contest_lowest_slot_share"]:
            out.append(finding("contest-no-gain", facts, unit, f"the lowest-numbered slot of {unit} won {lowest} of "
                               f"{len(picks)} picks", evidence={"picks": len(picks), "lowest_slot_wins": lowest,
                                                                "slots": len(picks[0]["slots"])}))
    return out


HISTORY_C5_C8: dict[str, Rule] = {
    "empty-pauses": empty_pauses, "interventions-per-run": interventions_per_run,
    "agent-rescues-alone": agent_rescues_alone, "supervision-cost-share": supervision_cost_share,
    "polling-supervisor": polling_supervisor, "callers-unknown": callers_unknown,
    "context-heavy-step": context_heavy_step, "outcome-escapes": outcome_escapes,
    "rendered-near-cut": rendered_near_cut, "council-rounds-no-gain": council_rounds_no_gain,
    "council-conformity": council_conformity, "contest-no-gain": contest_no_gain,
}

# The sample a rule counts when it is not the runs in the window (AUD-B5): records of its own shape.
SAMPLE_N: dict[str, Callable[[HistoryFacts], int]] = {
    "council-rounds-no-gain": lambda f: sum(len(v) for v in _councils(f).values()),
    "council-conformity": lambda f: sum(len(_later(c)) for v in _councils(f).values() for c in v),
    "contest-no-gain": lambda f: sum(1 for c in f.contests if _picked_among_many(c)),
}
