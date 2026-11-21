---
paths:
  - "**/*.plan.md"
---

# Plan

A plan turns the task's acceptance criteria and the specs into requirements, phases and task rows that a coding session can follow without designing anything.

## Structure

The example below is also installed as the fill-in template `docs/templates/plan.template.md`, generated from this file. Change this rule, never the template.

```markdown
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
```

## Front matter

- `task`: the run's task id.
- `complexity`: `simple` or `complex` (see Complexity).
- `status`: `planned` when the plan and expand steps write it, `in-progress` while the code step works, `completed` when every row is marked (see Status and marks).
- `specs`: the spec files the plan implements or depends on.

A plan is a working document for one task, not a spec: it carries its status and the completion marks of its rows, which no other document does.

## Requirements

- Every numbered acceptance criterion of the triage note appears in the `Criteria` cell of at least one requirement, written `AC <n>`.
- A requirement's id is `R<n>`. Every requirement is named by at least one task row.
- A requirement follows from a behaviour or a criterion. A plan never adds behaviour that no spec states: if a spec is missing or has an open question the plan needs, the plan is not written and the defect is reported against discovery.

## Phases and task rows

- A phase is one unit of work with one goal. Its heading is `### Phase <n>: <name>`, followed by a `Goal:` line and a `Weight:` line.
- A task row is one logical change in one exact file. Columns: `Row` (an id unique in the plan, such as `1.2`), `Kind` (`test`, `code`, `docs` or `chore`), `Req` (the requirement ids it serves, such as `R1` or `R1, R3`), `File`, `Proves`, `Change`, `Completed` (empty until the code step marks it).
- Every row names at least one requirement of the plan, and names none that the plan does not have.
- A `Change` cell says the whole change. Words that cut it down (a stub, a placeholder, "for now", a later task) are read by the plan judge: cut scope only when the task says so, and then say why in the hand-off.
- Before writing a row that changes a type, a signature or the order of fields, search the tests for code that pins it (constructs it by position, compares its fields, checks its signature). Each test it would break gets a row; if none, say so in the row's Change cell.
- Test first: in every phase, a `code` row comes after a `test` row of that phase. A `test` row names in `Proves` the acceptance criterion it proves: the spec's id (`SES-AC1`), or `AC <n>` of the task when no spec criterion fits.
- A plan of complexity `simple` carries its task rows. A plan of complexity `complex` is written with phases, goals and weights only; the expand step adds the rows and the proof table without changing sections 0, 1 and 4 or any goal.
- Write a plan in parts: first every section with the phase headings, goals and weights and no rows, then one edit per phase that adds its table. No single write is over about 12 KB. A response that runs too long is cut off and retried for a long time.

## Complexity

The plan states its complexity and the gate measures it. A plan is `complex` when any of these holds, and `simple` otherwise:

| Sign | Limit for `simple` |
|---|---|
| Phases | at most 3 |
| Task rows | at most 12 |
| Test rows | at most 6 |
| Files named by rows | at most 10 |
| Verification commands | at most 3 |
| Bytes of the files and specs the rows name | at most 200,000 |
| A heavy phase | none |

A phase is heavy when it is much heavier than the others. Mark it `Weight: heavy (<sign>)` with one of these signs: `refactor` (restructures code that other rows depend on), `many-tests` (a large number of tests), `large-context` (needs a large reading set), `long-running` (a command that runs for many minutes).

## Verification

- One list item per command, in a code span. Each is a single plain command that runs from the repository root: no pipe, no redirection, no absolute path. A command that must run in a sub-folder is written `cd <folder> && <command>`; no other chain is allowed.
- The commands are the ones the repository documents for its tests, lint and types.
- Never `git push` and never `gh`: only the last stage publishes.
- **The proof table** follows the commands. It has one row for each numbered acceptance criterion of the triage note: `Criterion` (`AC <n>`), `Test` (the file of a `test` row of the plan) and `Command` (one of the commands listed above, the one that runs that test). It fixes what "done" means before any code exists: the gate runs the command, and checks that a test in the file carries the criterion and is not skipped. A `simple` plan carries the table; for a `complex` plan the expand step writes it.
- A test carries its criterion in its name or in a comment on it: the spec's id (`SES-AC1`), or `AC <n>` of the task when no spec criterion fits. A test that carries a criterion is never skipped.

## Docs to update

Every document the change will make false, with the reason, or `None`. Each document listed here is the file of a `docs` row.

## Status and marks

- The plan and expand steps leave the status `planned` and every `Completed` cell empty.
- The code step sets the status to `in-progress` when it starts. When a row's change is in its file and the phase's tests pass, it writes `✓ <date>` in that row's `Completed` cell, with the date of that day as `YYYY-MM-DD` (`✓ 2026-11-21`). When every row is marked, it sets the status to `completed`.
- A mark is a claim. The code gate first checks that every row is marked and the plan is `completed`, and sends the run back to the code step at once when not, without running anything. A marked plan is then verified as if it had no marks: the file of each marked row must have changed in the run, the verification commands are run, and each criterion's test is read.
- The code step changes nothing else in the plan. A row it could not do stays unmarked, and the code report says why.
