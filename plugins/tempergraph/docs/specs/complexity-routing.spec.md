# Complexity routing between decompositions

## Purpose

A workflow may do the same job in a simple shape (one step does the whole task) or a detailed shape (a plan step, a map over its items, a join), and choose per run by how complex the task is or by another parameter, because per-phase work can cost more than one session on small plans while long single sessions time out on large ones ([research `routing-by-complexity-between-decompositions`](../research/routing-by-complexity-between-decompositions.rsrch.md) F1). A complexity switch is a measured switch ([SWM](measured-switches.spec.md)) whose predicate the engine builds from declared measures and a rules file, with five added rules: measures are model-free, the most detailed arm is the failsafe and wins the margin, re-arming runs one way and once, every arm honours one arm contract for the units after it, and the choice is reported by arm and zone ([ADR `complexity-chooses-a-decomposition-through-a-measured-switch`](../adr/complexity-chooses-a-decomposition-through-a-measured-switch.adr.md)); no new unit kind is added ([ADR `new-node-kinds-keep-the-gated-unit`](../adr/new-node-kinds-keep-the-gated-unit.adr.md)). Workflow authors, the gate, effort ladders ([LAD](effort-ladder-and-model-escalation.spec.md)) and the promotion check ([PRO](promotion-check.spec.md)) depend on it; design notes are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### CXR-B1 Zones

