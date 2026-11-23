---
task: TASK-12
complexity: simple
status: planned
specs: [docs/specs/session-expiry.spec.md]
---

# Plan: <goal in a few words>

## 0. Hand-off

- Triage note: `docs/tasks/TASK-12.triage.md`
- Specs read: `docs/specs/session-expiry.spec.md`
- Why this design: two or three sentences.

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | Idle sessions end after 30 minutes | SES-B1, SES-AC1 |

## 2. Phases

### Phase 1: Session expiry

Goal: a request on an idle session is refused.
Weight: light

| Row | Kind | Req | File | Proves | Change | Completed |
|---|---|---|---|---|---|---|
| 1.1 | test | R1 | `tests/test_session.py` | SES-AC1 | A request after 31 idle minutes is refused | |
| 1.2 | code | R1 | `src/auth/session.py` | | End a session idle for 30 minutes | |

## 3. Verification

- `pytest tests/test_session.py`

| Criterion | Test | Command |
|---|---|---|
| AC 1 | `tests/test_session.py` | `pytest tests/test_session.py` |

## 4. Docs to update

- None
