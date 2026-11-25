# ADR-0064 A contest runs several candidates and keeps the best by the gate's own judge and a fixed rule

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

"Best of n" (generate several alternatives, keep one) is the other half of the voting pattern ([R-060](../research/R-060-node-types-against-langgraph.rsrch.md) H3). It suits work where one good output beats an average of several: a plan, a draft, a patch. Selecting needs a grader; the engine already has one per gate, an independent judge whose verdict is derived by rule.

## Decision

We will add a unit kind **`contest`** ([CTS](../specs/contest-unit.spec.md)):

1. 2 to 5 **candidate slots** run the same step (optionally with a different executor, model or prompt variant per slot). Candidates that write files run in their own writer worktrees.
2. Each candidate passes the gate's **check** first; each that passes is graded by a **fresh session of the gate's own judge**, which sees that candidate only, never a comparison.
3. The engine **picks** by a fixed order: a derived PROCEED first, then fewest unmet warnings, then most criteria met, then highest confidence, then lowest cost, then slot order. The winner's artifacts become the unit's; a writer winner is merged, losers are discarded.
4. When no candidate passes, the unit's verdict is the best candidate's, and RETRY refines that candidate alone by default (`retry_scope: best`), or reruns all.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Gate's judge per candidate, pick by rule (chosen) | The same calibrated judge that guards the gate; no new grader to calibrate; no position bias | N judge sessions |
| A pairwise comparison judge | Finer choice between two good candidates | A new judge kind to calibrate; position and length bias (R-045) |
| A council chooses the winner | Several views | A model decides the outcome; costs a council on top |
| Generate once, retry on failure (today) | Cheapest | Retries carry the first attempt's direction; no exploration |

## Decision rationale

| Criterion | Judge per candidate | Pairwise | Council pick | Retry only |
|---|---|---|---|---|
| Outcome by rule | yes | partly | no | yes |
| Uses an accepted judge | yes | no | no | yes |
| Exploration | yes | yes | yes | no |
| Cost per attempt | 2N | N + N−1 | N + council | 2 |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| T1 | A judge's per-candidate verdict and counts are good enough to rank candidates; ties fall to cost and order, not to a model. | CTS-B1 to CTS-B5 |
| T2 | Losing candidates' work is not needed after the run; their records stay in the run log. | CTS-B6 to CTS-B10, WSP |

## Consequences

- Positive: an author can trade money for first-pass quality on one unit with one field. Eval and audit read per-candidate judgements as items.
- Negative: cost is roughly N times a step plus N judges; preflight shows the projection.
- Risk: candidates on one model are near-copies. Mitigation: the audit flags a contest whose slots share executor, model and prompt (`contest-identical-slots`).

## Revisit when

Pass-rate data show a contest's first-pass yield no better than a single step's with retries for the same cost.
