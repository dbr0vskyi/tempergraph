# Phase coding

## Purpose

How a plan that took the arm `phases` of the switch `code_mode` ([code mode](code-mode.spec.md)) is built. After the expand step has written its task rows, the phase step runs once for each phase of the plan, one after another, a phase item each. A phase item is a session of its own that builds only that phase's rows, tests first, and is committed and checked on its own. The code step then runs as the join, on the whole change. A large plan so gets a fresh context for each phase, and a phase that fails runs again alone, with the phases already committed left as they are ([MAP-B10](../../../tempergraph/docs/specs/map-unit.spec.md)). A phase's gate has no line back to an earlier step ([MAP-B11](../../../tempergraph/docs/specs/map-unit.spec.md)), so every check of the whole change and the lines back to the plan, discovery and triage steps stay with the code step's gate. The arm `single` is unchanged: its one code session builds the whole plan ([CDM-B6](code-mode.spec.md)). A step is entered when its first attempt of a visit begins, and the commit at which it was entered is the one the run's branch holds at that moment. The owner who waits for a large plan and the maintainers of the plan, expand and code steps depend on it. Part of the [overview](overview.spec.md); the unit is [phase](phase.spec.md).

## Depends on

- `../../../tempergraph/docs/specs/judge-and-verdict.spec.md`: check first (JDG-B1)
- `../../../tempergraph/docs/specs/map-unit.spec.md`: trip back reruns every item (MAP-B3); item budgets, pauses and the join (MAP-B10); what is refused (MAP-B11)
- `kept-marks.spec.md`: the code step is told to build only the rows without a mark (KMK-B7); a kept row's file need not change again (KMK-B8); a phase's marks are written in one edit after its tests pass (KMK-B9)
- `session-record-checks.spec.md`: a phase's source changed before its tests fails the code check (SRC-B6); without a session record the criterion does not apply (SRC-B8)

## Behaviours

### PHC-B1 One phase item for each phase, in plan order

WHEN the expand step has passed its gate on the arm `phases` THE workflow SHALL run one phase item for each phase of the plan, one after another in the order the plan lists its phases.

- GIVEN an expanded plan of phases 1, 2 and 3 WHEN the phase items run THEN three items run, in the order phase 1, phase 2, phase 3, and each starts only after the one before it has passed its gate
- GIVEN an expanded plan of one phase WHEN the phase items run THEN one item runs
- GIVEN an expanded plan of phases 1, 2 and 3 WHEN the phase items run THEN they are named `p1`, `p2` and `p3` after the numbers of the phase headings, so that a pause or a resume names `phase.p2` for phase 2

### PHC-B2 A phase is built in a session of its own

WHEN a phase item starts THE workflow SHALL start a new session for it, briefed on that phase and on no other, with the path of the plan and the path of the triage note.

- GIVEN a plan of three phases WHEN the phase items have run THEN three sessions ran, none of them a resumption of another
- GIVEN phases 1, 2 and 3 WHEN the session of phase 2 is briefed THEN its brief carries the heading, the goal and the weight of phase 2 and the path of the plan, and neither the heading of phase 1 nor that of phase 3

### PHC-B3 A phase session builds only its own rows, tests first

WHEN a phase session is briefed THE workflow SHALL tell it to build only the rows of its phase whose Completed cell is empty, writing the phase's test files before its source files, and to mark each row it built.

- GIVEN the brief of a phase session WHEN it is read THEN it tells the session to build only the rows of its phase whose Completed cell is empty and to leave the mark of every other row as it is ([KMK-B7](kept-marks.spec.md))
- GIVEN the same brief WHEN it is read THEN it tells the session to write the phase's tests first and see them fail, to run after the phase only the test files its rows name and never the plan's verification commands, and to change no file that no row of the phase names but the plan's marks and status
- GIVEN the same brief WHEN it is read THEN it tells the session to write `✓` and the day's date as `YYYY-MM-DD` in the Completed cell of each row it built, in one edit of the plan after the test files of the phase pass ([KMK-B9](kept-marks.spec.md)), and to run no `git commit`

### PHC-B4 A phase ends with a note

WHEN a phase session is briefed THE workflow SHALL tell it to end with a note of one line of at most 1,500 characters that names each test file it ran and each deviation from the plan with its reason, or says `none`.

- GIVEN the brief of a phase session WHEN it is read THEN it asks for one line of at most 1,500 characters that names the test files run and each deviation from the plan with its reason, or `none`
- GIVEN a phase session that ends with no note WHEN its attempt ends THEN that phase runs again, alone

