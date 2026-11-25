# Contest unit

## Purpose

A contest runs the same step in 2 to 5 candidate slots, grades each candidate with the gate's own check and a fresh session of the gate's own judge, and keeps the best by a fixed engine rule ([ADR-0064](../adr/0064-contest-picks-a-candidate-by-the-gates-own-judge.adr.md), [ADR-0062](../adr/0062-new-node-kinds-keep-the-gated-unit.adr.md)). It is best of n: it trades cost for first-pass quality on one unit, for work where one good output beats a blend (a plan, a draft, a patch). A council combines answers; a contest keeps one ([R-060](../research/R-060-node-types-against-langgraph.rsrch.md) H3). Any executor can host slots and judges, and slot overrides are how a contest compares executors on real work. Workflow authors and the compiler depend on it; design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### CTS-B6 Declaration

WHEN a unit of kind `contest` is declared THE engine SHALL read its base `step` (`StepSpec`) and its `contest` field ([CON](01-contracts.spec.md)) as `ContestSpec`: `slots` (2 to 5, an int running the base step unchanged in that many slots, or a list of `SlotSpec` with a slug `name`, optional `executor` and `model` overrides and an optional `prompt_variant` template appended to the base prompt under the fixed heading "Approach for this attempt"), `writes` (default false; slots that change files run in writer worktrees, [WSP-B11](13-workspace-and-concurrency.spec.md)), `retry_scope` (`best` or `all`, default `best`), `concurrency` (1 to 5, default 3) and `cost_cap_usd` (per attempt, unstarted slots skipped when reached), a run setting the last two as `concurrency` and `attempt_cost_cap_usd` ([RST-B19](80-run-settings-and-overrides.spec.md)); and treat slots like map items, item ids the slot names (`s1` to `sN` for an int), session keys `<unit>.<slot>.<attempt>.<kind>`, each slot with its own check and judge records.

- GIVEN `slots: 3` WHEN the contest runs THEN its items are `s1`, `s2` and `s3`
- GIVEN `slots: 3` and `concurrency: 2` WHEN the contest runs THEN two slots run at once and the third starts when one of them ends
- GIVEN `slots: 3`, `concurrency: 1`, `cost_cap_usd: 0.40` and slot sessions that each cost 0.30 WHEN the contest runs THEN `s1` and `s2` run and `s3` never starts
- GIVEN a contest declaring `concurrency: 3` and `cost_cap_usd: 1.00` WHEN a run sets its `concurrency` to 1 and its `attempt_cost_cap_usd` to 0.40 THEN the slots run one at a time and none starts once the attempt's cost has reached 0.40

### CTS-B7 Pick rule

WHEN every slot has run THE engine SHALL run the gate's check on each output, put out a slot whose check FAILs, give every remaining slot its own judge session seeing that slot's artifacts only, derive each slot's verdict as for a plain step ([JDG](05-judge-and-verdict.spec.md)), and order the slots by derived verdict (PROCEED first), then fewer unmet warnings, more criteria MET, higher judge confidence, lower session cost (reported, else estimated) and earlier slot order; the first is the winner, whose artifacts and verdict become the unit's; a writer winner is merged into the run branch at the pick without fast-forward and the other slots' worktrees of that attempt are discarded with their records kept; and a `contest` run event records every slot's keys and the winner ([EVT](30-run-events.spec.md)).

- GIVEN a winner WHEN the run event is read THEN it holds every slot's keys and names the winner

### CTS-B1 Pick by rule

WHEN slots tie on verdict, warnings, MET and confidence THE engine SHALL pick the cheaper one.

- GIVEN s1 PASS, RETRY, 0 warnings, 5 MET, 0.85, 0.30; s2 PASS, PROCEED, 1, 6, 0.85, 0.40; s3 PASS, PROCEED, 1, 6, 0.85, 0.55 WHEN picked THEN the winner is `s2`

### CTS-B2 Check first

WHEN a slot's check FAILs THE engine SHALL start no judge session for it.

- GIVEN a slot whose check fails WHEN graded THEN no judge session starts for it

### CTS-B3 Judge sees one candidate

WHEN slot judges run THE engine SHALL give each judge a view set holding one slot's artifacts and no other slot's text or score.

- GIVEN two slots WHEN their judges run THEN neither prompt contains the other slot's text

