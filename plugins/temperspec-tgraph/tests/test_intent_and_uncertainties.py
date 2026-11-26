"""The task's intent and its open questions: the triage note's `Intent` and `Uncertainties` sections, what the
check, the routes, the reading sessions and the list of the owner's questions do with them, and how the hand-off
ends each (rule `task-notes.rule.md`; specs `triage`, `parallel-reading`, `owner-questions`, `discovery`)."""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from tempergraph.package.loader import load_package
from tempergraph.run import asking

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
fmt = importlib.import_module("tgwf_temperspec.specfmt")
routing = importlib.import_module("tgwf_temperspec.routing")
checks = importlib.import_module("tgwf_temperspec.checks")
conversation = importlib.import_module("test_conversation")

U_CODE = "- U1 existing behaviour: does a refresh count as a request? Shapes how idle time is measured. Route: code\n"
U_BLOCK = "- U2 limits: how many attempts before the account locks? Blocks the lock behaviour. Route: code\n"
U_OWNER = "- U3 names: which exit code marks the failure? Blocks the criterion on the exit code. Route: owner\n"
U_PLAN = "- U4 failures: what does a refused client see? Detail of the refusal. Route: plan\n"
ENTRY = "- U3: Which exit code?\n  - Options: a) 2; b) 78\n  - Default: a\n  - If wrong: scripts miss the failure\n"


def _note(uncertainties: str = "None\n", gaps: str = "None\n", owner: str = "None\n", route: str = "discovery",
          assumptions: str = "- Assumptions: None\n") -> str:
    return ("# Triage: T\n\n## Task\n\nx\n\n## Acceptance criteria\n\n1. One\n\n## Intent\n\n- Goal: g\n- In scope: i\n"
            f"- Out of scope: o\n{assumptions}\n## Existing documents\n\n- None\n\n## Uncertainties\n\n{uncertainties}\n"
            f"## Gaps\n\n{gaps}\n## Owner decisions\n\n{owner}\n## Route\n\n- Deliver: code\n- Route: {route}\n")


def _check(tmp_path: Path, note: str, conv: str = "blocking") -> Any:
    return conversation._never(tmp_path, note, conv)


def _of(res: Any, criterion: str) -> list[Any]:
    return [f for f in res.findings if f.criterion == criterion]


# -- the format -------------------------------------------------------------------------------------------------------


def test_the_rule_example_of_the_triage_note_is_read_by_the_parser() -> None:
    rule = (ROOT / "rules" / "task-notes.rule.md").read_text(encoding="utf-8")
    example = next(b for b in fmt.EXAMPLE.findall(rule) if b.startswith("# Triage"))
    note = fmt.parse_triage(example)
    assert note.missing == [] and fmt.intent_problems(note) == []
    assert note.intent["goal"] and note.assumptions == {"A1": True}
    assert [(u.id, u.category, u.impact, u.route) for u in note.uncertainties] == [
        ("U1", "existing behaviour", "shapes", "code"), ("U2", "failures", "detail", "plan")]
    assert [u.id for u in note.working] == ["U1"] and [u.id for u in note.readable] == ["U1"]
    for word in (*fmt.UNCERTAINTY_CATEGORIES, "`Blocks`", "`Shapes`", "`Detail`", "`code`", "`docs`", "`source`",
                 "`owner`", "`plan`", "If wrong:"):
        assert word in rule, word
    template = (ROOT.parents[1] / "docs" / "templates" / "triage.template.md").read_text(encoding="utf-8")
    assert "## Intent" in template and "## Uncertainties" in template  # the installed copy follows the rule


def test_a_complete_note_passes_and_none_is_a_valid_list(tmp_path: Path) -> None:
    res = _check(tmp_path / "a", _note(U_CODE + U_OWNER + U_PLAN, owner=ENTRY))
    assert [f.status for f in _of(res, "ts-tri-form")] == ["pass"], res.evidence
    assert [f.status for f in _of(res, "ts-tri-owner")] == ["pass"], res.evidence
    assert [f.status for f in _of(res, "ts-tri-route")] == ["pass"], res.evidence
    none = _check(tmp_path / "b", _note(route="plan"))
    assert [f.status for f in _of(none, "ts-tri-form")] == ["pass"], none.evidence


