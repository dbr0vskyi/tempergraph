---
paths:
  - "**/*.triage.md"
  - "**/*.handoff.md"
  - "**/*.report.md"
  - "**/*.setup.md"
---

# Task notes: the triage note, the hand-off, the code report and the setup note

These notes carry a run from one step to the next. Each step starts with no memory of the others, so what is not in a note or a document does not exist for the next step. They live in `docs/tasks/`, named by the task id. Each example below is also installed as a fill-in template in `docs/templates/` (`triage.template.md`, `hand-off.template.md`, `code-report.template.md`, `setup.template.md`), generated from this file. Change this rule, never a template.

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
- G2 spec update: refusal wording. `docs/specs/session.spec.md` states it. Covered by SES-B1 and SES-AC1

## Route

- Deliver: code
- Route: discovery
```

- **Acceptance criteria** are numbered and copied from the task. None is added, none is dropped, none is reworded so that its meaning shifts. A task that states no acceptance criterion ends blocked.
- **Gaps** holds one row per gap, `G<n> <kind>: <concept>. <the search that found nothing>`, or the single word `None`. The kinds: `spec gap` (no spec covers the concept), `spec update` (a spec covers it wrongly or partly), `decision needed`, `research needed`. In doubt, list the gap.
- A gap that an existing spec already answers is still listed. Its row ends `Covered by <behaviour id> and <criterion id>`: a behaviour and a criterion that one spec defines once each, the criterion naming the behaviour, both read in the spec. When every gap row says so, the run takes the short discovery visit; any other gap takes the full one.
- **Route** has two lines. `Deliver` is `docs` when the task asks only for documents (it says so, or it asks for a spec, a decision record or research and no code), otherwise `code`. `Route` is `plan` or `quick` when Gaps is `None`; otherwise `discovery`, or `discovery-only` when `Deliver` is `docs`.

### The quick lane

A small fix goes from triage straight to code, with no discovery and no plan. A note takes `Route: quick` only when all of these hold:

| Condition | Limit |
|---|---|
| Gaps | `None` |
| Deliver | `code` |
| Behaviours and acceptance criteria of specs that must change | none. A bug where the code disagrees with a spec qualifies: the spec is already right |
| Acceptance criteria of the task | at most 3 |
| Code files to change, beside their tests | at most 2 |

A quick note ends with a Change section, which is the plan of the code step:

```markdown
## Route

- Deliver: code
- Route: quick

## Change

- Files: `src/auth/session.py`
- Tests: `tests/test_session.py`
- Verify: `pytest tests/test_session.py`
```

- `Files` names the code files, `Tests` the test files, `Verify` the commands that run those tests, each in a code span. A command follows the plan rule's Verification section.
- The code gate measures the change afterwards. A spec or decision record changed, a code file changed that `Files` does not name, more than 2 code files, or more than 200 changed lines sends the run back to triage, which then routes it to `plan`. A run that came back to triage never takes `quick` again.
- Each acceptance criterion is one row of the code report, with the id `AC <n>`, and is carried by a test in one of the `Tests` files.
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

## Reading list

- `docs/specs/session-expiry.spec.md` (SES-B1, SES-B2): the behaviours the plan implements
- `src/auth/session.py` (lines 10-60): where the idle time is read
```

- **Gaps closed** names, for every gap row of the triage note, the document that closes it. A gap that needs no document says why.
- After a short discovery visit (every gap row of the triage note says `Covered by`), **Gaps closed** names, for every gap row, the cited behaviour id and how it answers the gap, or the id and `Not covered:` with what it leaves out; **Changed documents** is `- None`, and the reading list holds at most 10 items. A `Not covered` line sends the run to the full discovery.
- **Changed documents** lists every document discovery created or edited, with its path in a code span, or `None`.
- **Open questions** lists what only a person can decide, with the options. An open question that blocks planning ends the step blocked.
- **Reading list** has one item for each file the plan will need: an existing file in a code span, the line ranges or ids that matter in brackets, a colon and one line on why. A hand-off with none is a finding, except in a run that ends after discovery. The plan starts from this list and opens another file only for what the list does not answer.

## Code report (`<task>.report.md`)

```markdown
# Code report: TASK-12

## Verification

- `pytest tests/test_session.py`: passed, 14 tests

## Deviations

- None
```

- A row's progress is marked in the plan, not here (`plan.rule.md`, Status and marks).
- **Rows** comes first, and only in the quick lane, where there is no plan to mark: one line per acceptance criterion, with the id `AC <n>`.

  ```markdown
  ## Rows

  | Row | Status | Note |
  |---|---|---|
  | AC 1 | done | `tests/test_session.py::test_idle_session_refused` |
  ```

  `Status` is `done` only when the change exists in the file the note's Change section names; otherwise `open`, with the reason.
- **Verification** reports each command of the plan as the step saw it. These are claims: the gate runs the commands itself.
- **Deviations** lists every place where the code differs from the plan, with the reason, or `None`, and every row left unmarked with the reason. The code step edits the plan only to mark rows and set its status.

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
