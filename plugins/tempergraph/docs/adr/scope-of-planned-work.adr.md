# Fold planned work into the design by fixed rules

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The design starts beside a list of planned work not yet built: about 70 engine capabilities and seven temperspec areas. The owner asked whether the design took them into account. [research `planned-work-coverage`](../research/planned-work-coverage.rsrch.md) checks every item against the specs. A rule is needed for which items enter the first design and which wait, so the choice is not made item by item without a reason.

## Decision

We will add a planned capability to the specs when it is a contract, a record or a model-free check that later work would otherwise have to retrofit (a field, a verb, a counter, a report row). We will defer it, naming it in the owning spec or in research `planned-work-coverage`, when it rests on an unrun probe of a real binary, needs measured judge reliability first, or is batch, schedule or multi-repository orchestration. Items that are code hygiene rather than a capability, or another plugin's or temperspec's own work, do not apply. Each added item is marked in research `planned-work-coverage` with its owning spec.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Fixed rules: add contracts and records, defer what needs data (chosen) | Retrofits are avoided where they are costly; deferrals carry reasons | Some designed items wait |
| Add everything planned | Complete | Specs would assert behaviour that rests on unrun probes and unmeasured judges, against the honesty rule |
| Add nothing; keep the planned list as reference | Small specs | Records, verbs and fields get added after data already exists, a costly retrofit |

## Decision rationale

| Criterion | Fixed rules | Everything | Nothing |
|---|---|---|---|
| Avoids retrofitting records and contracts | yes | yes | no |
| Keeps unproven behaviour out of specs | yes | no | yes |
| Every planned item has a stated fate | yes | yes | no |

## Consequences

- Positive: run-level spend cap, facts verb, lifecycle hooks, run aliases, prompt lint, live judge scoring and the other added items have owners from the start.
- Negative: the specs grow by about a tenth. Mitigation: every spec stays within its 400-line budget; research `planned-work-coverage` is the index, not a copy.
- Risk: deferred items are forgotten. Mitigation: each sits in a spec's open questions or in research `planned-work-coverage`, which a plan must read.

## Revisit when

A first live run records the probe results and judge scores the deferred items wait on.
