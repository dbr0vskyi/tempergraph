---
task: STANDIN-1
complexity: complex
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

### Phase 1: Restructure config loading

Goal: restructure config loading is in place.
Weight: heavy (refactor)

### Phase 2: Missing file message

Goal: missing file message is in place.
Weight: light

### Phase 3: Exit code

Goal: exit code is in place.
Weight: light

### Phase 4: Docs

Goal: docs is in place.
Weight: light


## 3. Verification

- `git --version`

## 4. Docs to update

- `README.md`: say what happens when `tool.toml` is missing