### PHC-B5 A phase's files are committed when its attempt ends

WHEN a phase attempt ends THE workflow SHALL commit the files the attempt changed on the run's branch, before the next attempt or the next phase starts.

- GIVEN a plan of three phases that each change one file and pass at the first attempt WHEN the phase items have run THEN the branch holds, after the commit of the expand step, one commit for each phase in plan order, each holding that phase's files and the marks of its rows
- GIVEN phase 2 WHEN its session starts THEN the files of phase 1 are committed and the working tree holds no change
- GIVEN a phase attempt that changes no file WHEN it ends THEN no commit is made

### PHC-B6 The phase check reads the rows of the phase only

WHEN a phase attempt ends and a row of that phase has no completed mark with its date, or has one while its file does not differ from the run's base commit, THE phase check SHALL fail the attempt, naming the row.

- GIVEN phase 2 with rows 2.1 and 2.2 and a session that marks only row 2.1 WHEN the phase check runs THEN it fails, naming row 2.2
- GIVEN phase 2 whose rows are all marked with their files changed, and phase 3 whose rows are not marked yet WHEN the check of phase 2 runs THEN it passes and names no row of phase 3
- GIVEN row 2.1 marked `✓ 2026-11-24` and its file the same as at the run's base commit WHEN the phase check runs THEN it fails, naming row 2.1
- GIVEN row 1.2 marked by an earlier visit with its file different from the run's base commit, and a visit that changes no file WHEN the check of its phase runs THEN it makes no finding about row 1.2 ([KMK-B8](kept-marks.spec.md))

### PHC-B7 A criterion a test row proves is carried by a test that runs

WHEN a phase attempt ends and a test row of that phase proves a criterion that no test in the row's file carries, or that only a skipped test carries, THE phase check SHALL fail the attempt, naming the row.

- GIVEN a test row of phase 2 that proves `AC 1` and a test file in which no test names `AC 1` WHEN the phase check runs THEN it fails, naming the row
- GIVEN the same row and a test file in which the only test that names `AC 1` is skipped WHEN the phase check runs THEN it fails, naming the row
- GIVEN the same row and a test file with a test that names `AC 1` and runs WHEN the phase check runs THEN it makes no finding about the row

### PHC-B8 A phase's source is not changed before its tests are written

WHEN the session record of a phase attempt shows a source file of the phase changed before the phase's test file was first written THE phase check SHALL fail the attempt, naming the phase, by the rule of [SRC-B6](session-record-checks.spec.md).

- GIVEN phase 2 with the test file `tests/test_b.py` and the source file `src/b.py` and a record that edits `src/b.py` and then writes `tests/test_b.py` WHEN the phase check runs THEN it fails, naming phase 2
- GIVEN the same plan and a record that writes `tests/test_b.py` and then edits `src/b.py` WHEN the phase check runs THEN it makes no finding about the order
- GIVEN an attempt for which the engine gives the check no session record WHEN the phase check runs THEN the order criterion is not applicable and its message says there is no session record to read ([SRC-B8](session-record-checks.spec.md))

### PHC-B9 Each phase attempt is judged on its own

WHEN a phase attempt passes its check THE workflow SHALL grade it with one judge session of its own, on whether each row's change is in the file the row names and no file outside the rows of the phase and of earlier phases, other than the plan's marks and status, was changed since the phase step was entered.

- GIVEN a plan of three phases that pass WHEN the phase items have run THEN the run holds three judge sessions for them, one for each, besides the judge session of the code step
- GIVEN a phase attempt whose check fails WHEN the attempt ends THEN no judge session starts for it ([JDG-B1](../../../tempergraph/docs/specs/judge-and-verdict.spec.md))
- GIVEN a document that only an earlier step wrote and a phase that changed only the files of its rows WHEN the phase attempt is judged THEN the document counts as no file outside the phase's rows

### PHC-B10 A failed phase runs again alone

WHEN a phase attempt fails its gate THE workflow SHALL run that phase again, on its own, with the phases that passed before it left as they are and the phases after it not started.

- GIVEN phases 1, 2 and 3 where the first attempt of phase 2 leaves a row unmarked WHEN the phase items run THEN phase 2 runs a second session, phase 1 ran one session, and phase 3 starts only after phase 2 has passed and runs one session
- GIVEN the same run WHEN phase 2 runs again THEN the commit of phase 1 is still on the branch and the rows of phase 1 are still marked
- GIVEN phase 2 whose attempts all fail until its retries are spent WHEN the phase items run THEN the run pauses at `phase.p2` and phase 3 starts no session ([MAP-B10](../../../tempergraph/docs/specs/map-unit.spec.md))

