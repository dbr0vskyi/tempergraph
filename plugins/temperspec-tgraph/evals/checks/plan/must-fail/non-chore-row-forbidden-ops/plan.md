---
task: STANDIN-1
complexity: simple
status: planned
specs: []
---

# Plan: clean up an old file and add a rule

## 0. Hand-off

- Triage note: `triage_note.md`
- Why this design: the deletion and the rule update are done in the same phase.

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | src/old.py is absent after the run | |
| R2 | AC 2 | .claude/rules/x.md contains the new rule | |

## 2. Phases

### Phase 1: Update files

Goal: src/old.py is absent and the rule file is in place.
Weight: light

| Row | Kind | Req | File | Proves | Change | Completed |
|---|---|---|---|---|---|---|
| 1.1 | test | R1, R2 | `tests/test_config.py` | AC 1, AC 2 | A test for the absence of src/old.py and the presence of the rule | |
| 1.2 | code | R1 | `src/old.py` | | Delete src/old.py | |
| 1.3 | docs | R2 | `README.md` | | Write .claude/rules/x.md with the new rule | |

## 3. Verification

- `git --version`

| Criterion | Test | Command |
|---|---|---|
| AC 1 | `tests/test_config.py` | `git --version` |
| AC 2 | `tests/test_config.py` | `git --version` |

## 4. Docs to update

- None
