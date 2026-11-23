"""The history rules of C5 to C8 (ARC-B12 to ARC-B15) and the rendered owned rules (ARC-B1, ARC-AC4): each raised by a
fixture of synthetic run records and quiet on a clean one (AUD-AC1, ARC-AC1), with the catalog's severity,
confidence, cause and remedy, and skipped with `n=<n> of <min>` below its minimum sample (AUD-AC3). The council rules
read synthetic records shaped by CNL-B10, CNL-B2 and CNL-B12, whose unit is not built yet; the contest rule reads
synthetic records shaped by CTS-B7 and the `contest` record the engine writes (EVT-B15)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tempergraph.audit import catalog as cat

from .test_audit import clean_step, wf
from .test_audit_history import audit_history, many, read, write_run
from .test_audit_history_rules import CASES as CASES_C1_C3
from .test_audit_history_rules import Build, each, found, sample, uniform


def pause(*, feedback: bool = False, unit: str = "draft") -> list[dict[str, Any]]:
    return [{"kind": "pause", "unit": unit, "pause_kind": "approval"},
            {"kind": "human", "unit": unit, "decision": "proceed", "feedback": feedback}]


def sup(**kw: Any) -> dict[str, Any]:
    touches = {c: {} for c in ("designed", "rescue", "steer", "engine")}
    touches.update(kw.pop("touches", {}))
    return {"kind": "supervision", "undesigned": 0, "agent_own_rescues": 0, "touches": touches, **kw}


def council(r0: dict[str, str], r1: dict[str, str], changed: dict[str, bool], outcome: str) -> dict[str, Any]:
    """A `council` record: rounds with each member's choice and `changed` flag (CNL-B10, CNL-B2, CNL-B12)."""
    return {"kind": "council", "unit": "verdict", "outcome": outcome,
            "rounds": [{"round": 0, "choices": r0, "changed": {}}, {"round": 1, "choices": r1, "changed": changed}]}


def contest(winner: int) -> dict[str, Any]:
    """A `contest` run event: every slot's keys and the winner (CTS-B7)."""
    return {"kind": "contest", "unit": "pick", "winner": winner,
            "slots": [{"slot": n, "keys": ["notes"]} for n in (1, 2, 3)]}


R0 = {"A": "x", "B": "x", "C": "y"}
CONFORMS = council(R0, {"A": "x", "B": "x", "C": "x"}, {"C": True}, "x")  # C moved to the round-0 majority; no gain
AGAINST = council(R0, {"A": "y", "B": "x", "C": "y"}, {"A": True}, "y")  # A left the majority; the outcome moved


def _escapes(root: Path, n: int) -> None:
    each(root, n, lambda i: {"extra": [{"kind": "outcome", "verdict": "met"}],
                              "run_started": {"rerun_of": {"thread": "w/t000"}} if i == 5 else {}})


def _wins(root: Path, n: int) -> None:
    each(root, n, lambda i: {"extra": [contest(i % 3 + 1)]})


# rule id -> (raising fixture, clean fixture); each builds `n` runs
CASES: dict[str, tuple[Build, Build]] = {
    "empty-pauses": (uniform(extra=pause()), uniform(extra=pause(feedback=True))),
    "interventions-per-run": (uniform(extra=[sup(undesigned=2, touches={"rescue": {"person": 2}})]),
                              uniform(extra=[sup()])),
    "agent-rescues-alone": (
        uniform(extra=[sup(undesigned=3, agent_own_rescues=2, touches={"rescue": {"agent": 2, "person": 1}})]),
        uniform(extra=[sup(undesigned=3, touches={"rescue": {"person": 3}})])),
    "supervision-cost-share": (uniform(extra=[sup(supervision_share=0.3)]),
                               uniform(extra=[sup(supervision_share=0.05)])),
    "polling-supervisor": (uniform(extra=[sup(observations=30)]), uniform(extra=[sup(observations=5)])),
    "callers-unknown": (uniform(extra=[sup(touches={"rescue": {"unknown": 1, "person": 1}})]),
                        uniform(extra=[sup(touches={"rescue": {"person": 2}})])),
    "context-heavy-step": (uniform(attempts=[{"peak_context": 200_000}]), uniform(attempts=[{}])),
    "outcome-escapes": (_escapes, uniform(extra=[{"kind": "outcome", "verdict": "met"}])),
    "rendered-near-cut": (uniform(attempts=[{"prompt_cut": True}]), uniform(attempts=[{}])),
    "council-rounds-no-gain": (uniform(extra=[CONFORMS]), uniform(extra=[AGAINST])),
    "council-conformity": (uniform(extra=[CONFORMS]), uniform(extra=[AGAINST])),
    "contest-no-gain": (uniform(extra=[contest(1)]), _wins),
}
UNITS = {"empty-pauses": "draft", "context-heavy-step": "draft", "rendered-near-cut": "draft",
         "council-rounds-no-gain": "verdict", "council-conformity": "verdict", "contest-no-gain": "pick"}


