# ADR-0133 A sub-workflow runs inside its parent's thread, workspace and cap

| | |
|---|---|
| Status | accepted (owner, 2026-11-22) |
| Date | 2026-11-22 |
| Authors | Claude (release 3 preparation for the owner) |
| Supersedes | — |

Numbers 0130 and 0131 are held by the pull-request gate research, in review.

## Context

[CMP-B10 to CMP-B16](../specs/03-compiler-and-flow.spec.md) lists a sub-workflow unit in one row: a registered workflow compiled as a subgraph under the parent's checkpointer, at most three deep, never recursive. The first real workflow asks for one: its repository setup should be a workflow of its own, run alone or inside the delivery run ([R-140](../research/R-140-release-three-readiness-and-gaps.rsrch.md) F2, F3). Before it can be built, one choice decides most of the rest: is the child a part of the parent's run, or a run of its own that the parent starts and waits for?

## Decision

We will run a child as a subgraph inside the parent's run: one thread, one checkpoint, one lock, one `run.jsonl`, one workspace, one cost cap and one finalizer, the parent's. The child keeps what makes it the same workflow when run alone: its own units, gates, budgets, outcome gate, judge calibration and findings. The details are [SWF](../specs/99-subworkflow-unit.spec.md).

## Options considered

| Option | For | Against |
|---|---|---|
| **A subgraph in the parent's thread (chosen)** | `status`, `stop`, `resume`, carrying and the monitor work unchanged; one cap; the parent pauses on the child's question as on its own | The child's records need a `child` field; a child's finalizer cannot run |
| A child run per unit, the parent waiting on it (the batch shape) | The child's run is the same as a run alone, byte for byte | Two threads to resume and carry; two caps to reconcile; a pause in the child is not a pause of the parent; a stop must reach both |
| Inline the child's units into the parent at compile time | No new runtime concept | The child's outcome gate, version and findings are lost; a change of the child silently changes every parent |

## Decision rationale

| Criterion | Subgraph | Child run | Inline |
|---|---|---|---|
| One place to stop, resume and read a run | yes | no | yes |
| The child learns in one place, alone or inside a parent | yes | yes | no |
| A cap a person can trust | one cap | two | one |
| New concepts | a `child` field, a namespace | a parent-child link and a wait | none, but a lost identity |

## Consequences

- Positive: a workflow can be built from workflows without a second run model; temperspec's setup becomes reusable.
- Negative: a child's finalizer never runs; a child that declares one is warned, and the parent's finalizer must call the same code.
- Risk: a child written for running alone may assume its own workspace. Mitigation: the child's `run.workspace` is ignored and noted, and validation refuses a child that needs git under a parent outside git.

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | The repository setup and delivery runs share one worktree; a child that needs its own would be a writer branch, not a sub-workflow. | SWF-B8 |
| A2 | A child's measures should count runs inside a parent only when its promotion window says so, since a parent shapes the child's inputs. | SWF-B9, PRO |
