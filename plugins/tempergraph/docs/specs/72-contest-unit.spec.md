---
title: Contest unit
type: component
status: review
prefix: CTS
adrs: [0062, 0064]
---

# Contest unit

## 1. Overview

A **contest** runs the same step in 2 to 5 **candidate slots**, grades each candidate with the gate's own check and a fresh session of the gate's own judge, and keeps the best by a fixed engine rule ([ADR-0064](../adr/0064-contest-picks-a-candidate-by-the-gates-own-judge.adr.md)). It is "best of n": it trades cost for first-pass quality on one unit, for work where one good output beats a blend (a plan, a draft, a patch). A council combines answers; a contest keeps one ([R-060](../research/R-060-node-types-against-langgraph.rsrch.md) H3).

## 2. Contract

### 2.1 Declaration

| Type | Field | Kind | Meaning |
|---|---|---|---|
| `UnitSpec` (CON §2.1) | `step` | `StepSpec` | The base step every slot runs. |
| | `contest` | `ContestSpec`, for kind `contest` | |
| `ContestSpec` | `slots` | int 2–5, or a list of 2–5 `SlotSpec` | An int runs the base step in that many slots unchanged. |
| | `writes` | bool, default false | Slots that change files run in writer worktrees ([WSP §2.1](13-workspace-and-concurrency.spec.md)). |
| | `retry_scope` | `best` \| `all`, default `best` | What a RETRY re-runs (§2.3). |
| | `concurrency` | int, default 3 | Slots at once. |
| | `cost_cap_usd` | float, optional | Per attempt; unstarted slots are skipped when reached. |
| `SlotSpec` | `name` | slug | |
| | `executor`, `model` | optional | Overrides of the base step's. |
| | `prompt_variant` | template, optional | Appended to the base prompt under a fixed heading ("Approach for this attempt"). |

Slots behave like map items: item ids are slot names (`s1`…`sN` for an int), session keys are `<unit>.<slot>.<attempt>.<kind>`, and each slot has its own check and judge records.

### 2.2 Pick rule

Each slot runs, then the gate's check runs on its output. A slot whose check FAILs is out. Every remaining slot gets its own judge session, which sees that slot's artifacts only. The engine derives each slot's verdict as for a plain step ([JDG](05-judge-and-verdict.spec.md)), then orders slots by:

| Rank | Key | Better is |
|---|---|---|
| 1 | Derived verdict | PROCEED before any other |
| 2 | Unmet warnings | Fewer |
| 3 | Criteria MET | More |
| 4 | Judge confidence | Higher |
| 5 | Session cost (reported, else estimated) | Lower |
| 6 | Slot order | Earlier |

The first slot is the **winner**. Its artifacts become the unit's, and its verdict becomes the unit's verdict. A writer winner is merged into the run branch at the pick without fast-forward; the other slots' worktrees are discarded and their records kept. A `contest` run event records every slot's keys and the winner ([EVT](30-run-events.spec.md)).

### 2.3 Retry

When the winner's verdict is RETRY, `retry_scope: best` re-runs the winner's slot alone with its judge's notes (the contest becomes a single step for the rest of the visit), and `all` re-runs every slot, each with its own previous notes. A BACK, ESCALATE or STOP verdict of the winner applies to the unit.

### 2.4 What is refused

| Refused before a run (`error`) |
|---|
| Fewer than 2 or more than 5 slots; two slots with one name |
| `writes: true` in a workflow without worktrees, or in a sequential map |
| A contest inside a map item or a parallel branch (a contest is itself a fan-out) |
| No judge on the gate |
| A slot override whose executor cannot bind the alias or map the tools (preflight, [EXI](10-executor-interface.spec.md)) |

Warning: every slot shares executor, model and prompt (`contest-identical-slots`).

## 3. Behaviours

**CTS-B1 Pick by rule.** Given three slots whose judgements are as below, when the pick runs, then the winner is `s2`.

| Slot | Check | Derived verdict | Unmet warnings | MET | Confidence | Cost |
|---|---|---|---|---|---|---|
| s1 | PASS | RETRY | 0 | 5 | 0.85 | 0.30 |
| s2 | PASS | PROCEED | 1 | 6 | 0.85 | 0.40 |
| s3 | PASS | PROCEED | 1 | 6 | 0.85 | 0.55 |

**CTS-B2 Check first.** Given a slot whose check FAILs, when the contest is graded, then no judge session starts for it.

**CTS-B3 Judge sees one candidate.** Given two slots, when their judges run, then each judge's view set holds one slot's artifacts and no other slot's text or score.

**CTS-B4 No winner passes.** Given every slot's derived verdict RETRY and `retry_scope: best`, when the gate routes, then the best-ranked slot alone runs again with its notes and the retry budget is charged once.

**CTS-B5 Writer contest.** Given `writes: true` and two slots that both edit `src/a.py`, when the pick runs, then only the winner's worktree is merged; no merge conflict can arise between slots.

## 4. Error conditions

| Type | Result |
|---|---|
| Every slot fails on infra | Infra failure of the attempt |
| Every slot's check FAILs | The unit's check result is the first slot's FAIL; retry per the gate |
| Winner's merge fails | As a writer join conflict ([WSP §2.1](13-workspace-and-concurrency.spec.md)) |

## 5. Design notes

- Using the gate's own judge per candidate means no new grader needs calibration ([JCL](50-judge-calibration.spec.md)); a pairwise judge was rejected for its position and length biases ([R-045](../research/R-045-evaluating-llm-judges-public-practice.rsrch.md)).
- Costs grow with slots; preflight shows the projected range from the stats projection ([CST](34-central-run-stats.spec.md)).
- Any of the four executors can host slots and judges; slot overrides are how a contest compares executors on real work.

## 6. Acceptance criteria

- [ ] CTS-AC-1 Every row of §2.4 has a fixture workflow that fails validation with its own finding code.
- [ ] CTS-AC-2 The CTS-B1 table holds offline, and the pick code calls no model (source scan).
- [ ] CTS-AC-3 A judge's prompt for one slot contains no other slot's text (prompt capture).
- [ ] CTS-AC-4 The run detail shows every slot with its check, verdict, keys and cost, and marks the winner ([RDD](31-run-detail-document.spec.md)).

## Open questions

None.

## References

[CON](01-contracts.spec.md) · [CMP](03-compiler-and-flow.spec.md) · [JDG](05-judge-and-verdict.spec.md) · [WSP](13-workspace-and-concurrency.spec.md) · [ADR-0064](../adr/0064-contest-picks-a-candidate-by-the-gates-own-judge.adr.md)
