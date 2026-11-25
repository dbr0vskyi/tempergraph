# ADR-0046 Split calibration cases into tune and holdout, and score only on holdout

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Calibrating a judge by hand means writing cases, running the judge, and sharpening the brief or criteria until the judge grades them right. When the same cases then count as the judge's score, the score measures the fit: a brief fitted to a set no longer has its error measured by that set ([R-045 F14](../research/R-045-evaluating-llm-judges-public-practice.rsrch.md)). The improvement proposer of the parallel self-improvement design also edits briefs from cases ([R-046 E7](../research/R-046-eval-and-judge-gap-analysis.rsrch.md)).

## Decision

We will mark every gold case `holdout` when written and `tune` the first time it is shown to anyone editing that gate's brief, stance or criteria, with no way back. The acceptance bar is computed on holdout cases only ([JCL-B11](../specs/judge-calibration.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| One-way tune marking on use (chosen) | Automatic; no fixed ratio to guess; the holdout set shrinks only when used | Authors who iterate a lot consume cases quickly |
| A fixed random split at authoring (for example 50/50) | Standard in machine learning | Half the cases are unusable for tuning even when never needed; a small set gets smaller |
| No split | Every case counts | Scores measure the fit, not the judge |

## Decision rationale

| Criterion | One-way marking | Fixed split | No split |
|---|---|---|---|
| Score measures unseen cases | yes | yes | no |
| Keeps small sets usable | yes | no | yes |
| Needs author discipline | no (tools mark) | yes | no |

## Consequences

- Positive: a score always means "on cases the brief was not fitted to".
- Negative: a gate whose author tuned on most cases falls below the bar and needs new ones. Mitigation: `evals bar` lists exactly how many holdout findings are missing.
- Risk: a person reads cases outside the tools. Mitigation: the rule is stated in the authoring skill; it cannot be enforced beyond the tools.

## Assumptions

- The authoring skill and the proposer are the main readers of cases during brief edits.

## Revisit when

Gold sets grow large enough (hundreds of findings per gate) that a fixed split costs little.
