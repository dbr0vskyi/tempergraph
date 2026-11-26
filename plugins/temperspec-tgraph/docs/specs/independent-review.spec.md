# Independent review

## Purpose

What reads a run's change before the outcome gate, in a session that knows nothing of the run's own reasoning, so that a defect that every gate of the run passed is found while the run can still go back and fix it. After the code step ([code join](code-join.spec.md)) a reader is given the change and the task's acceptance criteria and reads the repository; it changes no file but its findings document. It numbers what it finds and marks each finding blocking or not blocking ([review findings](review-findings.spec.md)). A blocking finding sends the run back once, to the plan step or to the code step; a finding that is not blocking blocks nothing and is listed in the draft pull request's description ([pull request description](pull-request-description.spec.md)). The *change* is what the run's commits changed since the run's base commit, leaving out the hand-over documents and the files that the prepare step wrote or changed ([project note](project-note.spec.md), [RCM-B9](repository-commands.spec.md)). A *hand-over document* is a document that a step of the run writes for a later step or for the owner to read about the run: the triage note, the setup note, the hand-off, the plan, the code report and the findings document. The change *touches* a file when it adds, changes or deletes it. This spec does not own what the judges of the other gates read ([judge reading](judge-reading.spec.md)), the final criteria ([outcome gate](outcome-gate.spec.md)), or the engine's trip back and the pause of a spent budget ([BUD-B4](../../../tempergraph/docs/specs/budgets-and-failures.spec.md), [HUM-B8](../../../tempergraph/docs/specs/gate-and-human.spec.md)). The reasons are in [the decision on independence](../adr/review-independence-is-held-by-inputs-and-the-session-record.adr.md) and [the decision on the quick lane](../adr/a-quick-lane-run-takes-no-review.adr.md). The owner who reads a run's pull request and the maintainers of the workflow depend on it. Part of the [overview](overview.spec.md).

## Depends on

- `session-record-checks.spec.md`: without a session record the criterion does not apply (SRC-B8)

## Behaviours

### IRV-B1 The review follows the code step

WHEN a run outside the quick lane passes the code step THE workflow SHALL run the review before the outcome gate, whether the plan was built at once or one phase at a time.

- GIVEN a run that built its plan at once in one session and passed the code step WHEN it goes on THEN the review runs and the outcome gate runs after it
- GIVEN a run that built its plan one phase at a time and passed the code step WHEN it goes on THEN the review runs and the outcome gate runs after it
- GIVEN a run that ends after discovery with documents only WHEN it ends THEN it takes no review

### IRV-B2 A quick-lane run takes no review

WHEN a run in the quick lane passes the code step THE workflow SHALL go on to the outcome gate with no review.

- GIVEN a run that went from triage straight to the code step and passed it WHEN it goes on THEN no reader session starts and the outcome gate runs next
- GIVEN a run that the code gate sent back to triage, which then routed it to the plan step WHEN it passes the code step THEN the review runs

### IRV-B3 The reader is given the change

WHEN the reader starts THE review unit SHALL hand it the change since the run's base commit, with no hand-over document in it and no file that the prepare step wrote or changed.

- GIVEN a run whose commits changed a source file and a test file and wrote a plan, a hand-off and a code report WHEN the reader starts THEN the change it is handed holds the source file and the test file and none of the three documents
- GIVEN a run whose commits edited a spec and deleted a file WHEN the reader starts THEN the change holds the spec's edit and the deletion
- GIVEN a review that follows a trip back WHEN the reader starts THEN the change holds the commits of both visits since the run's base commit

### IRV-B4 The reader is given the acceptance criteria

WHEN the reader starts THE review unit SHALL hand it the task's acceptance criteria, numbered as the triage note numbers them, and no other part of the triage note.

- GIVEN a triage note with three numbered criteria, two gaps and an owner decision WHEN the reader starts THEN it is handed the three criteria with their numbers and nothing of the gaps or of the owner decision

### IRV-B5 The reader's prompt and values hold nothing of the run's reasoning

