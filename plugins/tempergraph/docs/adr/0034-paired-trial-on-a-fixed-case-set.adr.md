# ADR-0034 Compare workflow versions by a paired trial on a fixed case set, decided by a sign test

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

A proposal needs evidence ([ADR-0030](0030-improvement-closes-through-measured-proposals.adr.md)). Comparing versions on whatever runs arrive measures the issue mix, not the version. Optimizers in public work score candidates on a fixed dataset ([R-030 F3](../research/R-030-self-improving-agent-systems.rsrch.md)). Cases cost dollars each, so trials are small, and model output is not deterministic.

## Decision

We will run each case of a reviewed case set on the current and the proposed version, score each pair as win, loss or tie on one target metric, and decide on out-of-sample non-tied pairs: `shown_better` at the one-sided sign-test count for p ≤ 0.05 with every guard metric within its margin, `regressed` on the mirror count or a broken guard, otherwise `not_shown`; fewer than 8 non-tied pairs is `not_shown`. An A/A run records each case set's noise floor ([PRP-B18, PRP-B19, PRP-B20](../specs/improvement-proposals.spec.md), [R-031 F3](../research/R-031-self-improvement-gap-analysis.rsrch.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Paired sign test on a fixed set (chosen) | Distribution-free; pairs cancel case difficulty; exact at small n; easy to explain in a pull request | Low power: only large effects show |
| Compare means of unpaired recent runs | No case set needed | Measures issue mix |
| Bootstrap intervals or Bayesian comparison | Uses magnitudes | Harder to read; still needs the same pairs; little gain at n ≤ 20 |
| Judge-scored preference between A and B outputs | Cheap signal per pair | Judge biases (position, verbosity); grades an unmeasured judge |

## Decision rationale

| Criterion | Chosen | Unpaired | Bootstrap | Pairwise judge |
|---|---|---|---|---|
| Controls for case difficulty | yes | no | yes | yes |
| Valid at 8 to 20 cases | yes | no | partly | yes |
| Independent of judge reliability | yes, for deterministic targets | yes | yes | no |
| Readable by a reviewer | yes | yes | partly | yes |

## Consequences

- Positive: "shown better" means something a reviewer can check by counting.
- Negative: small fixes are mostly `not_shown`. Mitigation: `not_shown` is not a rejection; a person may merge with that report, and the post-release watch still applies.
- Risk: in-sample cases inflate results. Mitigation: cases harvested from the cluster's own runs are reported but never counted.

## Assumptions

- p ≤ 0.05 one-sided is a starting bar with no data behind it; it is a parameter with provenance `default_no_data` ([IMD](../specs/improvement-data.spec.md)).

## Revisit when

Ten trials and their A/A floors exist, so the bar and the minimum pair count can be fitted.
