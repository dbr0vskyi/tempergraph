# ADR-0123 Complexity chooses a decomposition through a measured switch, failing safe and re-arming one way

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — (builds on [ADR-0079](0079-switches-are-measured-before-they-route.adr.md)) |

## Context

The owner asked on 2026-11-20 for release 2 to switch "between branches of workflow based on task complexity or other parameters, at least between simpler decomposition of workflow vs detailed decomposition with map". A detailed decomposition is not free: on small tasks it costs more than one session, while a long single session can time out on a large one ([R-126](../research/R-126-routing-by-complexity-between-decompositions.rsrch.md) F1). A switch between them is safe when it decides by counts a check can verify, takes the longer path on any fault, and escalates one way only. Public work favours trying the simple shape and decomposing on failure ([R-126](../research/R-126-routing-by-complexity-between-decompositions.rsrch.md) F4).

## Decision

We will add a **complexity switch**: a measured switch whose predicate the engine builds from declared model-free measures and a rules file of thresholds per arm ([CXR](../specs/94-complexity-routing.spec.md)). Arms are ordered from simple to detailed; the most detailed is the default and takes faults, the margin and anything no arm's bounds cover. A run re-arms at most once and only toward a more detailed arm, on a spent budget with climbing evidence or a step timeout. Every arm honours an arm contract for the units after it, and no arm changes the gates that verify the result. The remedy order for a failing unit is: effort ladder, re-arm, one model step, a person. A model's assessment of complexity counts only as a check fact.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| A plain switch with a hand-written predicate (SWM today) | Already designed | Each workflow reinvents measures, margins and failsafes; nothing reportable by zone |
| **Measures plus a rules file, failsafe to detailed, one-way re-arm (chosen)** | Deterministic, reportable, movable by measured proposals | Thresholds are guesses until runs exist |
| Always try simple first, decompose on failure (ADaPT style) | No prediction to get wrong | Most temperspec tasks are complex, so most runs pay one failed attempt |
| A model step picks the shape | Reads nuance | The step can pick the cheap path for itself (temperspec 7.4) |

## Decision rationale

| Criterion | Plain switch | Chosen | Fallback only | Model picks |
|---|---|---|---|---|
| Model-free routing (C1, C5) | yes | yes | yes | no |
| Fails to the safe shape | if written so | yes | yes | no |
| Reportable by zone and arm | no | yes | partly | no |
| Wasted attempts on complex tasks | depends | few | many | depends |

## Consequences

- Positive: "simple versus detailed decomposition" is a declared, measured choice any workflow can make.
- Negative: validation must prove the arm contract; authors declare `joins_at`.
- Risk: thresholds that send hard tasks to the simple arm. Mitigation: shadow mode first, the margin goes to the safe arm, and one re-arm on evidence.

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| X1 | "Other parameters" means anything a model-free measure can read: inputs, settings, labels, facts, the stage, an operator's pick. | CXR-B9 |
| X2 | Two or three arms cover the need. | CXR-B7 |

## Revisit when

A workflow needs a decomposition chosen per item, or the report shows the margin holding most runs.