WHEN the reader's prompt is rendered THE review unit SHALL keep out of it, and out of each value it reads, the text of the plan, the hand-off, the code report, any earlier judgement and any step's session, and the path of every hand-over document.

- GIVEN a run whose earlier gates left unmet warnings and whose steps ended with accounts WHEN the reader's prompt is rendered THEN it holds no warning and no account
- GIVEN a run that wrote a plan, a hand-off and a code report WHEN the reader's prompt is rendered THEN it holds no line of them and no path of them
- GIVEN a review that follows a trip back WHEN the reader's prompt is rendered THEN it holds nothing of the first review's findings

### IRV-B6 The reader opens no hand-over document

WHEN the reader's session ends THE review unit SHALL fail its check, naming the document, for each hand-over document that the session opened.

- GIVEN a session that opened the plan with the read tool WHEN the check runs THEN it fails and names the plan
- GIVEN a session that only searched the repository and opened no hand-over document WHEN the check runs THEN it does not fail for a hand-over document
- GIVEN a session of which the engine gives no record WHEN the check runs THEN the criterion does not apply, as [SRC-B8](session-record-checks.spec.md) says

### IRV-B7 The reader changes only its findings document

WHEN the reader's session ends THE review unit SHALL fail its check, naming the file, when the session wrote or edited a file other than the findings document.

- GIVEN a session that wrote the findings document and edited a source file WHEN the check runs THEN it fails and names the source file
- GIVEN a session that wrote only the findings document WHEN the check runs THEN it does not fail for a file

### IRV-B8 What a blocking finding is

WHEN the reader is briefed THE review unit SHALL tell it to mark a finding blocking only when a person using the change as the acceptance criteria describe would meet the defect as a wrong or missing result, a failure, a hang, a loss of data or a break of behaviour the repository had before the change, and to mark every other finding not blocking.

- GIVEN the reader's brief WHEN a person reads it THEN it says that a wrong or missing result, a failure, a hang, a loss of data and a break of earlier behaviour are blocking
- GIVEN the reader's brief WHEN a person reads it THEN it says that every other finding, such as a name that could be clearer, is not blocking

### IRV-B9 A blocking finding on a file the change touches goes back to the code step

WHEN a review lists blocking findings and each names a file that the change touches THE workflow SHALL send the run back to the code step.

- GIVEN a review with one blocking finding on a changed source file and one finding that is not blocking WHEN the review ends THEN the run goes back to the code step
- GIVEN a review with a blocking finding on a spec that the change edited WHEN the review ends THEN the run goes back to the code step

### IRV-B10 A blocking finding on a file the change does not touch goes back to the plan step

WHEN a review lists a blocking finding that names a file the change does not touch THE workflow SHALL send the run back to the plan step, whatever the other blocking findings name.

- GIVEN a review with one blocking finding on a file the change does not touch WHEN the review ends THEN the run goes back to the plan step
- GIVEN a review with a blocking finding on a changed file and another on a file the change does not touch WHEN the review ends THEN the run goes back to the plan step

### IRV-B11 The step the run goes back to is given the blocking findings, numbered

WHEN the review sends the run back THE workflow SHALL give the step it goes back to, as the reason for its visit, each blocking finding with its number, file, line and text, in the order of the findings document, and no finding that is not blocking.

- GIVEN a review whose findings 1 and 3 are blocking and whose finding 2 is not WHEN the run goes back THEN the reason for the visit holds findings 1 and 3 with their numbers, files, lines and texts and does not hold finding 2

### IRV-B12 One trip back

WHEN a review has sent the run back THE workflow SHALL send it back no second time, whichever step the findings of a later review name.

- GIVEN a first review that sent the run to the code step and a second review with a blocking finding on a file the change does not touch WHEN the second review ends THEN the run is not sent to the plan step
- GIVEN a first review that sent the run to the plan step and a second review with a blocking finding on a changed file WHEN the second review ends THEN the run is not sent to the code step

