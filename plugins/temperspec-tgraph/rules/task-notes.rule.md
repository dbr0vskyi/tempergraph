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
```

- **Acceptance criteria** are numbered and copied from the task. None is added, none is dropped, none is reworded so that its meaning shifts. A task that states no acceptance criterion ends blocked.
- **Intent** says what the task is for and where it stops, in the note's own words: `Goal` (the result the person who asked wants, not the change), `In scope`, `Out of scope` (what a reader might expect and the task does not ask for), and `Assumptions`: the single word `None`, or one row `A<n>: <what the note takes as true>. If wrong: <what it costs>` for each thing the task does not say and the note takes as true. The acceptance criteria stay as the task wrote them; a criterion two readers could measure differently gets an uncertainty row, never a rewrite.
- **Uncertainties** holds one row for each question the task leaves open about its own intent, or the single word `None`. A row is `U<n> <category>: <question>. <Impact> <what rests on it>. Route: <route>`.
  - The categories are scanned one by one, so that a kind of question is not forgotten: `goal`, `scope`, `actors` (who or what starts the behaviour), `data` (what is stored, and its state), `names` (a name others depend on: a command, a file, a field), `side effects`, `failures` (errors and edge cases), `limits` (sizes, times, counts), `life cycle` (the first use and the empty state, and what happens when the thing is changed, switched off, removed or upgraded), `dependencies`, `existing behaviour` (what the system does today where the task touches it), `terms` (a word the task uses that the documents do not define).
  - The impact says how much rests on the answer: `Blocks` (no spec can be written without it), `Shapes` (the answer changes which behaviours are written), `Detail` (the plan can settle it).
  - The route says where the answer is looked for: `code`, `docs`, `source` (a public source), `owner` (only the owner can answer; the row then has an entry under `Owner decisions`), or `plan` (a `Detail` row, and only one).
  - A question is written once: a concept that no spec covers is a gap row, and a question about what the task means is an uncertainty row. A `Blocks` or `Shapes` row is answered before the plan: it keeps the run out of `plan` and `quick`, as a gap does.
- **Gaps** holds one row per gap, `G<n> <kind>: <concept>. <the search that found nothing>`, or the single word `None`. The concept is the general capability, and the row names the spec that owns its mechanism (or says that none does yet), so that discovery writes the rule there and not where the task's case happened to show. The kinds: `spec gap` (no spec covers the concept), `spec update` (a spec covers it wrongly or partly), `existing behaviour` (the code the task touches already does it and no spec states it), `decision needed`, `research needed`. Triage finds the owning spec in the capability list the run writes at its start (`.tempergraph/capabilities.md`), and names an existing capability over a near-duplicate. In doubt, list the gap.
- A gap that an existing spec already answers is still listed. Its row ends `Covered by <behaviour id> and <criterion id>`: a behaviour and a criterion that one spec defines once each, the criterion naming the behaviour, both read in the spec. When every gap row says so and no uncertainty row says `Blocks` or `Shapes`, the run takes the short discovery visit; any other note takes the full one.
- **Route** has two lines. `Deliver` is `docs` when the task asks only for documents (it says so, or it asks for a spec, a decision record or research and no code), otherwise `code`. `Route` is `plan` or `quick` when Gaps is `None` and no uncertainty row says `Blocks` or `Shapes`; otherwise `discovery`, or `discovery-only` when `Deliver` is `docs`.

### The quick lane

A small fix goes from triage straight to code, with no discovery and no plan. A note takes `Route: quick` only when all of these hold:

| Condition | Limit |
|---|---|
| Gaps | `None` |
| Uncertainties | no row that says `Blocks` or `Shapes` |
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

### Owner decisions (the conversation setting)

A run's note sorts its gaps and lists its owner decisions under every value of the conversation setting: `never`, `blocking` or `always`. A run on `never` takes each default and never pauses; a run on `blocking` or `always` pauses once, after the reading sessions of discovery, and asks the owner each of the decisions, each with its default, and each `Blocks` question the reading could not answer. The note does two more things:

- Each gap row ends with its sort: `Findable` when the code, the documents or a public source can answer the gap (a row that says `Covered by` is findable with no extra word), or `Owner decision` when only the owner can.
- The section `## Owner decisions` sits between `Gaps` and `Route`. It holds the single word `None`, or one entry for each gap row that ends `Owner decision` and each uncertainty row that ends `Route: owner`, and for no other.

```markdown
## Gaps

- G1 spec gap: idle expiry. Searched `docs/specs/` for "idle", "expiry": nothing. Findable
- G2 decision needed: the idle limit of a session. The task gives no number. Owner decision
- G3 spec update: refusal wording. `docs/specs/session.spec.md` states it. Covered by SES-B1 and SES-AC1

## Owner decisions

- G2: How long may a session be idle before a request is refused?
  - Options: a) 30 minutes; b) 15 minutes; c) 60 minutes
  - Default: a
  - If wrong: clients idle for longer than the real limit are signed out too early or too late
```

