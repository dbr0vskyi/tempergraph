# Setup: STANDIN-1

## Components

| Component | Spec | Code |
|---|---|---|
| System | `overview.md` | `src/` |
| Config file | `docs/specs/config-file.spec.md` | `src/tool/config.py` |

## Commands

- Tests: `pytest`

## Evidence

| Behaviour | Basis | Code | Test |
|---|---|---|---|
| SYS-B1 | read | `src/tool/main.py:1-6` | - |
| CFG-B1 | tested | `src/tool/config.py:1-80` | `tests/config_cases.py::test_missing_file` |

## Anomalies

- None

## Not covered

- None
