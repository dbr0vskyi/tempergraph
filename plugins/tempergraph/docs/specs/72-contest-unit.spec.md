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

### CTS-B11 A later attempt runs in worktrees of its own

WHEN a contest with `writes: true` runs an attempt after its first (a retry, CTS-B8, or its first run after a BACK, [BUD-B4](08-budgets-and-failures.spec.md); attempt numbers rise across visits, [BUD-B3](08-budgets-and-failures.spec.md)) THE engine SHALL run each slot that runs in that attempt in a worktree and on a branch cut for that attempt from the run branch's head after the checkpoint commit ([WSP-B19](13-workspace-and-concurrency.spec.md)), under names that no earlier attempt's worktree or branch holds ([WTR-B20](82-worktree-mode.spec.md)).

- GIVEN `retry_scope: best` and a first attempt whose winner `s1` got RETRY WHEN the retry runs THEN `s1` alone runs, in a worktree and on a branch that the first attempt did not make, the branch starting at the head the run branch held before the retry's first session, so the worktree holds the files the first attempt's merge put there
- GIVEN `retry_scope: all` and a RETRY WHEN the retry runs THEN every slot runs again, each in a worktree and on a branch that the first attempt did not make
- GIVEN a first attempt that ended and a BACK to the unit before the contest WHEN the contest runs again THEN each slot runs in a worktree and on a branch that no earlier attempt made

### CTS-B12 An earlier attempt's slot work is left as it is

WHEN a contest with `writes: true` runs an attempt after its first THE engine SHALL leave every slot branch and worktree of its earlier attempts as it is, still listed among the run's worktrees ([WTR-B24](82-worktree-mode.spec.md)).

- GIVEN the first attempt's branch of `s2` at commit C and its worktree WHEN the retry has run to its end THEN that branch is still at C, that worktree is still there and the run's workspace record still lists it in the state it had

### CTS-B13 A later attempt merges only its own winner

WHEN a contest with `writes: true` picks a winner in an attempt after its first THE engine SHALL merge into the run branch only the branch the winner has in that attempt, and no branch of an earlier attempt.

- GIVEN a first attempt whose winner `s1` was merged and a retry under `best` in which `s1` alone runs and writes one file WHEN the retry is picked THEN the run branch gains one merge commit, with `s1`'s branch of the retry as second parent, and none with a branch of the first attempt as second parent
- GIVEN a retry under `all` whose slots each write one file and whose winner is `s2` WHEN the retry is picked THEN the run branch gains one merge commit, with `s2`'s branch of the retry as second parent, and none with another branch as second parent

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
- CTS-AC7 (CTS-B11): In a contest of two slots with `writes: true` and `retry_scope: best`, run by a scripted executor, the RETRY of the first attempt's winner is followed by a run of that slot in a worktree and on a branch that the first attempt did not make, starting at the head the run branch held before the retry's first session, and the run finishes with no `workspace_refused` record
- CTS-AC8 (CTS-B11): With `retry_scope: all`, a RETRY of a writing contest is followed by a run of every slot, each in a worktree and on a branch that the first attempt did not make
- CTS-AC9 (CTS-B11): After a BACK to the unit before a writing contest, the contest's slots run in worktrees and on branches that no earlier attempt made, and the run records no `workspace_refused`
- CTS-AC10 (CTS-B12): After a retry of a writing contest, every slot branch of the first attempt is at the commit it held when the first attempt ended, every worktree of the first attempt is still present and the run's workspace record lists the worktrees of both attempts
- CTS-AC11 (CTS-B13): After a retry of a writing contest under either scope whose running slots each write one file, the run branch has gained one merge commit, whose second parent is the branch the retry's winner has in that attempt, and none whose second parent is a branch of the first attempt

## Open questions

- What should preflight show for a contest's projected cost range, the last clause of CTS-B10? The central run stats hold one projection per workflow and none per unit ([CST-B15](34-central-run-stats.spec.md)), so what the slots add to a workflow's range cannot be read from them. Options: the workflow's own median and 90th percentile with the slot count beside them; or the slot count times the base step's per-session cost cap where one is declared. Until answered: preflight shows no range for a contest. Owner: engine owner.
