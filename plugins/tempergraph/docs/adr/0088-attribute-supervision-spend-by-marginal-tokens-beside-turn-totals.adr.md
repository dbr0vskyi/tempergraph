# ADR-0088 Attribute a supervising session's spend to runs by marginal tokens, shown beside turn totals

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

A supervising session's message is billed for its whole context, which holds everything the session did, not only the run in question. A session may supervise several runs and do unrelated work. Most of an orchestrating session's own cost is re-writing its context into the cache after idle wakes ([R-085](../research/R-085-callers-supervision-and-babysitting-cost.rsrch.md) B2): the cost of babysitting is mostly the re-read the run causes, not the call.

## Decision

We will attribute per engine call two figures, never summed ([SCO §2.4](../specs/87-supervision-cost.spec.md)): a **marginal** figure (the issuing message's output share, the result the next message read, and the cache write of a wake the run caused, as `rewake`) and a **turn** figure (the whole usage of the messages involved, relay messages between a shown pause and its decision, and the whole usage of helper subagents that called about the run). Calls about an orchestration are split equally over its live runs. Everything else in the session is `other` and never on a run. Promotion and the audit use the marginal figure.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Marginal and turn, both shown (chosen) | Brackets the truth; names the re-read cost | Two numbers to explain |
| Turn totals only | Simple; matches the bill | Overstates per run; a long conversation makes every run look expensive |
| Output tokens only | Cheap to compute | Misses the re-read, the largest part (B2) |
| Whole session cost split over the runs it touched | Sums to the bill | Charges unrelated work to runs |

## Decision rationale

| Criterion | Both | Turn only | Output only | Split session |
|---|---|---|---|---|
| Counts the re-read after a wake | yes | yes | no | yes |
| Excludes unrelated work | yes | partly | yes | no |
| Comparable across sessions of different length | marginal yes | no | yes | no |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| D1 | Four bytes per token is close enough to price a result the next message read; the figure is capped by that message's actual new input. | SCO §2.4 |
| D2 | A message after 300 s of idle that follows a background engine call's end is a wake the run caused. | SCO §2.4 |

## Consequences

- Positive: a polling habit, long contexts and helper agents show up as figures per run.
- Negative: the marginal figure is an estimate and is labelled so.

## Revisit when

A host reports per-message cache hits and misses, or the first live orchestration gives a measured figure to check the marginal estimate against.
