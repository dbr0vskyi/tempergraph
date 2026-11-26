"""Phase coding (spec `phase-coding.spec.md`, PHC-B1 to PHC-B15, and the unit spec `phase.spec.md`): the phase items
of an expanded plan, the phase check, the prompts of the phase step and its judge, and stand-in runs of the map `phase`
between the expand step and the code step."""

from __future__ import annotations

import dataclasses
import importlib
import json
import re
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tempergraph.api import CheckResult
from tempergraph.constants import ExitCode
from tempergraph.contracts import CallableRef, SessionRequest, SessionResult
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import answer, standin
from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts
from tempergraph.run.runner import RunSettings, start
from tempergraph.store.layout import run_dir, state_root_path

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
routing = importlib.import_module("tgwf_temperspec.routing")
checks = importlib.import_module("tgwf_temperspec.checks")
fmt = importlib.import_module("tgwf_temperspec.specfmt")
TODAY = "✓ 2026-11-24"
BASE = "b" * 40

Row = tuple[str, str, str, str, str]  # id, kind, file, proves, the Completed cell


def _plan(phases: list[tuple[str, list[Row]]], status: str = "planned") -> str:
    """An expanded plan of the plan rule's shape: each phase is (heading text after `### `, its rows)."""
    out = [f"---\ntask: T-1\ncomplexity: complex\nstatus: {status}\nspecs: []\n---\n", "# Plan: a goal\n",
           "## 0. Hand-off\n\n- Triage note: `triage_note.md`\n- Why this design: one place.\n",
           "## 1. Requirements\n\n| Req | Criteria | Statement | Spec ids |\n|---|---|---|---|\n"
           "| R1 | AC 1 | One line names the file | |\n", "## 2. Phases\n"]
    for heading, rows in phases:
        name = heading.split(":", 1)[-1].strip()
        out.append(f"### {heading}\n\nGoal: {name} goal is reached.\nWeight: light\n")
        out.append("| Row | Kind | Req | File | Proves | Change | Completed |\n|---|---|---|---|---|---|---|")
        for rid, kind, file, proves, mark in rows:
            out.append(f"| {rid} | {kind} | R1 | `{file}` | {proves} | A change of {file} | {mark} |")
        out.append("")
    out.append("## 3. Verification\n\n- `git --version`\n\n| Criterion | Test | Command |\n|---|---|---|\n"
               "| AC 1 | `tests/test_a.py` | `git --version` |\n")
    out.append("## 4. Docs to update\n\n- None\n")
    return "\n".join(out)


THREE = _plan([
    ("Phase 1: Alpha", [("1.1", "test", "tests/test_a.py", "AC 1", ""), ("1.2", "code", "src/a.py", "", "")]),
    ("Phase 2: Beta", [("2.1", "test", "tests/test_b.py", "AC 1", ""), ("2.2", "code", "src/b.py", "", "")]),
    ("Phase 3: Gamma", [("3.1", "test", "tests/test_c.py", "AC 1", ""), ("3.2", "code", "src/c.py", "", "")]),
])


def _items(tmp_path: Path, text: str) -> list[dict[str, str]]:
    folder = tmp_path / "docs" / "plans"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "T-1.plan.md").write_text(text, encoding="utf-8")
    return list(routing.phase_items(SimpleNamespace(artifact=folder / "T-1.plan.md", workdir=tmp_path, values={})))


# -- the phase items (PHC-B1, PHC-B2) ----------------------------------------------------------------------------------


def test_each_phase_of_an_expanded_plan_is_one_item_named_after_its_number_in_plan_order(tmp_path: Path) -> None:
    # AC 1, PHC-AC1 (PHC-B1)
    got = _items(tmp_path, THREE)
    assert [i["id"] for i in got] == ["p1", "p2", "p3"]
    one = _plan([("Phase 1: Only", [("1.1", "test", "tests/test_a.py", "AC 1", "")])])
    assert [i["id"] for i in _items(tmp_path, one)] == ["p1"]


def test_a_heading_with_no_number_or_a_repeated_number_takes_a_position_based_id(tmp_path: Path) -> None:
    # AC 1, PHC-AC1 (PHC-B1): no id repeats, so the list is never shorter than the phases
    row = [("1.1", "test", "tests/test_a.py", "AC 1", "")]
    repeated = _items(tmp_path, _plan([("Phase 1: A", row), ("Phase 2: B", row), ("Phase 2: C", row)]))
    assert [i["id"] for i in repeated] == ["p1", "p2", "p3"]
    unnumbered = _items(tmp_path, _plan([("Phase 1: A", row), ("Phase 3: B", row), ("Setup", row)]))
    ids = [i["id"] for i in unnumbered]
    assert len(ids) == 3 and len(set(ids)) == 3 and ids[:2] == ["p1", "p3"]
    clash = _items(tmp_path, _plan([("Phase 2: A", row), ("Phase 2: B", row), ("Phase 2: C", row)]))
    assert len({i["id"] for i in clash}) == 3 and clash[0]["id"] == "p2"


def test_the_text_of_an_item_holds_its_heading_goal_weight_and_the_plans_path_and_no_other_phase(tmp_path: Path) -> None:
    # AC 1, PHC-AC1 (PHC-B1), PHC-AC2 (PHC-B2)
    got = {i["id"]: i["text"] for i in _items(tmp_path, THREE)}
    text = got["p2"]
    assert "Phase 2: Beta" in text and "Beta goal is reached." in text and "light" in text
    assert "docs/plans/T-1.plan.md" in text
    assert "Phase 1: Alpha" not in text and "Phase 3: Gamma" not in text
    assert "2.1" not in text, "the rows stay in the plan; the session reads them there"


# -- the phase check reads the rows of the phase only (PHC-B6 to PHC-B8) -----------------------------------------------


def _context(work: Path, item: str, changed: tuple[str, ...] = (), session: Any = None, clean: bool = True) -> CheckContext:
    return CheckContext(unit="phase", item=item, workdir=work, request={}, values={},
                        artifacts={"expand": {"phases": "plan.md"}, "triage": {"triage_note": "triage_note.md"}},
                        git=GitFacts(base=BASE, changed_paths=changed, clean=clean), allow=SPEC.allow_commands,
                        out_dir=work.parent / f"{work.name}.out", deadline_at=time.monotonic() + 60,
                        session=session)


TESTS = {"tests/test_a.py": "# AC 1\ndef test_a(): ...\n", "tests/test_b.py": "# AC 1\ndef test_b(): ...\n",
         "tests/test_c.py": "# AC 1\ndef test_c(): ...\n", "src/a.py": "a = 1\n", "src/b.py": "b = 1\n",
         "src/c.py": "c = 1\n"}


