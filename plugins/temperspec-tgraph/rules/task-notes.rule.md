---
paths:
  - "**/*.triage.md"
  - "**/*.handoff.md"
  - "**/*.report.md"
  - "**/*.setup.md"
---

# Task notes: the triage note, the hand-off, the code report and the setup note

These notes carry a run from one step to the next. Each step starts with no memory of the others, so what is not in a note or a document does not exist for the next step. They live in `docs/tasks/`, named by the task id.

## Triage note (`<task>.triage.md`)

```markdown
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

## Route

- Deliver: code
- Route: discovery
```

- **Acceptance criteria** are numbered and copied from the task. None is added, none is dropped, none is reworded so that its meaning shifts. A task that states no acceptance criterion ends blocked.
- **Gaps** holds one row per gap, `G<n> <kind>: <concept>. <the search that found nothing>`, or the single word `None`. The kinds: `spec gap` (no spec covers the concept), `spec update` (a spec covers it wrongly or partly), `decision needed`, `research needed`. In doubt, list the gap.
- **Route** has two lines. `Deliver` is `docs` when the task asks only for documents (it says so, or it asks for a spec, a decision record or research and no code), otherwise `code`. `Route` is `plan` when Gaps is `None`; otherwise `discovery`, or `discovery-only` when `Deliver` is `docs`.
- Triage writes this note and nothing else.

## Hand-off (`<task>.handoff.md`)

```markdown
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
```

- **Gaps closed** names, for every gap row of the triage note, the document that closes it. A gap that needs no document says why.
- **Changed documents** lists every document discovery created or edited, with its path in a code span, or `None`.
- **Open questions** lists what only a person can decide, with the options. An open question that blocks planning ends the step blocked.

## Code report (`<task>.report.md`)

```markdown
# Code report: TASK-12

## Rows

| Row | Status | Note |
|---|---|---|
| 1.1 | done | `tests/test_session.py::test_idle_session_refused` |
| 1.2 | done | `src/auth/session.py` |

## Verification

- `pytest tests/test_session.py`: passed, 14 tests

## Deviations

- None
```

- **Rows** has one line per task row of the plan, by the row's id. `Status` is `done` only when the row's change exists in the file the row names; otherwise `open`, with the reason.
- **Verification** reports each command of the plan as the step saw it. These are claims: the gate runs the commands itself.
- **Deviations** lists every place where the code differs from the plan, with the reason, or `None`. The plan itself is not edited by the code step.

## Setup note (`<task>.setup.md`)

Written once, by the run that finds a repository with no overview spec.

```markdown
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
```

- **Components** has one row per spec the setup step wrote, the overview first, each with its path in a code span and the code it describes.
- **Commands** lists the repository's own commands for tests, lint and types, as its README or build files give them, or `None found`.
- **Not covered** lists every part of the code base that got no spec, with the reason, or `None`.
