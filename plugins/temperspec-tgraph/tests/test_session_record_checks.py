"""Task i72: the checks of the temperspec steps read the session record the engine gives them (SRC-B1 to SRC-B9).

A context here carries `ctx.session`, the calls the attempt's session made, as `{name, capability, target, ok}` dicts;
every other test of the package builds its context without one and still passes (SRC-B8).
"""

from __future__ import annotations

import importlib
import json
import re
import time
from pathlib import Path
from typing import Any

import pytest

from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts, run_check

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
checks = importlib.import_module("tgwf_temperspec.checks")
OWNER = {key: unit for unit in SPEC.order for key in (SPEC.units[unit].step.produces if SPEC.units[unit].step else {})}
RULES = ".claude/rules/temperspec"
FIXTURES = {
    "setup": "setup/must-pass/1-single", "triage": "triage/must-pass/1-gap",
    "discovery_short": "discovery_short/must-pass/1-settled", "discovery": "discovery/must-pass/2-new-spec",
    "plan": "plan/must-pass/1-complex", "expand": "expand/must-pass/1-expanded", "code": "code/must-pass/1-done"}
CRITERION = {"setup": "ts-set-ruleread", "triage": "ts-tri-ruleread", "discovery_short": "ts-dsh-ruleread",
             "discovery": "ts-dis-ruleread", "plan": "ts-plan-ruleread", "expand": "ts-exp-ruleread",
             "code": "ts-code-ruleread"}
UNITS = list(FIXTURES)
PROMPTS = ROOT / "prompts"


def _copy(src: Path, dst: Path) -> list[Path]:
    out = []
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        target = dst / f.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f.read_bytes())
        out.append(target)
    return out


def call(capability: str, target: str | None, ok: bool = True, name: str | None = None) -> dict[str, Any]:
    names = {"read": "Read", "search": "Grep", "edit": "Edit", "write": "Write", "shell": "Bash"}
    return {"name": name or names[capability], "capability": capability, "target": target, "ok": ok}


def reads(*names: str) -> list[dict[str, Any]]:
    return [call("read", f"{RULES}/{n}") for n in names]


def ctx_for(unit: str, work: Path, session: list[dict[str, Any]] | None, *, rules: bool | list[str] = True,
            preview: bool = False, fixture: Path | None = None,
            visit_session: Any = "same") -> CheckContext:
    """A context on the passing fixture of the unit's gate, with the rule files its prompt names in the workspace.
    `visit_session` defaults to the same calls as `session` (the calls of the whole visit, VSR-B1)."""
    if isinstance(visit_session, str):
        visit_session = session
    files = _copy(fixture or ROOT / "evals" / "checks" / FIXTURES[unit], work)
    artifacts: dict[str, dict[str, str]] = {}
    for f in files:
        if f.stem in OWNER:
            artifacts.setdefault(OWNER[f.stem], {})[f.stem] = f.relative_to(work).as_posix()
    held = checks._rule_names(unit) if rules is True else (rules or [])
    for name in held:
        (work / RULES).mkdir(parents=True, exist_ok=True)
        (work / RULES / name).write_text("# rule\n")
    ctx = CheckContext(unit=unit, workdir=work, request={}, artifacts=artifacts,
                       values={"triage": {"route": "plan"}} if unit == "code" else {}, git=GitFacts(),
                       allow=SPEC.allow_commands, out_dir=work.parent / f"{work.name}.out",
                       deadline_at=time.monotonic() + 60, preview=preview,
                       session=None if session is None else tuple(session),
                       visit_session=None if visit_session is None else tuple(visit_session))
    return ctx


def run(unit: str, ctx: CheckContext) -> tuple[Any, list[Any]]:
    res, _ = run_check(SPEC.units[unit].gate, ctx)
    return res, [f for f in res.findings if f.criterion == CRITERION[unit]]


