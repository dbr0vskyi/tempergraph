"""Task i125: a trip back to plan keeps the completed marks of rows that did not change (kept-marks spec,
KMK-B1 to KMK-B8): the plan and expand checks read the run's history, the code check takes a kept row, and the
prompts, the plan rule and `outcome.json` say so. The file builds its own scratch repository."""

from __future__ import annotations

import importlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts, git_facts, run_check

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
fmt = importlib.import_module("tgwf_temperspec.specfmt")
DONE = ROOT / "evals" / "checks" / "code" / "must-pass" / "1-done"
PLAN = "docs/plans/t.plan.md"
CODE = "feat(temperspec): code for t"
PLAN_STEP = "docs(temperspec): plan for t"
MARK, LATER = "✓ 2026-11-22", "✓ 2026-11-24"

# row id -> (kind, file, change)
ROWS = {"1.1": ("test", "tests/test_a.py", "Assert the refusal"),
        "1.2": ("code", "src/a.py", "Report the missing file"),
        "2.1": ("code", "src/c.py", "Name the folder in the message")}
FILES = ("tests/test_a.py", "src/a.py", "src/c.py", "src/other.py")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout


def _commit(root: Path, subject: str) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--allow-empty", "-m", subject)


def _plan_text(rows: dict[str, tuple[str, str, str]], marks: dict[str, str], status: str = "planned") -> str:
    out = [f"---\ntask: t\ncomplexity: complex\nstatus: {status}\nspecs: []\n---\n", "# Plan: t\n",
           "## 0. Hand-off\n\n- Triage note: `docs/tasks/t.triage.md`\n",
           "## 1. Requirements\n\n| Req | Criteria | Statement | Spec ids |\n|---|---|---|---|\n| R1 | AC 1 | x | |\n",
           "## 2. Phases\n"]
    for n in sorted({i.split(".")[0] for i in rows}):
        out.append(f"### Phase {n}: part {n}\n\nGoal: part {n} is in place.\nWeight: light\n\n"
                   "| Row | Kind | Req | File | Proves | Change | Completed |\n|---|---|---|---|---|---|---|")
        out += [f"| {i} | {k} | R1 | `{f}` | AC 1 | {c} | {marks.get(i, '')} |"
                for i, (k, f, c) in rows.items() if i.split(".")[0] == n]
        out.append("")
    out.append("## 3. Verification\n\n- `git --version`\n\n| Criterion | Test | Command |\n|---|---|---|\n"
               "| AC 1 | `tests/test_a.py` | `git --version` |\n\n## 4. Docs to update\n\n- None\n")
    return "\n".join(out)


def _write(root: Path, path: str, text: str) -> None:
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(text, encoding="utf-8")


def _repo(root: Path, *, marking: str = CODE, later: str | None = None) -> str:
    """A base commit, a commit that builds every file and marks the three rows `✓ 2026-11-22`, and when `later` is
    given a commit of the run that changes that file. Returns the base commit."""
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    for f in FILES:
        _write(root, f, "base\n")
    _commit(root, "base")
    base = _git(root, "rev-parse", "HEAD").strip()
    for f in FILES[:3]:
        _write(root, f, "built\n")
    _write(root, PLAN, _plan_text(ROWS, dict.fromkeys(ROWS, MARK), "completed"))
    _commit(root, marking)
    if later:
        _write(root, later, "changed by a later commit\n")
        _commit(root, CODE)
    return base


def _hand_over(root: Path, rows: dict[str, tuple[str, str, str]], marks: dict[str, str]) -> None:
    """The plan a planning step hands over, committed as its own commit."""
    _write(root, PLAN, _plan_text(rows, marks))
    _commit(root, PLAN_STEP)


def _ctx(root: Path, unit: str, base: str | None) -> CheckContext:
    key = {"plan": {"plan": PLAN}, "expand": {"phases": PLAN}}[unit]
    facts = git_facts(root, base) if base else GitFacts()
    return CheckContext(unit=unit, workdir=root, request={}, artifacts={unit: key}, values={}, git=facts,
                        allow=SPEC.allow_commands, out_dir=root.parent / f"{root.name}.out",
                        deadline_at=time.monotonic() + 60)


CRITERION = {"plan": "ts-plan-form", "expand": "ts-exp-rows"}


def _verdict(root: Path, unit: str, base: str | None) -> tuple[list[Any], list[Any]]:
    """(the failing findings, every finding) of the criterion a plan or expand check holds the marks to."""
    res, _ = run_check(SPEC.units[unit].gate, _ctx(root, unit, base))
    mine = [f for f in res.findings if f.criterion == CRITERION[unit]]
    return [f for f in mine if f.status == "fail"], mine


