# Hand-off: TASK-12

## Problem

Two or three sentences.

## Gaps closed

- G1: `docs/specs/session-expiry.spec.md` (SES-B1, SES-B2)

## Changed documents

- `docs/specs/session-expiry.spec.md`: new

## Decisions

- Idle time is measured from the last served request (stated by the task)

## Open questions

- None

## Reading list

- `docs/specs/session-expiry.spec.md` (SES-B1, SES-B2): the behaviours the plan implements
- `src/auth/session.py` (lines 10-60): where the idle time is read