### PHC-B11 The code step is the join, after the last phase

WHEN the last phase item has passed its gate THE workflow SHALL run the code step on the whole change, as the join of the phases.

- GIVEN a plan of three phases that pass WHEN the last passes THEN the code step starts after the gate of phase 3 has passed, and one code session runs on the whole change
- GIVEN a plan of three phases that spends the retries of phase 2 WHEN the run pauses at phase 2 THEN the code step has not started

### PHC-B12 The code step is briefed on what the phases did

WHEN the code step starts THE workflow SHALL brief its session with the note of each phase, one line for each phase led by its number, in the order of the plan, or with the statement that no phase ran.

- GIVEN phases 1, 2 and 3 that ended with notes WHEN the code step starts THEN its brief lists the note of phase 1, then that of phase 2, then that of phase 3, each line led by its phase
- GIVEN the brief of the code step WHEN it is read THEN it says that when the notes list the phases, the phases built and committed their rows, so that the session builds only a row whose Completed cell is empty ([KMK-B7](kept-marks.spec.md)), sets the plan's status to `completed` and writes the code report with each deviation the notes name
- GIVEN a run on the arm `single` and a run in the quick lane WHEN the code step starts THEN its brief lists no note and says that no phase ran

### PHC-B13 The code gate checks the whole change

WHEN the code step ends after the phase items THE code gate SHALL check the whole change as it checks one built in a single session: the marks of every row and the plan's status, the file of each marked row, each verification command of the plan run by the gate itself, the proof of each criterion of the proof table, and the quick-lane guard.

- GIVEN a plan of two phases that passed their gates and a verification command that exits 0 at the run's base commit and fails when the code gate runs it WHEN the code gate runs THEN the code step fails its check and only the code step runs again, with no phase session started
- GIVEN a plan of two phases whose phases changed the file of every row and a code session that changes no file WHEN the code gate runs THEN it makes no finding about the files of the rows ([KMK-B8](kept-marks.spec.md))
- GIVEN a plan whose status is not `completed` after the last phase WHEN the code gate runs THEN it fails the code step before any command runs
- GIVEN a run on the arm `phases` WHEN the code gate runs THEN its result holds the quick-lane guard, not applicable because the run is not in the quick lane

### PHC-B14 The code gate holds the lines back

WHEN the code step ends after the phase items with a claim that the output of the plan, discovery or triage step is at fault, and the gate accepts the claim, THE workflow SHALL send the run back to that step.

- GIVEN two phases that passed and a code session that claims the plan step's output is at fault, and a gate that accepts the claim WHEN the code gate judges it THEN the run goes back to the plan step; the same holds for a claim about the discovery step and for one about the triage step
- GIVEN the workflow WHEN it is validated THEN it reports no error, and the gate of the phase step names no step to go back to ([MAP-B11](../../../tempergraph/docs/specs/map-unit.spec.md))

### PHC-B15 A trip back runs every phase again

WHEN the code gate sends the run back to the plan step and the run reaches the phase items again THE workflow SHALL run every phase of the plan as it then stands, each building only its rows whose Completed cell is empty ([MAP-B3](../../../tempergraph/docs/specs/map-unit.spec.md)).

- GIVEN a plan of two phases that passed, a code gate that sends the run back to the plan step, and a plan that keeps every mark WHEN the run reaches the phase items again THEN both phases run again, change no file, make no commit and pass their gates
- GIVEN the same trip back and a plan that rewrote row 2.2 and emptied its mark WHEN the phase items run THEN phase 1 changes no file and phase 2 builds row 2.2 only

### PHC-B16 The phase check sorts the changed paths for its judge

WHEN a phase attempt passes its check THE phase check SHALL hand its judge the paths the run changed since its base as two lists, each in ascending order of path, a list that holds no path stating so: the paths changed since the commit at which the phase step was entered, and the paths that only earlier steps changed.

