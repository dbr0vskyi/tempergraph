# ADR-0073 A person rewinds a live thread in place, and reruns any thread as a new linked thread forked from a checkpoint

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner asked for ways to retry, rerun and resume. [R-070](../research/R-070-config-overrides-and-reruns-gaps.rsrch.md) finds retries, trips back, re-opens and resumes at every thread state, but two holes: a person can send a run back only to a gate's declared `back_targets` (F21), and a finished thread can only be replaced by a new run from scratch (F20). LangGraph keeps each thread's checkpoint history and can fork from any checkpoint; Temporal's reset makes a new run from a chosen point and keeps the old history; Argo separates retrying a workflow from resubmitting a new one.

## Decision

We will add two forms ([RRN](../specs/81-reruns-and-feedback.spec.md)):

1. **Rewind**, a person's decision `rewind:<unit>` on a `paused`, `stopped` or `unfinished` thread, to any unit completed on the current path. It clears like a trip back, charges the human cap, not a loop budget, and leaves files untouched.
2. **Rerun**, a verb that starts a new thread `<task_id>~r<n>` from the checkpoint before a chosen unit of any thread but a running one, finished threads included. Earlier verdicts and the resolved input are kept, the source's settings are copied and may be changed, and both threads record the link. The source's history is never rewritten.

Both refuse to cross a unit with external effects (a pull request, a tracker issue, a wiki page, an `external` script) without `--accept-external`.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Rewind in place plus rerun as a fork (chosen) | Live corrections stay in one thread; finished runs stay as reported | Two verbs to learn |
| Reopen a finished thread in place | One thread per task | Rewrites what the finalizer, stats and improvement loop already recorded |
| Only reruns, never rewind | One mechanism | A live run's correction scatters over threads |
| Let `back` reach any unit | No new decision word | `back_targets` also bound automatic attribution; widening it changes the engine's routing |

## Decision rationale

| Criterion | Chosen | Reopen | Reruns only | Wider `back` |
|---|---|---|---|---|
| Finished records unchanged | yes | no | yes | yes |
| Automatic trips still bounded | yes | yes | yes | no |
| A live correction keeps one story | yes | yes | no | yes |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | A person may judge that a fault lies earlier than any declared target; that judgement belongs to them, like any pause decision (C6). | RRN §2.3 |
| A2 | Workspace files are not reset by a rewind or a default rerun, as for a trip back ("nothing resets the worktree", temperspec 7.6); a rerun may start from the commit recorded at the unit instead. | RRN §2.4 |
| A3 | A workflow's finalizer handles an existing pull request for its branch; the engine does not. | RRN-B6 |

## Consequences

- Positive: "run it again from code with a bigger model and this note" is one command and costs only the units it reruns.
- Negative: `unit_entered` must record the workspace commit for `--workspace at-unit`; lineage needs a small file per source run.
- Risk: reruns inflate first-pass statistics. Mitigation: rows carry `rerun_of`, and reports show reruns apart.
