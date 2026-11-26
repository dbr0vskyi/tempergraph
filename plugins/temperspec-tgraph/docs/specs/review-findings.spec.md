# Review findings

## Purpose

The document in which the review's reader states what it found, the model-free check that refuses an incomplete finding, and the record that a trip back adds to the document. The document lists numbered findings, each naming a file and a line and marked blocking or not blocking, so that the step the run goes back to, the owner and the pull request's description each read a finding in one way. The record of a visit's result is one for the whole visit: the engine's blocker that every point of a visit's reason is addressed ([RRN-B14](../../../tempergraph/docs/specs/reruns-and-feedback.spec.md)) gives none for a single point, as [the decision on independence](../adr/review-independence-is-held-by-inputs-and-the-session-record.adr.md) records. The owner who reads a run's pull request and the maintainers of the workflow depend on it. Part of the [overview](overview.spec.md).

## Does not own

- When the review runs, what the reader is given and what a blocking finding does: `independent-review.spec.md`
- What the pull request's description lists of the findings: `pull-request-description.spec.md`

## Behaviours

### RVF-B1 The findings document is committed beside the triage note

WHEN the reader's session ends THE review unit SHALL leave the findings in a document committed on the run's branch, in the folder that holds the run's triage note, named by the task id and ending `.review.md`.

- GIVEN a triage note in the folder `docs/tasks/` WHEN the review ends THEN the findings document is in `docs/tasks/`, named by the task id and `.review.md`, and is committed
- GIVEN a triage note in another folder of the repository WHEN the review ends THEN the findings document is in that folder

### RVF-B2 A finding is one numbered item

WHEN the findings document lists a finding THE review unit SHALL write it as one numbered item under `Findings`: its number, its file and line in a code span as `file:line`, its mark, `blocking` or `not blocking`, a colon and its text.

- GIVEN a finding on line 42 of a source file that blocks the change WHEN it is written THEN its item reads ``1. `src/a.py:42` blocking: the loop never ends when every source fails``
- GIVEN a finding on line 7 of a spec that blocks nothing WHEN it is written THEN its item reads ``2. `docs/a.spec.md:7` not blocking: the sentence can be read two ways``

### RVF-B3 The check refuses an incomplete finding

WHEN the reader's findings hold a finding with no file, with a file that does not exist on the branch, with no line, with a line past the end of its file, or with a mark that is neither `blocking` nor `not blocking`, THE review unit SHALL fail its check, naming the finding's number.

- GIVEN a finding that names a file that does not exist on the branch WHEN the check runs THEN it fails and names the finding's number
- GIVEN a finding with the mark `maybe`, or with no mark WHEN the check runs THEN it fails and names the finding's number
- GIVEN a finding whose file exists, whose line is inside the file and whose mark is `not blocking` WHEN the check runs THEN it does not fail for that finding

### RVF-B4 The check refuses a document of the wrong form

WHEN the findings document has no `Findings` section, an empty one, or items whose numbers do not run 1, 2, 3 and so on in order, THE review unit SHALL fail its check, naming the section or the number.

- GIVEN a document with no `Findings` section WHEN the check runs THEN it fails and names the section
- GIVEN a document whose items are numbered 1, 2 and 4 WHEN the check runs THEN it fails and names the number 4

### RVF-B5 A review that finds nothing says so

WHEN the reader finds nothing THE review unit SHALL accept a findings document whose section `Findings` holds the single word `None`.

- GIVEN a document whose `Findings` section says `None` WHEN the check runs THEN it does not fail
- GIVEN a document whose `Findings` section is empty WHEN the check runs THEN it fails and names the section

### RVF-B6 The first review's findings stay after a trip back

WHEN a review follows a trip back THE review unit SHALL keep the first review's findings in a section `Earlier review` of the findings document, each with its number, file, line, mark and text as the first review gave it.

- GIVEN a first review with findings 1, blocking, and 2, not blocking, and a second review with one finding WHEN the second review ends THEN `Findings` holds the second review's finding and `Earlier review` holds findings 1 and 2 as the first review gave them

### RVF-B7 The visit's result is recorded for each blocking finding of the first review

WHEN the findings document keeps a first review THE review unit SHALL end each blocking finding of it with `Visit: built` when the visit that the trip back started passed its gate and with `Visit: refused` when it did not, the same for every finding.

- GIVEN a first review with two blocking findings and a visit that passed its gate WHEN the second review ends THEN both findings end with `Visit: built`
- GIVEN a first review with a blocking and a not blocking finding WHEN the second review ends THEN the finding that is not blocking ends with no visit result
- GIVEN a visit that did not pass its gate before the run reached the second review WHEN the second review ends THEN each blocking finding of the first review ends with `Visit: refused`

## Acceptance criteria

- RVF-AC1 (RVF-B1): After a fixture review the findings document exists beside the triage note, named by the task id and ending `.review.md`, and no uncommitted change is left, for a triage note in `docs/tasks/` and for one in another folder
- RVF-AC2 (RVF-B2): A fixture reader's finding on line 42 of a source file that blocks the change is written as an item that reads ``1. `src/a.py:42` blocking: the loop never ends when every source fails``, and one that blocks nothing as an item with the mark `not blocking`, each under `Findings`
- RVF-AC3 (RVF-B3): The review's check fails and names the finding's number for a finding with a missing file, a missing line, a file that does not exist, a line past the end of its file, a mark `maybe` and no mark, and does not fail for a complete finding
- RVF-AC4 (RVF-B4): The review's check fails and names the section for a document with no `Findings` section and for an empty one, and names the number 4 for items numbered 1, 2 and 4
- RVF-AC5 (RVF-B5): The review's check accepts a `Findings` section that holds only `None`
- RVF-AC6 (RVF-B6): After a second review the findings document holds the second review's findings under `Findings` and the first review's findings under `Earlier review`, each as the first review gave it
- RVF-AC7 (RVF-B7): After a second review the document ends each blocking finding of the first review with `Visit: built` for a visit that passed its gate and with `Visit: refused` for one that did not, and a finding that is not blocking with no visit result