- GIVEN a triage note written by the triage step and `src/a.py` written by the first phase WHEN the first phase passes its check THEN the evidence lists `src/a.py` among the paths changed since the phase step was entered and the note among the paths that only earlier steps changed
- GIVEN `src/a.py` written by the first phase and `src/b.py` written by the second WHEN the second phase passes its check THEN both files are among the paths changed since the phase step was entered
- GIVEN the plan, written by the plan step and the expand step and marked by the phase WHEN the phase passes its check THEN the plan is among the paths changed since the phase step was entered and not among the paths that only earlier steps changed

### PHC-B17 A path that only earlier steps changed is listed with its step

WHEN the phase check lists a path that only earlier steps changed THE phase check SHALL name beside the path each step whose commit changed it, in the order of the commits.

- GIVEN a triage note written by the triage step WHEN a phase passes its check THEN the note is listed with the step `triage`
- GIVEN a spec written by the discovery step and edited by the plan step WHEN a phase passes its check THEN the spec is listed with the steps `discovery` and `plan`, in that order
- GIVEN a path changed by a commit that names no step WHEN a phase passes its check THEN the path is listed with no step name

### PHC-B18 The phase judge takes the check's sorting as given

WHEN the phase judge is briefed THE workflow SHALL tell it that the check has sorted the changed paths into the paths changed since the phase step was entered and the paths that only earlier steps changed, and that it takes that sorting as given.

- GIVEN the brief of the phase judge WHEN it is read THEN it says that the check sorted the changed paths, and that the judge takes that sorting as given and does not look for the step that changed a path
- GIVEN the same brief WHEN it is read THEN it tells the judge to grade `ts-phs-scope` on the paths changed since the phase step was entered, so that a path that only an earlier step changed lowers no grade and sets no gap

### PHC-B19 The join is handed the changed paths sorted the same way

WHEN the code step ends after the phase items THE code gate SHALL hand its judge the paths the run changed since its base as the two lists of PHC-B16 and PHC-B17, counted from the commit at which the code step was entered.

- GIVEN two phases that changed `src/a.py` and `src/b.py` and a code session that changed only the plan's status WHEN the code gate hands its judge the evidence THEN the plan is among the paths changed since the code step was entered and the two source files are among the paths that only earlier steps changed, each listed with the step `phase`
- GIVEN a code session that changed no file WHEN the code gate hands its judge the evidence THEN the list of paths changed since the code step was entered states that it holds no path

## Acceptance criteria

