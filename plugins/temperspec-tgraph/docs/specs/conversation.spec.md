# Conversation setting

## Purpose

How much a run may ask the owner. The workflow has a conversation setting with two values. `blocking`, the default, leaves the workflow as it is: triage sorts no gap, a step that meets a question only a person can answer ends blocked when the question blocks planning, and the pull request description lists no assumptions. `never`, for a pipeline or a night run, keeps the run unattended: triage sorts each gap into a findable gap (the code, the documents or a public source can answer it) or an owner decision (only the owner can) and takes a default for each owner decision, no step or gate stops to ask about one, and the draft pull request lists each default as an assumption to confirm, so the owner still sees every guess. A person sets the value for one run with `--set settings.conversation=never`, or for a repository in the engine's settings files, as for any setting a workflow declares ([RST-B7](../../../tempergraph/docs/specs/80-run-settings-and-overrides.spec.md)). Whoever starts runs from a pipeline or overnight, and the owner who reads their pull requests, depend on it. The design is in [next features](../research/next-features.rsrch.md); the setting changes what [triage](04-triage.spec.md) and [discovery](05-discovery.spec.md) do and what the last stage writes. Part of the [overview](00-overview.spec.md).

## Behaviours

### CONV-B1 A run has one conversation value

WHEN a run of the workflow starts THE workflow SHALL give the run the conversation value `never` or `blocking`: the value the start options or the repository's settings set, else `blocking`.

- GIVEN a start that sets no conversation value WHEN the settings the run will use are shown THEN `conversation` is `blocking`
- GIVEN a start with `--set settings.conversation=never` WHEN the settings the run will use are shown THEN `conversation` is `never`
- GIVEN a settings entry of the repository that sets `conversation` to `never` and a start that sets no value WHEN the settings the run will use are shown THEN `conversation` is `never`
- GIVEN a start with `--set settings.conversation=always` WHEN the start is validated THEN it is refused before the run spends anything and the message lists `never` and `blocking`

### CONV-B2 Triage sorts each gap

WHEN triage writes the triage note of a run whose conversation value is `never` THE triage step SHALL say for each gap row whether the gap is findable, because the code, the documents or a public source can answer it, or an owner decision, because only the owner can.

- GIVEN `never` and a task that leaves open whether a missing config file gives exit code 2 or exit code 1 WHEN triage writes the note THEN that gap's row says owner decision
- GIVEN `never` and a gap that a spec of the repository already answers WHEN triage writes the note THEN that gap's row says findable
- GIVEN `never` and a gap whose answer is in the code WHEN triage writes the note THEN that gap's row says findable
- GIVEN `blocking` WHEN the triage step is briefed THEN it is told to sort no gap

### CONV-B3 An owner decision carries its default

WHEN triage sorts a gap as an owner decision in a run whose conversation value is `never` THE triage step SHALL write for it, under `Owner decisions` in the triage note, one entry with its question, two to four options, its default, which is one of the options, and what the default costs if it is wrong.

- GIVEN `never` and the owner decision on the exit code of a missing config file WHEN triage writes the note THEN `Owner decisions` has one entry that asks which exit code the tool gives, offers 2, 1 and 78, takes 2 as the default, and says that a script testing for 1 would see another code if 2 is wrong
- GIVEN `never` and a note with no owner decision, because every gap is findable or because there is no gap WHEN triage writes the note THEN `Owner decisions` says `None`

### CONV-B4 The triage check refuses an incomplete sort

WHEN the triage check reads the triage note of a run whose conversation value is `never` THE triage check SHALL fail `ts-tri-owner`, naming the gap or the section and what is missing, for each place where the note falls short of the sort of CONV-B2 and the entries of CONV-B3.

- GIVEN `never` and a gap row that says neither findable nor owner decision WHEN the check runs THEN it fails `ts-tri-owner` and names that gap
- GIVEN `never` and a note with no `Owner decisions` section WHEN the check runs THEN it fails `ts-tri-owner` and names the section
- GIVEN `never` and a gap row that says owner decision with no entry, or an entry for a gap row that says findable WHEN the check runs THEN it fails `ts-tri-owner` and names that gap
- GIVEN `never` and an entry with one option, or with five WHEN the check runs THEN it fails `ts-tri-owner`, naming the gap and the number of options
- GIVEN `never` and an entry with no question, with no default, with a default that is not one of its options, or with no cost WHEN the check runs THEN it fails `ts-tri-owner`, naming the gap and the missing part
- GIVEN `never` and a note whose entries each have a question, two to four options, a default among them and a cost, or whose `Owner decisions` says `None` and whose gap rows all say findable WHEN the check runs THEN `ts-tri-owner` passes
- GIVEN `blocking`, or no conversation value given to the check, and a note with neither a sort of its gap rows nor an `Owner decisions` section WHEN the check runs THEN it passes, as it does for the notes of the triage judge's met seeds

