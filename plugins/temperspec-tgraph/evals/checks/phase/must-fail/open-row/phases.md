---
task: STANDIN-1
complexity: complex
status: in-progress
specs: []
---

# Plan: report a missing config file

## 0. Hand-off

- Triage note: `triage_note.md`
- Why this design: the file is read in one place, so the check and the message belong there.

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | One line on standard error names the missing file | |

## 2. Phases

### Phase 1: Missing file message

Goal: missing file message is in place.
Weight: light

| Row | Kind | Req | File | Proves | Change | Completed |
|---|---|---|---|---|---|---|
| 1.1 | test | R1 | `tests/test_config.py` | AC 1 | The phase's result is asserted | ✓ 2026-11-21 |
| 1.2 | code | R1 | `src/tool/config.py` | | The phase's change | |

## 3. Verification

- `git --version`

| Criterion | Test | Command |
|---|---|---|
| AC 1 | `tests/test_config.py` | `git --version` |

## 4. Docs to update

- None
