# ADR-0049 Grade step and workflow evals by code, then an accepted judge, then a person

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The design has evals for judges but none of its own for checks, steps or whole workflows; prompt quality is seen only as live gate rates ([R-046 E12–E14](../research/R-046-eval-and-judge-gap-analysis.rsrch.md)). Public guidance names three grader kinds (code, model, human), says model graders need calibration against humans, and recommends pass^k where consistency matters ([R-045 F10, F11](../research/R-045-evaluating-llm-judges-public-practice.rsrch.md)). Using an unmeasured judge to grade an eval would rebuild the problem this work closes.

## Decision

We will grade every step and workflow eval case by the first grader that can decide it: code assertions and the gate's check, then the gate's or outcome judge only if it is `accepted` under [JCL](../specs/50-judge-calibration.spec.md), then a person. A case no grader decides is `needs_person` and counts in no rate. Live suites are opt-in and capped; only model-free suites run in CI ([EVS](../specs/51-eval-suites.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Fixed order with an accepted-judge rung (chosen) | Cheap where code decides; never trusts an unmeasured judge | Early on many cases need a person |
| Always grade with the gate's judge | Fully automatic | Grades with an unmeasured, likely agreeable judge |
| Always a person | Gold standard | Too costly to run often |
| Code only | Free, objective | Cannot judge most step outputs |

## Decision rationale

| Criterion | Fixed order | Judge always | Person always | Code only |
|---|---|---|---|---|
| Trustworthy result | yes | no | yes | where it applies |
| Running cost | low to medium | low | high | none |
| Coverage | full | full | full | partial |

## Consequences

- Positive: step and workflow evals exist with the same discipline as gates: deterministic first.
- Negative: until judges are accepted, step suites without assertions need a person. Mitigation: authors add `expect` assertions where a requirement is mechanical, as the authoring rules already ask.
- Risk: live suites are skipped because they cost money. Mitigation: model-free regression suites gate the stamp; live results are shown with their age and binding.

## Assumptions

- The owner accepts that evals of model behaviour are run by a person on demand, not in CI.

## Revisit when

Most gates are `accepted`, so the person rung is rarely reached.
