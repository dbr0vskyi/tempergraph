---
task: TASK-7
complexity: complex
specs: [docs/specs/config-file.spec.md, docs/specs/cli.spec.md]
---

# Plan: report a missing config file

## 0. Hand-off

- Triage note: `docs/tasks/TASK-7.triage.md`
- Hand-off: `docs/tasks/TASK-7.handoff.md`
- Specs read: `docs/specs/config-file.spec.md`, `docs/specs/cli.spec.md`
- Why this design: the settings are read in one place, so the check for the file and its message belong there; the entry point only turns the result into the exit code.

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | Exactly one line on standard error names the missing file | CFG-B1, CFG-AC1 |
| R2 | AC 2 | The run ends with exit code 2 when `tool.toml` is missing | CFG-B2, CFG-AC2 |
| R3 | AC 1, AC 2 | `--version` keeps working in a folder with no config file | CLI-B1 |

## 2. Phases

### Phase 1: Settings reader

Goal: the settings are read in one module that other code calls.
Weight: heavy (refactor)

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 1.1 | test | `tests/test_config.py` | CFG-AC1 | A start with no config file prints exactly one line that names it |
| 1.2 | code | `src/tool/config.py` | | Move reading `tool.toml` out of the entry point; report a missing file on standard error |

### Phase 2: Exit code

Goal: a start with no `tool.toml` exits with code 2, and `--version` still answers.
Weight: light

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 2.1 | test | `tests/test_config.py` | CFG-AC2 | A start with no config file exits with code 2 |
| 2.2 | code | `src/tool/main.py` | | Use the settings reader; return exit code 2 when the file is missing |
| 2.3 | code | `src/tool/color.py` | | Print the message in red when the terminal supports colour |

### Phase 3: Docs

Goal: the README says what happens when the file is missing.
Weight: light

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 3.1 | docs | `README.md` | | Say what happens when `tool.toml` is missing |

## 3. Verification

- `pytest tests/test_config.py`
- `ruff check src tests`

## 4. Docs to update

- `README.md`: it names `tool.toml` and must say what happens when the file is missing