@pytest.mark.parametrize(("change", "said"), [
    (lambda n: n.replace("- Goal: g\n", ""), "`Goal:`"),
    (lambda n: n.replace("- Out of scope: o\n", ""), "`Out of scope:`"),
    (lambda n: n.replace("- Assumptions: None\n", ""), "Assumptions"),
    (lambda n: n.replace("- Assumptions: None\n", "- Assumptions:\n  - A1: the file is local\n"), "A1"),
    (lambda n: n.replace("## Uncertainties\n\nNone\n", "## Uncertainties\n\nnothing much\n"), "neither `None` nor rows"),
])
def test_an_incomplete_intent_fails_and_names_the_part(change: Any, said: str, tmp_path: Path) -> None:
    res = _check(tmp_path, change(_note(route="plan")))
    found = _of(res, "ts-tri-form")
    assert res.result == "FAIL" and any(said in f.message for f in found), res.evidence


@pytest.mark.parametrize(("row", "said"), [
    ("- U1 wording: how long? Shapes the text. Route: code\n", "category"),
    ("- U1 limits: how long? Route: code\n", "no impact"),
    ("- U1 limits: how long? Shapes the text\n", "does not end `Route:`"),
    ("- U1 limits: how long? Shapes the text. Route: guess\n", "does not end `Route:`"),
    ("- U1 limits: how long? Detail of the text. Route: code\n", "`Detail` row goes to `plan`"),
    ("- U1 limits: how long? Blocks the text. Route: plan\n", "`Detail` row goes to `plan`"),
])
def test_an_uncertainty_row_with_a_wrong_part_fails_and_names_the_row(row: str, said: str, tmp_path: Path) -> None:
    res = _check(tmp_path, _note(row))
    found = _of(res, "ts-tri-form")
    assert res.result == "FAIL" and any(said in f.message and f.place == "U1" for f in found), res.evidence


def test_a_row_for_the_owner_needs_an_entry_and_no_other_row_takes_one(tmp_path: Path) -> None:
    missing = _check(tmp_path / "a", _note(U_OWNER))
    assert any("U3" in f.message and "no entry" in f.message for f in _of(missing, "ts-tri-owner")), missing.evidence
    extra = _check(tmp_path / "b", _note(U_CODE, owner=ENTRY.replace("U3", "U1")))
    assert any("does not go to the owner" in f.message for f in _of(extra, "ts-tri-owner")), extra.evidence


# -- the route --------------------------------------------------------------------------------------------------------


def test_a_question_that_blocks_or_shapes_keeps_the_run_out_of_plan_and_quick(tmp_path: Path) -> None:
    plan = _check(tmp_path / "a", _note(U_CODE, route="plan"))
    assert any("give `discovery`" in f.message for f in _of(plan, "ts-tri-route")), plan.evidence
    detail = _check(tmp_path / "b", _note(U_PLAN, route="plan"))
    assert [f.status for f in _of(detail, "ts-tri-route")] == ["pass"], detail.evidence
    quick = fmt.parse_triage(_note(U_CODE, route="quick") + "\n## Change\n\n- Files: `a.py`\n- Tests: `t.py`\n"
                             "- Verify: `pytest t.py`\n")
    assert any("U1" in p for p in fmt.quick_problems(quick))
    assert fmt.quick_problems(fmt.parse_triage(_note(U_PLAN, route="quick") + "\n## Change\n\n- Files: `a.py`\n"
                                               "- Tests: `t.py`\n- Verify: `pytest t.py`\n")) == []


def test_the_units_run_in_the_order_reading_questions_pause_writing() -> None:
    order = list(SPEC.order)
    assert order[order.index("read_gap"):order.index("discovery") + 1] == [
        "read_gap", "owner_questions", "ask_route", "ask_owner", "discovery"]
    assert routing.route_triage(SimpleNamespace(values={"route": "discovery"}, artifact_keys=())) == "read_gap"
    assert routing.route_ask(SimpleNamespace(values={}, artifact_keys=("empty",))) == "discovery"
    record = (ROOT / "docs" / "adr" / "the-owner-is-asked-once-after-the-reading-sessions.adr.md").read_text()
    assert fmt.headings_missing(record, fmt.DECISION_HEADINGS) == []


