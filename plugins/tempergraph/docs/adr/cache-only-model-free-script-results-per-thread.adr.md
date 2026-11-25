# Cache only model-free script results, per thread, keyed by declared inputs

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

LangGraph offers a node cache keyed by input ([research `node-types-against-langgraph`](../research/node-types-against-langgraph.rsrch.md) L16). In this engine a retry or a trip back re-enters units whose inputs have not changed: an export, a render, a build of an untouched part. For model steps and judges a cache is wrong: a judge must run fresh on each subject (C4), and a cached step answer would replay a failed direction.

## Decision

We will allow `cache: thread` on a **script** unit or a hybrid step's script whose `side_effects` is `none` ([SCR](../specs/script-units-and-hybrid-steps.spec.md)). The key is a digest of the resolved argv or callable reference with the package's content digest, the rendered arguments, and the content digests of the declared inputs (artifact keys, paths, or the workspace tree). A hit restores the recorded outputs and result, is logged with `cached: true`, and spends nothing. Caches live under the thread's folder and are deleted with it. Model steps, judges, councils and contests are never cached.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Script-only, per thread (chosen) | Saves repeat work on retries and trips back; cannot hide a model's nondeterminism | Authors must declare inputs and side effects |
| Cache any node by state digest | Broadest | Caches judges (breaks C4) and steps (replays failures) |
| Cross-thread cache | More hits | Stale outputs across runs; harder to reason about |
| No cache | Simplest | Repeated exports and builds on every trip back |

## Decision rationale

| Criterion | Script, thread | Any node | Cross-thread | None |
|---|---|---|---|---|
| Keeps C4 | yes | no | yes | yes |
| Hit is provably the same work | yes, by declared inputs | no | partly | n/a |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| K1 | Authors can name a script's inputs; a script that cannot is left uncached. | SCR-B9 |

## Consequences

- Positive: cheaper, faster trips back for pipelines with heavy model-free steps.
- Negative: one more field set to validate.
- Risk: an undeclared input makes a hit stale. Mitigation: `inputs: workspace` keys on the whole tree; the audit flags cached scripts whose declared inputs are paths only and whose command reads elsewhere when history shows a later FAIL after a hit.

## Revisit when

A measured workflow shows scripts spending more than 10% of run time on cache-eligible repeats across threads.
