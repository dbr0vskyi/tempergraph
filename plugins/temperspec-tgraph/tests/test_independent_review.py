"""Task i173: the independent review unit (IRV-B1 to IRV-B14), its findings document (RVF-B1 to RVF-B7) and the
description's list of findings that block nothing (PRD-B9).

Phase 1 holds the model-free parts: the findings document, the change and the criteria handed to the reader, the
choice of the step a blocking finding goes back to, and the checks of the session record."""

from __future__ import annotations

import importlib
import subprocess
import time
from pathlib import Path
from typing import Any

from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
review = importlib.import_module("tgwf_temperspec.review")
checks = importlib.import_module("tgwf_temperspec.checks")

DRAFT = ".tempergraph/review/findings.md"


def _doc(*items: str, earlier: tuple[str, ...] = ()) -> str:
    body = "\n".join(items) if items else ""
    text = f"# Review: i1\n\n## Findings\n\n{body}\n"
    if earlier:
        text += "\n## Earlier review\n\n" + "\n".join(earlier) + "\n"
    return text


def _work(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "a.py").write_text("".join(f"line {i}\n" for i in range(1, 51)))
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "a.spec.md").write_text("one\ntwo\n")
    return tmp_path


def _problems(tmp_path: Path, text: str) -> list[tuple[str, str]]:
    return review.form_problems(text, _work(tmp_path))


def _places(problems: list[tuple[str, str]]) -> list[str]:
    return [place for place, _ in problems]


# -- the findings document (RVF-B2 to RVF-B5) ----------------------------------------------------------------------


def test_a_finding_is_written_as_one_numbered_item() -> None:
    # AC 3, RVF-AC2 (RVF-B2)
    blocking = review.Finding(1, "src/a.py", 42, "blocking", "the loop never ends when every source fails")
    assert review.format_finding(blocking) == "1. `src/a.py:42` blocking: the loop never ends when every source fails"
    quiet = review.Finding(2, "docs/a.spec.md", 7, "not blocking", "the sentence can be read two ways")
    assert review.format_finding(quiet) == "2. `docs/a.spec.md:7` not blocking: the sentence can be read two ways"
    doc = review.parse_document(_doc(review.format_finding(blocking), review.format_finding(quiet)))
    assert doc.findings == [blocking, quiet]


def test_the_check_names_the_number_of_each_refused_finding(tmp_path: Path) -> None:
    # AC 3, RVF-AC3 (RVF-B3)
    items = ["1. `src/a.py:3` blocking: complete",
             "2. `:5` blocking: no file",
             "3. `src/a.py` blocking: no line",
             "4. `src/missing.py:1` blocking: the file does not exist",
             "5. `src/a.py:51` blocking: the line is past the end",
             "6. `src/a.py:4` maybe: a mark that is neither",
             "7. `src/a.py:4`: no mark",
             "8. `src/a.py:50` not blocking: the last line"]
    problems = _problems(tmp_path, _doc(*items))
    assert _places(problems) == [f"finding {n}" for n in (2, 3, 4, 5, 6, 7)]
    assert all(message for _, message in problems)


def test_a_complete_finding_passes(tmp_path: Path) -> None:
    # AC 3, RVF-AC3 (RVF-B3)
    assert _problems(tmp_path, _doc("1. `src/a.py:3` blocking: x", "2. `docs/a.spec.md:2` not blocking: y")) == []


def test_the_check_names_the_section_or_the_number_of_a_document_of_the_wrong_form(tmp_path: Path) -> None:
    # AC 3, RVF-AC4 (RVF-B4)
    assert _places(_problems(tmp_path, "# Review: i1\n\nno sections\n")) == ["Findings"]
    assert _places(_problems(tmp_path, _doc())) == ["Findings"]
    out_of_order = _doc("1. `src/a.py:1` blocking: a", "2. `src/a.py:2` blocking: b", "4. `src/a.py:3` blocking: c")
    assert _places(_problems(tmp_path, out_of_order)) == ["finding 4"]


def test_a_section_that_holds_only_none_passes(tmp_path: Path) -> None:
    # AC 3, RVF-AC5 (RVF-B5)
    assert _problems(tmp_path, _doc("None")) == []


# -- the built document (RVF-B6, RVF-B7) ---------------------------------------------------------------------------

FIRST = _doc("1. `src/a.py:3` blocking: first", "2. `docs/a.spec.md:1` not blocking: second",
             "3. `src/a.py:9` blocking: third")
SECOND_DRAFT = "## Findings\n\n1. `src/a.py:5` blocking: still wrong\n"


