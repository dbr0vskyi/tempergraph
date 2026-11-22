# ADR-0048 Report judge-graded rates with the judge's state and a corrected estimate

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Per-criterion pass rates, gate pass rates, step-suite rates and judge-graded trial targets all count a judge's statuses as if true ([OBS-B15](../specs/15-observability-and-cost.spec.md)). A judge with known error rates biases such a rate in a known direction, and the Rogan-Gladen estimator corrects it from the judge's true-positive and true-negative rates ([R-045 F4](../research/R-045-evaluating-llm-judges-public-practice.rsrch.md)).

## Decision

We will show every judge-graded rate with its judge's acceptance state, and, for an accepted or provisional judge that separates well enough, a corrected estimate beside the raw rate. The raw rate is never hidden or replaced ([EVS-B15](../specs/51-eval-suites.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Raw plus state plus corrected (chosen) | A reader sees both the record and its likely bias | One more column; the correction carries the gold set's own uncertainty |
| Raw only | Simple | Overstates quality for an agreeable judge |
| Corrected only | One figure | Hides the record; wrong when the judge's rates are stale |
| Hide judge-graded rates until the judge is accepted | Safe | Throws away the only signal most workflows have early on |

## Decision rationale

| Criterion | Chosen | Raw only | Corrected only | Hide |
|---|---|---|---|---|
| Keeps the record | yes | yes | no | no |
| Shows bias | yes | no | yes | n/a |
| Useful before acceptance | yes (flagged) | yes | no | no |

## Consequences

- Positive: a reader can tell a real quality change from a judge artefact.
- Negative: corrected estimates on small gold sets are noisy. Mitigation: shown as a reading aid and labelled; an interval that carries calibration uncertainty is a later refinement.

## Assumptions

- A judge's error rates on gold cases carry over to production subjects of the same gate.

## Revisit when

Production labels (FBK) are numerous enough to estimate the rates on real subjects directly.
