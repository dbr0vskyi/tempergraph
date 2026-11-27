# Pull request description

## Purpose

What the draft pull request's description holds and how it reaches the pull request. The last stage writes it with no model, from the run's own files, so that the owner reads the task's criteria, the behaviours that changed, the choices the run made and the findings that block nothing, and not the notes that steps handed to each other. This spec does not own the push of the branch, nor the outcome of the last stage except where it concerns the description. The owner who reads a run's pull request depends on it. Part of the [overview](overview.spec.md).

## Does not own

- The sections `Decided` and `Assumptions to confirm` (CONV-B7, CONV-B8): `conversation.spec.md`
- When the review runs and what a blocking finding does: `independent-review.spec.md`
- The findings the description lists, as the reader writes them: `review-findings.spec.md`
- What a last stage may do and how it ends: `../../../tempergraph/docs/specs/finalizer-contract.spec.md`

## Behaviours

### PRD-B1 The description lists the task's acceptance criteria

WHEN the last stage writes the description THE last stage SHALL list under `Acceptance criteria of the task` the lines of the triage note's `Acceptance criteria` section, the first 14 of them.

- GIVEN a triage note whose section holds one criterion WHEN the description is written THEN the heading lists that criterion as the note states it
- GIVEN a triage note whose section holds 15 lines WHEN the description is written THEN the heading lists the first 14

### PRD-B2 The description lists what each changed spec gained or lost

WHEN the run changed a spec or a decision record THE last stage SHALL list under `Read these` each changed spec by its path with the behaviour and criterion lines it gained or lost since the run's base, the first 14, and each changed decision record by its path.

- GIVEN a spec that gained a behaviour heading, its sentence and a criterion, and some prose WHEN the description is written THEN `Read these` lists the spec's path and the three lines as added and none of the prose
- GIVEN a spec changed with no behaviour or criterion line changed WHEN the description is written THEN `Read these` lists the spec's path and says that no such line changed
- GIVEN a run that changed no spec and no decision record WHEN the description is written THEN `Read these` says that none changed

### PRD-B3 The description lists decisions, open questions and deviations

WHEN the hand-off lists decisions or open questions, or the code report lists deviations, THE last stage SHALL list each kind that lists something under its own heading, `Decisions taken`, `Open questions` or `Deviations from the plan`, the first 14 lines of each.

- GIVEN a hand-off whose decisions list one decision and whose open questions say `None` WHEN the description is written THEN it has `Decisions taken` with the decision and no `Open questions` heading
- GIVEN a code report whose deviations list one deviation WHEN the description is written THEN `Deviations from the plan` lists it
- GIVEN a code report whose deviations say `None` WHEN the description is written THEN it has no `Deviations from the plan` heading

### PRD-B4 The notes that steps handed to each other are named by path

WHEN the run wrote the triage note, the hand-off, the plan or the code report THE last stage SHALL name each of them by its path in a line that says they are not needed for review.

- GIVEN a run that wrote the four documents WHEN the description is written THEN the line names the four paths and says they are not needed for review
- GIVEN a run that wrote no plan WHEN the description is written THEN the line names the other three

### PRD-B5 The description is never committed

WHEN the last stage writes the description THE last stage SHALL write it where no step commits it.

- GIVEN a run whose last stage wrote the description WHEN the workspace's status is read THEN it lists no description file, and no commit of the branch holds one

### PRD-B6 A description that cannot be written never fails the last stage

WHEN the description cannot be written THE last stage SHALL still push the branch and open or reuse the draft pull request, with no description.

- GIVEN a workspace in which the description cannot be written WHEN the last stage runs on a branch with no open pull request THEN the draft pull request is opened with no description

### PRD-B7 A new pull request gets the description

WHEN the last stage opens a draft pull request THE last stage SHALL give it the description.

- GIVEN a pushed branch with no open pull request WHEN the last stage runs THEN the draft pull request it opens carries the description

### PRD-B8 An open pull request gets the new description

WHEN the branch already has an open pull request THE last stage SHALL replace that pull request's description with the new one.

- GIVEN a pushed branch whose pull request is open WHEN the last stage runs THEN no second pull request is opened and the open one carries the new description
- GIVEN a host that refuses the replacement WHEN the last stage runs THEN its result says that the description was not updated

### PRD-B9 The findings that block nothing are listed

WHEN the findings document lists a finding marked not blocking, in either of its sections, THE last stage SHALL list it under `Review findings that block nothing`, after `Read these`, with its file, line and text.

- GIVEN a findings document with finding 1, blocking, and findings 2 and 3, not blocking WHEN the description is written THEN the heading lists findings 2 and 3 with their files, lines and texts and does not list finding 1
- GIVEN a findings document whose `Findings` section says `None` WHEN the description is written THEN it has no such heading
- GIVEN a run with no findings document WHEN the description is written THEN it has no such heading

## Acceptance criteria

- PRD-AC1 (PRD-B1): The description built from a triage note with one criterion lists it under `Acceptance criteria of the task`, and from a note whose section holds 15 lines lists the first 14
- PRD-AC2 (PRD-B2): The description built from a run that changed a spec lists under `Read these` the spec's path and its added behaviour heading, behaviour sentence and criterion and none of the added prose, names a spec with no such line changed as such, lists a changed decision record by its path, and says that none changed for a run that changed neither
- PRD-AC3 (PRD-B3): The description built from a hand-off with one decision and `None` for open questions has `Decisions taken` and no `Open questions` heading, and one built from a code report with one deviation lists it under `Deviations from the plan`, while a code report whose deviations say `None` gives no such heading
- PRD-AC4 (PRD-B4): The description names the triage note, the hand-off, the plan and the code report the run wrote by their paths in a line that says they are not needed for review, and names no document the run did not write
- PRD-AC5 (PRD-B5): After the last stage the workspace's status lists no description file and no commit of the branch holds one
- PRD-AC6 (PRD-B6): The last stage of a run whose description cannot be written ends with the draft pull request opened by a command that carries no description
- PRD-AC7 (PRD-B7): The draft pull request that the last stage opens is given the description the last stage wrote
- PRD-AC8 (PRD-B8): For a branch whose pull request is open, the last stage opens no second pull request and replaces the description of the open one, and its result says that the description was not updated when the replacement is refused
- PRD-AC9 (PRD-B9): The description built from a findings document with findings 1, blocking, and 2 and 3, not blocking, lists findings 2 and 3 with their files, lines and texts after `Read these` and not finding 1, and has no such heading for a document that says `None` and for a run with no document