def test_a_second_review_keeps_the_first_reviews_findings_as_given() -> None:
    # AC 3, AC 8, RVF-AC6 (RVF-B6)
    built = review.parse_document(review.build_document("i1", SECOND_DRAFT, FIRST, built=True))
    assert [f.text for f in built.findings] == ["still wrong"]
    assert [(f.number, f.file, f.line, f.mark, f.text) for f in built.earlier] == [
        (1, "src/a.py", 3, "blocking", "first"), (2, "docs/a.spec.md", 1, "not blocking", "second"),
        (3, "src/a.py", 9, "blocking", "third")]


def test_each_blocking_finding_of_the_first_review_ends_with_the_visits_result() -> None:
    # AC 8, RVF-AC7 (RVF-B7)
    for built, word in ((True, "built"), (False, "refused")):
        text = review.build_document("i1", SECOND_DRAFT, FIRST, built=built)
        earlier = text.split("## Earlier review", 1)[1].splitlines()
        items = [line for line in earlier if line[:1].isdigit()]
        assert [line.endswith(f"Visit: {word}") for line in items] == [True, False, True]
        assert "Visit:" not in text.split("## Earlier review", 1)[0]


def test_a_first_review_has_no_earlier_section() -> None:
    # AC 3, RVF-AC6 (RVF-B6)
    text = review.build_document("i1", SECOND_DRAFT, None, built=True)
    assert "Earlier review" not in text and "1. `src/a.py:5` blocking: still wrong" in text


# -- the change and the criteria handed to the reader (IRV-B3, IRV-B4) ---------------------------------------------


def _git(work: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=work, check=True,
                   capture_output=True)


def _commit(work: Path, subject: str, files: dict[str, str | None]) -> None:
    for rel, text in files.items():
        path = work / rel
        if text is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", subject)


TRIAGE = """# Triage: i1

## Task

Something.

## Acceptance criteria

1. A request is refused
2. A retry is served
3. The list is sorted

## Gaps

- G1 spec gap: secretgap. Searched: nothing. Owner decision

## Owner decisions

- G1: secretquestion?
  - Options: a) x; b) y
  - Default: a
  - If wrong: nothing

## Route

- Deliver: code
- Route: plan
"""


def _run(tmp_path: Path) -> Path:
    work = tmp_path / "repo"
    work.mkdir()
    _git(work, "init", "-q")
    _commit(work, "init", {"README.md": "r\n", "src/gone.py": "x\n", "docs/specs/a.spec.md": "one\n"})
    _commit(work, "docs(temperspec): prepare for i1", {"CLAUDE.md": "block\n", ".claude/rules/temperspec/x.rule.md": "r\n"})
    _commit(work, "docs(temperspec): triage for i1", {"docs/tasks/i1.triage.md": TRIAGE})
    _commit(work, "docs(temperspec): plan for i1", {"docs/plans/i1.plan.md": "plan\n", "docs/tasks/i1.handoff.md": "h\n"})
    _commit(work, "feat(temperspec): code for i1", {
        "src/new.py": "def f():\n    return 1\n", "tests/test_new.py": "def test_f():\n    pass\n",
        "docs/specs/a.spec.md": "one\ntwo\n", "src/gone.py": None, "docs/tasks/i1.report.md": "report\n",
        "CLAUDE.md": "block\nmore\n"})
    return work


def test_the_change_holds_the_runs_files_and_no_hand_over_document(tmp_path: Path) -> None:
    # AC 2, IRV-AC3 (IRV-B3)
    work = _run(tmp_path)
    changed = review.write_inputs(work, "i1", "docs/tasks/i1.triage.md")
    diff = (work / ".tempergraph" / "review" / "change.diff").read_text()
    for held in ("src/new.py", "tests/test_new.py", "docs/specs/a.spec.md", "src/gone.py"):
        assert held in diff and held in changed
    for refused in ("i1.triage.md", "i1.plan.md", "i1.handoff.md", "i1.report.md", "CLAUDE.md", "x.rule.md"):
        assert refused not in diff and not any(refused in p for p in changed)
    assert "deleted file" in diff
    assert (work / ".tempergraph" / "review" / ".gitignore").read_text().strip() == "*"


def test_a_review_after_a_trip_back_holds_the_commits_of_both_visits(tmp_path: Path) -> None:
    # AC 2, IRV-AC3 (IRV-B3)
    work = _run(tmp_path)
    _commit(work, "docs(temperspec): independent_review for i1", {"docs/tasks/i1.review.md": "# Review\n"})
    _commit(work, "feat(temperspec): code for i1", {"src/new.py": "def f():\n    return 2\n", "src/second.py": "y = 2\n"})
    review.write_inputs(work, "i1", "docs/tasks/i1.triage.md")
    diff = (work / ".tempergraph" / "review" / "change.diff").read_text()
    assert "return 2" in diff and "src/second.py" in diff and "tests/test_new.py" in diff
    assert "i1.review.md" not in diff


