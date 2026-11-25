# ADR-0103 Worktree removal is opt-in, only of clean worktrees, and never deletes the branch

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

By default the engine never removes a worktree on its own: a list verb and a prune verb exist, and branches are never deleted, on the principle "the workspace is disposable; the branch is not". Worktrees still pile up; Claude Code leaves `-p` worktrees locked forever ([R-100](../research/R-100-native-worktrees-and-executor-worktree-features.rsrch.md) F3.1). git removes a worktree without `--force` only when it is clean (F2.3), and a branch keeps every commit reachable after its folder is gone.

## Decision

We will keep `run.worktree.cleanup: never` as the default and add `on_finish`, which removes a finished run's clean worktrees after its finalizer, without `--force`, keeping the branch. `worktree prune` lists by default and removes only with `--apply`, the same clean-only way, never for a running thread. The engine locks each run worktree with a reason while its thread is not finished, so `git worktree prune` and other tools' sweeps leave it, and never deletes a branch ([WTR-B23](../specs/worktree-mode.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Opt-in clean-only removal, branch kept (chosen) | No work can be lost; disk can be reclaimed | Worktrees still accumulate under the default |
| Remove on finish by default | Tidy | A first release would delete trees before removal has run live |
| Remove with `--force` | Always tidy | Loses uncommitted work |
| Delete merged branches too | Fewer refs | Deletion of a pushed or reviewed branch is a person's decision |

## Decision rationale

| Criterion | Opt-in clean | Default on | Force | Delete branches |
|---|---|---|---|---|
| Uncommitted work never lost | yes | yes | no | yes |
| Commits never lost | yes | yes | yes | only if merged |
| Disk reclaimable without a person | with the setting | yes | yes | yes |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | A paused run's clean worktree can be removed, because resume re-attaches it from the branch and bootstraps it again. | WTR-B16 |

## Consequences

- Positive: one setting gives tidy machines for routine runs; the branch is still never deleted.
- Negative: removal of a tree a person still had open in an editor surprises them. Mitigation: only with the setting or `--apply`.

## Revisit when

`on_finish` has run live for a release without a lost-work report; then consider it as the default (WTR open question).
