---
task: TASK-7
complexity: complex
status: in-progress
specs: []
---

# Plan: report a missing config file

## 0. Hand-off

- Triage note: `docs/tasks/TASK-7.triage.md`
- Why this design: the file is read in one place, so the message belongs there.

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | One line on standard error names the missing file | |

## 2. Phases

### Phase 1: Missing file message

Goal: a missing file is named on standard error.
Weight: light

| Row | Kind | Req | File | Proves | Change | Completed |
|---|---|---|---|---|---|---|
| 1.1 | test | R1 | `tests/test_config.py` | AC 1 | Assert that one line on standard error names the missing file | ✓ 2026-11-25 |
| 1.2 | code | R1 | `src/tool/config.py` | | Print one line naming the missing file to standard error | ✓ 2026-11-25 |

## 3. Verification

- `python -m pytest tests/test_config.py`

| Criterion | Test | Command |
|---|---|---|
| AC 1 | `tests/test_config.py` | `python -m pytest tests/test_config.py` |

## 4. Docs to update

- None
