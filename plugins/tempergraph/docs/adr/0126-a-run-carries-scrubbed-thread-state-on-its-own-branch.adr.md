# ADR-0126 A run carries a scrubbed, thread-scoped state on its own branch, and deletes it when done

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

On 2026-11-20 the owner moved CI pipelines to a later release and proposed a stopgap: push the project's `.tempergraph` folder to a branch so its state and SQLite travel with the work, and remove it when the workflow is done, leaving no traces. The same shape serves CI: a paused run's state saved on its branch, and a required check failing a branch that still carries state. The whole folder holds transcripts, prompts, operator config and other runs ([R-133](../research/R-133-carrying-run-state-on-a-branch.rsrch.md) F2).

## Decision

We will let a person turn on **carrying** for a run ([CAR](../specs/run-state-on-a-branch.spec.md)). The engine commits a scrubbed, thread-scoped subset (the thread's checkpoint rows, its run folder without transcripts and prompts, its ledger rows, a path-relative workspace record, a manifest) to an orphan **state branch** `tempergraph/state/<workflow>/<task_id>` at every pause and exit, and pushes it. Another machine pulls it and resumes; a lease keeps one machine driving. When the thread finishes, the engine deletes the state branch locally and on the remote.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| The whole `.tempergraph` folder on the work branch (the literal proposal) | Simplest | Publishes transcripts, prompts, config and other runs (C9); a removal commit leaves it in the branch history and the pull request |
| **A scrubbed subset on a separate state branch, deleted at finish (chosen)** | Nothing private travels; the work branch and its pull request never hold state; deletion leaves no reachable trace | One more branch per carried run; plumbing code |
| The subset on the work branch, removed at finish, squash-merged | Keeps one branch | History of the work branch keeps the state until it is deleted; reviewers see state commits |
| Wait for a hosted store | No git use | Nothing until a later release |

## Decision rationale

| Criterion | Whole folder | Chosen | Subset on work branch | Hosted store |
|---|---|---|---|---|
| OVR-B11 and LOS "local only" marks | no | yes | yes | yes |
| No trace after the finish | no | yes | only after squash and branch deletion | yes |
| Available in release 2 | yes | yes | yes | no |
| Pull request diff free of state | no | yes | no | yes |

## Consequences

- Positive: a paused run can move between a person's machines now, and the pipeline of a later release gets its state transport.
- Negative: carried state includes a person's feedback and rulings verbatim; acceptable on a private repository only, so it stays opt-in.
- Risk: a finished run whose remote deletion fails. Mitigation: `attention` lists it with `carry drop`.

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| T1 | The owner's "push to branch" is met by a dedicated state branch; the work-branch variant is the alternative put to the owner on 2026-11-20. | CAR-B6 |
| T2 | Repositories that carry state are private. | CAR |

## Revisit when

Pipelines arrive, or a hosted run store exists.