WHEN a run reaches a complexity switch THE engine SHALL evaluate in order the `fault` zone (any measure faulted, or the rules file missing or invalid) taking the safe arm; the `margin` zone (any measure inside its margin band) taking the safe arm unless exploration picks; the `simple` zone taking the simplest arm whose every bound holds; and the `complex` zone (no arm's bounds hold) taking the safe arm.

- GIVEN arms `[direct, planned]`, rules `direct.when: {criteria: {max: 3}, files: {max: 2}}` and margin `criteria: {from: 4, to: 5}` WHEN `criteria` 2 and `files` 1 THEN the zone is `simple` and `direct` runs
- GIVEN the same switch WHEN `criteria` 2 and `files` 4 THEN the zone is `complex` and `planned` runs
- GIVEN the same switch WHEN `criteria` 4 and `files` 1 THEN the zone is `margin` and `planned` runs
- GIVEN the same switch WHEN `criteria` faults THEN the zone is `fault` and `planned` runs

### CXR-B2 Shadow first

WHEN a complexity switch is in `mode: shadow` THE engine SHALL run the safe arm and record the arm and zone the rules chose as `would_choose` and `zone`.

- GIVEN the switch of CXR-B1 in shadow mode WHEN a run has `criteria: 2, files: 1` THEN `planned` runs and the route record holds `would_choose: direct, zone: simple`

### CXR-B3 One-way re-arm on evidence

WHEN a unit named in a `rearm` entry spends its budget or times out THE engine SHALL re-arm to the later arm with `chosen_by: rearm` only when the attempt that spent the budget carried climbing evidence ([LAD-B10](effort-ladder-and-model-escalation.spec.md)) or the timeout was a step timeout, and otherwise, or after one re-arm in the run, apply the gate's `on_budget_spent`.

- GIVEN `rearm: [{from: direct, to: planned, units: [do_all], on: [budget_spent, timeout]}]` WHEN `do_all`'s last attempt was a judge RETRY from an `accepted` judge on a substantive blocker THEN the run re-arms to `planned`
- GIVEN the same entry WHEN `do_all` hits a step timeout THEN it re-arms to `planned`
- GIVEN the same entry WHEN `do_all` failed on a turn cap or infra THEN the gate's `on_budget_spent` applies
- GIVEN a run that has re-armed once WHEN any unit fails again THEN the gate's `on_budget_spent` applies

### CXR-B4 Arm contract

WHEN a complexity switch is validated THE engine SHALL require every artifact key, item-keyed artifact and fact that a unit from `joins_at` on reads (prompt fields, judge references and a map's list) to be produced on every arm path, else `arm-contract` naming the arm, the key and the reader.

- GIVEN `joins_at: verify` where `verify` reads `change`, `planned`'s join producing `change` and `direct`'s `do_all` producing only `patch` WHEN the workflow validates THEN it fails `arm-contract` naming `direct`, `change` and `verify`

### CXR-B5 Exploration stays out of the pipeline

WHEN a margin run is picked by exploration THE engine SHALL run a simpler eligible arm with `zone: explore` at a local stage within the weekly limit, and never at stage `pipeline`, on a scheduled fire ([TCK](schedule-ticks-and-unattended-fires.spec.md)) or in a trial.

- GIVEN `explore: {rate: 0.2, per_week: 2}`, a hash that picks exploration and one explored run this week WHEN the stage is `local-stable` THEN `direct` runs with `zone: explore`
- GIVEN the same run WHEN the stage is `pipeline` THEN `planned` runs

### CXR-B6 Other parameters

WHEN a measure reads a setting or an input THE engine SHALL route by it like any other measure, and an operator's `--arm` ([CMP](compiler-and-flow.spec.md)) SHALL win over every zone with `chosen_by: operator`.

- GIVEN `setting(review_depth)` and rules `direct.when: {review_depth: {in: [light]}}` WHEN a run starts with `--set review_depth=thorough` THEN the zone is `complex` and `planned` runs
- GIVEN the same run with `--arm size=direct` WHEN the switch resolves THEN `direct` runs with `chosen_by: operator`

### CXR-B7 Declaring a complexity switch

WHEN a `switch` unit declares `complexity` THE engine SHALL read `arms` (2 or 3, ordered from the simplest to the most detailed, the last being the safe arm and the switch's `default`); `complexity.measures` (`{name, from}`, `from` a stock measure or a callable `(ctx: MeasureContext) -> int | float | str`, pure and model-free); `complexity.rules` (a package path, default `routing/<switch>.json`); optional `complexity.size` (the measure that size-adjusts cost in the report); optional `complexity.explore` (`{rate, per_week}`, off when absent, `rate` at most 0.25 and `per_week` at most 5, else `complexity-explore`); `complexity.joins_at` (the first unit every arm path reaches, `complexity-joins` when it is not); `mode`, `arm_overrides` and `sticky` as SWM, `sticky` being `run` so the switch is never re-evaluated per visit; and optional `rearm` as [SWM-B7](measured-switches.spec.md); refuse a `predicate` on a complexity switch (`complexity-predicate`), a plain switch with a hand-written predicate staying available for any other choice; refuse an arm path that holds the final outcome gate or gates from `joins_at` on that differ between arms, because an arm changes how the work is done, never what verifies it ([ADR `overrides-never-change-what-verifies-the-work`](../adr/overrides-never-change-what-verifies-the-work.adr.md)); refuse a `rearm` toward a simpler arm (`complexity-rearm`); refuse a complexity switch inside a map item, as a map in a map is ([MAP-B11](map-unit.spec.md)); and report other malformed declarations `complexity-invalid`.

- GIVEN a complexity switch with a `predicate` WHEN the workflow validates THEN it fails `complexity-predicate`

### CXR-B8 Shapes

WHEN a workflow places a complexity switch THE engine SHALL allow it before planning, choosing between a direct step and a plan, map and join by measures such as request size, acceptance criteria counted by a triage check, files or components named and input labels (for example `direct` when criteria are at most 3 and named files at most 2), and after planning, choosing between one session for the whole plan and a map over its phases by measures such as plan phases and rows counted by the plan's check and files per phase (for example `single` when phases are at most 3 and rows at most 30), both arms joining before a shared verifying unit.

- GIVEN a switch after a plan step with measures from the plan's check WHEN the plan has 5 phases THEN the per-phase arm runs

### CXR-B9 Measures

WHEN a measure is evaluated THE engine SHALL give it a `MeasureContext` holding `request`, `facts` (check facts of earlier units on the path), `artifacts` (pointers only), `settings`, `stage` ([PRO](promotion-check.spec.md), `local-stable` for a workflow in `stable` mode, else `local-dev`), `git` (of the run's workspace at the switch) and `read_text(path)` for files under the workspace, and no step value, a step's assessment counting only once a check verified it and recorded it as a fact ([research `routing-by-complexity-between-decompositions`](../research/routing-by-complexity-between-decompositions.rsrch.md) F2); offer the stock measures `fact(<unit>, <key>)` (a check fact, as a number when it parses as one), `input(<name>)`, `setting(<name>)`, `count_items(<unit>, <key>)` (items a map would read, by the map's own extractor, [MAP-B7](map-unit.spec.md)), `count_lines(<unit>, <key>, <pattern>)` and `changed_paths()`; treat a measure that raises, exceeds 1 s or returns another type as a fault; and evaluate the measures and rules once per run in the switch's step node, keeping the result on its attempt record for the gate's pick.

- GIVEN a step that writes `ARTIFACT size: trivial` WHEN the switch routes THEN it routes as if the step wrote nothing

### CXR-B10 Rules file

WHEN the rules file is read THE engine SHALL read `schema_version` 1, `arms.<arm>.when` for every arm but the safe arm (measure to `{max}`, `{min}` or `{in: [...]}`, every bound holding) and optional `margin.<measure>` `{from, to}` bands; let a repository override it whole-file at `.tempergraph/routing/<workflow>/<switch>.json`; and refuse at load a file naming an undeclared arm or measure (`complexity-rules`), a repository override doing so at run time giving the `fault` zone.

- GIVEN a repository override naming an unknown measure WHEN a run reaches the switch THEN the zone is `fault`

### CXR-B11 Re-arm rules

WHEN a `rearm` is declared or applied THE engine SHALL require it to go from an arm to a later arm, allow at most one re-arm per run with the safe arm's own policy applying after it, need a step timeout rather than an infra `slow_host` for a re-arm on `timeout`, apply the gate's `on_budget_spent` to a budget spent on held causes, and never escalate the model of a unit while a re-arm is available for it ([LAD-B12](effort-ladder-and-model-escalation.spec.md)).

- GIVEN a unit with a re-arm available WHEN its budget is spent with climbing evidence THEN it re-arms and does not escalate its model

### CXR-B12 Exploration

WHEN a run is in the margin and `explore` is declared THE engine SHALL take a simpler eligible arm when `hash(thread_id, switch) mod 1000 < rate × 1000` and fewer than `per_week` explored runs of the workflow started in the last 7 days, recording it `zone: explore`, subject to CXR-B5.

- GIVEN `per_week: 2` and two explored runs this week WHEN a margin run's hash picks exploration THEN the safe arm runs

### CXR-B13 Records and report

WHEN a complexity switch resolves THE engine SHALL add to the `route` record ([SWM-B5](measured-switches.spec.md)) `zone`, `measures` (name to value or fault), `rules_digest` and `rules_source` (`package` or `repository`); and `report --switch <workflow>/<switch>` SHALL show per arm and zone, for finished runs of one workflow version, runs, first-pass yield of the gates from the switch to `joins_at`, cost per completed run, cost per unit of `size`, wall time, re-arm rate and the outcome verdict mix, re-armed runs shown apart and excluded from per-arm figures, a cell with fewer than 5 runs marked `too few to compare` ([research `routing-by-complexity-between-decompositions`](../research/routing-by-complexity-between-decompositions.rsrch.md) F8).

- GIVEN 3 runs of arm `direct` in zone `simple` WHEN `report --switch` runs THEN that cell is `too few to compare`

## Acceptance criteria

- CXR-AC1 (CXR-B1, CXR-B2, CXR-B3, CXR-B5, CXR-B6, CXR-B8, CXR-B12): CXR-B1 to CXR-B6 and every scenario hold offline with scripted executors
- CXR-AC2 (CXR-B9): A measure cannot read a step `value`: a fixture whose step writes `ARTIFACT size: trivial` routes the same as one that writes nothing
- CXR-AC3 (CXR-B4, CXR-B7, CXR-B10): Every validation code has a fixture workflow that fails with it
- CXR-AC4 (CXR-B13): `report --switch` excludes re-armed runs from per-arm figures and marks cells under 5 runs
- CXR-AC5 (CXR-B11): A run never re-arms twice and never re-arms toward a simpler arm

## Open questions

- Should `route` mode be refused in `local-stable` without a shadow record? Until answered: warned in `local-stable`; the promotion check needs at least 5 runs per used arm for `pipeline`. Owner: owner.
- Should the report suggest new thresholds? Until answered: no, figures only, as SWM; the loop proposes changes through PRP. Owner: owner.