# -- the reading sessions ---------------------------------------------------------------------------------------------


def test_the_items_read_are_the_gaps_and_the_questions_routed_to_a_source(tmp_path: Path) -> None:  # PRL-AC1
    gap = "- G1 spec gap: a. Searched `docs/specs/`: nothing. Findable\n"
    path = tmp_path / "n.md"
    path.write_text(_note(U_CODE + U_OWNER + U_PLAN, gaps=gap, owner=ENTRY), encoding="utf-8")
    items = routing.gap_items(SimpleNamespace(artifact=str(path), workdir=tmp_path, values={}))
    assert [i["id"] for i in items] == ["G1", "U1"] and items[1]["text"].startswith("- U1 existing behaviour")
    path.write_text(_note(U_CODE + U_BLOCK), encoding="utf-8")  # no gap, two questions to read
    assert [i["id"] for i in routing.gap_items(SimpleNamespace(artifact=str(path), workdir=tmp_path, values={}))] == [
        "U1", "U2"]
    path.write_text(_note(U_CODE + U_OWNER + U_PLAN, owner=ENTRY), encoding="utf-8")  # one row to read: no session
    assert routing.gap_items(SimpleNamespace(artifact=str(path), workdir=tmp_path, values={})) == []


def test_the_reading_prompt_and_its_judge_tell_answered_from_not_answered() -> None:
    prompt = (ROOT / "prompts" / "read_gap.md").read_text(encoding="utf-8")
    brief = (ROOT / "judges" / "read_gap.md").read_text(encoding="utf-8")
    for text in (prompt, brief):
        assert "`Answered:`" in text and "`Not answered:`" in text
    assert "`Reach:`" in prompt


# -- the owner's questions (OWQ-AC11) ---------------------------------------------------------------------------------


def _ask(tmp_path: Path, note: str, conv: str, findings: dict[str, str]) -> list[Any]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "triage_note.md").write_text(note, encoding="utf-8")
    ctx = SimpleNamespace(unit="owner_questions", workdir=tmp_path, request={},
                          values={"read_gap": {f"gap_finding[{k}]": v for k, v in findings.items()}},
                          artifacts={"triage": {"triage_note": "triage_note.md"}}, settings={"conversation": conv})
    got = routing.owner_questions(ctx)
    return asking.from_list((tmp_path / got["question_list"]).read_text()) if "empty" not in got else []


def test_owq_ac11_a_blocking_question_the_reading_could_not_answer_is_asked_in_words(tmp_path: Path) -> None:
    note = _note(U_CODE + U_BLOCK + U_OWNER, owner=ENTRY)
    open_ = {"U1": "Not answered: searched src/ for refresh", "U2": "Not answered: searched src/ for \"lock\""}
    listed = _ask(tmp_path / "a", note, "blocking", open_)
    assert [q.name for q in listed] == ["u3", "u2"]  # the owner decision first; U1 only shapes, so it is not asked
    assert listed[0].kind == "choice" and listed[0].choices == ("a", "b")
    assert listed[1].kind == "text" and listed[1].default == routing.LEAST_CHANGE and "U2 limits" in listed[1].text
    assert len(listed[1].text) <= 500
    answered = _ask(tmp_path / "b", note, "blocking", {"U2": "Answered: 3 attempts (src/lock.py, lines 4-9)"})
    assert [q.name for q in answered] == ["u3"]
    assert _ask(tmp_path / "c", note, "never", open_) == []
    assert [q.name for q in _ask(tmp_path / "d", note, "blocking", {})] == ["u3"]  # no reading session ran


# -- the hand-off -----------------------------------------------------------------------------------------------------


def _closed(tmp_path: Path, handoff: str, note: str) -> list[Any]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "triage_note.md").write_text(note, encoding="utf-8")
    return checks._uncertain(conversation._context(tmp_path), handoff, "h.md")