def _work(tmp_path: Path, plan: str, files: dict[str, str] | None = None) -> Path:
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    (work / "plan.md").write_text(plan, encoding="utf-8")
    (work / "triage_note.md").write_text("# Triage: T-1\n", encoding="utf-8")
    for name, body in (TESTS if files is None else files).items():
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        (work / name).write_text(body, encoding="utf-8")
    return work


def _fails(res: CheckResult, criterion: str | None = None) -> list[Any]:
    return [f for f in res.findings if f.status == "fail" and criterion in (None, f.criterion)]


def _named(res: CheckResult) -> str:
    return " ".join(f"{f.criterion} {f.place} {f.message}" for f in _fails(res))


def _two_marked(first: str, second: str) -> str:
    return _plan([
        ("Phase 1: Alpha", [("1.1", "test", "tests/test_a.py", "AC 1", TODAY), ("1.2", "code", "src/a.py", "", TODAY)]),
        ("Phase 2: Beta", [("2.1", "test", "tests/test_b.py", "AC 1", first), ("2.2", "code", "src/b.py", "", second)]),
        ("Phase 3: Gamma", [("3.1", "test", "tests/test_c.py", "AC 1", ""), ("3.2", "code", "src/c.py", "", "")]),
    ], status="in-progress")


def test_the_phase_check_fails_naming_the_row_the_session_left_unmarked(tmp_path: Path) -> None:
    # AC 1, PHC-AC6 (PHC-B6)
    work = _work(tmp_path, _two_marked(TODAY, ""))
    res = checks.phase_check(_context(work, "p2", ("tests/test_b.py", "src/b.py")))
    assert res.result == "FAIL"
    assert "2.2" in _named(res) and "2.1" not in _named(res)
    assert {f.criterion for f in _fails(res)} == {"ts-phs-rows"}


def test_the_phase_check_fails_naming_a_marked_row_whose_file_is_as_at_the_base(tmp_path: Path) -> None:
    # AC 1, PHC-AC6 (PHC-B6)
    work = _work(tmp_path, _two_marked(TODAY, TODAY))
    res = checks.phase_check(_context(work, "p2", ("tests/test_b.py",)))
    assert res.result == "FAIL" and "2.2" in _named(res) and "2.1" not in _named(res)
    assert {f.criterion for f in _fails(res)} == {"ts-phs-changed"}


def test_the_phase_check_makes_no_finding_about_the_rows_of_another_phase(tmp_path: Path) -> None:
    # AC 1, PHC-AC6 (PHC-B6): phase 3 is not marked yet, and phase 2 is whole
    work = _work(tmp_path, _two_marked(TODAY, TODAY))
    res = checks.phase_check(_context(work, "p2", ("tests/test_b.py", "src/b.py")))
    assert res.result == "PASS", _named(res)
    assert "3." not in _named(res)


def test_a_mark_of_an_earlier_visit_needs_no_new_change_when_its_file_differs_from_the_base(tmp_path: Path) -> None:
    # AC 1, PHC-AC6 (PHC-B6), KMK-B8: the changed paths count from the run's base commit, whichever visit changed them
    work = _work(tmp_path, _two_marked(TODAY, TODAY))
    res = checks.phase_check(_context(work, "p1", ("tests/test_a.py", "src/a.py", "tests/test_b.py", "src/b.py")))
    assert res.result == "PASS", _named(res)


# -- a criterion a test row proves is carried by a test that runs (PHC-B7) -----------------------------------------------


def test_the_phase_check_fails_a_test_row_whose_file_has_no_test_that_names_the_criterion(tmp_path: Path) -> None:
    # AC 1, PHC-AC7 (PHC-B7)
    files = {**TESTS, "tests/test_b.py": "def test_b(): ...\n"}
    work = _work(tmp_path, _two_marked(TODAY, TODAY), files)
    res = checks.phase_check(_context(work, "p2", ("tests/test_b.py", "src/b.py")))
    assert [f.criterion for f in _fails(res)] == ["ts-phs-proof"] and "AC 1" in _named(res)


def test_the_phase_check_fails_when_the_only_test_that_names_the_criterion_is_skipped(tmp_path: Path) -> None:
    # AC 1, PHC-AC7 (PHC-B7)
    files = {**TESTS, "tests/test_b.py": "import pytest\n\n@pytest.mark.skip\ndef test_b():  # AC 1\n    ...\n"}
    work = _work(tmp_path, _two_marked(TODAY, TODAY), files)
    res = checks.phase_check(_context(work, "p2", ("tests/test_b.py", "src/b.py")))
    assert [f.criterion for f in _fails(res)] == ["ts-phs-proof"] and "skipped" in _named(res)


def test_the_phase_check_makes_no_finding_for_a_test_that_names_the_criterion_and_runs(tmp_path: Path) -> None:
    # AC 1, PHC-AC7 (PHC-B7)
    work = _work(tmp_path, _two_marked(TODAY, TODAY))
    res = checks.phase_check(_context(work, "p2", ("tests/test_b.py", "src/b.py")))
    assert _fails(res, "ts-phs-proof") == [] and any(
        f.criterion == "ts-phs-proof" and f.status == "pass" for f in res.findings)


# -- a phase's source is not changed before its tests are written (PHC-B8) -----------------------------------------------


def _call(capability: str, target: str) -> dict[str, Any]:
    return {"name": capability.title(), "capability": capability, "target": target, "ok": True}


def test_the_phase_check_fails_naming_the_phase_when_its_source_was_changed_before_its_test_file(tmp_path: Path) -> None:
    # AC 1, PHC-AC8 (PHC-B8)
    work = _work(tmp_path, _two_marked(TODAY, TODAY))
    session = (_call("edit", "src/b.py"), _call("write", "tests/test_b.py"))
    res = checks.phase_check(_context(work, "p2", ("tests/test_b.py", "src/b.py"), session=session))
    assert [f.criterion for f in _fails(res)] == ["ts-phs-order"] and "phase 2" in _named(res)


def test_the_phase_check_makes_no_finding_about_the_order_when_the_tests_come_first(tmp_path: Path) -> None:
    # AC 1, PHC-AC8 (PHC-B8)
    work = _work(tmp_path, _two_marked(TODAY, TODAY))
    session = (_call("write", "tests/test_b.py"), _call("edit", "src/b.py"))
    res = checks.phase_check(_context(work, "p2", ("tests/test_b.py", "src/b.py"), session=session))
    assert res.result == "PASS", _named(res)
    assert any(f.criterion == "ts-phs-order" and f.status == "pass" for f in res.findings)


