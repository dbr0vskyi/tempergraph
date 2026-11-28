"""Plan check refuses non-`chore` rows with forbidden file operations (PLN-B2, PLN-AC2, PLN-AC3, PLN-AC1, AC 1)."""

from __future__ import annotations

import importlib
import json
import time
from pathlib import Path

from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts, run_check

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
fmt = importlib.import_module("tgwf_temperspec.specfmt")

OWNER = {key: unit for unit in SPEC.order
         for key in (SPEC.units[unit].step.produces if SPEC.units[unit].step else {})}

_FIXTURE = ROOT / "evals" / "checks" / "plan" / "must-pass" / "2-simple"
_COMMANDS = {"schema_version": 1, "commands": ["git"]}

_TRIAGE = """\
# Triage: STANDIN-1

## Task

Source: the start request. Summary: the tool reports a missing config file instead of crashing.

## Acceptance criteria

1. Starting the tool with no config file prints one line that names the missing file
2. Starting the tool with no config file exits with code 2

## Intent

- Goal: the tool reports a missing config file instead of crashing
- In scope: the change the acceptance criteria describe
- Out of scope: any behaviour the criteria do not name
- Assumptions: None

## Existing documents

- `README.md`: says the tool reads `tool.toml`, says nothing about a missing file

## Uncertainties

None

## Gaps

None

## Route

- Deliver: code
- Route: plan
"""

_PLAN_TEMPLATE = """\
---
task: STANDIN-1
complexity: simple
status: planned
specs: []
---

# Plan: report a missing config file

## 0. Hand-off

- Triage note: `triage_note.md`
- Why this design: the file is read in one place.

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | One line on standard error names the missing file | |
| R2 | AC 2 | The run ends with exit code 2 when the file is missing | |

## 2. Phases

### Phase 1: Missing config file

Goal: a start with no `tool.toml` prints one line and exits with code 2.
Weight: light

| Row | Kind | Req | File | Proves | Change | Completed |
|---|---|---|---|---|---|---|
{rows}

## 3. Verification

- `git --version`

| Criterion | Test | Command |
|---|---|---|
| AC 1 | `tests/test_config.py` | `git --version` |
| AC 2 | `tests/test_config.py` | `git --version` |

## 4. Docs to update

- None
"""


def _rows(*rows: str) -> str:
    return "\n".join(rows)


def _plan(rows: str) -> str:
    return _PLAN_TEMPLATE.format(rows=rows)


def _context(work: Path, artifacts: dict) -> CheckContext:
    return CheckContext(unit="plan", workdir=work, request={}, artifacts=artifacts, values={},
                       git=GitFacts(), allow=SPEC.allow_commands, out_dir=work.parent / f"{work.name}.out",
                       deadline_at=time.monotonic() + 60)


def _setup(work: Path, plan_text: str) -> CheckContext:
    work.mkdir(parents=True, exist_ok=True)
    (work / "plan.md").write_text(plan_text)
    (work / "triage_note.md").write_text(_TRIAGE)
    (work / "tempergraph.commands.json").write_text(json.dumps(_COMMANDS))
    artifacts = {
        "plan": {"plan": "plan.md"},
        "triage": {"triage_note": "triage_note.md"},
    }
    return _context(work, artifacts)


def _has_forbidden_fail(res: object) -> bool:
    return any(getattr(f, "status", None) == "fail" and getattr(f, "criterion", None) == "ts-plan-form"
               and "forbidden" in (getattr(f, "message", "") or "").lower()
               for f in getattr(res, "findings", []))


def _named(res: object, criterion: str) -> list[str]:
    return [f.status for f in res.findings if f.criterion == criterion]  # type: ignore[attr-defined]


def test_plan_check_fails_a_code_row_whose_change_deletes_a_file(tmp_path: Path) -> None:
    # PLN-AC2, AC 1 (a): a `code` row whose Change is "Delete src/old.py" is refused
    rows = _rows(
        "| 1.1 | test | R1 | `tests/test_config.py` | AC 1 | A start with no config file prints one line | |",
        "| 1.2 | test | R2 | `tests/test_config.py` | AC 2 | A start with no config file exits with code 2 | |",
        "| 1.3 | code | R1, R2 | `src/tool/config.py` | | Delete src/old.py | |",
    )
    ctx = _setup(tmp_path / "a", _plan(rows))
    res, _ = run_check(SPEC.units["plan"].gate, ctx)
    assert res.result == "FAIL", res.evidence
    assert _has_forbidden_fail(res), res.evidence


