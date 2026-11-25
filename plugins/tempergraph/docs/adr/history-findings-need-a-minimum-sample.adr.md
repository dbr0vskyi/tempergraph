# History findings need a minimum sample, report their n, and size limits from passing attempts

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The history layer reads recorded runs. Figures from a few runs per version move with the issue mix more than with the version, and a loop threshold set without data is only a default ([research `why-runs-fail-stall-repeat-or-overspend`](../research/why-runs-fail-stall-repeat-or-overspend.rsrch.md)). A timeout fits best near the 90th percentile of the same work; one global timeout fits nothing. An audit that reads a rate from two runs, or recommends a limit from failed attempts, would mislead.

## Decision

We will give every history rule a **minimum sample** (`min_n`, in runs, visits or attempts as the rule says). Below it the rule yields no finding and is listed as skipped with `n` and the minimum. Every history finding prints its numbers with their `n`. By default the window is 30 days of the **current workflow version**. Timeout advice is computed from the **p90 of passing attempts** only: a finding below 1.25 × p90, advice at about 1.5 × p90.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Minimum sample, n shown, passing-attempt p90 (chosen) | Honest about small data; limits follow what healthy work takes | Quiet on young workflows |
| Report any rate | Says something from the first run | Two runs make a 100% rate; a signal nearly every run raises ranks nothing |
| Statistical tests per rule (confidence intervals) | Principled | Heavy for a CLI report; few rules have enough runs for a test to mean anything early |
| Limits from all attempts | More data | Timed-out attempts end at the old limit and pull the figure toward it |

## Decision rationale

| Criterion | Min sample | Any rate | Tests | All attempts |
|---|---|---|---|---|
| Avoids findings from one or two runs | yes | no | yes | n/a |
| Simple to read | yes | yes | no | yes |
| Limit advice not biased by the current limit | yes | n/a | n/a | no |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| H1 | A workflow version identity exists on each run record (the ledger row), so the window can be one version. | AUD-B11, AUD-B6, AUD-B9 |
| H2 | The minimum samples (mostly 5 runs, 10 for unused grants, 20 attempts for infra share) are defaults with no data, revisited after the first 20 runs of a real workflow. | ARC, TSA |

## Consequences

- Positive: no finding rests on a sample too small to mean it; limit advice is grounded in the workflow's own healthy runs.
- Negative: a new workflow gets few history findings until it has runs.
- Risk: a version with a handful of runs hides a real problem. Mitigation: `--version all` widens the window, and the report says how many runs each skipped rule still needs.

## Revisit when

Shared run stats across machines (spec `central-run-stats`, PR 7) give enough runs for interval estimates.