def test_the_order_is_not_applicable_when_the_engine_gives_the_check_no_session_record(tmp_path: Path) -> None:
    # AC 1, PHC-AC8 (PHC-B8), SRC-B8
    work = _work(tmp_path, _two_marked(TODAY, TODAY))
    res = checks.phase_check(_context(work, "p2", ("tests/test_b.py", "src/b.py"), session=None))
    (order,) = [f for f in res.findings if f.criterion == "ts-phs-order"]
    assert order.status == "n_a" and "no session record to read" in order.message


# -- the brief of a phase session and the phase judge (PHC-B2 to PHC-B4, PHC-B9) -------------------------------------------


def _said(text: str) -> str:
    return " ".join(text.split()).lower()


def _prompt(name: str = "phase") -> str:
    return (ROOT / "prompts" / f"{name}.md").read_text(encoding="utf-8")


def test_the_phase_prompt_names_its_keys_and_renders_one_phase_with_the_two_paths(tmp_path: Path) -> None:
    # AC 1, PHC-AC2 (PHC-B2)
    text = _prompt()
    for key in ("{task_id}", "{triage_note}", "{plan}", "{item_id}", "{item}"):
        assert key in text, key
    item = {i["id"]: i for i in _items(tmp_path, THREE)}["p2"]
    brief = text.format(task_id="T-1", triage_note="docs/tasks/T-1.triage.md", plan="docs/plans/T-1.plan.md",
                        item_id=item["id"], item=item["text"])
    assert "Phase 2: Beta" in brief and "Beta goal is reached." in brief and "Weight: light" in brief
    assert "docs/plans/T-1.plan.md" in brief and "docs/tasks/T-1.triage.md" in brief
    assert "Phase 1: Alpha" not in brief and "Phase 3: Gamma" not in brief


def test_the_phase_prompt_tells_the_session_what_to_build_how_to_mark_and_what_never_to_run() -> None:
    # AC 1, AC 3, PHC-AC3 (PHC-B3)
    text = _prompt()
    said = _said(text)
    for phrase in ("write the completed marks of the rows you built in one phase in one edit of the plan",
                   "after the change of each row is in its file and the test files that the phase's rows name pass",
                   "not in one edit for each row",
                   "build only the rows of the phase whose completed cell is empty",
                   "leave the mark of every other row as it is",
                   "write the phase's tests first and see them fail",
                   "run only the test files its rows name",
                   "never run the plan's verification commands",
                   "change no file that no row of the phase names, but the plan's marks and status",
                   "`✓ <today's date as yyyy-mm-dd>`",
                   "run no `git commit`"):
        assert phrase in said, phrase
    assert ".rule.md" not in text, "the phase step reads no rule file (the rule files are the prepare step's)"


def test_the_phase_prompt_asks_for_a_one_line_note_and_names_the_row_when_the_plan_is_at_fault() -> None:
    # AC 1, PHC-AC4 (PHC-B4)
    text = _prompt()
    said = _said(text)
    assert "`phase_note`" in text and "ARTIFACT phase_note:" in text
    for phrase in ("one line of at most 1,500 characters", "name each test file you ran",
                   "each deviation from the plan with its reason", "or say `none`",
                   "name the row and the conflict"):
        assert phrase in said, phrase


def test_the_phase_judge_states_a_stance_and_grades_each_rows_change_in_its_file_and_the_files_outside_the_rows() -> None:
    # AC 1, PHC-AC4 (PHC-B9)
    text = (ROOT / "judges" / "phase.md").read_text(encoding="utf-8")
    assert text.startswith("# Stance") and "\n# Brief\n" in text
    said = _said(text)
    for phrase in ("each row of the phase", "the line of its file that holds the row's change",
                   "no row of the phase names", "the plan's marks and status",
                   "cite the row id for every met"):
        assert phrase in said, phrase
    # AC 3, AC 4, PHC-AC18 (PHC-B18): the check sorted the paths, the judge takes it as given, scope is on the first list
    for phrase in ("changed since the phase step was entered", "changed only by earlier steps",
                   "sorted the changed paths into", "takes that sorting as given",
                   "does not look for the step that changed a path", "graded on the first list alone",
                   "lowers no grade and sets no gap"):
        assert phrase in said.lower(), phrase


def _git(work: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=work,
                          capture_output=True, text=True, check=True).stdout.strip()


