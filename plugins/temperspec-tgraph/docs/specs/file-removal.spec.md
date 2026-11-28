# File removal

## Purpose

How the file of a removal row goes away. A *removal row* is a task row of kind `remove` ([plan task rows](plan-rows.spec.md)); it is *marked* when its Completed cell holds `✓` and a date. A session of the code step or of a phase has tools that create and change files and run commands, and none that deletes or moves a file, so the workflow removes the file itself: when the session ends, and before the step's check reads the workspace, it removes the file of each marked removal row, starts no model session for it, and commits the removal with the session's files. A file that moves is a removal row for its old path and a row of another kind for its new path, which the session writes while the old file is still in the workspace. A change that needs a file removed or moved is a change of a plan, so it is not a change of the quick lane. The owner who reads a run's branch and the maintainers of the plan, phase and code steps depend on it. Part of the [overview](overview.spec.md).

## Depends on

- `plan-rows.spec.md`: the removal row, a task row of kind `remove` (PRW-B1)
- `repository-commands.spec.md`: the commands the code step's session may run (RCM-B5)
- `kept-marks.spec.md`: a kept mark is accepted when no later commit changed the row's file (KMK-B1)
- Outside: git, which commits the removal with the session's files

## Does not own

- How a generated file is refreshed and committed: `regeneration.spec.md`
- How a phase's files are committed when its attempt ends: `phase-coding.spec.md`
- What the code check requires of the rows of a plan: `code.spec.md`

## Behaviours

### FRM-B1 A session has no tool that deletes or moves a file

WHEN the workflow starts the session of the code step or of a phase THE workflow SHALL give it tools that read, search and list files, create and change files, and run the commands of [RCM-B5](repository-commands.spec.md), and no tool that deletes or moves a file.

- GIVEN the tools declared for the code step and for a phase WHEN they are listed THEN each holds tools that read, search, list, create and change files and run commands, and none that deletes or moves a file

### FRM-B2 The file of a marked removal row is removed when the session ends

WHEN the session of the code step or of a phase ends with no timeout or error and a removal row of the plan ([PRW-B1](plan-rows.spec.md)) is marked while the row's file is still in the workspace THE workflow SHALL remove that file before the code check or the phase check reads the workspace.

- GIVEN a plan with a removal row for `src/old.py` and a session that marks the row WHEN the session ends THEN `src/old.py` is not in the workspace when the check reads it
- GIVEN the same plan and a session that leaves the row's Completed cell empty WHEN the session ends THEN `src/old.py` is still in the workspace
- GIVEN the same plan and a session that marks the row and ends in a timeout WHEN the attempt ends THEN `src/old.py` is still in the workspace

### FRM-B3 No session carries out a removal

WHEN the workflow removes the file of a removal row THE workflow SHALL start no model session for the removal.

- GIVEN a fixture run with a scripted executor that counts its sessions and a plan whose removal row the session marks WHEN the file is removed THEN the count is the same before and after the removal

### FRM-B4 A removal is committed with the session's files

WHEN the workflow has removed a file THE workflow SHALL commit the removal together with the files and the plan's marks of the same attempt.

- GIVEN a phase whose session changes `src/new.py` and marks a removal row for `src/old.py` WHEN the attempt ends THEN the run's branch holds one commit of the phase that holds the change to `src/new.py`, the plan's marks and the deletion of `src/old.py`, and the workspace holds no uncommitted change
- GIVEN that commit and a trip back to the plan step that leaves the removal row as it was with its mark WHEN the plan check runs THEN it accepts the mark ([KMK-B1](kept-marks.spec.md))

### FRM-B5 A file that is already gone passes

WHEN the file of a marked removal row is not in the workspace THE workflow SHALL carry out nothing for that row and let the attempt go on.

- GIVEN a second visit of the code step whose first visit removed `src/old.py`, with the row's mark kept WHEN the second session ends THEN nothing is removed and the attempt does not fail for the row

### FRM-B6 A path that cannot be removed pauses the run

WHEN the file of a marked removal row is a folder, lies outside the workspace, or is refused by the file system THE workflow SHALL remove nothing for that row and pause the run at once, naming the path and the reason.

