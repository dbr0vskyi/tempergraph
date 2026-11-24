# Triage: TASK-12

## Task

Source and a one-line summary.

## Acceptance criteria

1. A request on a session idle for more than 30 minutes is refused
2. ...

## Existing documents

- `docs/specs/session.spec.md`: covers sign-in, says nothing about idle time

## Gaps

- G1 spec gap: idle expiry. Searched `docs/specs/` for "idle", "expiry", "timeout": nothing
- G2 spec update: refusal wording. `docs/specs/session.spec.md` states it. Covered by SES-B1 and SES-AC1

## Route

- Deliver: code
- Route: discovery
