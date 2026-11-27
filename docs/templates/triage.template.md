# Triage: TASK-12

## Task

Source and a one-line summary.

## Acceptance criteria

1. A request on a session idle for more than 30 minutes is refused
2. ...

## Intent

- Goal: a session left open on a shared machine stops being usable
- In scope: refusing requests on an idle session
- Out of scope: a limit on the whole life of a session; signing the user out on other devices
- Assumptions:
  - A1: idle time counts from the last request the server answered. If wrong: the limit is measured from another moment and SES-B1 is rewritten

## Existing documents

- `docs/specs/session.spec.md`: covers sign-in, says nothing about idle time

## Uncertainties

- U1 existing behaviour: does a refresh of the token count as a request? Shapes how idle time is measured. Route: code
- U2 failures: what does a client see when it is refused? Detail of the refusal. Route: plan

## Gaps

- G1 spec gap: idle expiry. Searched `docs/specs/` for "idle", "expiry", "timeout": nothing
- G2 spec update: refusal wording. `docs/specs/session.spec.md` states it. Covered by SES-B1 and SES-AC1

## Route

- Deliver: code
- Route: discovery