def fails(found: list[Any]) -> list[str]:
    return [f.place.rsplit("/", 1)[-1] for f in found if f.status == "fail"]


# -- the rule file a prompt names is opened (SRC-B1, SRC-AC1 to SRC-AC3) ------------------------------------------


@pytest.mark.parametrize("unit", UNITS)
def test_a_record_that_opens_every_held_rule_file_gives_no_failure(unit: str, tmp_path: Path) -> None:
    # AC 1, SRC-AC1 (SRC-B1)
    names = checks._rule_names(unit)
    assert names
    _, found = run(unit, ctx_for(unit, tmp_path, reads(*names)))
    assert [f.status for f in found] == ["pass"]


@pytest.mark.parametrize("unit", UNITS)
def test_a_rule_file_the_record_never_opens_fails_the_check_naming_it(unit: str, tmp_path: Path) -> None:
    # AC 1, SRC-AC1 (SRC-B1)
    names = checks._rule_names(unit)
    for i, missing in enumerate(names):
        res, found = run(unit, ctx_for(unit, tmp_path / str(i), reads(*[n for n in names if n != missing])))
        assert fails(found) == [missing] and res.result == "FAIL"
        assert missing in found[0].message and found[0].fix


def test_the_triage_case_a_searched_rule_file_is_not_opened(tmp_path: Path) -> None:  # AC 1, SRC-AC1 (SRC-B1)
    session = [*reads("task-notes.rule.md"), call("search", f"{RULES}/documents.rule.md")]
    _, found = run("triage", ctx_for("triage", tmp_path, session))
    assert fails(found) == ["documents.rule.md"]


def test_a_search_a_failed_read_a_path_form_and_a_missing_rule_file(tmp_path: Path) -> None:
    # AC 1, SRC-AC2 (SRC-B1)
    session = [call("search", f"{RULES}/plan.rule.md"), call("read", f"{RULES}/plan.rule.md", ok=False),
               *reads("documents.rule.md")]
    _, found = run("plan", ctx_for("plan", tmp_path / "a", session))
    assert fails(found) == ["plan.rule.md"]
    session = [call("read", "plugins/x/rules/spec.rule.md"), *reads("extraction.rule.md", "decision.rule.md", "research.rule.md",
                                                                     "task-notes.rule.md", "documents.rule.md")]
    _, found = run("discovery", ctx_for("discovery", tmp_path / "b", session))
    assert [f.status for f in found] == ["pass"]  # the last segment of the target is the file's name
    # the prompt names two files and the repository holds one: only the held one is asked for
    _, found = run("triage", ctx_for("triage", tmp_path / "c", [call("read", "src/x.py")],
                                     rules=["documents.rule.md"]))
    assert fails(found) == ["documents.rule.md"]


def test_the_check_reads_only_the_session_it_is_given(tmp_path: Path) -> None:  # AC 1, SRC-AC3 (SRC-B1)
    first_attempt = reads(*checks._rule_names("plan"))  # opened them all; never handed to the check
    retry = [call("read", "src/x.py"), call("edit", "plan.md")]
    assert first_attempt
    _, found = run("plan", ctx_for("plan", tmp_path, retry))
    assert fails(found) == checks._rule_names("plan")


@pytest.mark.parametrize("unit", UNITS)
def test_without_rule_files_in_the_repository_the_criterion_is_not_applicable(unit: str, tmp_path: Path) -> None:
    # AC 1, SRC-AC5 (SRC-B3)
    res, found = run(unit, ctx_for(unit, tmp_path, [call("read", "src/x.py")], rules=False))
    assert [f.status for f in found] == ["n_a"] and "rule files are not in the repository" in found[0].message
    assert res.result != "FAIL" or not fails(found)


