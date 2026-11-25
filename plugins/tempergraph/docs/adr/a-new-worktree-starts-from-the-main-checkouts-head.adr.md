# A new run worktree starts from the main checkout's HEAD unless the run names another base

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

No document said which commit a new run worktree starts from. Claude Code's `--worktree` defaults to the remote default branch (`fresh`), with `head` as the alternative ([research `native-worktrees-and-executor-worktree-features`](../research/native-worktrees-and-executor-worktree-features.rsrch.md) F3.1). temperspec opens the draft pull request against the default branch or an operator's override, and an orchestration may chain runs where a later run builds on an earlier run's branch ([ORC](../specs/orchestration.spec.md)).

## Decision

We will start from the main checkout's `HEAD` commit by default, recording the branch it was on as the pull request base, and offer `default_branch` (fetched, falling back to the local copy) and `ref:<name>` (any branch, tag or commit) through `run.worktree.base` ([WTR-B21](../specs/worktree-mode.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| `head` default, two alternatives (chosen) | Starts from what the person sees; offline; matches a local workflow of "work on top of my branch" | Uncommitted changes are not carried (warned) |
| Remote default branch by default | Matches Claude Code; fresh base for a pull request | Needs network; ignores the branch the person is on |
| Copy uncommitted changes into the worktree | Nothing left behind | The base no longer names a commit; the judge cannot tell the run's work from the person's |

## Decision rationale

| Criterion | `head` | Default branch | Copy changes |
|---|---|---|---|
| Works offline | yes | falls back | yes |
| Base is one recorded commit | yes | yes | no |
| A chained run can build on another branch | via `ref:` | via `ref:` | no |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | A person who starts a run from a feature branch wants the run built on it, and its pull request aimed at it. | WTR-B21 |

## Consequences

- Positive: an orchestration chains runs with `ref:` and nothing new.
- Negative: a pull request base of a feature branch may surprise a person who expected the default branch. Mitigation: `run --check` prints the base and `base_branch`.
