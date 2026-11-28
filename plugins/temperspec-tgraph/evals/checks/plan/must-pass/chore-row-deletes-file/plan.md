---
task: STANDIN-1
complexity: simple
status: planned
specs: []
---

# Plan: remove src/old.py

## 0. Hand-off

- Triage note: `triage_note.md`
- Why this design: a chore row handles the file deletion; a test row in the first phase proves the outcome.

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | src/old.py is absent after the run | |

## 2. Phases

### Phase 1: Verify the deletion

Goal: a test proves src/old.py is absent.
Weight: light

| Row | Kind | Req | File | Proves | Change | Completed |
|---|---|---|---|---|---|---|
| 1.1 | test | R1 | `tests/test_config.py` | AC 1 | A test asserting src/old.py is absent | |
| 1.2 | code | R1 | `src/config.py` | | Update the config file to drop the reference to src/old.py | |

### Phase 2: Delete the file

Goal: src/old.py is absent in the committed result.
Weight: light

| Row | Kind | Req | File | Proves | Change | Completed |
|---|---|---|---|---|---|---|
| 2.1 | chore | R1 | `src/old.py` | | Delete src/old.py | |

## 3. Verification

- `git --version`

| Criterion | Test | Command |
|---|---|---|
| AC 1 | `tests/test_config.py` | `git --version` |

## 4. Docs to update

- None
