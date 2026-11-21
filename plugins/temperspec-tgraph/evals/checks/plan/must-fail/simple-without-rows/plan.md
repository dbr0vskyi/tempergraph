---
task: STANDIN-1
complexity: simple
status: planned
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
Weight: light


## 3. Verification

- `git --version`

## 4. Docs to update

- `README.md`: say what happens when `tool.toml` is missing