@pytest.mark.parametrize("unit", UNITS)
def test_the_prompts_tell_the_session_to_open_each_rule_file_with_the_read_tool(unit: str) -> None:
    # AC 1, AC 2, SRC-AC4, SRC-AC13 (SRC-B2, SRC-B10)
    text = " ".join((PROMPTS / f"{unit}.md").read_text(encoding="utf-8").split()).lower()
    assert "open each rule file named here that this repository holds with the read tool" in text
    assert "whole machine" not in text and "already in your instructions" not in text  # the rule files are in the repository
    assert "outside this working directory" not in text
    assert "a search of a rule file is not opening it" in text
    if unit == "discovery_short":
        assert "the rule files do not count in that limit of 10 files" in text
        assert "read at most 10 files" in text  # the phrase ts-dsh-limit reads


# -- no record, no verdict (SRC-B8, SRC-AC11) -----------------------------------------------------------------------


@pytest.mark.parametrize("unit", UNITS)
def test_with_no_session_record_the_rule_file_criterion_is_not_applicable(unit: str, tmp_path: Path) -> None:
    # AC 5, SRC-AC11 (SRC-B8)
    cases = {"stand-in": (None, False), "preview": (None, True),
             "tool inputs off": ([call("read", None), call("edit", None)], False)}
    for i, (session, preview) in enumerate(cases.values()):
        _, found = run(unit, ctx_for(unit, tmp_path / str(i), session, preview=preview))
        assert [f.status for f in found] == ["n_a"] and "no session record to read" in found[0].message


# -- a finding quotes no call of the session (SRC-B9, SRC-AC12) -----------------------------------------------------


@pytest.mark.parametrize("unit", ["plan", "code"])
def test_a_finding_and_the_evidence_quote_no_call_of_the_session(unit: str, tmp_path: Path) -> None:
    # AC 1, SRC-AC12 (SRC-B9)
    session = [call("shell", "echo zanzibar"), call("read", "zanzibar/notes.md"), call("search", "zanzibar")]
    res, found = run(unit, ctx_for(unit, tmp_path, session))
    assert fails(found) == checks._rule_names(unit)
    blob = json.dumps([[f.criterion, f.place, f.message, f.fix] for f in res.findings]) + res.evidence
    assert "zanzibar" not in blob


# -- the expand step opens each file a row names (SRC-B4, SRC-B5; SRC-AC6, SRC-AC7) --------------------------------


def test_the_expand_prompt_tells_the_session_to_open_each_file_a_row_names() -> None:  # AC 2, SRC-AC6 (SRC-B4)
    text = " ".join((PROMPTS / "expand.md").read_text(encoding="utf-8").split()).lower()
    assert "open each file a task row names with the read tool before you write that row" in text


def _expand(work: Path, session: list[dict[str, Any]] | None, files: tuple[str, ...] = (),
            visit_session: Any = "same", plan_edit: Any = None) -> tuple[Any, list[Any]]:
    ctx = ctx_for("expand", work, session, visit_session=visit_session)
    for rel in files:
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text("x\n")
    if plan_edit is not None:
        plan_edit(work / "phases.md")
    res, _ = run_check(SPEC.units["expand"].gate, ctx)
    return res, [f for f in res.findings if f.criterion == "ts-exp-opened"]


ROW_PATH = re.compile(r"(\d+\.\d+)\D+?`([^`]+)`")


def _unread(found: list[Any]) -> list[tuple[str, str]]:
    """The rows and paths of the one failing finding of `ts-exp-opened`."""
    fails_ = [f for f in found if f.status == "fail"]
    assert len(fails_) <= 1, "one finding for all unopened rows"
    return sorted(ROW_PATH.findall(fails_[0].message)) if fails_ else []


