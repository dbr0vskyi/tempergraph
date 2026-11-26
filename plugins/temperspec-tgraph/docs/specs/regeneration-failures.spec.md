# Regeneration failures

## Purpose

How a regeneration that fails reaches the code step, once: what the code step is given, which step runs, and the pause when the trip did not help or the failure is not one the code step can fix. A regeneration *fails* when its command ends with an exit code other than 0; it fails *for the environment* when its command does not start, is ended by a signal or does not finish in time. [Regeneration](regeneration.spec.md) owns what runs, when and what is committed, and this spec does not own them. The engine's rule that sends a run back from a gate with no judge, bounded by a loop budget, is [HUM-B15](../../../tempergraph/docs/specs/gate-and-human.spec.md) to [HUM-B17](../../../tempergraph/docs/specs/gate-and-human.spec.md), and the unit uses it. The owner who reads a run's pause and the maintainers of a repository's generated files depend on it. Part of the [overview](overview.spec.md); the unit is [regenerate](regeneration.spec.md).

## Behaviours

### RGF-B1 A failed regeneration sends the run back to the code step

WHEN a due regeneration fails and the failure is not one of the environment THE workflow SHALL send the run back to the code step, giving it as the reason of its visit one numbered finding for each thing the command reported, in the order it reported them.

- GIVEN a due regeneration whose command exits 2 after it reported three findings WHEN the unit ends THEN the code step has a second visit whose reason lists three findings, numbered 1 to 3 in the order the command reported them
- GIVEN a regeneration that fails once and passes after the code step's second visit WHEN the run goes on THEN the unit runs a second time, passes, and the run goes on with no pause
- GIVEN a due regeneration whose command exits 0 WHEN the unit ends THEN no trip back is made

### RGF-B2 One trip carries the findings of every regeneration that failed

WHEN a due regeneration fails and the failure is not one of the environment THE regeneration unit SHALL run the due regenerations that follow it as well, so that the one trip back carries the findings of every regeneration that failed, in the order the declaration lists the regenerations.

- GIVEN two due regenerations that both fail WHEN the unit ends THEN one trip back is made and its reason lists the findings of the first regeneration, then those of the second, numbered from 1 in one run
- GIVEN two due regenerations of which only the second fails WHEN the unit ends THEN one trip back is made with the findings of the second alone

### RGF-B3 A report of the engine's two commands makes one finding for each thing it reports

WHEN a failed regeneration command printed the JSON that `tempergraph author verify --json` or `tempergraph upgrade-check --json` prints THE workflow SHALL make one finding for each error finding and each failed check the report holds, with the rung or check, the code, the unit, the message and the remedy as the report gives them.

- GIVEN an `author verify` report whose rung `compare` holds one finding with the code `blueprint-difference`, the unit `plan`, a message and a remedy WHEN the regeneration fails THEN one finding holds `compare`, `blueprint-difference`, `plan`, that message and that remedy
- GIVEN an `upgrade-check` report whose check `V4 audit` failed with the evidence `new findings: outcome-unverified-blocker` WHEN the regeneration fails THEN one finding holds `V4 audit` and that evidence
- GIVEN an `author verify` report whose rungs `load` and `compare` each hold one finding WHEN the regeneration fails THEN two findings come in the order of the report, that of `load` first

### RGF-B4 Any other failed command makes one finding

WHEN a failed regeneration command printed no such report THE workflow SHALL make one finding for it, holding the command, its exit code and the last 40 lines of its output as the engine's command run keeps them ([CHK-B12](../../../tempergraph/docs/specs/check-contract-and-command-runs.spec.md)).

- GIVEN a command `make docs` that prints three lines of errors and exits 2 WHEN the unit ends THEN one finding holds `make docs`, the exit code 2 and the three lines
- GIVEN a command that prints JSON of another form and exits 1 WHEN the unit ends THEN one finding holds the command, the exit code 1 and the last lines of its output

### RGF-B5 The code step is told to fix those findings and nothing else

WHEN the code step is entered with the findings of a failed regeneration as its reason THE workflow SHALL tell its session to fix those findings and to change nothing else.