def test_the_hand_off_gives_each_working_question_its_end(tmp_path: Path) -> None:
    note = _note(U_CODE + U_BLOCK + U_PLAN)
    good = ("## Uncertainties closed\n\n- U1: Answered: it counts (`src/s.py`, lines 4-9)\n"
            "- U2: Assumed: three attempts. If wrong: the limit is one constant to change\n")
    assert [f.status for f in _closed(tmp_path / "a", good, note)] == ["pass"]
    assert [f.status for f in _closed(tmp_path / "b", "## Problem\n\nx\n", _note(U_PLAN))] == ["n_a"]
    missing = _closed(tmp_path / "c", "## Problem\n\nx\n", note)
    assert missing[0].status == "fail" and "Uncertainties closed" in missing[0].message
    partial = _closed(tmp_path / "d", "## Uncertainties closed\n\n- U1: it counts\n- U2: Assumed: three\n", note)
    assert [f.place for f in partial] == ["U1", "U2"] and all(f.status == "fail" for f in partial)
    owner = _closed(tmp_path / "e", "## Uncertainties closed\n\n- U1: Owner: it counts\n- U2: Owner: 3\n", note)
    assert [f.status for f in owner] == ["pass"]


def test_the_rule_example_of_the_hand_off_carries_the_new_sections() -> None:
    rule = (ROOT / "rules" / "task-notes.rule.md").read_text(encoding="utf-8")
    example = next(b for b in fmt.EXAMPLE.findall(rule) if b.startswith("# Hand-off"))
    assert fmt.headings_missing(example, fmt.HANDOFF_HEADINGS) == []
    for heading in ("Uncertainties closed", "Left to the plan", "Reach"):
        assert f"## {heading}" in example and f"**{heading}**" in rule
    assert checks.CLOSED_ROW.search(re.search(r"^- U1: .*$", example, re.M).group(0))


# -- the prompts ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["triage", "read_gap", "discovery"])
def test_a_reshaped_prompt_says_what_the_step_owns_and_what_it_does_not(name: str) -> None:
    text = (ROOT / "prompts" / f"{name}.md").read_text(encoding="utf-8")
    assert "## What is yours" in text and "\nYou own:\n" in text and "\nYou do not own:\n" in text
    opening = text.split("\n\n")[1]
    assert opening.startswith("You are ") and len(re.findall(r"[.:] [A-Z]", opening)) >= 2  # role, reader, lens


def test_the_triage_and_discovery_prompts_name_the_new_sections() -> None:
    triage = (ROOT / "prompts" / "triage.md").read_text(encoding="utf-8")
    discovery = (ROOT / "prompts" / "discovery.md").read_text(encoding="utf-8")
    plan = (ROOT / "prompts" / "plan.md").read_text(encoding="utf-8")
    for word in ("`## Intent`", "`## Uncertainties`", "`Blocks`", "`Shapes`", "`Detail`", "Never rewrite the criterion"):
        assert word in triage, word
    for word in ("`## Uncertainties closed`", "`Answered:`", "`Owner:`", "`Assumed:`", "`## Left to the plan`",
                 "`## Reach`", "Write no behaviour for what you find"):
        assert word in discovery, word
    assert "`Left to the plan`" in plan and "`Reach`" in plan


def test_the_outcome_record_holds_the_criteria_and_their_revision() -> None:
    o = json.loads((ROOT / "outcome.json").read_text(encoding="utf-8"))
    triage = {c["id"]: c for c in o["intermediate"]["triage"]["criteria"]}
    discovery = {c["id"]: c for c in o["intermediate"]["discovery"]["criteria"]}
    assert "intent" in triage["ts-tri-form"]["text"] and "ts-tri-intent" not in triage  # one form criterion, nine would
    # make the step oversized for one gate
    assert (triage["ts-tri-uncertain"]["severity"], triage["ts-tri-uncertain"]["verified_by"]) == ("warning", "judge")
    assert (discovery["ts-dis-uncertain"]["severity"], discovery["ts-dis-uncertain"]["verified_by"]) == ("blocker", "check")
    entry = next(r for r in o["revisions"] if "discovery of intent" in r.get("note", ""))
    assert entry["origin"] == "authored" and o["revision"] >= entry["revision"] == 26