### CONV-B5 A step goes on with the default

WHEN a step of a run whose conversation value is `never` meets an owner decision THE workflow SHALL have the step go on with the decision's default instead of ending blocked.

- GIVEN `never` and an owner decision of the triage note whose default is exit code 2 WHEN discovery closes its gap THEN the spec it writes states the behaviour of exit code 2 and holds no open question for the decision, and discovery does not end blocked
- GIVEN `never` and a question only the owner can answer that the triage note does not list WHEN discovery meets it THEN it goes on with the option that changes the least of what exists and records the question, the options and that option in the hand-off's open questions as the default in force (`Until answered: <option>`)
- GIVEN `never` and a task that states no acceptance criterion WHEN triage reads it THEN the step still ends blocked, because nothing in the task can take a default
- GIVEN `blocking` and a question only a person can answer that blocks planning WHEN discovery meets it THEN it ends blocked and states the question with its options

### CONV-B6 No gate stops for a default

WHEN a gate of a run whose conversation value is `never` judges the output of a step that went on with a default THE gate SHALL decide the step on its check and its judge alone, without asking a person.

- GIVEN `never` and a hand-off whose open question says `Until answered: (a)` WHEN the discovery gate judges the hand-off THEN the question changes no grade and the run does not stop for it
- GIVEN the workflow's units WHEN they are listed THEN none asks a person a question or waits for an answer, and no gate requires a sign-off

### CONV-B7 The description lists the defaults as assumptions

WHEN the last stage writes the pull request description of a run whose triage note has an `Owner decisions` section THE last stage SHALL list under `Assumptions to confirm` each owner decision with its question, its default and what the default costs if it is wrong, or say that the run took no default.

- GIVEN a triage note with two owner decisions WHEN the description is written THEN `Assumptions to confirm` lists both, each with its question, its default and its cost
- GIVEN a triage note with 16 owner decisions WHEN the description is written THEN all 16 are listed
- GIVEN a triage note whose `Owner decisions` says `None` WHEN the description is written THEN `Assumptions to confirm` says that the run took no default
- GIVEN a triage note with no `Owner decisions` section WHEN the description is written THEN the description has no `Assumptions to confirm` heading
- GIVEN a hand-off whose open question carries the default a later step took WHEN the description is written THEN the question is listed with its default among the description's open questions

## Acceptance criteria

- CONV-AC1 (CONV-B1): The workflow declares the setting `conversation` as a choice of `never` and `blocking` with the default `blocking`; the settings shown for a start with no value give `blocking`, for `--set settings.conversation=never` give `never`, for a repository settings entry that sets `never` give `never`, and a start with `--set settings.conversation=always` is refused with a message that lists the two values
- CONV-AC2 (CONV-B2, CONV-B3): The triage prompt names the run's conversation value and tells the session, only when it is `never`, to say for each gap row whether it is findable or an owner decision and to write under `Owner decisions` each owner decision's question, two to four options, a default among them and the cost of a wrong default, or `None`
- CONV-AC3 (CONV-B4): With `never`, the triage check fails `ts-tri-owner`, naming the gap or the section, for a gap row that is not sorted, a missing `Owner decisions` section, a gap row that says owner decision with no entry, and an entry for a gap row that says findable
- CONV-AC4 (CONV-B4): With `never`, the triage check fails `ts-tri-owner`, naming the gap and the missing part, for an entry with no question, with one option or five, with no default, with a default that is not one of its options, or with no cost
- CONV-AC5 (CONV-B4): The triage check passes under `never` a note with two complete entries and a note whose `Owner decisions` says `None`, and passes the notes of the triage judge's met seeds, and a note with neither a sort nor an `Owner decisions` section, when the conversation value is `blocking` or is not given to the check
- CONV-AC6 (CONV-B5): The discovery prompt names the run's conversation value and tells the session, only when it is `never`, to close each owner decision of the triage note on its default with no open question left in the spec, to take the option that changes the least for a question the note does not list and record it in the hand-off's open questions as `Until answered`, and never to end blocked on an owner decision; for `blocking` it tells the session to end blocked on a question only a person can answer that blocks planning
- CONV-AC7 (CONV-B6): No unit of the workflow asks a person a question or waits for an answer, no gate requires a sign-off, and the brief of each step judge after triage says that an open question the hand-off lists changes no grade
- CONV-AC8 (CONV-B7): The description built from a triage note with two owner decisions lists both under `Assumptions to confirm` with question, default and cost; built from a note with 16 owner decisions it lists 16; built from a note whose `Owner decisions` says `None` it says the run took no default; built from a note with no such section it has no such heading; an open question of the hand-off that carries a default is listed with it among the open questions
