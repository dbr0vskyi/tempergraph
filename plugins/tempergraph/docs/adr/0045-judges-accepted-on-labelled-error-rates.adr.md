# ADR-0045 Accept a judge on its two error rates over a labelled gold set, bounded from below

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Every gate rests on one LLM judge, and nobody has measured how often a judge is wrong ([R-046](../research/R-046-eval-and-judge-gap-analysis.rsrch.md)). The design scores judges ([LIF](../specs/lifecycle-and-evals.spec.md)) and samples an audit judge ([JDG-B7](../specs/judge-and-verdict.spec.md)), but nothing says what a score must show before stable mode, filing or a report may trust a judge. Public work finds judges recognise good work and miss most bad work (true-negative rates under 25% in one study), that overall agreement hides this, and that judge-to-judge agreement is not correctness ([R-045 F1–F3, F5](../research/R-045-evaluating-llm-judges-public-practice.rsrch.md)).

## Decision

We will accept a judge binding for a gate only on a reviewed, class-balanced gold set, on two rates computed per criterion finding: the **catch rate** on known-bad findings and the **clean rate** on known-good findings, each judged on its Wilson 95% lower bound, plus bars on the flip rate under repeats and on robustness variants ([JCL-B16](../specs/judge-calibration.spec.md)). Labels come only from people and facts; another judge never supplies one. Acceptance licenses trust elsewhere and never changes a verdict.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Two error rates on gold, lower bounds (chosen) | Separates the dangerous error (false pass) from the costly one; small sets admit a judge only with near-zero misses | Needs at least 20 known-bad findings per gate before anything is accepted |
| One agreement or accuracy figure against labels | Simple | Hides an agreeable judge; picks the wrong judge at low prevalence of bad work ([R-045 F1](../research/R-045-evaluating-llm-judges-public-practice.rsrch.md)) |
| Production labels only (FBK in pull request 4) | No authoring effort; real cases | Few bad results reach a person; accepted results are weak labels; a judge can look reliable with no known-bad evidence |
| Agreement between two judges | Fully automatic | Measures consistency, not correctness; same-family judges share errors |
| Point thresholds (R-011 G7's example: false pass ≤ 0.05) | Easy to read | A set of 10 with no miss would pass with a true rate that could be 30% |

## Decision rationale

| Criterion | Chosen | One figure | Production only | Two judges | Point thresholds |
|---|---|---|---|---|---|
| Detects an agreeable judge | yes | no | weakly | no | yes |
| Honest at small sample sizes | yes | no | no | n/a | no |
| Cost to start | medium | medium | low | low | medium |
| Grounded in public practice | yes | no | partly | no | partly |

## Consequences

- Positive: "no one grades the judges" gets a definite answer per gate and binding, readable by every spec that trusts a grade.
- Positive: the bar is asymmetric (catch ≥ 0.75, clean ≥ 0.65 on lower bounds), matching that a false pass ships and a false fail only retries.
- Negative: no gate is accepted until someone writes or harvests at least 20 known-bad findings for it. Mitigation: harvest from real runs, and the readiness report lists the cases still needed.
- Risk: per-criterion findings of one case are correlated, so bounds are optimistic. Mitigation: minimum distinct-case counts; a clustered bound later.
- Risk: the default numbers are wrong. Mitigation: one config file, stricter-only overrides, revisited with the first scores.

## Assumptions

- The owner wants judge grades trusted only after measurement; no owner statement says so directly.
- Gold labels by one reviewer are good enough to start; a second review is recorded where available, not required.
- The bar numbers are defaults chosen so that 20 known-bad findings with one miss pass and with two misses fail.

## Revisit when

The first gates are scored live, or the self-improvement thread decides whether FBK's `reliable` grade requires this bar.