def test_every_c5_to_c8_history_rule_has_a_fixture() -> None:
    """AUD-AC1: with the rendered owned rules of the next tests, no history rule of C5 to C8 is left out."""
    owned = {"cost-lens-rules", "engine-fault-open", "prompt-change-moved-gate"}
    history = {r.id for r in cat.RULES if r.layer == "history" and r.family != "C4"}
    assert history == set(CASES) | set(CASES_C1_C3) | owned


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_a_fixture_raises_the_rule_with_the_catalog_record(tmp_path: Path, rule_id: str) -> None:
    """AUD-AC1, ARC-AC1: the raising fixture fires the rule with the catalog's severity, confidence, cause, remedy."""
    r = cat.BY_ID[rule_id]
    n = sample(rule_id)
    _, fs = found(tmp_path, rule_id, n, CASES[rule_id][0])
    assert fs, rule_id
    f = fs[0]
    assert (f.layer, f.severity, f.confidence, f.cause, f.remedy) == ("history", r.severity, r.confidence, r.cause,
                                                                      r.remedy)
    assert f.unit == UNITS.get(rule_id) and f.evidence["window_days"] == 30
    assert f.evidence["n"] == n


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_a_clean_fixture_does_not_raise_the_rule(tmp_path: Path, rule_id: str) -> None:
    """AUD-AC1: the clean fixture is quiet, and the rule ran (it is not skipped)."""
    rep, fs = found(tmp_path, rule_id, max(sample(rule_id), 10), CASES[rule_id][1])
    assert fs == []
    assert rule_id not in {s["rule"] for s in rep.rules_skipped}


@pytest.mark.parametrize("rule_id", sorted(r for r in CASES if sample(r) > 1))
def test_below_min_n_a_rule_is_skipped_with_its_n(tmp_path: Path, rule_id: str) -> None:
    """AUD-AC3 (AUD-B5): below the minimum sample the rule gives no finding and is skipped as `n=<n> of <min>`."""
    need = sample(rule_id)
    rep, fs = found(tmp_path, rule_id, need - 1, CASES[rule_id][0])
    assert fs == []
    skipped = next(s for s in rep.rules_skipped if s["rule"] == rule_id)
    assert skipped["reason"] == f"n={need - 1} of {need}" and skipped["min_n"] == need


@pytest.mark.parametrize("rule_id", ["council-rounds-no-gain", "council-conformity", "contest-no-gain"])
def test_a_workflow_with_no_council_or_contest_records_is_skipped_never_passed(tmp_path: Path, rule_id: str) -> None:
    """ARC-AC1 (ARC-B7, ARC-B15): runs with no such records: skipped with `n=0 of 10`, no finding."""
    many(tmp_path, 12)
    rep = audit_history(wf({"draft": clean_step()}), read(tmp_path), tmp_path)
    skipped = next(s for s in rep.rules_skipped if s["rule"] == rule_id)
    assert skipped["reason"] == "n=0 of 10" and not [f for f in rep.findings if f.rule == rule_id]


def test_council_evidence_names_the_counts(tmp_path: Path) -> None:
    """ARC-B15: later rounds changed the outcome in 0 of 10 visits; every changing member joined the majority."""
    _, fs = found(tmp_path, "council-rounds-no-gain", 10, CASES["council-rounds-no-gain"][0])
    assert (fs[0].evidence["visits"], fs[0].evidence["changed_outcome"]) == (10, 0)
    _, fs = found(tmp_path, "council-conformity", 10, CASES["council-conformity"][0])
    assert (fs[0].evidence["rounds"], fs[0].evidence["conforming"]) == (10, 10)


