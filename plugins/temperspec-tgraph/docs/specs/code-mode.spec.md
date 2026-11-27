# Code mode

## Purpose

What chooses, once the plan has passed its gate, between building the plan at once in the one code session (`single`) and having the expand step write its task rows first and then building the plan one phase at a time (`phases`). The choice is the engine's complexity switch `code_mode` ([CXR](../../../tempergraph/docs/specs/complexity-routing.spec.md)): it measures facts that the plan check records, reads its limits from `routing/code_mode.json` in the package, takes `phases` whenever it cannot decide, and lets the operator name the arm when a run starts. The switch is a unit of its own with no session, no gate, no approval and no file. The limits are the plan rule's limits for a simple plan ([plan rule](../../rules/plan.rule.md), and `ts-plan-size` of the [plan spec](plan.spec.md)), so a plan the check passes as `simple` takes `single`, one it passes as `complex` takes `phases`, and no step's own word for its complexity decides the arm. Both arms end in the same code step with the same gate: on `single` its one session builds the whole plan, and on `phases` it follows the phase items, which have built and committed the plan one phase at a time ([phase coding](phase-coding.spec.md)), and its gate checks the whole change. The operator who starts a run, the owner who reads the report by arm and the maintainers of the plan check depend on it. Part of the [overview](overview.spec.md).

## Depends on

- `phase-coding.spec.md`: phase coding

## Behaviours

### CDM-B1 The route after the plan is the switch `code_mode`

WHEN a run passes the plan step THE workflow SHALL route through the complexity switch `code_mode`, whose arms are `single` and `phases` (the last being the safe arm), whose measures are facts of the plan check and whose rules are read from `routing/code_mode.json` in the package.

- GIVEN the workflow WHEN it is validated THEN it reports no error and the switch `code_mode` lists the arms `single` and `phases`, in that order
- GIVEN a run that passes the plan step WHEN it goes on THEN one `route` record names `code_mode`, the arm taken, the zone and the value of each measure

### CDM-B2 The plan check records the plan's measured signs

WHEN the plan check reads a plan THE plan check SHALL record seven facts, one for each sign of the plan rule's Complexity table: `phases`, `rows` (task rows), `test_rows`, `files` (files named by rows), `commands` (verification commands), `reading_bytes` (bytes of the files and specs the rows name) and `heavy_phases`, each the number the check itself measures for that sign.

- GIVEN a plan of 2 phases with 8 task rows, 4 of them test rows, naming 6 files, listing 2 verification commands, whose files and specs hold 90,000 bytes, with no heavy phase WHEN the plan check reads it THEN the facts are `phases` 2, `rows` 8, `test_rows` 4, `files` 6, `commands` 2, `reading_bytes` 90000 and `heavy_phases` 0
- GIVEN a plan of 5 phases with no task rows, as a complex plan has before the expand step WHEN the plan check reads it THEN `phases` is 5 and `rows`, `test_rows` and `files` are 0
- GIVEN a plan whose phases 1 and 2 are marked `Weight: heavy (refactor)` and `Weight: heavy (many-tests)` WHEN the plan check reads it THEN `heavy_phases` is 2

### CDM-B3 The arm follows the facts

WHEN the plan step passes THE workflow SHALL take `single` when every fact is within its bound in the rules file, and `phases` otherwise.

- GIVEN a plan that the plan check passes as `simple` WHEN the plan step passes THEN `single` is taken and the zone is `simple`
- GIVEN a plan of 5 phases that the plan check passes as `complex` WHEN the plan step passes THEN `phases` is taken and the zone is `complex`
- GIVEN a plan of 2 phases with one heavy phase and every other fact within its bound WHEN the plan step passes THEN `phases` is taken
- GIVEN a plan of 2 phases whose rows name files and specs of 300,000 bytes and every other fact within its bound WHEN the plan step passes THEN `phases` is taken

### CDM-B4 The limits are the plan rule's limits

WHEN the rules file `routing/code_mode.json` is read THE workflow SHALL bound `single` by the limits the plan rule gives a simple plan, one bound for each sign of its Complexity table.

- GIVEN each row of the plan rule's Complexity table WHEN the rules file is read THEN `single` is bounded for that sign by the row's limit, a heavy phase being bounded to none
- GIVEN the rules file WHEN it is read THEN it declares no margin band, so a plan inside its limits is never sent to `phases` for being near them

### CDM-B5 `phases` is the safe arm

WHEN a fact is missing, or the rules file is missing or not valid, THE workflow SHALL take `phases`.

- GIVEN a plan check that recorded no `phases` fact WHEN the plan step passes THEN `phases` is taken and the zone is `fault`
- GIVEN a repository override of the rules at `.tempergraph/routing/temperspec/code_mode.json` that is not valid JSON WHEN a run passes the plan step THEN `phases` is taken and the zone is `fault`

### CDM-B6 `single` goes straight to the code step

WHEN `single` is taken THE workflow SHALL run the code step on the plan as the plan step wrote it, with no expand step and no phase item.

- GIVEN a run that takes `single` WHEN it goes on THEN neither the expand step nor a phase item is entered, and one code session builds the whole plan, whose task rows the plan check verified

### CDM-B7 `phases` runs the expand step, the phases and then the code step

WHEN `phases` is taken THE workflow SHALL run the expand step on the plan, then one phase item for each phase of the plan ([phase coding](phase-coding.spec.md)), and the code step after the last of them.

- GIVEN a run that takes `phases` WHEN it goes on THEN the expand step is entered first, the phase items only after the expand step has passed its gate, and the code step only after the last phase item has passed its gate