def _commit(work: Path, subject: str, files: dict[str, str]) -> None:
    for name, body in files.items():
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        (work / name).write_text(body, encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", subject)


def _history_repo(tmp_path: Path, phase_commit: bool = True) -> tuple[Path, str]:
    """A repository with a base commit, a triage and a discovery commit and (when asked) a phase commit that
    edits a file discovery also wrote."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    work = _work(tmp_path, _plan([("Phase 1: Alpha", [("1.1", "test", "tests/test_a.py", "AC 1", TODAY),
                                                      ("1.2", "code", "src/a.py", "", TODAY)])], status="in-progress"),
                 files={})
    _git(work, "init", "-q")
    _commit(work, "chore: base", {"README.md": "r\n"})
    base = _git(work, "rev-parse", "HEAD")
    _commit(work, "docs(temperspec): triage for T", {"triage_note.md": "# Triage: T\n", "shared.md": "1\n"})
    _commit(work, "docs(temperspec): discovery for T", {"handoff.md": "h\n", "shared.md": "2\n"})
    _commit(work, "chore: a person's edit", {"notes.md": "n\n"})
    if phase_commit:
        _commit(work, "feat(temperspec): phase for T", {"src/a.py": "a = 1\n", "tests/test_a.py": "# AC 1\n",
                                                        "shared.md": "3\n"})
    return work, base


def _phase_context(work: Path, base: str, *, facts_base: str | None = None) -> CheckContext:
    from tempergraph.run.checks import git_facts

    facts = git_facts(work, base)
    assert facts is not None
    if facts_base is not None:
        facts = dataclasses.replace(facts, base=facts_base)
    return CheckContext(unit="phase", workdir=work, request={}, values={}, artifacts={"expand": {"phases": "plan.md"}},
                        git=facts, allow=SPEC.allow_commands, out_dir=work.parent / "phase.out",
                        deadline_at=time.monotonic() + 60)


def _line(res: CheckResult, head: str) -> str:
    lines = [ln for ln in res.evidence.splitlines() if ln.startswith(head)]
    assert len(lines) == 1, (head, res.evidence)
    return lines[0][len(head):]


def test_the_phase_evidence_lists_the_paths_changed_since_the_phase_step_was_entered_in_order(tmp_path: Path) -> None:
    # AC 1, PHC-AC16 (PHC-B16, PHC-B9)
    work, base = _history_repo(tmp_path)
    res = checks.phase_check(_phase_context(work, base))
    # the file an earlier step and the phase both changed is among them
    assert _line(res, "Changed since the phase step was entered: ") == "shared.md, src/a.py, tests/test_a.py"
    assert "Changed paths since the run's base" not in res.evidence
    # no phase commit yet and nothing uncommitted: the first list holds none
    work2, base2 = _history_repo(tmp_path / "two", phase_commit=False)
    res2 = checks.phase_check(_phase_context(work2, base2))
    assert _line(res2, "Changed since the phase step was entered: ") == "none"
    # a repository with no commit of the step phase yet: the paths of the commits that do not name it
    (work2 / "src").mkdir(exist_ok=True)
    (work2 / "src" / "a.py").write_text("a = 1\n", encoding="utf-8")
    res3 = checks.phase_check(_phase_context(work2, base2))
    assert _line(res3, "Changed since the phase step was entered: ") == "src/a.py"


def test_the_phase_evidence_lists_each_path_only_earlier_steps_changed_with_their_steps(tmp_path: Path) -> None:
    # AC 2, PHC-AC17 (PHC-B17)
    work, base = _history_repo(tmp_path)
    res = checks.phase_check(_phase_context(work, base))
    assert _line(res, "Changed only by earlier steps: ") == "handoff.md (discovery), notes.md, triage_note.md (triage)"
    work2, base2 = _history_repo(tmp_path / "two", phase_commit=False)
    res2 = checks.phase_check(_phase_context(work2, base2))
    assert _line(res2, "Changed only by earlier steps: ") == ("handoff.md (discovery), notes.md, shared.md (triage, "
                                                               "discovery), triage_note.md (triage)")
    # a path two steps changed lists both in the order of the commits
    one = _plan([("Phase 1: A", [("1.1", "code", "x.py", "", TODAY)])])
    work3 = tmp_path / "three"
    work3.mkdir()
    _git(work3, "init", "-q")
    _commit(work3, "chore: base", {"README.md": "r\n", "plan.md": one})
    base3 = _git(work3, "rev-parse", "HEAD")
    _commit(work3, "docs(temperspec): triage for T", {"shared.md": "1\n"})
    _commit(work3, "docs(temperspec): discovery for T", {"shared.md": "2\n"})
    _commit(work3, "feat(temperspec): phase for T", {"x.py": "x\n"})
    res3 = checks.phase_check(_phase_context(work3, base3))
    assert _line(res3, "Changed only by earlier steps: ") == "shared.md (triage, discovery)"
    assert _line(res3, "Changed since the phase step was entered: ") == "x.py"
    # the line ends none when no path qualifies
    work4 = tmp_path / "four"
    work4.mkdir()
    _git(work4, "init", "-q")
    _commit(work4, "chore: base", {"README.md": "r\n", "plan.md": one})
    base4 = _git(work4, "rev-parse", "HEAD")
    _commit(work4, "feat(temperspec): phase for T", {"x.py": "x\n"})
    res4 = checks.phase_check(_phase_context(work4, base4))
    assert _line(res4, "Changed only by earlier steps: ") == "none"
    # history that cannot be read: the first list holds every changed path, the second none
    res5 = checks.phase_check(_phase_context(work, base, facts_base="f" * 40))
    assert _line(res5, "Changed only by earlier steps: ") == "none"
    assert "triage_note.md" in _line(res5, "Changed since the phase step was entered: ")


def test_the_phase_note_of_the_step_in_the_workflow_caps_at_1500_characters() -> None:
    # AC 1, PHC-AC4 (PHC-B4)
    step = SPEC.units["phase"].step
    assert step is not None and set(step.produces) == {"phase_note"}
    assert step.produces["phase_note"].max_chars == 1500


# -- stand-in runs of the package's own units -------------------------------------------------------------------------------

TASK = "P-1"
NAMES = {1: "Alpha", 2: "Beta", 3: "Gamma", 4: "Delta"}
NOTE = ("# Triage: P-1\n\n## Task\n\nA task.\n\n## Acceptance criteria\n\n1. A thing\n\n## Existing documents\n\n- None\n\n"
        "## Gaps\n\n- None\n\n## Route\n\n- Deliver: code\n- Route: plan\n")


def _run_plan(phases: int = 3, command: str = "git --version", marked: tuple[str, ...] = (),
              status: str = "planned") -> str:
    """A plan of `phases` phases, each with a test row N.1 and a code row N.2; the rows named in `marked` carry a mark."""
    rows = {n: [(f"{n}.1", "test", f"tests/test_p{n}.py", "AC 1", TODAY if f"{n}.1" in marked else ""),
                (f"{n}.2", "code", f"src/p{n}.py", "", TODAY if f"{n}.2" in marked else "")]
            for n in range(1, phases + 1)}
    text = _plan([(f"Phase {n}: {NAMES[n]}", rows[n]) for n in rows], status=status)
    return text.replace("- `git --version`\n", f"- `{command}`\n").replace("| `git --version` |", f"| `{command}` |")


def _mark(text: str, number: int, rows: tuple[str, ...]) -> str:
    """The plan with the empty Completed cell of each named row of the phase marked (the rows of other phases and
    rows that carry a mark are left as they are)."""
    out = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and cells and cells[0] in rows and cells[0].startswith(f"{number}.") and not cells[-1]:
            line = line.rstrip()[:-1].rstrip() + f" {TODAY} |"
        out.append(line)
    return "\n".join(out) + "\n"


def _empty(text: str, row: str) -> str:
    """The plan with the mark of one row emptied and its Change cell rewritten (a plan that rewrote the row)."""
    out = []
    for line in text.splitlines():
        if line.startswith(f"| {row} |"):
            cells = line.strip().strip("|").split("|")
            cells[-2], cells[-1] = f"{cells[-2].strip()} again", ""
            line = "|" + "|".join(f" {c.strip()} " for c in cells) + "|"
        out.append(line)
    return "\n".join(out) + "\n"


class Stand:
    """A stand-in executor that answers by the unit of the session key and records each session with the prompt, the
    state of the working tree at its start and, for each step session, the files it wrote."""

    def __init__(self, *, phases: int = 3, plans: list[str] | None = None, fail: dict[str, int] | None = None,
                 idle: dict[str, int] | None = None, no_note: dict[str, int] | None = None,
                 claims: list[str] | None = None, claim_accepted: bool = True, route: str = "plan",
                 finish: bool = True, delete_flag: bool = False) -> None:
        self.inner = standin("claude")
        self.name = self.inner.name
        self.route = route  # what triage says: `plan`, or `quick` for a run with no plan
        self.finish = finish  # whether the code session sets the plan's status to `completed`
        self.delete_flag = delete_flag  # whether the first session of phase 1 deletes `flag.txt`, a file of the base
        self.plans = plans or [_run_plan(phases)]
        self.fail = dict(fail or {})  # item -> its first attempts that leave the code row unmarked
        self.idle = dict(idle or {})  # item -> its first attempts that change no file and mark no row
        self.no_note = dict(no_note or {})  # item -> its first attempts that end with no note
        self.claims = list(claims or [])  # the unit each code session names in turn as at fault, `""` for none
        self.accepted = claim_accepted
        self.sessions: list[dict[str, Any]] = []
        self.workdir: Path | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    @staticmethod
    def whose(req: SessionRequest) -> tuple[str, str | None]:
        parts = req.session_key.split(".")
        return parts[0], (parts[1] if parts[0] == "phase" else None)

    def count(self, kind: str, unit: str, item: str | None = None) -> int:
        return sum(1 for s in self.sessions if s["kind"] == kind and s["unit"] == unit and item in (None, s["item"]))

    def keys(self, kind: str, unit: str) -> list[str]:
        return [s["key"] for s in self.sessions if s["kind"] == kind and s["unit"] == unit]

    def prompts(self, unit: str, kind: str = "step") -> list[str]:
        return [s["prompt"] for s in self.sessions if s["kind"] == kind and s["unit"] == unit]

    def _enter(self, kind: str, req: SessionRequest) -> dict[str, Any]:
        unit, item = self.whose(req)
        self.workdir = Path(req.workdir)
        dirty = subprocess.run(["git", "status", "--porcelain", "--", ".", ":(exclude).tempergraph"], cwd=req.workdir,
                               capture_output=True, text=True).stdout.strip()
        row = {"kind": kind, "unit": unit, "item": item, "key": req.session_key, "prompt": req.prompt,
               "clean": not dirty, "order": len(self.sessions)}
        self.sessions.append(row)
        return row

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        row = self._enter("step", req)
        unit, item = row["unit"], row["item"]
        work = Path(req.workdir)
        if unit == "triage":
            (work / "triage_note.md").write_text(NOTE, encoding="utf-8")
            return answer("Triaged.\nARTIFACT triage_note: triage_note.md\nARTIFACT gaps: none\n"
                          f"ARTIFACT route: {self.route}", session_id="s-triage")
        if unit == "discovery":
            (work / "handoff.md").write_text("# Hand-off: P-1\n", encoding="utf-8")
            return answer("Closed.\nARTIFACT handoff: handoff.md", session_id="s-discovery")
        if unit == "plan":
            n = self.count("step", "plan")
            (work / "plan.md").write_text(self.plans[min(n, len(self.plans)) - 1], encoding="utf-8")
            return answer("Planned.\nARTIFACT plan: plan.md\nARTIFACT complexity: complex", session_id=f"s-plan-{n}")
        if unit == "expand":
            with (work / "plan.md").open("a", encoding="utf-8") as fh:
                fh.write(f"\n<!-- expanded {self.count('step', 'expand')} -->\n")
            return answer("Expanded.\nARTIFACT phases: plan.md", session_id=f"s-expand-{self.count('step', 'expand')}")
        if unit == "phase":
            return self._phase(work, str(item))
        if unit == "code":
            return self._code(work)
        raise AssertionError(f"a session of {unit} that the stand-in does not answer")

    def _phase(self, work: Path, item: str) -> SessionResult:
        number, attempt = int(item[1:]), self.count("step", "phase", item)
        text = (work / "plan.md").read_text(encoding="utf-8")
        todo = tuple(r for r in (f"{number}.1", f"{number}.2") if re.search(rf"^\| {re.escape(r)} \|.*\| *\|$", text, re.M))
        if attempt <= self.idle.get(item, 0) or not todo:
            todo = ()
        else:
            if f"{number}.1" in todo:
                (work / "tests").mkdir(exist_ok=True)
                (work / "tests" / f"test_p{number}.py").write_text(
                    f"# AC 1\ndef test_p{number}(): ...  # session {len(self.sessions)}\n", encoding="utf-8")
            if self.delete_flag and item == "p1" and (work / "flag.txt").exists():
                (work / "flag.txt").unlink()
            if f"{number}.2" in todo:
                (work / "src").mkdir(exist_ok=True)
                (work / "src" / f"p{number}.py").write_text(f"p{number} = {len(self.sessions)}\n", encoding="utf-8")
            built = tuple(r for r in todo if not (r.endswith(".2") and attempt <= self.fail.get(item, 0)))
            (work / "plan.md").write_text(_mark(text, number, built), encoding="utf-8")
        if self.no_note.get(item, 0) >= attempt:
            return answer("Built the phase.", session_id=f"s-{item}-{attempt}")
        return answer(f"Built.\nARTIFACT phase_note: built {item} ({len(todo)} rows)", session_id=f"s-{item}-{attempt}")

    def _code(self, work: Path) -> SessionResult:
        n = self.count("step", "code")
        claim = self.claims[n - 1] if n <= len(self.claims) else ""
        if claim:
            return answer(f"Cannot build.\nUPSTREAM {claim}: the output of the {claim} step is at fault",
                          session_id=f"s-code-up-{n}")
        if (work / "plan.md").exists():
            text = (work / "plan.md").read_text(encoding="utf-8")
            status = "completed" if self.finish else "in-progress"
            (work / "plan.md").write_text(re.sub(r"^status: .*$", f"status: {status}", text, flags=re.M),
                                          encoding="utf-8")
        (work / "report.md").write_text("# Code report\n\n## Verification\n\n- `git --version`: passed\n\n"
                                        f"## Deviations\n\n- None\n\n<!-- code session {n} -->\n", encoding="utf-8")
        return answer("Coded.\nARTIFACT code_report: report.md\nARTIFACT tests_passed: yes", session_id=f"s-code-{n}")

    def run_judge(self, req: SessionRequest, views: Any, sink: Any) -> SessionResult:
        row = self._enter("judge", req)
        unit = row["unit"]
        count = max(len(SPEC.units[unit].gate.criteria), 1)
        if "upstream-claim" in req.prompt:
            count = 1
        rows = [{"n": i, "status": "MET", "evidence": "stand-in", "defect_in": None, "no_change": False}
                for i in range(1, count + 1)]
        text = "Reviewed.\n```json\n" + json.dumps({"criteria": rows, "gap": False, "confidence": 0.9}) + "\n```"
        return answer(text, tools=("Read",), session_id=f"j-{unit}-{len(self.sessions)}")


def passes(ctx: Any) -> CheckResult:
    return CheckResult(result="PASS", evidence="stand-in")


def ready(ctx: Any) -> dict[str, str]:
    return {"setup_ready": "yes"}


def _spec(real: tuple[str, ...] = ("phase",)) -> Any:
    """The package's spec with `prepare` answered by a callable, the checks of the units not named in `real` replaced by
    one that passes, the step of `code` not asked for its own check run, and no outcome gate or last stage."""
    units = {}
    for name, u in SPEC.units.items():
        gate = u.gate
        if gate.check is not None and name not in real:
            gate = dataclasses.replace(gate, check=CallableRef(module=__name__, qualname="passes", func=passes))
        step = u.step
        if step is not None and name == "code":
            step = dataclasses.replace(step, self_check=False)
        units[name] = dataclasses.replace(u, gate=gate, step=step)
    script = dataclasses.replace(SPEC.units["prepare"].script, run=None,
                                 call=CallableRef(module=__name__, qualname="ready", func=ready))
    units["prepare"] = dataclasses.replace(units["prepare"], script=script)
    return dataclasses.replace(SPEC, units=units, outcome=None, finalizer=None, finalizer_outcomes=())


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "Test")):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    (root / "README.md").write_text("scratch\n", encoding="utf-8")
    (root / "flag.txt").write_text("flag\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True, capture_output=True)
    return root


def _go(repo: Path, stand: Stand, *, real: tuple[str, ...] = ("phase",), arm: str = "phases", **settings: Any) -> Any:
    registry = Registry()
    registry.register(stand)
    flags = {"code_mode.arm": arm}
    return start(_spec(real), TASK, {"request": "x"}, repo, registry,
                 RunSettings(sleep=lambda s: None, flags=flags, **settings))


def _records(repo: Path, kind: str) -> list[dict[str, Any]]:
    path = run_dir(state_root_path(repo), SPEC.name, TASK) / "run.jsonl"
    return [r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if r["kind"] == kind]


def _log(stand: Stand, *args: str) -> str:
    assert stand.workdir is not None
    return subprocess.run(["git", *args], cwd=stand.workdir, capture_output=True, text=True, check=True).stdout


def _phase_commits(stand: Stand) -> list[str]:
    """The commits of the phase step on the run's branch, oldest first, as their hashes."""
    rows = _log(stand, "log", "--reverse", "--format=%H %s").splitlines()
    return [r.split()[0] for r in rows if " feat(temperspec): phase for " in r]


def test_three_phases_run_one_after_another_each_in_a_session_of_its_own_and_each_is_committed(repo: Path) -> None:
    # AC 1, PHC-AC1 (PHC-B1), PHC-AC2 (PHC-B2), PHC-AC5 (PHC-B5)
    stand = Stand(phases=3, idle={"p2": 1})
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert stand.keys("step", "phase") == ["phase.p1.1.step", "phase.p2.1.step", "phase.p2.2.retry", "phase.p3.1.step"]
    # each phase starts only after the gate of the one before it passed
    started = [s for s in stand.sessions if s["kind"] == "step" and s["unit"] == "phase"]
    passed = {r["item"]: r for r in _records(repo, "gate") if r.get("unit") == "phase" and r.get("verdict") == "PROCEED"}
    assert set(passed) == {"p1", "p2", "p3"}
    log = run_dir(state_root_path(repo), SPEC.name, TASK) / "run.jsonl"
    kinds = [(r["kind"], r.get("unit"), r.get("item")) for r in map(json.loads, log.read_text("utf-8").splitlines())]
    gate_at = {item: kinds.index(("gate", "phase", item)) for item in ("p1", "p2", "p3")}
    assert gate_at["p1"] < gate_at["p2"] < gate_at["p3"]
    assert [s["item"] for s in started] == ["p1", "p2", "p2", "p3"]
    # the brief of phase 2 holds its own heading, goal and weight and the two paths, and no other phase's heading
    brief = stand.prompts("phase")[1]
    assert "Phase 2: Beta" in brief and "Beta goal is reached." in brief and "Weight: light" in brief
    assert "plan.md" in brief and "triage_note.md" in brief
    assert "Phase 1: Alpha" not in brief and "Phase 3: Gamma" not in brief
    # one commit for each phase, in plan order, holding that phase's files and the marks of its rows (the idle first
    # attempt of phase 2 changed no file and made no commit)
    commits = _phase_commits(stand)
    assert len(commits) == 3
    for number, sha in enumerate(commits, start=1):
        files = set(_log(stand, "show", "--name-only", "--format=", sha).split())
        assert files == {"plan.md", f"tests/test_p{number}.py", f"src/p{number}.py"}, files
        plan = _log(stand, "show", f"{sha}:plan.md")
        for later in range(1, 4):
            marked = re.search(rf"^\| {later}\.2 \|.*{TODAY}", plan, re.M) is not None
            assert marked == (later <= number), (number, later)
    # the working tree is clean when a session starts, and the expand step's commit is before the first phase commit
    assert all(s["clean"] for s in stand.sessions if s["unit"] == "phase" and s["kind"] == "step")
    subjects = _log(stand, "log", "--reverse", "--format=%s").splitlines()
    assert subjects.index(next(s for s in subjects if " expand for " in s)) < subjects.index(
        next(s for s in subjects if " phase for " in s))
    assert stand.count("step", "code") == 1


def test_a_plan_of_one_phase_runs_one_item(repo: Path) -> None:
    # AC 1, PHC-AC1 (PHC-B1)
    stand = Stand(phases=1)
    assert _go(repo, stand).exit_code is ExitCode.FINISHED
    assert stand.keys("step", "phase") == ["phase.p1.1.step"] and len(_phase_commits(stand)) == 1


def test_each_passing_phase_has_a_judge_session_and_a_failing_check_starts_none(repo: Path) -> None:
    # AC 1, PHC-AC9 (PHC-B9), PHC-AC11 (PHC-B11)
    stand = Stand(phases=3, fail={"p2": 1})
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert stand.count("step", "phase", "p2") == 2
    assert [stand.count("judge", "phase", p) for p in ("p1", "p2", "p3")] == [1, 1, 1], "none for the failed attempt"
    assert stand.count("judge", "code") == 1, "besides the judge session of the code step"
    # the code step starts after the gate of phase 3 passed, and one session runs on the whole change
    log = run_dir(state_root_path(repo), SPEC.name, TASK) / "run.jsonl"
    seen = [(r["kind"], r.get("unit"), r.get("item"), r.get("verdict")) for r in map(json.loads, log.read_text("utf-8").splitlines())]
    last_phase_gate = max(i for i, r in enumerate(seen) if r[:3] == ("gate", "phase", "p3"))
    first_code = min(i for i, r in enumerate(seen) if r[:2] == ("unit_entered", "code"))
    assert last_phase_gate < first_code and seen[last_phase_gate][3] == "PROCEED"
    assert stand.count("step", "code") == 1


# -- a failed phase runs again alone (PHC-B10) --------------------------------------------------------------------------------


def test_a_phase_that_fails_its_gate_runs_again_alone_and_the_earlier_commits_stay(repo: Path) -> None:
    # AC 2, PHC-AC10 (PHC-B10)
    stand = Stand(phases=3, fail={"p2": 1})
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert [stand.count("step", "phase", p) for p in ("p1", "p2", "p3")] == [1, 2, 1]
    order = [s["item"] for s in stand.sessions if s["kind"] == "step" and s["unit"] == "phase"]
    assert order == ["p1", "p2", "p2", "p3"], "phase 3 starts after phase 2 passed; phase 1 is not rerun"
    first = _phase_commits(stand)[0]
    assert re.search(rf"^\| 1\.2 \|.*{TODAY}", _log(stand, "show", f"{first}:plan.md"), re.M), "phase 1 stays marked"
    assert re.search(rf"^\| 1\.2 \|.*{TODAY}", (stand.workdir / "plan.md").read_text(encoding="utf-8"), re.M)  # type: ignore[operator]


def test_a_phase_that_spends_its_retries_pauses_the_run_at_that_phase_and_the_later_steps_start_nothing(repo: Path) -> None:
    # AC 2, PHC-AC10 (PHC-B10), PHC-AC11 (PHC-B11)
    stand = Stand(phases=3, fail={"p2": 99})
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.PAUSED, out.message
    pauses = [r for r in _records(repo, "pause") if r.get("unit") == "phase"]
    assert pauses and pauses[-1]["item"] == "p2"
    assert stand.count("step", "phase", "p3") == 0 and stand.count("step", "code") == 0
    assert stand.count("step", "phase", "p1") == 1


def test_a_phase_session_that_ends_with_no_note_runs_again_alone(repo: Path) -> None:
    # AC 2, PHC-AC4 (PHC-B4), PHC-AC10 (PHC-B10)
    stand = Stand(phases=3, no_note={"p2": 1})
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert [stand.count("step", "phase", p) for p in ("p1", "p2", "p3")] == [1, 2, 1]


# -- the code step is the join (PHC-B11 to PHC-B13) ----------------------------------------------------------------------------


def _item_line(brief: str, phase: str) -> int:
    return brief.index(f"built {phase} ")


def test_the_brief_of_the_code_step_lists_the_note_of_each_phase_in_plan_order(repo: Path) -> None:
    # AC 3, PHC-AC12 (PHC-B12)
    stand = Stand(phases=3)
    assert _go(repo, stand).exit_code is ExitCode.FINISHED
    (brief,) = stand.prompts("code")
    assert _item_line(brief, "p1") < _item_line(brief, "p2") < _item_line(brief, "p3")
    said = _said(brief)
    for phrase in ("when the notes list the phases", "build only a row whose completed cell is empty",
                   "set the plan's `status` to `completed`", "each deviation the notes name"):
        assert phrase in said, phrase


@pytest.mark.parametrize("arm, route", [("single", "plan"), ("phases", "quick")])
def test_a_single_session_run_and_a_quick_lane_run_list_no_note_and_enter_no_phase(repo: Path, arm: str, route: str) -> None:
    # AC 3, PHC-AC12 (PHC-B12), CDM-AC15 (CDM-B9)
    stand = Stand(phases=2, route=route)
    assert _go(repo, stand, arm=arm).exit_code is ExitCode.FINISHED
    assert stand.count("step", "phase") == 0 and stand.count("step", "expand") == 0
    (brief,) = stand.prompts("code")
    assert "built p" not in brief
    said = _said(brief)
    assert "no phase ran" in said
    assert "or `none` when no phase ran: none " in said, "the notes are rendered as `none`"


def _code_context(stand: Stand, base: str) -> CheckContext:
    """The code gate's check on the run's worktree as the run left it, with the run's own git facts."""
    from tempergraph.run.checks import git_facts

    assert stand.workdir is not None
    work = stand.workdir
    return CheckContext(unit="code", workdir=work, request={}, values={"triage": {"route": "plan"}},
                        artifacts={"triage": {"triage_note": "triage_note.md"}, "plan": {"plan": "plan.md"},
                                   "expand": {"phases": "plan.md"}, "code": {"code_report": "report.md"}},
                        git=git_facts(work, base), allow=SPEC.allow_commands, out_dir=work.parent / "code.out",
                        deadline_at=time.monotonic() + 120)


def _head(repo: Path) -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


def test_the_code_gate_checks_the_whole_change_after_the_phases(repo: Path) -> None:
    # AC 4, PHC-AC13 (PHC-B13)
    base = _head(repo)
    stand = Stand(phases=2)
    out = _go(repo, stand, real=("phase", "code"))
    assert out.exit_code is ExitCode.FINISHED, out.message
    # the code session changed no file of a row (the phases did), and the gate makes no finding about the rows' files
    res = checks.code_check(_code_context(stand, base))
    assert res.result == "PASS", res.evidence
    by = {f.criterion: f for f in res.findings}
    assert by["ts-code-changed"].status == "pass" and by["ts-code-rows"].status == "pass"
    assert by["ts-code-lane"].status == "n_a" and "not in the quick lane" in by["ts-code-lane"].message
    assert by["ts-code-verify"].status == "pass" and by["ts-code-proof"].status == "pass"
    # AC 6, PHC-AC19 (PHC-B19): the two lists counted from the code step's entry
    # (the stand-in's code session wrote the plan's status and the report: the first list holds those two, none of the phases' files)
    assert _line(res, "Changed since the code step was entered: ") == "plan.md, report.md"
    earlier = _line(res, "Changed only by earlier steps: ")
    for path in ("src/p1.py", "src/p2.py", "tests/test_p1.py", "tests/test_p2.py"):
        assert f"{path} (phase)" in earlier, (path, earlier)
    assert "Changed paths since the run's base" not in res.evidence
    # a run with no commit of the step phase keeps the one line
    work, base2 = _history_repo(stand.workdir.parent / "nophase", phase_commit=False)  # type: ignore[union-attr]
    plain = checks.code_check(dataclasses.replace(_phase_context(work, base2), unit="code"))
    assert "Changed paths since the run's base" in plain.evidence


def test_a_stand_in_run_of_two_phases_with_earlier_documents_passes_every_phase_gate_with_no_pause(repo: Path) -> None:
    # AC 5, PHC-AC20 (PHC-B9, PHC-B16, PHC-B17)
    stand = Stand(phases=2, route="discovery")  # the run takes the discovery step, which writes handoff.md
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert [r for r in _records(repo, "pause")] == []
    assert [r for r in _records(repo, "escalate")] == []
    prompts = stand.prompts("phase", "judge")
    assert len(prompts) == 2
    for number, prompt in enumerate(prompts, start=1):
        assert "Changed only by earlier steps:" in prompt and "Changed since the phase step was entered:" in prompt
        earlier = next(ln for ln in prompt.splitlines() if ln.startswith("Changed only by earlier steps:"))
        own = next(ln for ln in prompt.splitlines() if ln.startswith("Changed since the phase step was entered:"))
        assert "handoff.md (discovery)" in earlier and "triage_note.md (triage)" in earlier
        assert f"src/p{number}.py" in own and f"tests/test_p{number}.py" in own
        assert "triage_note.md" not in own and "handoff.md" not in own


def test_the_code_judge_brief_says_the_changed_paths_are_two_lists_counted_from_the_code_steps_entry() -> None:
    # AC 6, PHC-AC19 (PHC-B19)
    said = _said((ROOT / "judges" / "code.md").read_text(encoding="utf-8")).lower()
    for phrase in ("two lists counted from the code step's entry", "changed since the code step was entered",
                   "changed only by earlier steps", "the files of the phases", "need no row",
                   "docs/tasks/", "the plan", "written by prepare"):
        assert phrase in said, phrase


def test_a_plan_whose_status_is_not_completed_after_the_last_phase_fails_before_any_command_runs(repo: Path) -> None:
    # AC 4, PHC-AC13 (PHC-B13)
    base = _head(repo)
    stand = Stand(phases=2)
    assert _go(repo, stand, real=("phase", "code")).exit_code is ExitCode.FINISHED
    plan = stand.workdir / "plan.md"  # type: ignore[operator]
    plan.write_text(re.sub(r"^status: .*$", "status: in-progress", plan.read_text(encoding="utf-8"), flags=re.M),
                    encoding="utf-8")
    ctx = _code_context(stand, base)
    res = checks.code_check(ctx)
    assert res.result == "FAIL" and "not `completed`" in _named(res) and ctx.runs == []


def test_a_command_that_exits_zero_at_the_base_and_fails_at_the_gate_reruns_only_the_code_step(repo: Path) -> None:
    # AC 4, PHC-AC13 (PHC-B13): phase 1 deletes `flag.txt`, so `git show HEAD:flag.txt` exits 0 at the base only
    stand = Stand(phases=2, plans=[_run_plan(2, command="git show HEAD:flag.txt")], delete_flag=True)
    out = _go(repo, stand, real=("phase", "code"))
    assert out.exit_code is not ExitCode.FINISHED
    assert stand.count("step", "code") >= 2, "the code step runs again"
    assert [stand.count("step", "phase", p) for p in ("p1", "p2")] == [1, 1], "no phase session starts again"
    verdicts = [r["verdict"] for r in _records(repo, "gate") if r.get("unit") == "code"]
    assert verdicts and all(v != "PROCEED" for v in verdicts)


# -- the code gate holds the lines back (PHC-B14, PHC-B15) ------------------------------------------------------------------------


@pytest.mark.parametrize("claim", ["plan", "discovery", "triage"])
def test_a_claim_of_the_code_session_that_the_gate_accepts_sends_the_run_back_to_that_step(repo: Path, claim: str) -> None:
    # AC 4, PHC-AC14 (PHC-B14)
    stand = Stand(phases=2, claims=[claim])
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert stand.count("step", claim) == (1 if claim == "discovery" else 2), claim
    assert stand.count("step", "code") == 2
    assert stand.count("step", "phase", "p1") == 2 and stand.count("step", "phase", "p2") == 2


def test_the_readme_the_docstring_and_the_diagram_say_the_phase_step_runs_between_expand_and_code() -> None:
    # AC 5
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    rows = [ln for ln in readme.splitlines() if ln.startswith("| phase |")]
    assert len(rows) == 1 and "one fresh session" in rows[0]
    assert "Per-phase coding is not built yet" not in readme
    (full,) = [ln for ln in readme.splitlines() if ln.startswith("| full |")]
    assert "expand → phase → code" in full
    doc = importlib.import_module("tgwf_temperspec").__doc__ or ""
    assert "phase" in doc and "per-phase coding waits" not in doc
    diagram = (ROOT / "diagram" / "workflow.md").read_text(encoding="utf-8")
    node = {name: uid for uid, name in re.findall(r'^\s*(u\d+)\["(\w+)<br/>', diagram, re.M)}
    assert {"expand", "phase", "code"} <= set(node)
    assert f"{node['expand']} --> {node['phase']}" in diagram, "an edge from expand to phase"
    assert f"{node['phase']} --> {node['code']}" in diagram, "an edge from phase to code"
    assert f"{node['expand']} --> {node['code']}" not in diagram and f"{node['phase']} -.->|back|" not in diagram


def test_the_check_of_a_phase_with_no_item_reads_the_whole_plan_as_one_phase(tmp_path: Path) -> None:
    # AC 1, PHC-AC6 (PHC-B6): a fixture run of the check gives it no item
    work = _work(tmp_path, _two_marked(TODAY, ""))
    res = checks.phase_check(_context(work, None, ("tests/test_b.py", "src/b.py")))  # type: ignore[arg-type]
    assert res.result == "FAIL" and "2.2" in _named(res) and "3.1" in _named(res)


def test_the_workflow_validates_and_the_gate_of_the_phase_step_names_no_step_to_go_back_to() -> None:
    # AC 4, PHC-AC14 (PHC-B14)
    from tempergraph.executors.capabilities import DECLARED
    from tempergraph.model.validate import validate

    assert [f for f in validate(SPEC, DECLARED) if f.severity == "error"] == []
    assert not SPEC.units["phase"].gate.back_targets
    assert set(SPEC.units["code"].gate.back_targets) == {"plan", "discovery", "triage"}


def test_after_a_trip_back_that_keeps_every_mark_both_phases_run_again_change_no_file_and_make_no_commit(repo: Path) -> None:
    # AC 4, PHC-AC15 (PHC-B15)
    kept = _run_plan(2, marked=("1.1", "1.2", "2.1", "2.2"))
    stand = Stand(phases=2, plans=[_run_plan(2), kept], claims=["plan"])
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert [stand.count("step", "phase", p) for p in ("p1", "p2")] == [2, 2]
    assert len(_phase_commits(stand)) == 2, "the second visit made no commit"
    assert stand.count("judge", "phase") == 4, "and both passed their gates"


def test_after_a_trip_back_that_empties_one_mark_only_that_row_is_built(repo: Path) -> None:
    # AC 4, PHC-AC15 (PHC-B15)
    rewritten = _empty(_run_plan(2, marked=("1.1", "1.2", "2.1", "2.2")), "2.2")
    stand = Stand(phases=2, plans=[_run_plan(2), rewritten], claims=["plan"])
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    commits = _phase_commits(stand)
    assert len(commits) == 3, "phase 1 made no commit on the second visit; phase 2 made one"
    assert set(_log(stand, "show", "--name-only", "--format=", commits[-1]).split()) == {"plan.md", "src/p2.py"}
