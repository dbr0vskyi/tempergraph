# The owner is asked once, after the reading sessions

## Context

A run on the conversation value `blocking` or `always` makes one pause for the owner. The pause came straight after triage, so the owner was asked before anything had looked in the code for an answer. The triage note now lists what the task leaves open as uncertainty rows, some of which the repository may answer, and the place of the pause decides whether the owner is asked those.

## Current state

- The one pause and its questions are the behaviours of [owner questions](../specs/owner-questions.spec.md) (OWQ-B1 to OWQ-B11).
- Triage reads the task, the capability list and the documents; it reads code only far enough to tell whether an `existing behaviour` gap exists (`prompts/triage.md`, step 6).
- An uncertainty row carries an impact (`Blocks`, `Shapes`, `Detail`) and a route (`code`, `docs`, `source`, `owner`, `plan`) ([the task-notes rule](../../rules/task-notes.rule.md)).
- The reading sessions are read-only, run three at a time, write one findings line each, and are briefed with one row of the triage note and none of the owner's answers (`workflow/temperspec/__init__.py`, the unit `read_gap`; [parallel reading](../specs/parallel-reading.spec.md)).
- A script unit is given the values of earlier units, the findings of a map's items among them (`plugins/tempergraph/engine/src/tempergraph/run/nodes.py`, `_run_script`).
- 58 triage notes of this repository hold 3 owner-decision rows ([spec, decision and discovery formats](../research/spec-decision-and-discovery-formats.rsrch.md), F6).

## Forces

- C1 (constraint): a run pauses for the owner at most once. Source: OWQ-B1 of [owner questions](../specs/owner-questions.spec.md)
- F1: the owner is not asked what the code or the documents answer
- F2: a question that blocks the change and that no file answers reaches the owner in the pause, not as a blocked run later
- F3: a wrong task is stopped before sessions are paid for
- F4: the owner sees the pause soon after starting the run

## Options considered

### A. Pause after the reading sessions

How it works: triage routes a run with a gap or a working uncertainty row to `read_gap`. The script `owner_questions` runs after the map and reads the findings; `ask_route` sends a run with a question to `ask_owner` and any other to `discovery`.
For: nothing is asked that a reading session answered (F1); a `Blocks` row reported `Not answered` becomes a question of the same pause (F2). Against: the reading sessions are paid for before the owner can stop a wrong task (F3); the pause appears later (F4).

### B. Keep the pause after triage

How it works: `owner_questions` and `ask_owner` stay before `read_gap`.
For: a wrong task is stopped before any reading (F3); the pause appears at once (F4). Against: the owner is asked before anyone has looked (F1); a question the code does not answer is found by the writing session, which ends blocked, a second stop (F2).

### C. Two pauses, one after triage and one after reading

How it works: the owner decisions are asked after triage and the unanswered questions after reading, through a second ask unit.
Against: breaks C1.

## Decision

We will take option A: the order of the units is `read_gap`, `owner_questions`, `ask_route`, `ask_owner`, `discovery`, and the list of questions holds the owner decisions of the triage note and one question in words for each `Blocks` row whose reading session reported `Not answered`.

## Decision rationale

- C1: met. There is one ask unit and one pause.
- F1: met. A row routed to the code or the documents is read first, and only a `Not answered` finding is asked.
- F2: met. The unanswered blocking question is in the pause, with the reading that changes the least as its default at the deadline.
- F3: given up. The reading sessions are at most three `medium` read-only sessions at a time, the cheapest sessions of the run, and the owner can still stop the run at the pause before the writing session, the costliest step of discovery.
- F4: given up. A pause is rare (3 owner-decision rows in 58 notes), and the wait is one round of reading sessions.

## Consequences

A run that pauses has read its rows first. A `Blocks` row routed to the code that no file answers no longer blocks the writing session on `blocking`: the owner answers it in the pause, or the deadline takes the reading that changes the least. A row read by no reading session (a note with fewer than two rows to read) is still read by the writing session, which ends blocked on it as before. A run on `always` that calls a reading `wrong` has already paid for the reading sessions.

## Risks

- A reading session reports `Answered:` wrongly, so a question is hidden from the owner. Limited by: the reading judge opens the file behind each `Answered:`, and the writing session confirms each finding in its file before a document rests on it. Noticed by: an `Assumed:` or a corrected `Answered:` line for that row in the hand-off's `Uncertainties closed`, or the owner correcting the pull request.

## Assumptions

- A1: reading sessions answer more questions than owners would have stopped runs for. Check: count, over live runs, the rows reported `Answered:` against the pauses at which the owner stopped the run. If wrong: reading is paid for on tasks that are then corrected, and option B is cheaper.

## Revisit when

Live runs show more pauses at which the owner stopped the run for a wrong task than uncertainty rows a reading session reported `Answered:`.
