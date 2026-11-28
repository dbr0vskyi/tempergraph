"""Task i166e: what a task row may be and what the plan and expand checks refuse about it (plan-rows spec,
PRW-B1 to PRW-B5). The file builds its own scratch repository."""

from __future__ import annotations

import importlib
import subprocess
import time
from pathlib import Path
from typing import Any

from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts, git_facts, run_check

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
fmt = importlib.import_module("tgwf_temperspec.specfmt")
PLAN = "docs/plans/t.plan.md"
CRITERION = {"plan": "ts-plan-form", "expand": "ts-exp-tests"}

# (id, kind, file, proves, change)
Row = tuple[str, str, str, str, str]


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout


def _write(root: Path, path: str, text: str) -> None:
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(text, encoding="utf-8")


def _plan_text(rows: list[Row], complexity: str = "simple") -> str:
    out = [f"---\ntask: t\ncomplexity: {complexity}\nstatus: planned\nspecs: []\n---\n", "# Plan: t\n",
           "## 0. Hand-off\n\n- Triage note: `docs/tasks/t.triage.md`\n",
           "## 1. Requirements\n\n| Req | Criteria | Statement | Spec ids |\n|---|---|---|---|\n| R1 | AC 1 | x | |\n",
           "## 2. Phases\n",
           "### Phase 1: part\n\nGoal: part is in place.\nWeight: light\n\n"
           "| Row | Kind | Req | File | Proves | Change | Completed |\n|---|---|---|---|---|---|---|"]
    out += [f"| {i} | {k} | R1 | `{f}` | {p} | {c} | |" for i, k, f, p, c in rows]
    out.append("\n## 3. Verification\n\n- `git --version`\n\n| Criterion | Test | Command |\n|---|---|---|\n"
               "| AC 1 | `tests/test_a.py` | `git --version` |\n\n## 4. Docs to update\n\n- None\n")
    return "\n".join(out)


def _repo(root: Path, rows: list[Row], *, files: tuple[str, ...] = ("src/old.py", "src/a.py", "src/b.py"),
          removed_later: str | None = None) -> str:
    """A base commit that holds `files` and `src/dir/inner.py`, an optional later commit that removes one file,
    and the plan as the last commit. Returns the base commit."""
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    for f in (*files, "src/dir/inner.py", "tests/test_a.py"):
        _write(root, f, "base\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    base = _git(root, "rev-parse", "HEAD").strip()
    if removed_later:
        (root / removed_later).unlink()
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "feat(temperspec): code for t")
    _write(root, PLAN, _plan_text(rows, "simple"))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "docs(temperspec): plan for t")
    return base


def _failing(root: Path, unit: str, base: str) -> list[Any]:
    key = {"plan": {"plan": PLAN}, "expand": {"phases": PLAN}}[unit]
    ctx = CheckContext(unit=unit, workdir=root, request={}, artifacts={unit: key}, values={},
                       git=git_facts(root, base) if base else GitFacts(), allow=SPEC.allow_commands,
                       out_dir=root.parent / f"{root.name}.out", deadline_at=time.monotonic() + 60)
    res, _ = run_check(SPEC.units[unit].gate, ctx)
    return [f for f in res.findings if f.status == "fail" and f.criterion in (CRITERION[unit], "ts-exp-rows")]


def _names(failing: list[Any], *rows: str) -> list[Any]:
    return [f for f in failing if all(f"`{r}`" in f.message for r in rows)]


def _run(tmp: Path, name: str, rows: list[Row], unit: str, **kw: Any) -> list[Any]:
    base = _repo(tmp / name, rows, **kw)
    return _failing(tmp / name, unit, base)


TEST_ROW: Row = ("1.1", "test", "tests/test_a.py", "AC 1", "Assert it")


# -- PRW-B1, PRW-B2: the kinds and the removal row -----------------------------------------------------------


def test_a_row_of_an_unknown_kind_or_with_no_file_fails_and_the_five_kinds_pass(tmp_path: Path) -> None:
    # PRW-AC1, AC 1
    bad_kind = [TEST_ROW, ("1.2", "refactor", "src/a.py", "", "Change a")]
    assert _names(_run(tmp_path, "a", bad_kind, "plan"), "1.2")
    no_file = [TEST_ROW, ("1.2", "code", "", "", "Change a")]
    assert _names(_run(tmp_path, "b", no_file, "expand"), "1.2")
    five = [TEST_ROW, ("1.2", "code", "src/a.py", "", "Change a"), ("1.3", "docs", "src/b.py", "", "Doc b"),
            ("1.4", "chore", "tests/test_b.py", "", "Chore"), ("1.5", "remove", "src/old.py", "", "Remove")]
    failing = _run(tmp_path, "c", five, "plan")
    assert not [f for f in failing if "needs an id, a kind" in f.message], [f.message for f in failing]


def test_a_removal_row_needs_no_proof_and_no_test_row_before_it(tmp_path: Path) -> None:
    # PRW-AC2, AC 1
    rows = [("1.0", "remove", "src/old.py", "", "Remove it"), TEST_ROW, ("1.2", "code", "src/a.py", "", "Change a")]
    failing = _run(tmp_path, "a", rows, "plan")
    assert not failing, [f.message for f in failing]
    only = [("1.1", "remove", "src/old.py", "", "Remove it")]
    failing = _run(tmp_path, "b", only, "expand")
    assert not [f for f in failing if "1.1" in f.message], [f.message for f in failing]


