"""Judgement parsing and the verdict rule (JDG §2.2, JDG-B2)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from tempergraph.contracts import CheckFinding, CheckResult, Criterion, GateSpec, Verdict
from tempergraph.run.judging import JudgeInputs, Unparsed, derive, parse_judgement, render_judge

GATE = GateSpec(criteria=(Criterion(text="file written", id="c-file"),
                          Criterion(text="tone", id="c-tone", severity="note")))


def block(rows: list[dict[str, Any]], **top: Any) -> str:
    return "Review.\n```json\n" + json.dumps({"criteria": rows, **top}) + "\n```"


def row(n: int, status: str, evidence: str = "notes.md:1", **kw: Any) -> dict[str, Any]:
    return {"n": n, "status": status, "evidence": evidence, **kw}


@pytest.mark.parametrize("text, why", [
    ("no block here", "no judgement block"),
    ("```json\n{not json}\n```", "not JSON"),
    ("```json\n{\"gap\": false}\n```", "no criteria list"),
    (block([{"status": "MET"}]), "without a number"),
    (block([row(1, "GREAT")]), "has status"),
    (block([row(1, "MET", id="c-other")]), "does not match"),
])
def test_unparsed(text: str, why: str) -> None:
    with pytest.raises(Unparsed, match=why):
        parse_judgement(text, GATE)


def test_last_block_wins() -> None:
    text = block([row(1, "UNMET")]) + "\nOn reflection:\n" + block([row(1, "MET"), row(2, "MET")], confidence=0.9)
    j = parse_judgement(text, GATE)
    assert [f.status for f in j.criteria] == ["MET", "MET"] and j.confidence == 0.9


def outcome(rows: list[dict[str, Any]], check: CheckResult | None = None, back: dict[str, str] | None = None,
            gate: GateSpec = GATE, **top: Any) -> Any:
    return derive(parse_judgement(block(rows, **top), gate), gate, check, back)


def test_all_met_proceeds() -> None:
    assert outcome([row(1, "MET"), row(2, "MET")]).verdict is Verdict.PROCEED


def test_met_without_evidence_is_partial() -> None:
    o = outcome([row(1, "MET", evidence=" "), row(2, "MET")])
    assert o.verdict is Verdict.RETRY and o.statuses[0]["status"] == "PARTIAL"


def test_missing_criterion_is_unmet() -> None:
    assert outcome([row(2, "MET")]).verdict is Verdict.RETRY


def test_note_criterion_never_blocks() -> None:
    o = outcome([row(1, "MET"), row(2, "UNMET")])
    assert o.verdict is Verdict.PROCEED and o.notes and not o.blockers


def test_unreasoned_na_is_unmet_unless_the_check_said_so() -> None:
    assert outcome([row(1, "N/A", evidence=""), row(2, "MET")]).verdict is Verdict.RETRY
    check = CheckResult(result="PASS", findings=[CheckFinding(status="n_a", criterion="c-file", message="no plan")])
    assert outcome([row(1, "N/A", evidence=""), row(2, "MET")], check).verdict is Verdict.PROCEED


def test_gap_and_unverifiable_escalate() -> None:
    assert outcome([row(1, "MET"), row(2, "MET")], gap=True).verdict is Verdict.ESCALATE
    assert outcome([row(1, "UNVERIFIABLE")]).reason == "unresolved_gap"


def test_defect_in_goes_back_to_the_earliest() -> None:
    o = outcome([row(1, "UNMET", defect_in="plan")], back={"spec": "write_spec", "plan": "expand"})
    assert o.verdict is Verdict.BACK and o.back_to == "expand"
    assert outcome([row(1, "UNMET", defect_in="nowhere")], back={"plan": "expand"}).verdict is Verdict.RETRY


def test_no_change_escalates_only_by_policy() -> None:
    assert outcome([row(1, "UNMET", no_change=True)]).reason == "no_change"  # default policy: escalate
    retry = GateSpec(criteria=(Criterion(text="source", id="c-src", no_change_policy="retry"),))
    assert outcome([row(1, "UNMET", no_change=True)], gate=retry).verdict is Verdict.RETRY


def test_no_judgement_escalates_with_a_placeholder_confidence() -> None:
    o = derive(None, GATE, None)
    assert o.verdict is Verdict.ESCALATE and o.confidence_source == "engine_placeholder"


def test_prompt_marks_the_account_as_claims() -> None:
    text = render_judge(JudgeInputs(gate=GATE, stance="", brief="", request="Do X", step_account="I did it"))
    assert "claims to verify, not facts" in text and "Do X" in text and "1. [c-file] (blocker)" in text


def test_a_judge_never_grades_a_sign_off() -> None:  # OUT §2.2, live check L-25 (dr-approved UNVERIFIABLE)
    from tempergraph.run.judging import judged

    gate = GateSpec(criteria=(Criterion(text="review names each section", id="c-rev", verified_by="judge"),
                              Criterion(text="a person approves", id="c-ok", verified_by="person"),
                              Criterion(text="nobody yet", id="c-none", verified_by="none")))
    shown = judged(gate)
    assert [c.id for c in shown.criteria] == ["c-rev"]
    prompt = render_judge(JudgeInputs(gate=shown, stance="", brief="", request="r", references={}, subject={}))
    assert "c-rev" in prompt and "c-ok" not in prompt and "c-none" not in prompt
    only = GateSpec(criteria=(Criterion(text="a person approves", id="c-ok", verified_by="person"),))
    assert judged(only) is only


def test_check_evidence_is_given_not_a_claim() -> None:  # JDG §2.1, live check L-25 (outcome judge gap)
    from tempergraph.run.judging import CHECK_EVIDENCE

    prompt = render_judge(JudgeInputs(gate=GATE, stance="", brief="", request="r", references={}, subject={},
                                      check=CheckResult(result="PASS", evidence="Changes since v1.0: - abc fix")))
    assert CHECK_EVIDENCE in prompt and "not the step's claim" in prompt and "- abc fix" in prompt
