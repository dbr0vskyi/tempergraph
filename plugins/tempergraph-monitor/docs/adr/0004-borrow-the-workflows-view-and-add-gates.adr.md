# MADR-0004 Borrow the dynamic workflows view's navigation, and add the graph, the four nodes, judges and money

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner asked for a view "in same way how it is done for dynamic workflows", combining "the best sides of both". The workflows view gives a run list, phases with agent counts, drill-down with arrow keys, narrator lines and recent tool calls per agent; it has no gates, judges, money or cross-machine scope ([R-002](../research/R-002-dynamic-workflows-view.rsrch.md)). A tempergraph unit is four nodes (step, check, judge, gate) and a run is a graph with trips back ([engine ADR-0004](../../../tempergraph/docs/adr/0004-four-nodes-per-unit.adr.md)).

## Decision

We will copy the workflows view's levels, keys, filter and narrator lines unchanged where a matching meaning exists, draw the run as its declared graph with a `S C J G` node strip per unit, lead attempt views with the judge's reasons, and show money with honesty flags ([MRV](../specs/03-run-view.spec.md), [MDD](../specs/04-drill-down.spec.md)). Keys with no tempergraph meaning (pause, restart) are not faked.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Workflows navigation plus tempergraph layers (chosen) | Familiar; shows what makes tempergraph different | Two vocabularies on one screen |
| A graph canvas (nodes and edges drawn) | Shows topology | Does not fit a terminal pane; loses the list a person scans |
| A pure copy of the workflows view (units as agents) | Zero learning | Hides checks, judges, gates and trips back, the reasons the owner built tempergraph |
| A log stream only | Simple | No structure; tool calls scroll past and nobody sees them |

## Decision rationale

| Criterion | Borrow + add | Canvas | Pure copy | Log |
|---|---|---|---|---|
| Learnable from the workflows view | yes | no | yes | partly |
| Shows why work repeats | yes | partly | no | partly |
| Fits a terminal pane | yes | no | yes | yes |
| Shows trips back | yes (indented line) | yes | no | no |

## Consequences

- Positive: a person reads "the judge is running on attempt 2 of code because c3 failed" at one glance.
- Negative: `p` means pin here, pause there. Mitigation: footer buttons always name the action.

## Assumptions

- The workflows view's keys are stable enough to borrow (they come from public docs of one release).

## Revisit when

Claude Code exposes its workflows view as an extensible component a mod can feed.
