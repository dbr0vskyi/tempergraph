# ADR-0066 Five flow extensions for LangGraph parity: selective parallel, mapped sub-workflows, deadlines, fallback, breakpoints

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

[R-060](../research/R-060-node-types-against-langgraph.rsrch.md) finds five shapes LangGraph expresses and this design does not: a router that picks several destinations (L4), a `Send` to a subgraph per item (L7), a static breakpoint before a node (L13), an error handler that routes to a fallback node (L19), and a timeout on a wait.

## Decision

We will add, in [FLX](../specs/74-flow-extensions.spec.md):

1. **Selective parallel.** A parallel block may declare a pure `select` function that picks a non-empty subset of its declared branches at run time; the join waits for the selected branches only.
2. **Map over a sub-workflow.** A map's item body may be a registered sub-workflow, so each item runs several gated steps. The child may contain no map, wait or ask; depth rules hold.
3. **Deadlines.** A wait or ask unit may declare `deadline_s` and `on_deadline` (`escalate`, `stop` or a forward target). The deadline is shown when the pause is read and applied only by an explicit `resume --apply-deadline`; no background process runs it, and the orchestration supervisor never applies it (C16).
4. **Fallback target.** A gate may name a forward `fallback` unit used when its retry budget is spent or a hard failure stops it; the run is marked degraded. Infra failures never take it.
5. **Operator breakpoints.** `--pause-before <unit>` on start or resume pauses before that unit's step node with pause kind `breakpoint`, using LangGraph's per-call `interrupt_before`; nothing runs before it.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| The five extensions (chosen) | Closes every R-060 shape gap with static, declared targets | Five more validation rows and diagram forms |
| Expose `Command` and `Send` | Fewer engine features | Breaks C5 and ADR-0003 ([ADR-0062](0062-new-node-kinds-keep-the-gated-unit.adr.md)) |
| A background timer for deadlines | Deadlines act on time | A resident process per paused run, against the design's exit-3-and-leave model |
| Breakpoints as an extra node per unit | Visible in the graph | Changes the four-node rule and every diagram |

## Decision rationale

| Criterion | Chosen | `Command`/`Send` | Timer | Breakpoint node |
|---|---|---|---|---|
| Static, validated targets | yes | no | yes | yes |
| No resident process | yes | yes | no | yes |
| Four nodes per unit kept | yes | yes | yes | no |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| F1 | A deadline is advisory until someone applies it; owners who want time-driven action schedule `resume --apply-deadline` from their own scheduler. | FLX-B8 |
| F2 | A fallback is forward only; a backward recovery is already a back-edge. | FLX-B9 |

## Consequences

- Positive: every R-060 shape has a declared form; local debugging gets breakpoints, which fits the improve-locally-then-graduate lifecycle.
- Negative: the human node gains a second entry for breakpoints; HUM's "single place" wording is amended to include it.
- Risk: fallbacks hide failing units. Mitigation: a degraded run is never `finished` without the flag, and the audit reports fallback rates.

## Revisit when

A workflow needs a deadline that acts without anyone reading the run.