def test_a_row_that_names_an_existing_file_the_session_never_opened_fails_naming_row_and_path(tmp_path: Path) -> None:
    # AC 3, AC 9, SRC-AC7 (SRC-B5)
    rules = reads("plan.rule.md")
    searched = [*rules, call("search", "src/tool/config.py")]
    res, found = _expand(tmp_path / "a", searched, ("src/tool/config.py", "README.md"))
    assert res.result == "FAIL"
    # rows 1.2, 2.2 and 3.2 name the one unread file: each is named; the docs row names an unread README.md; the
    # test file does not exist, so no row names a failure for it
    assert _unread(found) == [("1.2", "src/tool/config.py"), ("2.2", "src/tool/config.py"),
                              ("3.2", "src/tool/config.py"), ("4.1", "README.md")]
    assert found[0].fix
    opened = [*rules, call("read", "src/tool/config.py"), call("read", "./README.md")]
    _, found = _expand(tmp_path / "b", opened, ("src/tool/config.py", "README.md"))
    assert [f.status for f in found] == ["pass"]
    errored = [*rules, call("read", "src/tool/config.py"), call("read", "README.md", ok=False)]
    _, found = _expand(tmp_path / "c", errored, ("src/tool/config.py", "tests/test_config.py", "README.md"))
    assert _unread(found) == [("1.1", "tests/test_config.py"), ("2.1", "tests/test_config.py"),
                              ("3.1", "tests/test_config.py"), ("4.1", "README.md")]  # an error is no opening


def test_with_no_record_the_opened_criterion_is_not_applicable_and_quotes_no_call(tmp_path: Path) -> None:
    # AC 7, SRC-AC11, SRC-AC12
    for i, session in enumerate([None, [call("read", None)]]):
        _, found = _expand(tmp_path / str(i), session, ("src/tool/config.py",))
        assert [f.status for f in found] == ["n_a"] and "no session record to read" in found[0].message
    # the record of the visit is the one read: none, or a call with no target, makes the criterion not applicable
    held = [*reads("plan.rule.md"), call("read", "src/tool/config.py")]
    for i, visit in enumerate([None, [*held, call("edit", None)]]):
        _, found = _expand(tmp_path / f"v{i}", held, ("src/tool/config.py",), visit_session=visit)
        assert [f.status for f in found] == ["n_a"] and "no session record to read" in found[0].message
    # the last session alone with no record or no target does not decide when the visit's record is whole
    for i, last in enumerate([None, [call("read", None)]]):
        _, found = _expand(tmp_path / f"l{i}", last, ("src/tool/config.py",), visit_session=held)
        assert [f.status for f in found] == ["pass"]
    session = [*reads("plan.rule.md"), call("shell", "echo zanzibar"), call("search", "zanzibar")]
    res, found = _expand(tmp_path / "z", session, ("src/tool/config.py",))
    assert any(f.status == "fail" for f in found)
    blob = json.dumps([[f.criterion, f.place, f.message, f.fix] for f in res.findings]) + res.evidence
    assert "zanzibar" not in blob


def test_a_retry_that_opens_only_the_file_the_first_session_missed_passes(tmp_path: Path) -> None:
    # AC 10, SRC-AC14 (SRC-B5)
    files = ("src/tool/config.py", "README.md")
    first = [*reads("plan.rule.md"), call("read", "src/tool/config.py")]
    retry = [call("read", "README.md")]
    _, found = _expand(tmp_path / "a", retry, files, visit_session=[*first, *retry])
    assert [f.status for f in found] == ["pass"]
    _, found = _expand(tmp_path / "b", retry, files, visit_session=first)
    assert _unread(found) == [("4.1", "README.md")]


