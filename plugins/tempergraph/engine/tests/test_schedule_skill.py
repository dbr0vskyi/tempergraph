"""The `tempergraph:schedule` skill (TCK-B21; TCK-AC7; AC 9): its shape, the verbs it names and its eval cases."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tempergraph.cli.main import COMMANDS, _parser

from .test_source_rules import SHIPPED_WORKFLOW_NAMES

SKILL = Path(__file__).resolve().parents[2] / "skills" / "schedule"
CASES = SKILL / "references" / "eval-cases.md"


def text() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(SKILL.rglob("*.md")))


def test_tck_ac7_the_skill_has_the_shape_of_the_other_skills_a_core_and_references() -> None:
    core = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    head = re.match(r"^---\nname: (\S+)\ndescription: (.+)\n---\n", core)
    assert head and head.group(1) == "schedule" and len(head.group(2)) <= 1024
    for ref in re.findall(r"\]\((references/[^)]+)\)", core):
        assert (SKILL / ref).exists(), ref
    assert CASES.is_file() and "references/eval-cases.md" in core


def test_tck_ac7_the_skill_names_only_built_verbs_and_options() -> None:
    parser = _parser()
    sub = next(a for a in parser._actions if isinstance(getattr(a, "choices", None), dict))
    schedule = sub.choices["schedule"]
    inner = next(a for a in schedule._actions if isinstance(getattr(a, "choices", None), dict)).choices
    seen = 0
    for words in re.findall(r"`tempergraph schedule ([^`]*)`", text()):
        verb = words.split()[0]
        assert verb in inner, f"schedule {verb} is not built"
        opts = {o for a in inner[verb]._actions for o in a.option_strings}
        for nested in inner[verb]._actions:  # `trigger install --os`
            if isinstance(getattr(nested, "choices", None), dict):
                for p in nested.choices.values():
                    opts |= {o for a in p._actions for o in a.option_strings}
        for opt in re.findall(r"(--[a-z-]+)", words):
            assert opt in opts, f"schedule {verb} {opt}"
        seen += 1
    assert seen >= 12 and "schedule" in COMMANDS


def test_tck_ac7_the_skill_calls_parse_saves_with_yes_relayed_and_offers_the_loop() -> None:
    t = text()
    assert "`tempergraph schedule parse" in t  # the echo is shown verbatim
    assert re.search(r"`tempergraph schedule add [^`]*--yes --relayed", t)
    assert "`tempergraph schedule loop --detach`" in t and "`tempergraph schedule trigger status`" in t
    assert "`tempergraph stats --projection`" in t and "--run-cost-cap" in t
    for verb in ("parse", "add", "list", "show", "edit", "pause", "resume", "skip", "remove", "fire", "runs", "trigger", "export"):
        assert f"schedule {verb}" in t, verb


def test_tck_ac7_the_skill_holds_no_state_and_never_uses_claude_codes_scheduled_tasks_or_loop() -> None:
    t = text()
    mentions = [ln for ln in t.splitlines()
                if ("scheduled task" in ln.lower() or "/loop" in ln) and not ln.startswith("- Words:")]  # a case's words are the person's
    bad = [ln[:60] for ln in mentions if not re.search(r"\b(never|not)\b", ln, re.I)]
    assert mentions and not bad, bad  # the skill names them only to forbid them
    assert re.search(r"holds no state", t, re.I) and "CronCreate" not in t
    assert not [w for w in SHIPPED_WORKFLOW_NAMES if w in t]  # the skill names no workflow of the repository


def case_blocks() -> dict[str, str]:
    body = CASES.read_text(encoding="utf-8")
    return dict(re.findall(r"^### (E\d+ .+?)\n(.*?)(?=^### |\Z)", body, re.S | re.M))


def test_tck_ac7_each_eval_case_has_the_words_the_verbs_and_the_outcome() -> None:
    blocks = case_blocks()
    assert len(blocks) >= 9
    for head, body in blocks.items():
        for field in ("Words:", "Verbs:", "Outcome:"):
            assert re.search(rf"^- {re.escape(field)} .+", body, re.M), (head, field)
        for verb in re.findall(r"`schedule ([a-z]+)", body):
            assert verb in {"parse", "add", "list", "show", "edit", "pause", "resume", "skip", "remove", "fire", "runs", "tick",
                            "loop", "trigger", "export", "history"}, (head, verb)


@pytest.mark.parametrize("needle", [
    "every weekday at 8",  # a clear phrase
    "every day at 9", "every monday", "03/04 at 10:00", "every month on the 31st",  # each `needs` case of SCH-B2
    "--rrule",  # the same schedule given in an exact format
    "no run cost cap", "without a person turn"])  # a missing cost cap, an agent call without a person turn
def test_tck_ac7_the_eval_cases_cover_the_five_kinds_of_case(needle: str) -> None:
    assert needle in CASES.read_text(encoding="utf-8")


def test_tck_ac7_the_cases_state_what_each_needs_case_of_sch_b2_must_end_in() -> None:
    body = CASES.read_text(encoding="utf-8")
    assert "exit 3" in body and "09:00" in body and "21:00" in body and "date_ambiguous" in body and "2027-03-04" in body
    assert "schedule_not_by_person" in body and "cost_cap_required" in body