- PHC-AC1 (PHC-B1): In a stand-in run of a plan of three phases that all pass, three phase items run in the order of the plan, each after the gate of the one before it has passed, and they are named `p1`, `p2` and `p3`; in a run of a plan of one phase one item runs
- PHC-AC2 (PHC-B2): In the same run three sessions start, none resuming another, and the brief of the session of phase 2 carries the heading, the goal and the weight of phase 2 and the path of the plan, and neither the heading of phase 1 nor that of phase 3
- PHC-AC3 (PHC-B3): The brief of a phase session tells it to build only the rows of its phase whose Completed cell is empty and to leave every other mark as it is, to write the phase's tests first and see them fail, to run after the phase only the test files its rows name and never the plan's verification commands, to change no file that no row of the phase names but the plan's marks and status, to mark each row it built with `✓` and the day's date in one edit of the plan after the test files of the phase pass, and to run no `git commit`
- PHC-AC4 (PHC-B4): The brief of a phase session asks for one line of at most 1,500 characters that names the test files run and each deviation from the plan with its reason, or `none`, and a phase session that ends with no note runs again, alone
- PHC-AC5 (PHC-B5): In a stand-in run of three phases that each write one file, the branch holds after the commit of the expand step one commit for each phase in plan order with that phase's files and the marks of its rows, the session of phase 2 starts with the files of phase 1 committed and no change in the working tree, and a phase attempt that changes no file makes no commit
- PHC-AC6 (PHC-B6): The phase check fails naming row 2.2 for a phase whose session marked only row 2.1, fails naming a marked row whose file is the same as at the run's base commit, makes no finding about the rows of another phase, and makes no finding about a marked row of an earlier visit whose file differs from the run's base commit
- PHC-AC7 (PHC-B7): The phase check fails naming the row for a test row whose file has no test that carries the criterion it proves and for one whose only such test is skipped, and makes no finding for a test that carries the criterion and runs
- PHC-AC8 (PHC-B8): The phase check fails naming phase 2 for a record that edits the phase's source file and then writes its test file, makes no finding about the order for the reverse order, and records the order criterion not applicable when the engine gives it no session record
- PHC-AC9 (PHC-B9): A stand-in run of three phases that pass holds three judge sessions for them besides the judge session of the code step, and a phase attempt whose check fails starts no judge session
- PHC-AC10 (PHC-B10): In a stand-in run in which the first attempt of phase 2 leaves a row unmarked, phase 2 runs a second session, phase 1 runs one session, phase 3 starts after phase 2 has passed and runs one session, and the commit of phase 1 is still on the branch; in a run in which phase 2 spends its retries, the run pauses at `phase.p2` and phase 3 starts no session
- PHC-AC11 (PHC-B11): In a stand-in run of three phases that pass, the code step starts after the gate of phase 3 has passed and one code session runs on the whole change, and in a run that pauses at phase 2 the code step has not started
- PHC-AC12 (PHC-B12): The brief of the code step after three phases lists the notes of phases 1, 2 and 3 in that order, each led by its phase, and says that when the notes list the phases the session builds only a row whose Completed cell is empty, sets the plan's status to `completed` and writes the code report with each deviation the notes name; in a run on the arm `single` and in a quick-lane run its brief lists no note and says that no phase ran
- PHC-AC13 (PHC-B13): In a stand-in run of two phases that pass, a verification command of the plan that exits 0 at the run's base commit and fails when the code gate runs it fails the code step and only the code step runs again with no phase session started; the gate makes no finding about the files of rows that the phases changed, fails a plan whose status is not `completed` before any command runs, and records the quick-lane guard not applicable
- PHC-AC14 (PHC-B14): In stand-in runs of two phases whose code session claims that the plan step, the discovery step or the triage step is at fault, with a gate that accepts the claim, the run goes back to the step named in each run, and the workflow validates with no error and no step to go back to on the gate of the phase step
- PHC-AC15 (PHC-B15): In a stand-in run of two phases that pass, a code gate that sends the run back to the plan step and a plan that keeps every mark, both phases run again, change no file, make no commit and pass; with row 2.2 rewritten and its mark emptied, phase 1 changes no file and phase 2 builds row 2.2 only
- PHC-AC16 (PHC-B16): The evidence of a phase that passes its check holds two lists of the paths the run changed since its base, each in ascending order of path and each stating that it holds no path when it holds none: the paths changed since the phase step was entered, which include a path that an earlier step and the phase both changed, and the paths that only earlier steps changed
- PHC-AC17 (PHC-B17): Each path of the second list is listed with each step whose commit changed it, in the order of the commits, and a path changed by a commit that names no step is listed with no step name
- PHC-AC18 (PHC-B18): The brief of the phase judge says that the check sorted the changed paths into the two lists and that the judge takes that sorting as given and does not look for the step that changed a path, and tells the judge to grade `ts-phs-scope` on the first list alone, a path of the second list lowering no grade and setting no gap
- PHC-AC19 (PHC-B19): In a stand-in run of two phases that pass, the evidence of the code gate holds the two lists counted from the commit at which the code step was entered, with the files of the two phases among the paths that only earlier steps changed, each listed with the step `phase`, and states that the first list holds no path when the code session changed no file
- PHC-AC20 (PHC-B9, PHC-B16, PHC-B17): In a stand-in run of two phases on the arm `phases` in which an earlier step wrote a document and each phase changes only the files of its rows, the evidence of each phase lists the document with its step among the paths that only earlier steps changed, and each phase gate passes with no pause

## Open questions

- How should the commit of a phase name its phase? The engine gives the script that commits a step's files the name of the step and not the id of the item, so every phase commit says `phase` and only the marks inside the commit tell which phase it holds. Until answered: the message names the step and the task, not the phase. Reopen when the engine gives such a script its item. Owner: owner.
- How many phases may a plan have? The map takes 20 items unless told otherwise and 50 at most ([MAP-B7](../../../tempergraph/docs/specs/map-unit.spec.md)), and the plan rule caps no number of phases, so a plan with more phases than the map takes stops the run at the map, naming the count, before any phase starts ([MAP-B5](../../../tempergraph/docs/specs/map-unit.spec.md)). Until answered: the map keeps the engine's default of 20 and the plan rule is not changed. Owner: owner.
- What should a phase do when the plan or a spec it rests on is at fault? A phase has no line back ([MAP-B11](../../../tempergraph/docs/specs/map-unit.spec.md)). Until answered: the session leaves the row unmarked and names the row and the conflict in its note, the check fails the row, and when the retries are spent the run pauses at the phase for a person ([MAP-B10](../../../tempergraph/docs/specs/map-unit.spec.md)). Owner: owner.