def test_one_finding_names_every_unopened_row_and_the_evidence_lists_them_in_full(tmp_path: Path) -> None:
    # AC 9, SRC-AC15 (SRC-B11)
    files = ("src/tool/config.py", "README.md", "tests/test_config.py")
    res, found = _expand(tmp_path / "a", reads("plan.rule.md"), files)
    assert [f.status for f in found] == ["fail"]
    assert _unread(found) == [("1.1", "tests/test_config.py"), ("1.2", "src/tool/config.py"),
                              ("2.1", "tests/test_config.py"), ("2.2", "src/tool/config.py"),
                              ("3.1", "tests/test_config.py"), ("3.2", "src/tool/config.py"),
                              ("4.1", "README.md")][:len(_unread(found))]
    for row, path in [("1.1", "tests/test_config.py"), ("1.2", "src/tool/config.py"), ("4.1", "README.md")]:
        assert f"{row}: {path}" in res.evidence
    # a plan with many unopened rows: the message is clipped, the evidence is not
    def many(plan: Path) -> None:
        text = plan.read_text()
        extra = "".join(f"| 9.{i} | docs | R1 | `docs/long/dir/name{i:03d}.md` | | change | |\n" for i in range(40))
        anchor = "| 4.1 | docs | R1 | `README.md` | | Describe the missing-file message | |\n"
        assert anchor in text
        plan.write_text(text.replace(anchor, anchor + extra, 1))
    big = [f"docs/long/dir/name{i:03d}.md" for i in range(40)]
    res, found = _expand(tmp_path / "b", reads("plan.rule.md"), tuple(big), plan_edit=many)
    assert [f.status for f in found] == ["fail"]
    for i, path in enumerate(big):
        assert f"9.{i}: {path}" in res.evidence