def _names(failing: list[Any], row: str) -> bool:
    return any(f"`{row}`" in f.message for f in failing)


def _all(unit: str, root: Path, base: str | None) -> list[Any]:
    return _verdict(root, unit, base)[0]


# -- KMK-B1, KMK-B3: a kept mark is accepted --------------------------------------------------------------


def test_the_plan_check_accepts_the_marks_of_rows_left_as_they_were(tmp_path: Path) -> None:
    # AC 1, KMK-AC1, KMK-AC6
    base = _repo(tmp_path / "a")
    _hand_over(tmp_path / "a", ROWS, dict.fromkeys(ROWS, MARK))
    failing, mine = _verdict(tmp_path / "a", "plan", base)
    assert failing == [] and [f.status for f in mine] == ["pass"]
    # a later commit of the run changed only the file of row 1.2, which the plan empties: row 2.1 keeps its mark
    base = _repo(tmp_path / "b", later="src/a.py")
    _hand_over(tmp_path / "b", ROWS, {"1.1": MARK, "2.1": MARK})
    failing, _ = _verdict(tmp_path / "b", "plan", base)
    assert failing == [], [f.message for f in failing]


# -- KMK-B2, KMK-B3, KMK-B4: a mark that history does not back is refused ----------------------------------


def test_the_plan_check_refuses_a_mark_that_history_does_not_back(tmp_path: Path) -> None:
    # AC 2, KMK-AC3, KMK-AC5, KMK-AC7, KMK-AC8
    root = tmp_path / "r"
    base = _repo(root)
    marks = dict.fromkeys(ROWS, MARK)

    rewritten = {**ROWS, "1.2": ("code", "src/a.py", "Report the missing file and exit with code 2")}
    _hand_over(root, rewritten, marks)
    failing = _all("plan", root, base)
    assert _names(failing, "1.2") and not _names(failing, "1.1") and not _names(failing, "2.1")

    moved = {**ROWS, "1.2": ("code", "src/other.py", "Report the missing file")}
    _hand_over(root, moved, marks)
    assert _names(_all("plan", root, base), "1.2")

    added = {**ROWS, "4.1": ("docs", "README.md", "Describe it")}
    _hand_over(root, added, {**marks, "4.1": LATER})
    failing = _all("plan", root, base)
    assert _names(failing, "4.1") and not _names(failing, "1.1")

    _hand_over(root, ROWS, {**marks, "1.1": LATER})
    failing = _all("plan", root, base)
    assert _names(failing, "1.1") and not _names(failing, "1.2")

    later = _repo(tmp_path / "s", later="src/c.py")  # a later commit of the run changed the file of row 2.1
    _hand_over(tmp_path / "s", ROWS, marks)
    failing = _all("plan", tmp_path / "s", later)
    assert _names(failing, "2.1") and not _names(failing, "1.1") and not _names(failing, "1.2")


def test_the_plan_check_makes_no_finding_about_a_changed_row_with_an_empty_cell(tmp_path: Path) -> None:
    # AC 2, KMK-AC4
    root = tmp_path / "r"
    base = _repo(root)
    rewritten = {**ROWS, "1.2": ("code", "src/other.py", "Report the missing file and exit with code 2")}
    _hand_over(root, rewritten, {"1.1": MARK, "2.1": MARK})
    failing, mine = _verdict(root, "plan", base)
    assert failing == [] and [f.status for f in mine] == ["pass"]


def test_the_plan_check_refuses_a_mark_in_a_run_with_no_base_commit(tmp_path: Path) -> None:
    # AC 2, KMK-AC9
    root = tmp_path / "r"
    _repo(root)
    _hand_over(root, ROWS, dict.fromkeys(ROWS, MARK))
    failing = _all("plan", root, None)
    assert all(_names(failing, row) for row in ROWS)


def test_a_mark_that_only_a_planning_commit_carries_is_refused(tmp_path: Path) -> None:
    # AC 2, KMK-AC7: the commit that hands the plan over did not write the mark
    root = tmp_path / "r"
    base = _repo(root, marking=PLAN_STEP)
    _hand_over(root, ROWS, dict.fromkeys(ROWS, MARK))
    failing = _all("plan", root, base)
    assert all(_names(failing, row) for row in ROWS)


# -- the expand check ---------------------------------------------------------------------------------------


