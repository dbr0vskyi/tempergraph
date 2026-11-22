# Ask unit

## Purpose

An ask unit pauses a run to take input from a person and stores the answers as an artifact later steps read ([ADR-0065](../adr/0065-ask-unit-takes-a-persons-input-as-an-artifact.adr.md), [ADR-0062](../adr/0062-new-node-kinds-keep-the-gated-unit.adr.md)). It is LangGraph's `interrupt()` for human input, in this engine's form: the pause is in the unit's human node, the answers are validated by rule, and there is no model and no judge, since the person's input is the bar ([R-060](../research/R-060-node-types-against-langgraph.rsrch.md) L11). Questions are declared, or taken from a list an earlier step wrote, such as a discovery step's open questions. An ask differs from an approval (a decision on work) and from a wait (a value from an outside system, checked): its answers are data for later steps. No executor is involved, so it behaves the same on every executor. Workflow authors and people answering runs depend on it; design and build notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### ASK-B5 Declaration

WHEN a unit of kind `ask` is declared THE engine SHALL read its `ask` field ([CON-B4](01-contracts.spec.md)) as `AskSpec` with exactly one of `questions` (1 to 20 `Question`) and `from` (`questions_from` in Python: an artifact key of a list in the `Question` shape, JSON or a Markdown list with one `name: question` per item); `context` (artifact keys shown with the questions, by pointer); `check` (a pure callable `check(answers)` returning nothing, `True`, `False` or a list of problems); and `deadline_s` and `on_deadline` ([FLX-B8](74-flow-extensions.spec.md)); each `Question` having a slug `name` (its key in the answers), `text` (a template of at most 500 characters), `kind` (`text`, `choice`, `choices` allowing several, `number`, `bool`, `file` or `url`), `choices` (slugs, for `choice` and `choices`), `required` (default true) and an optional `default` used when the person leaves it out.

- GIVEN an ask with both `questions` and `from` WHEN validated THEN it is refused

### ASK-B6 The answers artifact

WHEN an ask's answer set is complete THE engine SHALL write it to `runs/<workflow>/<thread>/answers/<unit>.json`, which becomes the unit's one artifact `answers` (kind `file`), read by a later step as a judge reference, a prompt input or step values like any artifact, the gate holding only the built-in answer check and the author's `check`.

- GIVEN a complete set WHEN the unit ends THEN `answers` points at the answers file

### ASK-B7 Placement

WHEN a workflow places an ask THE engine SHALL allow it on the main chain or inside a sub-workflow child (the child's pause is the parent's) and refuse it as a parallel branch, a map item, a contest slot or a council member.

- GIVEN an ask as a map item WHEN validated THEN it is refused

### ASK-B8 Answering

WHEN a person resumes a paused ask THE engine SHALL take `answer:<name>=<value>` decisions (repeatable, [CON-B12](01-contracts.spec.md)) and `--answers <file>` (a JSON or YAML map), each validated by kind; accept `proceed` only when every required answer has a value or a default; end the run with exit 4 on `stop`; keep the answers each accepted resume set and stay paused until the set is complete and the check passes, a complete set that passes continuing without `proceed`; show in the pause payload ([HUM](07-gate-and-human.spec.md), kind `input`) each question with its kind, choices, default and whether it is answered, and the exact resume command; and record who answered in the intervention row (`person` or `agent`, [HUM-B6](07-gate-and-human.spec.md)).

- GIVEN a partial answer, a crash and a resume WHEN the ask is read THEN the answers already accepted are kept

### ASK-B1 Typed answers

WHEN a resume sends an answer its kind refuses THE engine SHALL exit 2 naming what is allowed, write nothing and stay paused.

- GIVEN `env` of kind `choice` (`staging`, `prod`) and `ticket` of kind `text` WHEN a resume sends `answer:env=dev` THEN it exits 2 naming the choices and the run stays paused
- GIVEN `answer:env=staging` WHEN resumed THEN it is stored and the run stays paused for `ticket`
- GIVEN `answer:ticket=PRJ-12` then `proceed` WHEN resumed THEN it is stored, the check runs and the run continues
- GIVEN `proceed` with `ticket` missing and no default WHEN resumed THEN it exits 2 and stays paused
- GIVEN `stop` WHEN resumed THEN it exits 4

### ASK-B2 Questions from a step

WHEN an ask with `from` is entered THE engine SHALL validate the list against the `Question` shape and stop the unit before the pause with a finding naming the item on a malformed list or more than 20 questions, as for a bad map list, and stop it with run exit 4 naming the key when the artifact is missing.

- GIVEN a discovery step that produced `open_questions` and `from: open_questions` WHEN entered THEN the list is validated before the pause

### ASK-B9 A file answer outside the workspace

WHEN a `file` answer names a path outside the workspace THE engine SHALL exit 2 (contract C10) and write nothing.

- GIVEN `answer:spec=/etc/passwd` for a `file` question WHEN resumed THEN it exits 2

### ASK-B3 Answers reach later steps

WHEN a later step's prompt names `{answers}` and its judge references `answers` THE engine SHALL give the step the answers file and the judge grade against it.

- GIVEN a plan step naming `{answers}` WHEN it runs THEN the step reads the answers file and its judge grades against it

### ASK-B4 Listed for attention

WHEN `attention` runs with a paused ask THE engine SHALL show the item with kind `input`, the count of unanswered required questions and the resume command.

- GIVEN a paused ask WHEN `attention` runs THEN it shows kind `input`, the unanswered count and the resume command

## Acceptance criteria

- ASK-AC1 (ASK-B1, ASK-B8, ASK-B9): Every scenario of ASK-B1 holds offline
- ASK-AC2 (ASK-B8, ASK-B6): A partial answer, a crash and a resume keep the answers already accepted
- ASK-AC3 (ASK-B7, ASK-B5, ASK-B2): Validation refuses an ask in every placement ASK-B7 forbids
- ASK-AC4 (ASK-B4, ASK-B3): The monitor's documents show kind `input` with question counts ([RDD](31-run-detail-document.spec.md))

## Open questions

- Not met yet: ASK-AC3 holds for the placements built so far (a parallel branch and a map item); ASK-AC4 holds in the status document (`input` with answered and open counts) and waits on the monitor's own documents. Owner: engine owner.