def test_a_row_whose_mark_is_kept_asks_for_no_opening(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AC 8, SRC-AC16 (SRC-B12)
    def kept(ctx: Any, plan: Any, path: str) -> dict[str, str]:
        return {"1.2": "", "2.2": "the row differs from the row in its marking commit", "3.2": "no commit"}

    monkeypatch.setattr(checks, "_kept_marks", kept)
    _, found = _expand(tmp_path / "a", reads("plan.rule.md"), ("src/tool/config.py",))
    named = _unread(found)
    assert ("1.2", "src/tool/config.py") not in named  # kept: no new opening
    assert ("2.2", "src/tool/config.py") in named  # rewritten and its mark emptied or unbacked
    assert ("3.2", "src/tool/config.py") in named  # a mark the history does not back


# -- the code step writes a phase's tests before its source (SRC-B6, SRC-B7; SRC-AC8 to SRC-AC10) ----------------------


def _code(work: Path, session: list[dict[str, Any]] | None, edit: dict[str, str] | None = None,
          preview: bool = False) -> tuple[Any, list[Any]]:
    ctx = ctx_for("code", work, session, preview=preview)
    plan = work / "phases.md"
    text = plan.read_text()
    for old, new in (edit or {}).items():
        assert old in text, old
        text = text.replace(old, new)
    plan.write_text(text)
    res, _ = run_check(SPEC.units["code"].gate, ctx)
    return res, [f for f in res.findings if f.criterion == "ts-code-order"]


RULES_READ = reads(*checks._rule_names("code"))
OWN_FILES = {"| 2.1 | test | R1 | `tests/test_config.py`": "| 2.1 | test | R1 | `tests/test_b.py`",
             "| 2.2 | code | R1 | `src/tool/config.py`": "| 2.2 | code | R1 | `src/b.py`"}
TEST_1, CODE_1 = "tests/test_config.py", "src/tool/config.py"


def test_a_phase_whose_source_is_changed_before_its_test_is_written_fails_naming_the_phase(tmp_path: Path) -> None:
    # AC 4, SRC-AC8 (SRC-B6)
    good = [*RULES_READ, call("write", TEST_1), call("edit", CODE_1), call("write", "tests/test_b.py"),
            call("edit", "src/b.py")]
    _, found = _code(tmp_path / "a", good, OWN_FILES)
    assert [f.status for f in found] == ["pass"]
    bad = [*RULES_READ, call("write", TEST_1), call("edit", CODE_1), call("edit", "src/b.py"),
           call("write", "tests/test_b.py")]
    res, found = _code(tmp_path / "b", bad, OWN_FILES)
    assert [(f.status, f.place) for f in found] == [("fail", "phase 2")] and res.result == "FAIL"
    assert "src/b.py" not in found[0].message and "src/b.py" not in found[0].fix  # names the phase only


def test_what_counts_for_a_phase_and_what_does_not(tmp_path: Path) -> None:  # AC 4, SRC-AC9 (SRC-B6)
    # a file counts for the first phase that names it: phase 3 shares phase 1's files, so its writes after phase 1's
    # source are no failure, and a phase whose test file is never written is not measured
    shared = [*RULES_READ, call("write", TEST_1), call("edit", CODE_1), call("write", TEST_1), call("edit", CODE_1)]
    _, found = _code(tmp_path / "a", shared)
    assert [f.status for f in found] == ["pass"]
    _, found = _code(tmp_path / "b", [*RULES_READ, call("edit", "src/b.py")], OWN_FILES)
    assert [f.status for f in found] == ["pass"]
    # a `docs` row's or a `chore` row's file counts for no phase
    for kind, work in (("docs", "c"), ("chore", "d")):
        session = [*RULES_READ, call("edit", "README.md"), call("write", TEST_1), call("edit", CODE_1)]
        _, found = _code(tmp_path / work, session, {"| 4.1 | docs |": f"| 4.1 | {kind} |"})
        assert [f.status for f in found] == ["pass"], kind
    # a call that ended with an error is not a change
    session = [*RULES_READ, call("edit", CODE_1, ok=False), call("write", TEST_1), call("edit", CODE_1)]
    _, found = _code(tmp_path / "e", session)
    assert [f.status for f in found] == ["pass"]
    # and the same record with the first edit succeeding is the failure
    session = [*RULES_READ, call("edit", CODE_1), call("write", TEST_1), call("edit", CODE_1)]
    _, found = _code(tmp_path / "f", session)
    assert [(f.status, f.place) for f in found] == [("fail", "phase 1")]


def test_the_quick_lane_has_no_phases(tmp_path: Path) -> None:  # AC 4, SRC-AC10 (SRC-B7)
    _copy(ROOT / "evals" / "checks" / "code" / "must-pass" / "3-quick", tmp_path)
    artifacts = {"triage": {"triage_note": "triage_note.md"}, "code": {"code_report": "code_report.md"}}
    session = [call("edit", "src/tool/config.py"), call("write", "tests/test_config.py")]
    ctx = CheckContext(unit="code", workdir=tmp_path, request={}, artifacts=artifacts,
                       values={"triage": {"route": "quick", "gaps": "none"}}, allow=SPEC.allow_commands,
                       git=GitFacts(changed_paths=("src/tool/config.py", "tests/test_config.py")),
                       out_dir=tmp_path.parent / f"{tmp_path.name}.out", deadline_at=time.monotonic() + 60,
                       session=tuple(session))
    res, _ = run_check(SPEC.units["code"].gate, ctx)
    found = [f for f in res.findings if f.criterion == "ts-code-order"]
    assert [f.status for f in found] == ["n_a"] and "quick lane has no phases" in found[0].message


def test_the_code_gate_with_no_record_is_not_applicable_and_quotes_no_call(tmp_path: Path) -> None:
    # AC 5, SRC-AC11, SRC-AC12
    cases = {"none": (None, False), "preview": (None, True), "null target": ([call("write", None)], False)}
    for i, (session, preview) in enumerate(cases.values()):
        res, order = _code(tmp_path / str(i), session, preview=preview)
        ruleread = [f for f in res.findings if f.criterion == "ts-code-ruleread"]
        for found in (order, ruleread):
            assert [f.status for f in found] == ["n_a"] and "no session record to read" in found[0].message
    session = [call("shell", "echo zanzibar"), call("edit", CODE_1), call("write", TEST_1)]
    res, order = _code(tmp_path / "z", session)
    assert [f.status for f in order] == ["fail"]
    blob = json.dumps([[f.criterion, f.place, f.message, f.fix] for f in res.findings]) + res.evidence
    assert "zanzibar" not in blob
