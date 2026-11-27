# Kept marks

## Purpose

What becomes of a plan's completed marks when a later gate sends the run back to the plan step (a trip back). The files of the run stay as they are, so a row the code step already built keeps its mark while nothing about it changes, and the code step after the trip builds only the rows the trip changed. A commit of the run is a commit made after the run's base commit; a row's marking commit is the earliest commit of the run in which a row with that id carries the mark the plan now carries. It also says when and in how many edits the code step and a phase session ([phase coding](phase-coding.spec.md)) are told to write the completed marks of the rows they build. The plan, expand and code steps and the owner who reads a run depend on it. Part of the [overview](overview.spec.md).

## Does not own

- The plan, its marks and its status as the plan step writes them: `plan.spec.md`
- How the expand step adds to the plan: `expand.spec.md`
- What the code step builds from the plan: `code.spec.md`

## Behaviours

### KMK-B1 A kept mark is accepted

WHEN the plan that a step hands over carries a completed mark on a row that reads the same as in its marking commit (same id, kind, requirement, file, proof and change) and whose file no later commit of the run changed THE plan and expand checks SHALL accept the mark.

- GIVEN rows 1.1 and 1.2 marked `✓ 2026-11-22` by one commit of the run, a plan after a trip back that leaves both rows as they were with their marks and the status `planned`, and no later commit that changed their files WHEN the plan check runs THEN it accepts both marks
- GIVEN a complex plan whose rows 1.1 and 1.2 the expand step leaves as they were with their marks, and the same history WHEN the expand check runs THEN it accepts both marks

### KMK-B2 A mark on a changed row is refused

WHEN the plan that a step hands over carries a completed mark on a row whose kind, requirement, file, proof or change differs from the row in its marking commit THE plan and expand checks SHALL refuse the mark, naming the row.

- GIVEN row 3.2 marked `✓ 2026-11-22` with the change "Report the missing file", and a plan that rewrites the change to "Report the missing file and exit with code 2" and keeps the mark WHEN the plan check runs THEN it refuses the mark and names row 3.2
- GIVEN the same row 3.2 and a plan that names another file for it and keeps the mark WHEN the plan check runs THEN it refuses the mark and names row 3.2
- GIVEN the same row 3.2 and a plan that changes the row and empties its Completed cell WHEN the plan check runs THEN it makes no finding about row 3.2

### KMK-B3 A mark on a row whose file changed since is refused

WHEN the plan that a step hands over carries a completed mark on a row whose file a commit of the run changed after the row's marking commit THE plan and expand checks SHALL refuse the mark, naming the row.

- GIVEN row 2.1 marked `✓ 2026-11-22` by one commit of the run, a later commit of the run that changed its file, and a plan that leaves the row as it was with its mark WHEN the plan check runs THEN it refuses the mark and names row 2.1
- GIVEN the same plan and a later commit of the run that changed only the file of another row WHEN the plan check runs THEN it accepts the mark of row 2.1

### KMK-B4 A mark that no commit wrote is refused

WHEN the plan that a step hands over carries a completed mark on a row that has no marking commit for that mark THE plan and expand checks SHALL refuse the mark, naming the row.

- GIVEN a plan with a new row 4.1 marked `✓ 2026-11-24` and no commit of the run that marks a row 4.1 WHEN the plan check runs THEN it refuses the mark and names row 4.1
- GIVEN row 1.1 marked `✓ 2026-11-22` by a commit of the run and a plan that marks it `✓ 2026-11-24` WHEN the plan check runs THEN it refuses the mark and names row 1.1
- GIVEN a run with no base commit to count its commits from and a plan that marks any row WHEN the plan check runs THEN it refuses the mark and names the row

### KMK-B5 The planning steps are told to keep a mark

WHEN the plan step or the expand step is briefed THE workflow SHALL tell the session to keep the completed mark of each row it leaves exactly as it was.

- GIVEN the prompt of the plan step, the prompt of the expand step and the plan rule WHEN each is read THEN each tells the session to keep the completed mark of a row it leaves exactly as it was
- GIVEN the same three texts WHEN each is read THEN none tells the session to leave every Completed cell empty

### KMK-B6 The planning steps are told to empty the mark of a changed row

WHEN the plan step or the expand step is briefed THE workflow SHALL tell the session to empty the Completed cell of each row it changes or adds.

- GIVEN the prompt of the plan step, the prompt of the expand step and the plan rule WHEN each is read THEN each tells the session to empty the Completed cell of a row whose kind, requirement, file, proof or change it edits, and of every row it adds

