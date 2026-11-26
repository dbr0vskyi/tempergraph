# Hand-off: TASK-12

## Problem

Two or three sentences.

## Gaps closed

- G1: `docs/specs/session-expiry.spec.md` (SES-B1, SES-B2)

## Uncertainties closed

- U1: Answered: a refresh is served by the same handler, so it counts (`src/auth/session.py`, lines 40-52)

## Changed documents

- `docs/specs/session-expiry.spec.md`: new

## Decisions

- Idle time is measured from the last served request (stated by the task)

## Inferred behaviours

- SES-B2: read in `src/auth/session.py` (lines 40-52); the task asks only for SES-B1

## Open questions

- None

## Left to the plan

- The wording a refused client sees (U2)

## Reach

- `src/auth/middleware.py` (lines 12-30): calls the session check on every request

## Reading list

- `docs/specs/session-expiry.spec.md` (SES-B1, SES-B2): the behaviours the plan implements
- `src/auth/session.py` (lines 10-60): where the idle time is read