def test_the_expand_check_accepts_two_kept_rows_and_refuses_the_rest(tmp_path: Path) -> None:
    # AC 1, AC 2, KMK-AC2, KMK-AC3, KMK-AC5, KMK-AC7
    root = tmp_path / "r"
    base = _repo(root)
    _hand_over(root, ROWS, {"1.1": MARK, "1.2": MARK})
    failing, mine = _verdict(root, "expand", base)
    assert failing == [] and [f.status for f in mine] == ["pass"]

    rewritten = {**ROWS, "1.2": ("code", "src/a.py", "Report the missing file and exit with code 2")}
    _hand_over(root, rewritten, {"1.1": MARK, "1.2": MARK})
    failing = _all("expand", root, base)
    assert _names(failing, "1.2") and not _names(failing, "1.1")

    _hand_over(root, ROWS, {"1.1": MARK, "1.2": LATER})
    assert _names(_all("expand", root, base), "1.2")

    later = _repo(tmp_path / "s", later="src/a.py")
    _hand_over(tmp_path / "s", ROWS, {"1.1": MARK, "1.2": MARK})
    failing = _all("expand", tmp_path / "s", later)
    assert _names(failing, "1.2") and not _names(failing, "1.1")


# -- KMK-B8: the code check ----------------------------------------------------------------------------------


def test_the_code_check_makes_no_finding_about_a_row_marked_by_an_earlier_visit(tmp_path: Path) -> None:
    # AC 3, KMK-AC15: the first visit changed src/tool/config.py (row 1.2), the second only README.md (row 4.1)
    for f in sorted(p for p in DONE.rglob("*") if p.is_file()):
        _write(tmp_path, f.relative_to(DONE).as_posix(), f.read_text(encoding="utf-8"))
    artifacts = {"code": {"code_report": "code_report.md"}, "expand": {"phases": "phases.md"}}
    git = GitFacts(base="abc123", changed_paths=("tests/test_config.py", "src/tool/config.py", "README.md"))
    ctx = CheckContext(unit="code", workdir=tmp_path, request={}, artifacts=artifacts, git=git,
                       values={"triage": {"route": "plan"}}, allow=SPEC.allow_commands,
                       out_dir=tmp_path.parent / f"{tmp_path.name}.out", deadline_at=time.monotonic() + 60)
    res, _ = run_check(SPEC.units["code"].gate, ctx)
    changed = [f for f in res.findings if f.criterion == "ts-code-changed"]
    assert [f.status for f in changed] == ["pass"] and not any("1.2" in f.message for f in changed)


# -- KMK-B5 to KMK-B7: the briefings -------------------------------------------------------------------------


def _text(*parts: str) -> str:
    return " ".join((ROOT.joinpath(*parts)).read_text(encoding="utf-8").split())


KEEP = "keep the Completed mark of each row you leave exactly as it was"
EMPTY = "empty the Completed cell of each row you change or add"
BUILD = "build only the rows whose Completed cell is empty"
REST = "leave the mark of every other row as it is"


def test_the_planning_briefings_keep_the_mark_of_a_row_left_as_it_was() -> None:
    # AC 1, AC 2, KMK-AC10, KMK-AC11, KMK-AC12
    for parts in (("prompts", "plan.md"), ("prompts", "expand.md"), ("rules", "plan.rule.md")):
        text = _text(*parts).lower()
        assert KEEP.lower() in text, parts
        assert EMPTY.lower() in text, parts
        assert "every completed cell empty" not in text, parts


def test_the_code_briefings_build_only_the_rows_without_a_mark() -> None:
    # AC 3, KMK-AC13, KMK-AC14
    for parts in (("prompts", "code.md"), ("rules", "plan.rule.md")):
        text = _text(*parts).lower()
        assert BUILD.lower() in text, parts
        assert REST.lower() in text, parts


# -- the outcome mirror --------------------------------------------------------------------------------------


def test_outcome_json_states_the_kept_mark_criteria_and_revision_11() -> None:
    # AC 1, AC 2, AC 3
    outcome = json.loads((ROOT / "outcome.json").read_text(encoding="utf-8"))
    rows = {c["id"]: c for io in outcome["intermediate"].values() for c in io["criteria"]}
    for cid in ("ts-plan-form", "ts-exp-rows"):
        assert "a completed mark only on a row that kept its mark through a trip back (KMK-B1 to KMK-B4)" in \
            rows[cid]["text"], cid
        assert "history" in rows[cid]["check_method"], cid
    assert rows["ts-code-changed"]["text"].endswith("changed in the run, whichever visit of the code step changed it (KMK-B8)")
    assert outcome["revision"] == 11 and outcome["revisions"][-1]["revision"] == 11
