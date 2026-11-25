# ADR-0122 A judge is raised by a model-free risk rule, and every level is calibrated

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Choosing a judge's model and effort by risk has no design yet; temperspec gets the same effect with a fixed stronger code judge ([R-121](../research/R-121-judge-model-by-risk-and-evidence-for-escalation.rsrch.md) F1). A judge's alias is part of its calibrated binding ([JCL](../specs/judge-calibration.spec.md)), so a judge whose model varies is several judges. The owner put judges into release 2 on 2026-11-20.

## Decision

We will let a gate declare a **risk rule**: a pure, model-free function of engine-observed facts (check facts, the attempt's diff, inputs, the item, settings, the stage) that picks one of two or three judge levels ([JRK](../specs/judge-model-by-risk.spec.md)). Levels only rise from the gate's own judge; a fault picks the strongest; the rule never reads what the step wrote; a producer on an escalated tier floors the judge at that tier; each level is its own binding, scored, labelled and graded apart; stable mode and promotion need every level used in route mode `accepted`; a shadow mode records the level and runs the base judge.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Fixed judge per gate (today) | One binding to calibrate | Overpays on small work or underjudges large work |
| **Model-free risk rule, levels up only, each calibrated (chosen)** | Stronger judge where the work is risky; every level measured | More calibration cases to score; a rule to maintain |
| A model classifies risk | Reads nuance | An unmeasured judge in front of the judge; the step can steer it |
| Risk may lower the judge | Saves on easy work | The agreeable-judge hazard ([R-045](../research/R-045-evaluating-llm-judges-public-practice.rsrch.md)) |

## Decision rationale

| Criterion | Fixed | Chosen | Model classifier | Lowering |
|---|---|---|---|---|
| Every grade from a calibrated binding | yes | yes | no | yes if scored |
| The step cannot weaken its own judge | yes | yes | no | no |
| Spends more judging only where risk is shown | no | yes | yes | yes |

## Consequences

- Positive: the "stronger code judge" becomes data any workflow can use, and is measured.
- Negative: scoring cost rises with the number of levels.
- Risk: a rule that always picks the top level. Mitigation: the shadow report shows the level mix and cost before route mode.

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| J1 | "Judges" in the owner's release 2 ask means judge model by risk; calibration and labels are already in release 1. | Scope |
| J2 | Two or three levels are enough. | JRK-B6 |

## Revisit when

A workflow needs a fourth level, or the shadow report shows a rule that never picks level 0.