def test_plan_facts_counts_a_removal_row_as_a_row_and_its_file_as_a_file() -> None:
    # PRW-AC2, AC 1
    plan = fmt.parse_plan(_plan_text([TEST_ROW, ("1.2", "remove", "src/old.py", "", "Remove it")]))
    facts = fmt.plan_facts(plan)
    assert facts["rows"] == 2 and facts["files"] == 2 and facts["test_rows"] == 1


# -- PRW-B3 to PRW-B5: the refusals ----------------------------------------------------------------------------


def test_a_row_for_a_file_under_claude_is_refused(tmp_path: Path) -> None:
    # PRW-AC3, AC 1
    for unit in ("plan", "expand"):
        rows = [TEST_ROW, ("1.2", "docs", ".claude/rules/temperspec/plan.rule.md", "", "Doc"),
                ("1.3", "remove", ".claude/settings.json", "", "Remove")]
        failing = _run(tmp_path, f"a-{unit}", rows, unit, files=("src/old.py", ".claude/settings.json"))
        assert _names(failing, "1.2") and _names(failing, "1.3")
    ok = [TEST_ROW, ("1.2", "docs", ".claude-plugin/plugin.json", "", "Doc")]
    failing = _run(tmp_path, "b", ok, "plan")
    assert not [f for f in failing if "`1.2`" in f.message], [f.message for f in failing]


def test_a_removal_row_needs_a_file_of_the_base_commit(tmp_path: Path) -> None:
    # PRW-AC4, AC 1
    rows = [TEST_ROW, ("1.2", "remove", "src/missing.py", "", "R"), ("1.3", "remove", "src/dir", "", "R"),
            ("1.4", "remove", "../outside.txt", "", "R"), ("1.5", "remove", "/etc/hosts", "", "R")]
    failing = _run(tmp_path, "a", rows, "plan")
    for row in ("1.2", "1.3", "1.4", "1.5"):
        assert _names(failing, row), row
    ok = [("1.1", "remove", "src/old.py", "", "R")]
    failing = _run(tmp_path, "b", ok, "expand", removed_later="src/old.py")
    assert not [f for f in failing if "`1.1`" in f.message], [f.message for f in failing]


def test_the_file_of_a_removal_row_is_named_by_no_other_row(tmp_path: Path) -> None:
    # PRW-AC5, AC 1
    for unit in ("plan", "expand"):
        rows = [TEST_ROW, ("1.2", "remove", "src/old.py", "", "R"), ("1.3", "code", "src/old.py", "", "C")]
        assert _names(_run(tmp_path, f"a-{unit}", rows, unit), "1.2", "1.3")
        rows = [TEST_ROW, ("1.2", "remove", "src/old.py", "", "R"), ("1.3", "remove", "src/old.py", "", "R")]
        assert _names(_run(tmp_path, f"b-{unit}", rows, unit), "1.2", "1.3")
    rows = [TEST_ROW, ("1.2", "remove", "src/old.py", "", "R"),
            ("1.3", "code", "src/a.py", "", "Its content comes from `src/old.py`")]
    failing = _run(tmp_path, "c", rows, "plan")
    assert not [f for f in failing if "`1.2`" in f.message or "`1.3`" in f.message], [f.message for f in failing]


def test_ten_refused_rows_are_all_named_with_a_fix_text_each(tmp_path: Path) -> None:
    # PRW-AC3, PRW-AC4, AC 1
    rows = [TEST_ROW] + [(f"1.{n}", "remove", f"src/missing{n}.py", "", "R") for n in range(2, 12)]
    for unit in ("plan", "expand"):
        failing = _run(tmp_path, unit, rows, unit)
        for n in range(2, 12):
            hit = _names(failing, f"1.{n}")
            assert hit and all(f.fix for f in hit), n
    assert len({f.fix for f in _names(failing, "1.2")}) >= 1


def _said(*parts: str) -> str:
    return " ".join(ROOT.joinpath(*parts).read_text(encoding="utf-8").split()).lower()


def test_prw_ac6_plan_expand_and_rule_name_the_remove_kind_and_the_moved_file() -> None:
    # PRW-AC6, AC 1
    for parts in (("prompts", "plan.md"), ("prompts", "expand.md"), ("rules", "plan.rule.md")):
        text = _said(*parts)
        assert "a file that goes away is a row of kind `remove`" in text, parts
        assert ("a moved file is a `remove` row for its old path and a row of another kind for its new path"
                in text), parts


def test_prw_ac7_plan_and_expand_say_a_file_under_claude_gets_no_row() -> None:
    # PRW-AC7, AC 1
    for parts in (("prompts", "plan.md"), ("prompts", "expand.md")):
        text = _said(*parts)
        assert "no row names a file whose path starts with `.claude/`" in text, parts
        assert "the plan's hand-off section names the change a person makes" in text, parts