def test_contest_evidence_names_the_winner(tmp_path: Path) -> None:
    """ARC-B15: the lowest-numbered slot won every pick."""
    _, fs = found(tmp_path, "contest-no-gain", 10, CASES["contest-no-gain"][0])
    assert (fs[0].evidence["picks"], fs[0].evidence["lowest_slot_wins"], fs[0].evidence["slots"]) == (10, 10, 3)


def engine_contest(winner: int | None, *, slots: int = 3) -> dict[str, Any]:
    """The `contest` record the engine writes (EVT-B15): places counted from 1, the slot names, check, verdict, keys, cost."""
    return {"kind": "contest", "unit": "pick", "visit": 1, "attempt": 1, "winner": winner, "slots": [
        {"slot": n, "name": f"s{n}", "attempt": 1, "check": "PASS", "verdict": "PROCEED", "cost": 0.3,
         "keys": {"unmet_warnings": 0, "met": 2, "confidence": 0.8}} for n in range(1, slots + 1)]}


def test_contest_no_gain_reads_the_record_the_engine_writes(tmp_path: Path) -> None:  # ARC-AC2 (ARC-B15, EVT-B15)
    """`slot` and `winner` are the integer places of a real run's record, not the slots' names."""
    _, fs = found(tmp_path, "contest-no-gain", 10, uniform(extra=[engine_contest(1)]))
    assert fs and (fs[0].evidence["picks"], fs[0].evidence["lowest_slot_wins"], fs[0].evidence["slots"]) == (10, 10, 3)
    rep, quiet = found(tmp_path, "contest-no-gain", 10, lambda root, n: each(
        root, n, lambda i: {"extra": [engine_contest(i % 3 + 1)]}))
    assert quiet == [] and "contest-no-gain" not in {s["rule"] for s in rep.rules_skipped}


def test_contest_no_gain_counts_no_record_of_a_pick_with_no_winner_for_the_lowest_slot(tmp_path: Path) -> None:  # ARC-AC2 (ARC-B15)
    _, fs = found(tmp_path, "contest-no-gain", 10, uniform(extra=[engine_contest(None)]))
    assert fs == []  # every check failed: no slot won, the lowest-numbered one least of all


def test_a_retry_that_ran_one_slot_alone_is_no_pick_for_contest_no_gain(tmp_path: Path) -> None:  # ARC-AC2 (ARC-B15, CTS-B8)
    rep, fs = found(tmp_path, "contest-no-gain", 10, uniform(extra=[engine_contest(1, slots=1)]))
    assert fs == []
    assert next(s for s in rep.rules_skipped if s["rule"] == "contest-no-gain")["reason"] == "n=0 of 10"


def test_interventions_are_split_by_class_and_decider(tmp_path: Path) -> None:
    """ARC-B12: the evidence splits the undesigned touches by class and decider."""
    _, fs = found(tmp_path, "interventions-per-run", 5, CASES["interventions-per-run"][0])
    assert fs[0].evidence["per_run"] == 2.0 and fs[0].evidence["by_class"] == {"rescue": 10}
    assert fs[0].evidence["by_decider"] == {"person": 10}


# -- owned rules are rendered from the owning component (ARC-B1, ARC-AC4) ----------------------------------------------


