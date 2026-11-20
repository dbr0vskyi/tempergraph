# ADR-0101 One workspace setting, `run.workspace`, with an `auto` default resolved from the target and the workflow

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The workspace mode was a workflow field and a run setting with two values, `in_place` and `worktree`, and no default when a workflow declared none ([RST-B18, RST-B19, RST-B20, RST-B21](../specs/80-run-settings-and-overrides.spec.md)). tempergraph serves any workflow of the delivery pipeline, not only coding: a workflow that writes a Confluence page or a tracker issue gains nothing from a worktree and may run outside any git checkout. A coding workflow run in place edits the person's checkout; a worktree on its own branch keeps that checkout untouched ([R-100](../research/R-100-native-worktrees-and-executor-worktree-features.rsrch.md) F1.1, F1.3).

## Decision

We will keep one key, `run.workspace`, with a third value `auto` that is the engine default and the default of `WorkflowSpec.workspace`. `auto` resolves before spend, purely from the target and the workflow: not a git checkout gives `in_place`; writers or any declared file-writing tool or local-effect script give `worktree`; otherwise `in_place` ([WTR §2.2](../specs/82-worktree-mode.spec.md)). The few details of a worktree are sibling keys under `run.worktree.*`. The flags are `--workspace`, `--worktree` and `--in-place`. Every key but cleanup is fixed at the start.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| `auto` default plus explicit values (chosen) | Safe choice for coding workflows; no git needed for document workflows; one key to learn | A resolution rule to explain; `resolved_by` must be shown |
| Default `worktree` | Safest for code | Fails or adds a useless tree for non-git and non-coding workflows |
| Default `in_place` | Simplest | Coding workflows edit the person's checkout unless the author remembers |
| A boolean `worktree: true/false` | Shortest | No room for "decide for me"; reads badly beside the existing field |

## Decision rationale

| Criterion | `auto` | `worktree` | `in_place` | Boolean |
|---|---|---|---|---|
| Works outside git | yes | no | yes | yes |
| Coding workflow isolated without author effort | yes | yes | no | no |
| Existing `in_place` / `worktree` values still valid | yes | yes | yes | no |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | A declared `edit`, `write` or `shell` capability is a good enough sign that a workflow changes files in the repository. A shell-only step that never writes still gets a worktree, which costs a little disk and nothing else. | WTR §2.2 |
| A2 | The base, root and branch cannot change after the start, because the record names a path and a branch that later units and the finalizer use. | WTR §2.1 |

## Consequences

- Positive: a person rarely sets the parameter; when they do, it is one flag, and `config show` explains the result.
- Negative: the settings catalog gains six rows.
- Risk: an MCP tool that writes into the repository is not seen as writing. Mitigation: the author declares `workspace: worktree`.
