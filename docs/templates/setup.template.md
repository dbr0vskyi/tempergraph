# Setup: TASK-12

## Components

| Component | Spec | Code |
|---|---|---|
| System | `docs/specs/overview.spec.md` | `src/` |
| Sessions | `docs/specs/session.spec.md` | `src/auth/session.py` |

## Commands

- Tests: `pytest`
- Lint: `ruff check src tests`

## Not covered

- `scripts/`: one-off maintenance scripts, no behaviour anyone depends on