- GIVEN a marked removal row whose path is a folder WHEN the session ends THEN the folder and its files are still there, the run pauses and the pause names the folder
- GIVEN a marked removal row whose file is `../outside.txt`, a file that exists WHEN the session ends THEN `outside.txt` still exists, the run pauses and the pause names the path
- GIVEN a marked removal row whose file the file system refuses to remove WHEN the session ends THEN the run pauses, the pause names the file and the reason, and the step makes no second attempt

### FRM-B7 A preview does not fail a removal not yet carried out

WHEN the session runs the preview of the code check while a removal row is marked and its file is still in the workspace THE check SHALL not fail that row.

- GIVEN a plan marked completed whose removal row's file is in the workspace WHEN the session runs the preview THEN the preview lists no failure for the row
- GIVEN the same plan, and the file removed after the session ended WHEN the code check runs at the gate THEN it passes the row
- GIVEN the same plan, and the file still in the workspace WHEN the code check runs at the gate THEN it fails, naming the row

### FRM-B8 The code and phase sessions are told when to mark a removal row

WHEN the code step and a phase session are briefed THE workflow SHALL tell each to mark a removal row once no other row of the plan needs its file, and that the workflow removes that file after the session ends.

- GIVEN the prompt of the code step, the prompt of a phase session and the plan rule WHEN each is read THEN each says to mark a removal row once no other row of the plan needs its file
- GIVEN the same two prompts WHEN each is read THEN each says that the session deletes and moves no file and that the workflow removes the file after the session ends

### FRM-B9 A change that removes or moves a file is outside the quick lane

WHEN triage and the code step are briefed THE workflow SHALL tell each that a change that removes or moves a file is not a change of the quick lane.

- GIVEN the prompt of triage and the rule for task notes WHEN each is read THEN each says that a task whose change removes or moves a file takes the route `plan`
- GIVEN the prompt of the code step WHEN it is read THEN it says that a quick-lane change that needs a file removed or moved ends with `UPSTREAM triage: the task is larger than the quick lane`

## Acceptance criteria

- FRM-AC1 (FRM-B1): The tools declared for the code step and for the phase step each hold the tools that read, search, list, create and change files and run commands, and none that deletes or moves a file
- FRM-AC2 (FRM-B2): A fixture run of the arm `single` and a fixture run of the arm `phases`, each with a plan that has a removal row for an existing file and a session that marks the row, end with the file absent from the run's branch and with no pause
- FRM-AC3 (FRM-B2): A removal row whose Completed cell the session leaves empty keeps its file when the session ends, and so does a marked removal row when the session ends in a timeout, in a fixture run of each arm
- FRM-AC4 (FRM-B3): A fixture run with a scripted executor that counts sessions holds the same count before and after the removal of the file of a marked removal row
- FRM-AC5 (FRM-B4): After a phase attempt that changes a file and marks a removal row, the run's branch holds one commit of the phase with the change, the plan's marks and the deletion, the workspace holds no uncommitted change, and the plan check accepts the kept mark of the row after a trip back to the plan step
- FRM-AC6 (FRM-B5): A second visit of the code step whose first visit removed the file of a marked removal row removes nothing and does not fail for the row
- FRM-AC7 (FRM-B6): A fixture run whose marked removal row names a folder, one whose row names `../outside.txt` and one whose file the file system refuses to remove each pause at once naming the path, and leave the folder with its files and the file outside the workspace as they were
- FRM-AC8 (FRM-B7): The preview of the code check lists no failure for a marked removal row whose file is in the workspace, and the code check at the gate passes the row once the file is removed and fails it, naming the row, while the file is in the workspace
- FRM-AC9 (FRM-B8): The prompt of the code step, the prompt of a phase session and the plan rule each say to mark a removal row once no other row needs its file, and the two prompts say that the session deletes and moves no file and that the workflow removes the file after the session ends
- FRM-AC10 (FRM-B9): The prompt of triage and the rule for task notes each say that a task whose change removes or moves a file takes the route `plan`, and the prompt of the code step says that a quick-lane change that needs one ends with `UPSTREAM triage: the task is larger than the quick lane`
