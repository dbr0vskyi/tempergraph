"""The conversation setting (spec `conversation`, CONV-B1 to CONV-B7; task i60, `AC <n>` are the task's)."""

from __future__ import annotations

import importlib
import json
import time
from pathlib import Path
from typing import Any

import pytest
from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts, run_check
from tempergraph.run.commands import CommandRun
from tempergraph.settings import ConfigFiles, options_snapshot, resolve, workflow_settings

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
checks = importlib.import_module("tgwf_temperspec.checks")
fmt = importlib.import_module("tgwf_temperspec.specfmt")
summary = importlib.import_module("tgwf_temperspec.summary")


def _go(flags: dict[str, Any] | None = None, files: ConfigFiles | None = None) -> tuple[Any, list[Any]]:
    opts, findings = options_snapshot(SPEC, flags or {}, (), files or ConfigFiles())
    return resolve(SPEC, opts), findings


def _example(rule: str, opening: str) -> str:
    """The fenced example of a rule file that starts with `opening`."""
    for block in rule.split("```markdown\n")[1:]:
        body = block.split("\n```", 1)[0]
        if body.startswith(opening):
            return body + "\n"
    raise AssertionError(f"no example starts with {opening!r}")


def _read(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def _said(text: str, *phrases: str) -> None:
    flat = " ".join(text.lower().split())
    for phrase in phrases:
        assert " ".join(phrase.lower().split()) in flat, phrase


# -- phase 1: the setting and the note's shape --------------------------------------------------------------


def test_the_workflow_declares_the_conversation_setting() -> None:  # CONV-AC1, AC 1
    decl = SPEC.settings["conversation"]
    assert decl.kind == "choice" and tuple(decl.choices or ()) == ("never", "blocking") and decl.default == "blocking"


def test_a_start_with_no_value_gives_blocking() -> None:  # CONV-AC1, AC 1
    res, findings = _go()
    assert findings == [] and workflow_settings(res)["conversation"] == "blocking"


def test_a_start_with_the_flag_gives_never() -> None:  # CONV-AC1, AC 1
    res, findings = _go({"settings.conversation": "never"})
    assert findings == [] and workflow_settings(res)["conversation"] == "never"


def test_a_repository_settings_entry_gives_never() -> None:  # CONV-AC1, AC 1
    files = ConfigFiles(project={"schema_version": 1, "overrides": [
        {"workflow": SPEC.name, "set": {"settings.conversation": "never"}}]}, project_path=Path("/p/settings.json"))
    res, findings = _go(files=files)
    assert findings == [] and workflow_settings(res)["conversation"] == "never"


def test_a_start_with_always_is_refused_and_lists_the_two_values() -> None:  # CONV-AC1, AC 1
    _, findings = _go({"settings.conversation": "always"})
    assert [f.code for f in findings] == ["setting_value"]
    assert "never" in findings[0].message and "blocking" in findings[0].message


def test_the_triage_prompt_names_the_value_and_asks_for_the_sort_only_under_never() -> None:  # CONV-AC2, AC 1
    prompt = _read("prompts", "triage.md")
    assert "{settings.conversation}" in prompt
    _said(prompt, "only when the value is `never`", "Findable", "Owner decision", "Owner decisions", "Options:",
          "Default:", "If wrong:", "two to four options", "None", "sort no gap", "no such section")


def test_the_task_notes_rule_example_of_the_sort_is_read_by_the_parser() -> None:  # CONV-AC2, AC 1
    rule = _read("rules", "task-notes.rule.md")
    note = fmt.parse_triage(_example(rule, "## Gaps"))
    assert note.sorts == {"G1": "findable", "G2": "owner decision", "G3": "findable"}
    assert note.owner_section and not note.owner_none and len(note.owners) == 1
    entry = note.owners[0]
    assert entry.gap == "G2" and entry.question.endswith("?") and len(entry.options) == 3
    assert entry.default_text and entry.cost
    assert entry.default_text == entry.options[0][1]
    none = fmt.parse_triage("## Gaps\n\n- G1 spec gap: x. Searched: nothing. Findable\n\n## Owner decisions\n\nNone\n\n"
                            "## Route\n\n- Deliver: code\n- Route: discovery\n")
    assert none.owner_none and none.owner_section and none.owners == [] and none.sorts == {"G1": "findable"}
    _said(rule, "Owner decisions", "Findable", "Owner decision", "Options:", "Default:", "If wrong:",
          "two to four options", "`blocking`")


# -- phase 2: the triage check refuses an incomplete sort ---------------------------------------------------

TRIAGE_CHECKS = ROOT / "evals" / "checks" / "triage"
HEAD = ("# Triage: T\n\n## Task\n\nx\n\n## Acceptance criteria\n\n1. One\n\n## Existing documents\n\n- None\n\n"
        "## Gaps\n\n")
TAIL = "\n## Route\n\n- Deliver: code\n- Route: discovery\n"
SORTED = ("- G1 spec gap: a. Searched `docs/specs/`: nothing. Findable\n"
          "- G2 decision needed: b. Searched `docs/specs/`: nothing. Owner decision\n")


def _note(gaps: str = SORTED, owner: str | None = None) -> str:
    return HEAD + gaps + ("" if owner is None else f"\n## Owner decisions\n\n{owner}") + TAIL


def _entry(gap: str = "G2", question: str | None = "Which exit code does the tool give?",
           options: str | None = "a) 2; b) 1; c) 78", default: str | None = "a",
           cost: str | None = "a script testing for 1 sees another code") -> str:
    lines = [f"- {gap}: {question or ''}"]
    for key, value in (("Options", options), ("Default", default), ("If wrong", cost)):
        if value is not None:
            lines.append(f"  - {key}: {value}")
    return "\n".join(lines) + "\n"


def _context(work: Path, settings: dict[str, Any] | None = None) -> CheckContext:
    ctx = CheckContext(unit="triage", workdir=work, request={}, artifacts={"triage": {"triage_note": "triage_note.md"}},
                       values={"triage": {}}, git=GitFacts(), allow=SPEC.allow_commands,
                       out_dir=work.parent / f"{work.name}.out", deadline_at=time.monotonic() + 60)
    if settings is not None:
        ctx.settings = settings
    return ctx


def _run(work: Path, note: str, settings: dict[str, Any] | None = None) -> Any:
    work.mkdir(parents=True, exist_ok=True)
    (work / "triage_note.md").write_text(note, encoding="utf-8")
    return run_check(SPEC.units["triage"].gate, _context(work, settings))[0]


def _owner(res: Any) -> list[Any]:
    return [f for f in res.findings if f.criterion == "ts-tri-owner"]


def _never(work: Path, note: str) -> Any:
    return _run(work, note, {"conversation": "never"})


def _criterion_ids(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        if isinstance(node.get("id"), str):
            found.add(node["id"])
        for value in node.values():
            found |= _criterion_ids(value)
    elif isinstance(node, list):
        for value in node:
            found |= _criterion_ids(value)
    return found


def _fails_naming(res: Any, *words: str) -> None:
    owner = _owner(res)
    assert res.result == "FAIL" and owner and all(f.status == "fail" for f in owner), res.evidence
    said = " ".join(f"{f.place} {f.message}" for f in owner)
    for word in words:
        assert word in said, (word, said)
    assert {f.criterion for f in res.findings} <= _criterion_ids(json.loads(_read("outcome.json")))


def test_a_gap_row_with_no_sort_fails_and_names_the_gap(tmp_path: Path) -> None:  # CONV-AC3, AC 1
    gaps = "- G1 spec gap: a. Searched `docs/specs/`: nothing\n- G2 decision needed: b. Owner decision\n"
    _fails_naming(_never(tmp_path, _note(gaps, _entry())), "G1")


def test_a_note_with_no_owner_decisions_section_fails_and_names_the_section(tmp_path: Path) -> None:  # CONV-AC3, AC 1
    _fails_naming(_never(tmp_path, _note(owner=None)), "Owner decisions")


def test_an_owner_decision_row_with_no_entry_fails_and_names_the_gap(tmp_path: Path) -> None:  # CONV-AC3, AC 1
    _fails_naming(_never(tmp_path, _note(owner="None\n")), "G2")


def test_an_entry_for_a_findable_row_fails_and_names_the_gap(tmp_path: Path) -> None:  # CONV-AC3, AC 1
    _fails_naming(_never(tmp_path, _note(owner=_entry("G2") + _entry("G1"))), "G1")


def test_an_entry_for_no_gap_row_fails_and_names_the_gap(tmp_path: Path) -> None:  # CONV-AC3, AC 1
    _fails_naming(_never(tmp_path, _note(owner=_entry("G2") + _entry("G7"))), "G7")


@pytest.mark.parametrize(("options", "said"), [("a) 2", "1 option"), ("a) 1; b) 2; c) 3; d) 4; e) 5", "5 options")])
def test_an_entry_with_too_few_or_too_many_options_fails(options: str, said: str, tmp_path: Path) -> None:  # CONV-AC4, AC 1
    _fails_naming(_never(tmp_path, _note(owner=_entry(options=options))), "G2", said)


@pytest.mark.parametrize(("change", "said"), [
    ({"question": None}, "question"), ({"default": None}, "default"), ({"default": "d"}, "not one of"),
    ({"cost": None}, "cost"), ({"options": None}, "option")])
def test_an_entry_with_a_missing_part_fails_and_names_the_part(change: dict[str, Any], said: str,
                                                                tmp_path: Path) -> None:  # CONV-AC4, AC 1
    _fails_naming(_never(tmp_path, _note(owner=_entry(**change))), "G2", said)


def test_a_default_may_name_its_option_by_the_words(tmp_path: Path) -> None:  # CONV-AC5, AC 4
    res = _never(tmp_path, _note(owner=_entry(default="78")))
    assert [f.status for f in _owner(res)] == ["pass"], res.evidence


def test_complete_entries_and_none_pass_under_never(tmp_path: Path) -> None:  # CONV-AC5, AC 4
    both = "- G1 spec gap: a. Owner decision\n- G2 decision needed: b. Owner decision\n"
    res = _never(tmp_path / "a", _note(both, _entry("G1") + _entry("G2", options="a) x; b) y", default="b")))
    assert res.result == "PASS" and [f.status for f in _owner(res)] == ["pass"], res.evidence
    findable = "- G1 spec gap: a. Findable\n- G2 spec update: b. Findable.\n"
    res = _never(tmp_path / "b", _note(findable, "None\n"))
    assert res.result == "PASS" and [f.status for f in _owner(res)] == ["pass"], res.evidence


@pytest.mark.parametrize("settings", [{"conversation": "blocking"}, {}, None])
def test_a_note_with_no_sort_passes_unless_the_value_is_never(settings: dict[str, Any] | None,
                                                               tmp_path: Path) -> None:  # CONV-AC5, AC 4
    gaps = "- G1 spec gap: a. Searched `docs/specs/`: nothing\n"
    res = _run(tmp_path, _note(gaps), settings)
    assert res.result == "PASS" and [f.status for f in _owner(res)] == ["n_a"], res.evidence


@pytest.mark.parametrize("fixture", sorted(p for p in (TRIAGE_CHECKS / "must-pass").iterdir() if p.is_dir()),
                         ids=lambda p: p.name)
def test_every_triage_fixture_that_must_pass_still_passes_with_no_settings(fixture: Path,
                                                                           tmp_path: Path) -> None:  # CONV-AC5, AC 4
    for src in sorted(p for p in fixture.rglob("*") if p.is_file()):
        target = tmp_path / src.relative_to(fixture)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(src.read_bytes())
    res = run_check(SPEC.units["triage"].gate, _context(tmp_path))[0]
    assert res.result == "PASS", res.evidence


# -- phase 3: discovery goes on with the default -------------------------------------------------------------


def test_the_discovery_prompt_goes_on_with_the_default_only_under_never() -> None:  # CONV-AC6, AC 2
    prompt = _read("prompts", "discovery.md")
    assert "{settings.conversation}" in prompt
    _said(prompt, "when the value is `never`", "close each owner decision of the triage note on its default",
          "no open question for it", "the option that changes the least", "Until answered: <option>",
          "never end blocked on an owner decision",
          "a task with no acceptance criterion still ends blocked in triage",
          "when the value is `blocking`", "end blocked on a question only a person can answer that blocks planning")


def test_the_discovery_prompt_keeps_what_the_process_criterion_and_the_budget_read() -> None:  # CONV-AC6, AC 2
    assert [f.status for f in checks._prompt_says("ts-dis-narrow")] == ["pass"]
    _said(_read("prompts", "discovery.md"), "400 lines", "30,720 bytes", "split by capability")


def test_no_unit_asks_a_person_and_no_gate_requires_a_sign_off() -> None:  # CONV-AC7, AC 2
    for name, unit in SPEC.units.items():
        assert unit.kind != "ask" and unit.ask is None, name
        assert not unit.gate.approval, name


@pytest.mark.parametrize("brief", ["discovery_short", "discovery", "plan", "expand", "code"])
def test_each_judge_brief_after_triage_grades_no_open_question(brief: str) -> None:  # CONV-AC7, AC 2
    _said(_read("judges", f"{brief}.md"), "An open question that the hand-off lists", "changes no grade")


# -- phase 4: the description lists the assumptions, and the documents follow --------------------------------


class _Last:
    """A last-stage context with a workspace and no git history, for the pull request's description."""

    def __init__(self, work: Path, note: str, handoff: str = "# Hand-off\n\n## Open questions\n\n- None\n") -> None:
        (work / "note.md").write_text(note, encoding="utf-8")
        (work / "handoff.md").write_text(handoff, encoding="utf-8")
        (work / "report.md").write_text("# Code report\n\n## Verification\n\n- `pytest`: passed\n", encoding="utf-8")
        self.workdir, self.out_dir, self.task_id, self.base = work, work / ".out", "TASK-7", "main"
        self.git = GitFacts(branch="tg/task-7")
        self.artifacts = {"triage": {"triage_note": "note.md"}, "discovery": {"handoff": "handoff.md"},
                          "code": {"code_report": "report.md"}}
        self.values = {"triage": {"route": "discovery"}}

    def run(self, cmd: str) -> CommandRun:
        return CommandRun(argv=tuple(cmd.split()), not_started=True)


def _described(work: Path, owner: str | None, handoff: str = "# Hand-off\n\n## Open questions\n\n- None\n") -> str:
    note = ("# Triage: T\n\n## Acceptance criteria\n\n1. One\n\n## Gaps\n\n- G1 spec gap: a. Owner decision\n"
            + ("" if owner is None else f"\n## Owner decisions\n\n{owner}") + TAIL)
    return str(summary.build(_Last(work, note, handoff)))


def test_a_note_with_two_owner_decisions_lists_both_as_assumptions(tmp_path: Path) -> None:  # CONV-AC8, AC 3
    owner = (_entry("G1", "Which exit code does the tool give?") +
             _entry("G2", "How long may a session idle?", "a) 30 minutes; b) 15 minutes", "b", "users are signed out early"))
    body = _described(tmp_path, owner)
    block = body.split("### Assumptions to confirm")[1].split("###")[0]
    assert "Which exit code does the tool give?" in block and "How long may a session idle?" in block
    assert "2" in block and "a script testing for 1 sees another code" in block
    assert "15 minutes" in block and "30 minutes" not in block and "users are signed out early" in block
    assert body.index("### Assumptions to confirm") < body.index("### Read these")
    assert body.index("### Acceptance criteria of the task") < body.index("### Assumptions to confirm")


def test_a_note_with_sixteen_owner_decisions_lists_all_sixteen(tmp_path: Path) -> None:  # CONV-AC8, AC 3
    body = _described(tmp_path, "".join(_entry(f"G{n}", f"Question number {n}?") for n in range(1, 17)))
    block = body.split("### Assumptions to confirm")[1].split("###")[0]
    assert all(f"Question number {n}?" in block for n in range(1, 17))


def test_a_note_whose_owner_decisions_say_none_says_the_run_took_no_default(tmp_path: Path) -> None:  # CONV-AC8, AC 3
    block = _described(tmp_path, "None\n").split("### Assumptions to confirm")[1].split("###")[0]
    assert "took no default" in block


def test_a_note_with_no_owner_decisions_section_has_no_assumptions_heading(tmp_path: Path) -> None:  # CONV-AC8, AC 3
    assert "Assumptions to confirm" not in _described(tmp_path, None)


def test_an_open_question_with_a_default_is_listed_with_it(tmp_path: Path) -> None:  # CONV-AC8, AC 3
    handoff = ("# Hand-off\n\n## Open questions\n\n- Which exit code for a missing file? Options: (a) 2; (b) 1. "
               "Until answered: (a)\n")
    body = _described(tmp_path, None, handoff)
    assert "### Open questions" in body and "Until answered: (a)" in body.split("### Open questions")[1]


def test_the_readme_and_the_research_note_say_what_is_built() -> None:  # CONV-AC2, CONV-AC8, AC 4
    readme = _read("README.md")
    _said(readme, "--set settings.conversation=never", "owner decisions", "Assumptions to confirm", "`blocking`",
          "`always`")
    status = next(ln for ln in _read("docs", "research", "next-features.rsrch.md").splitlines()
                  if ln.startswith("| Status |"))
    _said(status, "conversation mode `never`")


ROW = "- [ ] ts-tri-owner "


def test_the_criteria_file_holds_ts_tri_owner_with_the_text_of_its_spec_row() -> None:  # CONV-AC3, AC 1
    outcome = json.loads(_read("outcome.json"))
    assert outcome["revision"] == outcome["revisions"][-1]["revision"] >= 15
    assert any("issue 60" in r.get("note", "") for r in outcome["revisions"])
    crit = next(c for c in outcome["intermediate"]["triage"]["criteria"] if c["id"] == "ts-tri-owner")
    assert crit["severity"] == "blocker" and crit["verified_by"] == "check" and crit["check_method"].strip()
    assert crit["verifier"] == {"check": "tgwf_temperspec.checks:triage_check"}
    row = next(ln for ln in _read("docs", "specs", "04-triage.spec.md").splitlines() if ln.startswith(ROW))
    assert crit["text"] == row[len(ROW):].strip()