def test_plan_check_fails_a_docs_row_whose_change_writes_under_claude(tmp_path: Path) -> None:
    # PLN-AC3, AC 1 (b): a `docs` row describing writing under `.claude/` is refused
    rows = _rows(
        "| 1.1 | test | R1 | `tests/test_config.py` | AC 1 | A start with no config file prints one line | |",
        "| 1.2 | test | R2 | `tests/test_config.py` | AC 2 | A start with no config file exits with code 2 | |",
        "| 1.3 | docs | R1 | `README.md` | | Write .claude/rules/x.md with the new rule | |",
    )
    ctx = _setup(tmp_path / "b", _plan(rows))
    res, _ = run_check(SPEC.units["plan"].gate, ctx)
    assert res.result == "FAIL", res.evidence
    assert _has_forbidden_fail(res), res.evidence


def test_plan_check_passes_a_chore_row_whose_change_deletes_a_file(tmp_path: Path) -> None:
    # PLN-AC2, PLN-AC1, AC 1 (c): a `chore` row with the same Change does not raise a forbidden-op finding
    rows = _rows(
        "| 1.1 | test | R1 | `tests/test_config.py` | AC 1 | A start with no config file prints one line | |",
        "| 1.2 | test | R2 | `tests/test_config.py` | AC 2 | A start with no config file exits with code 2 | |",
        "| 1.3 | chore | R1 | `src/old.py` | | Delete src/old.py | |",
    )
    ctx = _setup(tmp_path / "c", _plan(rows))
    res, _ = run_check(SPEC.units["plan"].gate, ctx)
    assert not _has_forbidden_fail(res), res.evidence


def test_plan_check_passes_a_code_row_whose_change_uses_remove_without_a_path(tmp_path: Path) -> None:
    # AC 1 (d): "Remove the duplicate check" does not match the FORBIDDEN_OP pattern (no explicit file path)
    rows = _rows(
        "| 1.1 | test | R1 | `tests/test_config.py` | AC 1 | A start with no config file prints one line | |",
        "| 1.2 | test | R2 | `tests/test_config.py` | AC 2 | A start with no config file exits with code 2 | |",
        "| 1.3 | code | R1, R2 | `src/tool/config.py` | | Remove the duplicate check | |",
    )
    ctx = _setup(tmp_path / "d", _plan(rows))
    res, _ = run_check(SPEC.units["plan"].gate, ctx)
    assert not _has_forbidden_fail(res), res.evidence


def test_forbidden_rows_function_returns_messages_for_non_chore_rows(tmp_path: Path) -> None:
    # PLN-AC2, PLN-AC3, AC 1: direct test of forbidden_rows in specfmt
    plan_delete = fmt.parse_plan(_plan(_rows(
        "| 1.1 | test | R1 | `tests/test_config.py` | AC 1 | A test | |",
        "| 1.2 | code | R1 | `src/tool/config.py` | | Delete src/old.py | |",
    )))
    plan_claude = fmt.parse_plan(_plan(_rows(
        "| 1.1 | test | R1 | `tests/test_config.py` | AC 1 | A test | |",
        "| 1.2 | docs | R1 | `README.md` | | Write .claude/rules/x.md with the new rule | |",
    )))
    plan_chore = fmt.parse_plan(_plan(_rows(
        "| 1.1 | test | R1 | `tests/test_config.py` | AC 1 | A test | |",
        "| 1.2 | chore | R1 | `src/old.py` | | Delete src/old.py | |",
    )))
    plan_remove = fmt.parse_plan(_plan(_rows(
        "| 1.1 | test | R1 | `tests/test_config.py` | AC 1 | A test | |",
        "| 1.2 | code | R1 | `src/tool/config.py` | | Remove the duplicate check | |",
    )))
    assert fmt.forbidden_rows(plan_delete), "Delete src/old.py should trigger a finding"
    assert "1.2" in fmt.forbidden_rows(plan_delete)[0]
    assert fmt.forbidden_rows(plan_claude), "Write .claude/rules/ should trigger a finding"
    assert "1.2" in fmt.forbidden_rows(plan_claude)[0]
    assert fmt.forbidden_rows(plan_chore) == [], "chore rows must not trigger a finding"
    assert fmt.forbidden_rows(plan_remove) == [], "Remove without a path must not trigger a finding"