def test_cost_lens_findings_are_rendered_from_the_lens(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ARC-AC4 (ARC-B1): a finding the lens returns is carried unchanged with owner `SIL`; the audit computes none."""
    lens = {"rule": "judge_over_step", "unit": "verify", "monthly_saving_usd": 12.5, "filed": True,
            "basis": "reported, else estimated"}
    seen: list[Any] = []

    def fake(spec: Any, root: Path, version: Any, now: Any = None) -> dict[str, Any]:
        seen.append((spec.name, root, version))
        return {"status": "ok", "findings": [lens]}

    monkeypatch.setattr("tempergraph.improve.lenses.cost_rules", fake)
    many(tmp_path, 1)
    rep = audit_history(wf({"draft": clean_step()}), read(tmp_path), tmp_path)
    (f,) = [f for f in rep.findings if f.rule.startswith("cost-lens:")]
    assert (f.rule, f.owner, f.unit, f.layer) == ("cost-lens:judge_over_step", "SIL", "verify", "history")
    assert f.evidence["monthly_saving_usd"] == 12.5 and f.evidence["basis"] == "reported, else estimated"
    assert seen and seen[0][1] == tmp_path
    assert {"owner": "SIL", "count": 1} in rep.owned
    monkeypatch.setattr("tempergraph.improve.lenses.cost_rules", lambda *a, **k: {"status": "thin", "findings": []})
    rep = audit_history(wf({"draft": clean_step()}), read(tmp_path), tmp_path)
    assert not [f for f in rep.findings if f.rule.startswith("cost-lens:")]


def test_engine_fault_open_renders_engine_side_findings_naming_this_workflows_units(tmp_path: Path) -> None:
    """ARC-B14: open engine- or executor-side findings that name this workflow's units are rendered as `SIL:<code>`."""
    engine = {"side": "engine", "cause": "spawn_failed", "unit": "draft", "class": "infra"}
    other_unit = {"side": "engine", "cause": "spawn_failed", "unit": "elsewhere", "class": "infra"}
    workflow_side = {"side": "workflow", "cause": "retry_burst", "unit": "draft", "class": "fault"}
    write_run(tmp_path, "t000", findings=[engine, other_unit, workflow_side])
    rep = audit_history(wf({"draft": clean_step()}), read(tmp_path), tmp_path)
    (f,) = [f for f in rep.findings if f.rule.startswith("SIL:")]
    assert (f.rule, f.owner, f.unit, f.severity, f.confidence) == ("SIL:spawn_failed", "SIL", "draft", "info", "high")
    assert f.evidence["runs"] == 1
    write_run(tmp_path, "t000", findings=[workflow_side])
    rep = audit_history(wf({"draft": clean_step()}), read(tmp_path), tmp_path)
    assert not [f for f in rep.findings if f.rule.startswith("SIL:")]


def test_prompt_change_moved_gate_is_rendered_from_the_watch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ARC-AC4: the post-release watch's finding is rendered as `SIL:<code>`; without the watch the rule is skipped
    with `owner not present`, never passed."""
    many(tmp_path, 1)
    spec = wf({"draft": clean_step()})
    rep = audit_history(spec, read(tmp_path), tmp_path)
    assert next(s for s in rep.rules_skipped if s["rule"] == "prompt-change-moved-gate")["reason"] == "owner not present"
    watch = {"code": "first_pass_fell", "unit": "draft", "digest": "d1", "date": "2026-11-20", "before": 0.8,
             "after": 0.4, "message": "the prompt change of d1 moved first-pass yield from 0.8 to 0.4"}
    monkeypatch.setattr("tempergraph.audit.owned._watch", lambda: lambda spec, root, version: [watch])
    rep = audit_history(spec, read(tmp_path), tmp_path)
    (f,) = [f for f in rep.findings if f.rule == "SIL:first_pass_fell"]
    assert f.statement == watch["message"] and f.unit == "draft" and f.owner == "SIL"
    assert (f.evidence["before"], f.evidence["after"], f.evidence["date"]) == (0.8, 0.4, "2026-11-20")
    monkeypatch.setattr("tempergraph.audit.owned._watch", lambda: lambda spec, root, version: [])
    rep = audit_history(spec, read(tmp_path), tmp_path)
    assert not [f for f in rep.findings if f.rule.startswith("SIL:")]
    assert "prompt-change-moved-gate" not in {s["rule"] for s in rep.rules_skipped}


def test_the_audit_holds_no_copy_of_the_lens_or_watch_logic() -> None:
    """ARC-AC4: a source test: the lens's codes and the watch's logic live in their owners, not in `audit`."""
    src = Path(cat.__file__).parent
    body = "".join(p.read_text(encoding="utf-8") for p in src.glob("*.py"))
    assert "lenses.cost_rules(" in body
    for code in ("retry_after_check", "judge_over_step", "expensive_unblocked", "recurring_blocker", "unpriced_gate"):
        assert code not in body, code
