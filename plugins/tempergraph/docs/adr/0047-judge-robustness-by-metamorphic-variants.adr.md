# ADR-0047 Test judge robustness with templated variants of gold cases

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Known judge biases include favouring longer answers, being swayed by confident claims, and favouring their own model family ([R-045 F6, F7](../research/R-045-evaluating-llm-judges-public-practice.rsrch.md)). The design's mitigations (the step account labelled "claims to verify, not facts", UNVERIFIABLE for out-of-reach text, cross-family judging) are argued, not measured ([R-046 E6](../research/R-046-eval-and-judge-gap-analysis.rsrch.md)). Writing a separate biased case for each gold case doubles authoring work.

## Decision

We will generate four variants of each gold case by fixed engine templates with no model call (`persuasive_account`, `padded`, `reordered`, `out_of_reach`), expect each to leave every blocker's status class unchanged (or, for `out_of_reach`, never MET), and bar a judge whose variants flip more than a set share. Self-preference is reported as a catch-rate split by producer family, not barred ([JCL §2.2](../specs/50-judge-calibration.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Templated variants (chosen) | Reproducible; costs only judge sessions; no extra authoring | Template text is recognisable and may understate real persuasion |
| Model-written variants | Realistic | Non-reproducible; a model call that itself needs checking |
| Hand-written adversarial cases | Most realistic | Authoring cost per case; rarely done |
| No robustness test | Free | Known biases stay unmeasured |

## Decision rationale

| Criterion | Templated | Model-written | Hand-written | None |
|---|---|---|---|---|
| Repeatable score | yes | no | yes | n/a |
| Authoring cost | none | none | high | none |
| Realism | low to medium | high | high | — |

## Consequences

- Positive: the controls against persuasion and out-of-reach acceptance get a number.
- Negative: four extra judge sessions per case per score. Mitigation: variants run once, not `k` times; the score takes a cap.
- Risk: a judge learns to spot the template. Mitigation: model-written variants are a later option once the templated ones pass.

## Assumptions

- Status classes (pass against fail), not exact statuses, are the right invariant for padding and persuasion.

## Revisit when

Scores show templated variants never flip while production labels show persuasion-like misses.