- An entry is `- G<n>: <question>` (or `- U<n>: <question>` for an uncertainty row) with three items under it: `Options:` (two to four options, each labelled `a)`, `b)`, … and separated by `;`), `Default:` (the label of one of the options) and `If wrong:` (what it costs if the default is wrong). The default is the option that changes the least of what exists and is cheapest to undo.
- The triage check fails a note that leaves a gap row unsorted, has no `Owner decisions` section, has an owner-decision row with no entry or an entry for a row that does not go to the owner, or has an entry with no question, fewer than two or more than four options, no default, a default that is not one of its options, or no cost.
- Triage still ends blocked on a task that states no acceptance criterion: nothing in it can take a default.

## Hand-off (`<task>.handoff.md`)

```markdown
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
```

- **Gaps closed** names, for every gap row of the triage note, the document that closes it. A gap that needs no document says why.
- **Uncertainties closed** has one line for each uncertainty row of the triage note that says `Blocks` or `Shapes`, led by its id, and says how the question ended: `Answered:` with what was read and where (path and lines, or a document's id), `Owner:` with the owner's answer, or `Assumed:` with the assumption taken and `If wrong:` with what it costs. No such row may be left without an end. Write the section only when the note has such a row.
- **Left to the plan** lists what discovery saw and did not write a behaviour for, one line each: every `Detail` row of the note, and each case the last look over the task found (a failure, a limit, an actor, an empty or first-time state, a removal or an upgrade) that no criterion of the task asks for. The plan settles each line or says why not. Discovery never writes a behaviour only because this look found a case. Write the section only when there is a line.
- **Reach** lists the code outside the files the task names that calls, reads or is called by what the task changes, each as an existing file in a code span with its lines and one line on how it is tied, as a reading session or discovery read it. It is a list of leads for the plan, not a claim that each file changes. Write the section only when there is one.
- After a short discovery visit (every gap row of the triage note says `Covered by`), **Gaps closed** names, for every gap row, the cited behaviour id and how it answers the gap, or the id and `Not covered:` with what it leaves out; **Changed documents** is `- None`, and the reading list holds at most 10 items. A `Not covered` line sends the run to the full discovery.
- **Changed documents** lists every document discovery created or edited, with its path in a code span, or `None`.
- **Inferred behaviours** lists each behaviour discovery wrote that neither the task's criteria nor the owner's answers ask for, with where it came from: `read` or `tested` in the code (path and lines), a research note, or a neighbouring spec (its id). Write the section only when there is one. The spec states the rule; its source stays here, so the judge and the owner see which rules were inferred.
- An `existing behaviour` gap is closed by extracting that capability's rules from the code, as `extraction.rule.md` says, into the spec that owns it, before the task's change is written; each extracted behaviour is an inferred behaviour.
- **Open questions** lists what only a person can decide, with the options. An open question that blocks planning ends the step blocked. Under the conversation setting `never` no step ends blocked on one: each open question carries the default the step took, written `Until answered: <option>`, and the pull request lists it with that default. Under `blocking` and `always` a step ends blocked on a question that blocks planning and the triage note does not list; an owner decision the triage note lists is closed on its answer or its default and is never an open question.
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

## Evidence

| Behaviour | Basis | Code | Test |
|---|---|---|---|
| SES-B1 | tested | `src/auth/session.py:10-60` | `tests/test_session.py::test_idle_session_refused` |
| SES-B2 | read | `src/auth/session.py:62-80` | - |

## Anomalies

- `src/auth/session.py:90-95`: a refresh resets the idle time only for some clients; no test pins it, so no behaviour states it

## Not covered

- `scripts/`: one-off maintenance scripts, no behaviour anyone depends on
```

- **Components** has one row per spec the setup step wrote, the overview first, each with its path in a code span and the code it describes.
- **Commands** lists the repository's own commands for tests, lint and types, as its README or build files give them, or `None found`.
- **Evidence** has one row per behaviour of every spec the setup step wrote: its id, its basis (`tested` when a test asserts it, `read` when the code was read on its whole path; `extraction.rule.md`), the code as `` `<path>:<from>-<to>` `` and, for `tested`, the test in a code span. The setup check confirms each row's files exist and its lines are inside them.
- **Anomalies** lists suspected bugs and rules only a name, comment or document states, each with its path and lines, or `None`. None of them is a behaviour; each is a candidate issue for the owner.
- **Not covered** lists every part of the code base that got no spec, with the reason, or `None`. A part read only in part (the extraction budget) is listed as partly covered.