### IRV-B13 A blocking finding left after the trip back pauses the run

WHEN a review that follows a trip back lists a blocking finding THE workflow SHALL pause the run, with each blocking finding left shown in the pause by its number, file, line and text.

- GIVEN a second review with two blocking findings and one finding that is not blocking WHEN it ends THEN the run pauses and the pause shows the two blocking findings and not the third
- GIVEN a second review with no blocking finding WHEN it ends THEN the run does not pause for the review

### IRV-B14 No blocking finding lets the run go on

WHEN a review lists no blocking finding THE workflow SHALL go on to the outcome gate with no trip back, whatever it lists as not blocking.

- GIVEN a review of a clean change whose findings say `None` WHEN it ends THEN the outcome gate runs next and no step runs again
- GIVEN a review whose findings are all not blocking WHEN it ends THEN the outcome gate runs next and no step runs again

## Acceptance criteria

- IRV-AC1 (IRV-B1): A fixture run outside the quick lane that passes the code step enters the review and then the outcome gate, on the arm that builds the plan at once and on the arm that builds it one phase at a time, and a documents-only run enters no review
- IRV-AC2 (IRV-B2): A fixture run in the quick lane that passes the code step starts no reader session and enters the outcome gate next, and a fixture run that the code gate sent back to triage and the triage step routed to the plan step enters the review
- IRV-AC3 (IRV-B3): The change handed to the reader in a fixture run holds the source and test files the run's commits changed, the edit of a spec and a deletion, and holds none of the hand-over documents and none of the files the prepare step wrote or changed; in a review after a trip back it holds the commits of both visits
- IRV-AC4 (IRV-B4): The criteria handed to the reader hold the numbered criteria of the triage note and nothing of its gaps or its owner decisions
- IRV-AC5 (IRV-B5): On the loaded workflow, the reader's rendered prompt and each value it reads hold no text of the plan, the hand-off, the code report, an earlier judgement or a step's session, no path of a hand-over document and nothing of an earlier review's findings, for a state that holds all of them
- IRV-AC6 (IRV-B6): The review's check fails and names the plan for a session record that shows the plan opened with the read tool, does not fail for a record that shows only a search, and does not apply to a run with no record
- IRV-AC7 (IRV-B7): The review's check fails and names the file for a session record that shows a write or an edit of a file other than the findings document, and does not fail for a record that shows only the findings document
- IRV-AC8 (IRV-B8): The reader's brief says that a wrong or missing result, a failure, a hang, a loss of data and a break of earlier behaviour are blocking and that every other finding is not blocking
- IRV-AC9 (IRV-B9): A fixture run whose change holds a planted defect in a changed file that every other gate passes is sent back by the review to the code step
- IRV-AC10 (IRV-B10): A fixture run whose review lists a blocking finding on a file the change does not touch is sent back by the review to the plan step, also when another blocking finding names a changed file
- IRV-AC11 (IRV-B11): The reason for the visit of the step the run goes back to holds each blocking finding with its number, file, line and text, in the order of the findings document, and no finding that is not blocking
- IRV-AC12 (IRV-B12): A fixture run that the review sent back once is sent back by its second review to neither step, whichever file the second review's blocking finding names
- IRV-AC13 (IRV-B13): A fixture run whose second review lists blocking findings pauses, and the pause shows each of them with its number, file, line and text and shows no finding that is not blocking
- IRV-AC14 (IRV-B14): A fixture run with a clean change passes the review with no trip back and no pause, and so does a run whose findings are all not blocking
- [ ] ts-rev-form Each finding names an existing file, a line inside it and a mark, in numbered order, or the section says None
- [ ] ts-rev-session The reader opened no hand-over document of the run and wrote no file but its draft
- [ ] ts-rev-commit Every file the step left is committed, with nothing uncommitted in the workspace
- [ ] ts-rev-step A blocking finding on a file the change touches sends the run to the code step, any other blocking finding to the plan step
- [ ] ts-rev-blockers No finding the reader marked blocking remains