def test_the_criteria_file_holds_the_numbered_criteria_and_nothing_else_of_the_note(tmp_path: Path) -> None:
    # AC 2, IRV-AC4 (IRV-B4)
    work = _run(tmp_path)
    review.write_inputs(work, "i1", "docs/tasks/i1.triage.md")
    text = (work / ".tempergraph" / "review" / "criteria.md").read_text()
    for line in ("1. A request is refused", "2. A retry is served", "3. The list is sorted"):
        assert line in text
    for refused in ("secretgap", "secretquestion", "G1", "Owner", "Route"):
        assert refused not in text


# -- the step a blocking finding goes back to, and the reason (IRV-B9 to IRV-B11) ----------------------------------

MIXED = [review.Finding(1, "src/a.py", 3, "blocking", "first wrong"),
         review.Finding(2, "src/b.py", 4, "not blocking", "quiet one"),
         review.Finding(3, "docs/c.spec.md", 9, "blocking", "third wrong")]


def test_blocking_findings_on_changed_files_go_back_to_the_code_step() -> None:
    # AC 4, IRV-AC9 (IRV-B9)
    changed = ["src/a.py", "docs/c.spec.md", "tests/test_a.py"]  # a spec the change edited counts
    assert review.choose_step(MIXED, changed) == "code"
    assert review.choose_step([MIXED[1]], []) == ""  # nothing blocks, no step


def test_a_blocking_finding_on_an_untouched_file_goes_back_to_the_plan_step() -> None:
    # AC 4, IRV-AC10 (IRV-B10)
    assert review.choose_step(MIXED, ["src/a.py"]) == "plan"
    assert review.choose_step([MIXED[0]], ["src/other.py"]) == "plan"


def test_the_reason_holds_the_blocking_findings_in_order_and_no_other() -> None:
    # AC 2, AC 4, IRV-AC11 (IRV-B11)
    reason = review.reason_text(MIXED)
    assert reason.index("src/a.py:3") < reason.index("docs/c.spec.md:9")
    assert "1." in reason and "3." in reason and "first wrong" in reason and "third wrong" in reason
    assert "quiet one" not in reason and "src/b.py" not in reason


# -- the checks of the session record (IRV-B6, IRV-B7) ---------------------------------------------------------------


def _call(capability: str, target: str | None, ok: bool = True) -> dict[str, Any]:
    names = {"read": "Read", "search": "Grep", "edit": "Edit", "write": "Write"}
    return {"name": names[capability], "capability": capability, "target": target, "ok": ok}


def _ctx(tmp_path: Path, session: list[dict[str, Any]] | None) -> CheckContext:
    work = _work(tmp_path)
    (work / "docs" / "tasks").mkdir(parents=True, exist_ok=True)
    (work / "docs" / "tasks" / "i1.review.md").write_text(_doc("None"))
    return CheckContext(unit="independent_review", workdir=work, request={"task_id": "i1"}, values={},
                        artifacts={"independent_review": {"findings": "docs/tasks/i1.review.md"}},
                        git=GitFacts(), allow=SPEC.allow_commands, out_dir=tmp_path.parent / f"{tmp_path.name}.out",
                        deadline_at=time.monotonic() + 60, session=None if session is None else tuple(session),
                        visit_session=None if session is None else tuple(session))


def _found(ctx: CheckContext, criterion: str) -> list[Any]:
    return [f for f in checks.review_check(ctx).findings if f.criterion == criterion]


def test_a_session_that_opened_a_hand_over_document_fails_naming_it(tmp_path: Path) -> None:
    # AC 1, AC 2, IRV-AC6 (IRV-B6)
    opened = [_call("read", "docs/plans/i1.plan.md"), _call("search", "docs/tasks/i1.handoff.md")]
    found = _found(_ctx(tmp_path / "a", opened), "ts-rev-session")
    failing = [f for f in found if f.status == "fail"]
    assert len(failing) == 1 and "plan" in failing[0].message and "i1.plan.md" in failing[0].place
    searched = [_call("search", "docs/plans/i1.plan.md"), _call("read", "src/a.py"), _call("read", "docs/plans/i1.plan.md", ok=False)]
    assert not [f for f in _found(_ctx(tmp_path / "b", searched), "ts-rev-session") if f.status == "fail"]
    assert [f.status for f in _found(_ctx(tmp_path / "c", None), "ts-rev-session")] == ["n_a"]


def test_a_session_that_changed_a_file_other_than_the_draft_fails_naming_it(tmp_path: Path) -> None:
    # AC 1, IRV-AC7 (IRV-B7)
    wrote = [_call("write", DRAFT), _call("edit", "src/a.py")]
    failing = [f for f in _found(_ctx(tmp_path / "a", wrote), "ts-rev-session") if f.status == "fail"]
    assert len(failing) == 1 and "src/a.py" in failing[0].place
    only = [_call("write", DRAFT), _call("write", str(tmp_path / "b" / DRAFT))]
    assert not [f for f in _found(_ctx(tmp_path / "b", only), "ts-rev-session") if f.status == "fail"]