- GIVEN the code prompt WHEN it is read THEN it says that a visit whose reason lists the findings of a failed regeneration fixes those findings, changes no file that fixing them does not need and edits no generated file by hand
- GIVEN a visit that follows a failed regeneration WHEN its brief is rendered THEN the brief holds the numbered findings under the reason of the visit

### RGF-B6 Only the code step runs a second time

WHEN a failed regeneration sends the run back THE workflow SHALL run the code step and no step before it, whether the plan was built at once or one phase at a time.

- GIVEN a run that built its plan one phase at a time and a regeneration that fails once WHEN the run goes back THEN one more code session runs and neither the expand step nor a phase item starts
- GIVEN a run that built its plan at once and a regeneration that fails once WHEN the run goes back THEN one more code session runs and neither the plan step nor the discovery step runs
- GIVEN the code step passes its gate after the visit WHEN the run goes on THEN the regeneration unit runs a second time, before the review

### RGF-B7 A failure after the trip pauses the run

WHEN a regeneration fails after the run has gone back to the code step once for a failed regeneration THE workflow SHALL pause the run instead of sending it back a second time, showing in the pause each finding left by its number and its text.

- GIVEN a regeneration that fails on the first pass and on the second pass after the code step's visit WHEN the unit ends the second time THEN the run pauses and the pause lists the findings of the second failure, each with its number and its text
- GIVEN a regeneration that fails the first time and passes after the visit WHEN the unit ends the second time THEN the run does not pause
- GIVEN a run that the review sent back to the code step and a regeneration that fails for the first time after that visit WHEN the unit ends THEN the run goes back to the code step

### RGF-B8 A failure of the environment pauses the run at once

WHEN a due regeneration's command is refused, does not start, is ended by a signal, or has not finished after 600 seconds THE workflow SHALL pause the run at once and send nothing back.

- GIVEN a command whose program does not exist, or one the unit refuses ([RGN-B10](regeneration.spec.md)), WHEN the unit runs it THEN the run pauses at the unit with kind `escalation`, no trip back is made and the check's evidence names the command
- GIVEN a command that has not finished after 600 seconds WHEN the limit passes THEN it is ended, the run pauses and nothing is sent back
- GIVEN a command that exits with 1 WHEN the unit runs it THEN the failure is sent back as [RGF-B1](regeneration-failures.spec.md) says and the run does not pause

## Acceptance criteria

- RGF-AC1 (RGF-B1): A fixture run whose regeneration fails once with three findings enters the code step a second time with a reason that lists three numbered findings in the order reported, the regeneration passes on the second visit, and the run goes on with no pause
- RGF-AC2 (RGF-B2): A fixture run with two due regenerations that both fail makes one trip back whose reason lists the findings of the first, then those of the second, numbered from 1 in one run, and one whose only second regeneration fails makes one trip back with its findings alone
- RGF-AC3 (RGF-B3): A fixture command that prints an `author verify` report with the failures of summary over 60 characters, check with no pass case and no fail case, blocker that no case verifies and blueprint difference, and an `upgrade-check` report with a failed check, comes back as one finding for each, each holding the rung or check, the code, the unit, the message and the remedy as the report gives them, so that a file the report names is named in the finding
- RGF-AC4 (RGF-B4): A fixture command that exits 2 with errors printed, and one that prints JSON of another form and exits 1, each come back as one finding holding the command, its exit code and the last lines of its output
- RGF-AC5 (RGF-B5): The code prompt says that a visit whose reason lists the findings of a failed regeneration fixes those findings and changes nothing else, and the brief of such a visit holds the numbered findings under its reason
- RGF-AC6 (RGF-B6): In a fixture run on each arm the trip back starts one code session and no expand step, no phase item, no plan step and no discovery step, and the unit runs a second time, before the review, after the code step passes
- RGF-AC7 (RGF-B7): A fixture run whose regeneration fails twice pauses after the second failure and the pause lists the findings left with their numbers and texts, a run whose second pass succeeds does not pause, and a run that the review sent back is sent back once more by a first regeneration failure
- RGF-AC8 (RGF-B8): A fixture command whose program does not exist, one the unit refuses and one that has not finished after 600 seconds each pause the run at the unit with kind `escalation` and send nothing back, and a command that exits with 1 is sent back and does not pause
