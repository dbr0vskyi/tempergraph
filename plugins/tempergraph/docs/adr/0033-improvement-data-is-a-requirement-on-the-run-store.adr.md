# ADR-0033 The loop states its data needs as requirements on the shared run store

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner asked, in the same message, for an observability design that gathers run statistics from every machine into one place and keeps a per-repository `.tempergraph` folder with all logs; that design is a separate piece of work. The loop needs data from many machines too: the pattern rule and cost windows read one machine's ledger today, so a pattern seen once on each of three machines never fires ([R-031 F1](../research/R-031-self-improvement-gap-analysis.rsrch.md), G6).

## Decision

We will design no store for the loop. [IMD](../specs/43-improvement-data.spec.md) lists the records, fields, events, retention and privacy split the loop needs, as numbered requirements on the run store that the observability design owns. Every record that may leave a machine is metadata only, keyed by a pseudonymous machine id, a repository digest and a keyed request digest; evidence text never leaves. Every loop query falls back to local records and says which scope it read.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Requirements on the shared store (chosen) | One store, one schema policy; the monitor shows the loop for free | The loop depends on another design's progress |
| A loop-owned store | Independent | Two stores of the same runs, two privacy rules, drift |
| Local only | No new infrastructure | Cross-machine patterns stay invisible |

## Decision rationale

| Criterion | Chosen | Own store | Local only |
|---|---|---|---|
| One source of run truth | yes | no | yes |
| Cross-machine patterns | yes | yes | no |
| Works on one laptop | yes (fallback) | yes | yes |

## Consequences

- Positive: labels, proposals and trials appear in the monitor beside runs.
- Negative: field names may change when the store is designed. Mitigation: IMD says the store's names win.
- Risk: the aggregate becomes a leak of request content. Mitigation: canary tests on every record kind; keyed digests.

## Assumptions

- The observability design will keep metadata-only aggregation, consistent with C9.
