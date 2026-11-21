---
task: STANDIN-1
complexity: simple
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
| R2 | AC 2 | The run ends with exit code 2 when the file is missing | |

## 2. Phases

### Phase 1: Missing config file

Goal: a start with no `tool.toml` prints one line and exits with code 2.
Weight: heavy (refactor)

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 1.1 | test | `tests/test_config.py` | AC 1 | A start with no config file prints one line that names it |
| 1.2 | test | `tests/test_config.py` | AC 2 | A start with no config file exits with code 2 |
| 1.3 | code | `src/tool/config.py` | | Report the missing file and exit with code 2 |
| 1.4 | docs | `README.md` | | Describe the missing-file message |

## 3. Verification

- `git --version`

## 4. Docs to update

- `README.md`: say what happens when `tool.toml` is missing
