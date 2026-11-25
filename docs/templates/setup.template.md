# Setup: TASK-12

## Components

| Component | Spec | Code |
|---|---|---|
| System | `docs/specs/overview.spec.md` | `src/` |
| Sessions | `docs/specs/session.spec.md` | `src/auth/session.py` |

## Commands

- Tests: `pytest`
- Lint: `ruff check src tests`

## Evidence

| Behaviour | Basis | Code | Test |
|---|---|---|---|
| SES-B1 | tested | `src/auth/session.py:10-60` | `tests/test_session.py::test_idle_session_refused` |
| SES-B2 | read | `src/auth/session.py:62-80` | - |

## Anomalies

- `src/auth/session.py:90-95`: a refresh resets the idle time only for some clients; no test pins it, so no behaviour states it

## Not covered

- `scripts/`: one-off maintenance scripts, no behaviour anyone depends on
