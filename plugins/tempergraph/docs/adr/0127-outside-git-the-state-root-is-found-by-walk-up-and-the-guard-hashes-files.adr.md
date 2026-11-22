# ADR-0127 Outside git, the state root is found by walk-up or declared, and the guard hashes files

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — (answers R-011 G9) |

## Context

The engine refuses to start outside a git repository, yet many workflows are not code and need only a folder and a fingerprint ([R-131](../research/R-131-running-outside-a-git-repository.rsrch.md) F2). Only two uses of git are needed to run at all: finding the state root and fingerprinting the workspace for the guard (F1).

## Decision

We will run workflows outside git ([WSP-B15 to WSP-B18](../specs/13-workspace-and-concurrency.spec.md)) with: a state root from `--state-root` or `TEMPERGRAPH_STATE_ROOT`, else walk-up to the nearest `.tempergraph/manifest.json`, else the start dir; `in_place` workspaces only, or an engine scratch folder for a workflow with no folder; a file-manifest fingerprint with a 20,000-file ceiling; and a `needs_git` refusal at validation for every feature that needs git.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Stay git-only | Nothing to build | Non-code workflows need a dummy repository |
| `git init` a hidden repository for the run | Reuses every git rule | Surprises the person; nested repositories confuse tools |
| **Walk-up root, manifest fingerprint, `needs_git` refusals (chosen)** | Every rule kept, by a replacement or a refusal | A tree walk per attempt |

## Decision rationale

| Criterion | Git-only | Hidden repo | Chosen |
|---|---|---|---|
| Non-code workflows run in their own folder | no | yes | yes |
| No silent loss of a guard | yes | yes | yes |
| Nothing created the person did not ask for | yes | no | yes |

## Consequences

- Positive: meeting notes, refinement and wiki workflows run where their files are.
- Negative: large folders may be refused for guarding.
- Risk: a stray `.tempergraph` in a parent folder captures runs. Mitigation: the home folder is never a root, and `--state-root` overrides.

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| N1 | Inside a repository the git rules always apply. | WSP-B15 to WSP-B18 |

## Revisit when

A workflow needs worktree-like isolation without git.