### CDM-B8 The operator names the arm when the run starts

WHEN a run starts with `--arm code_mode=<arm>` THE workflow SHALL take that arm after the plan step, whatever the facts say, recorded as `chosen_by: operator`.

- GIVEN `--arm code_mode=phases` and a plan the plan check passes as `simple` WHEN the plan step passes THEN `phases` is taken, the expand step runs, and the `route` record says `chosen_by: operator` and `would_choose: single`
- GIVEN `--arm code_mode=single` and a plan of 5 phases WHEN the plan step passes THEN `single` is taken, no expand step runs, and the `route` record says `chosen_by: operator` and `would_choose: phases`

### CDM-B9 A quick-lane run takes no arm

WHEN a run goes from triage straight to the code step THE workflow SHALL take no arm of `code_mode`.

- GIVEN a task the triage note routes to the quick lane WHEN the run finishes THEN no `route` record names `code_mode` and no expand step ran

### CDM-B10 The report counts each run under its arm

WHEN `tempergraph report --switch temperspec/code_mode` runs THE report SHALL show, for each arm and zone, the finished runs that took it and their cost per phase.

- GIVEN finished runs that took `single` in the zone `simple` and `phases` in the zone `complex`, and one run on which the operator named `phases` for a plan whose facts gave the zone `simple` WHEN the report runs THEN the operator's run is counted under `phases` and the zone `simple`, apart from the runs of `phases` in the zone `complex`
- GIVEN 5 finished runs of `single`, each with a plan of 2 phases, that cost 10.00 USD in all WHEN the report runs THEN the cell of `single` shows 1.00 USD per unit of size, a unit being a phase

### CDM-B11 The trial run is a live check

WHEN the owner reads the package's live checks THE live checks SHALL hold a row for a trial run of the workflow, with its command and its pass criterion.

- GIVEN the live checks WHEN they are read THEN a row gives the command `tempergraph author verify <path to plugins/temperspec-tgraph> --trial --case missing-config --cap 15`
- GIVEN the same row WHEN it is read THEN its pass criterion is that the trial run reaches the outcome gate with a verdict other than `not_reached` and no pause, and that its `route` record names `code_mode` and an arm

## Acceptance criteria

- CDM-AC1 (CDM-B1): The workflow validates with no error, and its switch `code_mode` lists the arms `single` and `phases` in that order
- CDM-AC2 (CDM-B1): A run with scripted sessions that passes the plan step has one `route` record that names `code_mode`, the arm taken, the zone and the value of each of the seven measures
- CDM-AC3 (CDM-B2): For each plan fixture of the plan check, the seven facts it records equal the numbers the check measures for that plan
- CDM-AC4 (CDM-B2): A plan with no task rows records `rows`, `test_rows` and `files` as 0 and `phases` as the number of its phases
- CDM-AC5 (CDM-B3): A run with scripted sessions whose plan the plan check passes as `simple` takes `single` in the zone `simple`, and one whose plan it passes as `complex` takes `phases` in the zone `complex`
- CDM-AC6 (CDM-B3): A plan that is over exactly one limit, whether phases, a heavy phase or reading bytes, takes `phases`
- CDM-AC7 (CDM-B4): For each row of the plan rule's Complexity table, the bound of `single` in `routing/code_mode.json` is the row's limit
- CDM-AC8 (CDM-B4): `routing/code_mode.json` declares no margin band
- CDM-AC9 (CDM-B5): A run whose plan check recorded no `phases` fact takes `phases` in the zone `fault`
- CDM-AC10 (CDM-B5): A run whose repository override of the rules is not valid JSON takes `phases` in the zone `fault`
- CDM-AC11 (CDM-B6): In a run that takes `single` neither the expand step nor a phase item is ever entered, and the code step is entered after the plan step has passed
- CDM-AC12 (CDM-B7): In a run that takes `phases` the expand step is entered before the first phase item, the phase items only after the expand step has passed its gate, and the code step only after the last phase item has passed its gate
- CDM-AC13 (CDM-B8): A run started with `--arm code_mode=phases` on a plan that passes as `simple` takes `phases`, and its `route` record says `chosen_by: operator` and `would_choose: single`
- CDM-AC14 (CDM-B8): A run started with `--arm code_mode=single` on a plan of 5 phases takes `single`, and its `route` record says `chosen_by: operator` and `would_choose: phases`
- CDM-AC15 (CDM-B9): A run in the quick lane has no `route` record for `code_mode` and enters no expand step
- CDM-AC16 (CDM-B10): The report over runs of both arms, one of them chosen by the operator, has a cell for each arm and zone and counts the operator's run under the arm it took
- CDM-AC17 (CDM-B10): The report divides the cost of a cell by the sum of the phases of its runs
- CDM-AC18 (CDM-B11): The live checks hold a row whose command is the trial run of the case `missing-config`
- CDM-AC19 (CDM-B11): The pass criterion of that row names the outcome gate, a verdict other than `not_reached` and the `route` record of `code_mode`

## Open questions

- Should a run that comes back to the plan step choose its arm again? Until answered: no, the arm of the first pass is kept for the run ([CXR-B7](../../../tempergraph/docs/specs/complexity-routing.spec.md)), so a plan that outgrows `single` after a trip back still goes to the code step with the task rows it has. Owner: owner.
- What should `--arm code_mode=single` do when the plan has no task rows? Until answered: the arm is taken as named ([CXR-B6](../../../tempergraph/docs/specs/complexity-routing.spec.md)), and the code check fails the code step with `ts-code-rows` ("the plan has no task row"). Owner: owner.