### CTS-B8 Retry

WHEN the winner's verdict is RETRY THE engine SHALL re-run the winner's slot alone with its judge's notes under `retry_scope: best`, the contest becoming a single step for the rest of the visit, or every slot with its own previous notes under `all`, and apply a winner's BACK, ESCALATE or STOP to the unit.

- GIVEN `retry_scope: all` and a RETRY WHEN the retry runs THEN every slot runs again with its own notes

### CTS-B4 No winner passes

WHEN every slot's derived verdict is RETRY under `retry_scope: best` THE engine SHALL run the best-ranked slot alone again with its notes and charge the retry budget once.

- GIVEN every slot RETRY WHEN the gate routes THEN only the best-ranked slot runs again and the budget is charged once

### CTS-B9 Contest failures

WHEN slots fail THE engine SHALL end the attempt as an infra failure when every slot fails on infrastructure, take the first slot's FAIL as the unit's check result and retry per the gate when every slot's check FAILs, and treat a failed winner merge as a writer join conflict ([WSP-B11](13-workspace-and-concurrency.spec.md)).

- GIVEN every slot's check failing WHEN graded THEN the unit's check result is the first slot's FAIL

### CTS-B5 Writer contest

WHEN a `writes: true` contest picks THE engine SHALL merge only the winner's worktree, so no merge conflict can arise between slots.

- GIVEN two slots that both edit `src/a.py` WHEN picked THEN only the winner's worktree is merged

### CTS-B10 What is refused

WHEN a workflow with a contest is validated THE engine SHALL refuse with an `error` fewer than 2 or more than 5 slots or two with one name; a `concurrency` outside 1 to 5 or a `cost_cap_usd` of 0 or less; `writes: true` in a workflow without worktrees or in a sequential map; a contest inside a map item or a parallel branch; no judge on the gate; and a slot override whose executor cannot bind the alias or map the tools (preflight, [EXI](10-executor-interface.spec.md)); warn `contest-identical-slots` when every slot shares executor, model and prompt; and show at preflight the projected cost range from the stats projection ([CST](34-central-run-stats.spec.md)).

- GIVEN a contest inside a map item WHEN validated THEN it is refused with its own finding code
- GIVEN a contest declaring `concurrency: 6` WHEN validated THEN it is refused with its own finding code
- GIVEN a contest declaring `cost_cap_usd: 0` WHEN validated THEN it is refused with its own finding code

## Acceptance criteria

- CTS-AC1 (CTS-B10, CTS-B6): Every refusal of CTS-B10 has a fixture workflow that fails validation with its own finding code
- CTS-AC2 (CTS-B1, CTS-B7, CTS-B2): The scenario of CTS-B1 holds offline, and the pick code calls no model (source scan)
- CTS-AC3 (CTS-B3): A judge's prompt for one slot contains no other slot's text (prompt capture)
- CTS-AC4 (CTS-B7, CTS-B8, CTS-B4, CTS-B5, CTS-B9): The run detail shows every slot with its check, verdict, keys and cost and marks the winner ([RDD](31-run-detail-document.spec.md)), and fixtures cover both retry scopes, a writer merge and each failure of CTS-B9
- CTS-AC5 (CTS-B6): A contest of three slots with `concurrency` 2 runs two slots at once and never a third, and with `concurrency` 1, `cost_cap_usd` 0.40 and slot sessions that each cost 0.30 starts `s1` and `s2` and never `s3` (stand-in sessions that log when each starts and ends)
- CTS-AC6 (CTS-B6): A contest that declares `concurrency` 3 and `cost_cap_usd` 1.00, run with `--set` giving its `concurrency` 1 and its `attempt_cost_cap_usd` 0.40, resolves both from the `flag` layer, runs its slots one at a time and starts none once the attempt's cost has reached 0.40

## Open questions

- What should preflight show for a contest's projected cost range, the last clause of CTS-B10? The central run stats hold one projection per workflow and none per unit ([CST-B15](34-central-run-stats.spec.md)), so what the slots add to a workflow's range cannot be read from them. Options: the workflow's own median and 90th percentile with the slot count beside them; or the slot count times the base step's per-session cost cap where one is declared. Until answered: preflight shows no range for a contest. Owner: engine owner.