### KMK-B7 The code step is told to build only the rows without a mark

WHEN the code step is briefed THE workflow SHALL tell the session to build only the rows whose Completed cell is empty.

- GIVEN the prompt of the code step and the plan rule WHEN each is read THEN each tells the session to build only the rows whose Completed cell is empty
- GIVEN the same two texts WHEN each is read THEN each tells the session to leave the mark of every other row as it is

### KMK-B8 A kept row's file need not change again

WHEN the code step hands over a plan in which a marked row's file differs from the run's base commit THE code check SHALL accept the row's mark whichever visit of the code step changed the file.

- GIVEN row 1.2 marked `✓ 2026-11-22` by the first visit of the code step with its file different from the run's base commit, and a second visit after a trip back that changed only the file of row 2.1 WHEN the code check runs THEN it makes no finding about the file of row 1.2

### KMK-B9 A phase's marks are written in one edit after its tests pass

WHEN the code step or a phase session is briefed to build the rows of a plan's phase THE workflow SHALL tell the session to write the completed marks of all the rows it built in that phase in one edit of the plan, after the change of each row is in its file and the test files that the phase's rows name pass.

- GIVEN the prompt of the code step, the prompt of a phase session and the plan rule WHEN each is read THEN each tells the session to write the completed marks of the rows it built in one phase in one edit of the plan, a single change to the plan file that marks all of them, and not in one edit for each row
- GIVEN the same three texts WHEN each is read THEN each tells the session to write those marks after the change of each row is in its file and the test files that the phase's rows name pass, and not before
- GIVEN a plan of two phases built in one code session WHEN the prompt of the code step is read THEN it tells the session to write the marks of phase 1 in one edit after the test files of phase 1 pass and the marks of phase 2 in one edit after the test files of phase 2 pass, and not the marks of both phases in one edit

## Acceptance criteria

- KMK-AC1 (KMK-B1): The plan check accepts the marks of two rows that a plan leaves as their marking commit had them, when no later commit of the run changed their files
- KMK-AC2 (KMK-B1): The expand check accepts the marks of two rows of a complex plan that the expand step leaves as their marking commit had them, when no later commit of the run changed their files
- KMK-AC3 (KMK-B2): The plan check and the expand check each refuse the mark of a row whose change, or whose file, differs from the row in its marking commit, and name the row
- KMK-AC4 (KMK-B2): The plan check makes no finding about a changed row whose Completed cell is empty
- KMK-AC5 (KMK-B3): The plan check and the expand check each refuse the mark of a row whose file a later commit of the run changed, and name the row
- KMK-AC6 (KMK-B3): The plan check accepts the mark of a row when the only later commit of the run changed the file of another row
- KMK-AC7 (KMK-B4): The plan check and the expand check each refuse a mark on a row that has no commit of the run carrying that mark, and name the row
- KMK-AC8 (KMK-B4): The plan check refuses the mark `✓ 2026-11-24` on a row that a commit of the run marked `✓ 2026-11-22`, and names the row
- KMK-AC9 (KMK-B4): The plan check refuses a mark in a run that has no base commit, and names the row
- KMK-AC10 (KMK-B5): The prompt of the plan step, the prompt of the expand step and the plan rule each tell the session to keep the completed mark of a row it leaves exactly as it was
- KMK-AC11 (KMK-B5): None of the prompt of the plan step, the prompt of the expand step and the plan rule tells the session to leave every Completed cell empty
- KMK-AC12 (KMK-B6): The prompt of the plan step, the prompt of the expand step and the plan rule each tell the session to empty the Completed cell of a row it changes and of a row it adds
- KMK-AC13 (KMK-B7): The prompt of the code step and the plan rule each tell the session to build only the rows whose Completed cell is empty
- KMK-AC14 (KMK-B7): The prompt of the code step and the plan rule each tell the session to leave the mark of every other row as it is
- KMK-AC15 (KMK-B8): The code check makes no finding about the file of a row marked by the first visit of the code step, whose file differs from the run's base commit, when the second visit changed only the file of another row
- KMK-AC16 (KMK-B9): The prompt of the code step, the prompt of a phase session and the plan rule each tell the session to write the completed marks of the rows it built in one phase in one edit of the plan, and not in one edit for each row
- KMK-AC17 (KMK-B9): The prompt of the code step, the prompt of a phase session and the plan rule each tell the session to write those marks after the change of each row is in its file and the test files that the phase's rows name pass
