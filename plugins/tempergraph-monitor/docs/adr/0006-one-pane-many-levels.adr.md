# MADR-0006 One pane with levels, not a pane per run

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

A person may have several live runs, orchestrations and batches at once. Claude Code's workflows view has one entry point with a run list and levels ([R-002](../research/R-002-dynamic-workflows-view.rsrch.md)). A pane opened without a person's action appears only on wide sidebar layouts, and each open pane takes room from the conversation ([R-001](../research/R-001-claude-code-mods.rsrch.md)).

## Decision

We will open one pane, `tempergraph`, whose levels go runs → run → unit → attempt → session, with a breadcrumb; the band and status line stay summaries ([MRV §2.1](../specs/run-view.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| One pane with levels (chosen) | One place; matches the workflows view; small layout cost | One run at a time in detail |
| A pane per run | Side-by-side runs | Crowds the layout; many panes to close; none appear unasked on narrow screens |
| Detail inline under tool rows | No pane | Runs are not tool calls of this session; nothing to attach to |

## Decision rationale

| Criterion | One pane | Pane per run | Inline |
|---|---|---|---|
| Layout cost | one pane | n panes | none |
| Familiar from workflows | yes | no | no |
| Several runs at a glance | list level and band | yes | no |

## Consequences

- Positive: the breadcrumb always says where the person is; Esc always goes up one level.
- Negative: comparing two runs side by side needs two sessions.

## Assumptions

- Comparing live runs side by side is rare; the run list and the fleet tab cover overview needs.

## Revisit when

Persons ask for split views often, or Claude Code adds tabs inside a pane.
