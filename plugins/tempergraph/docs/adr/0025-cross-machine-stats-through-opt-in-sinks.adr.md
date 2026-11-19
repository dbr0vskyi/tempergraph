# ADR-0025 Gather numbers across machines through opt-in, metadata-only sinks, with a shared folder as the default kind and no tempergraph server

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner wants "runs stats and numbers from all the machines in single place". Today stats rows stay on each machine and "nothing is sent anywhere"; tracing to an external service was marked "a governance decision" ([OBS](../specs/15-observability-and-cost.spec.md)). The project is a framework for small teams and non-experts; asking them to run a service is a cost. Records shared beyond a machine must carry metadata only (contract C9).

## Decision

We will let each machine push metadata-only rows (`run`, `heartbeat`, optionally `session`) to sinks the operator configures, none by default, through a local outbox ([CST](../specs/34-central-run-stats.spec.md)). Two sink kinds ship: `directory`, a folder every machine can write in which each machine writes only its own subfolder, and `otlp`, an OpenTelemetry receiver ([TEL](../specs/35-telemetry-export.spec.md)). `stats --source` aggregates a sink. User and repository names are hashed by default. There is no tempergraph server.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Opt-in sinks: shared folder and OTLP (chosen) | Nothing to host for the folder; OTLP reuses a team's backend; off by default | Folder sync latency; a team must pick a folder |
| A tempergraph collector service | One query API; real-time | A service to host, secure and upgrade; most users would not run it |
| Push to a git repository | History and access control for free | Merge conflicts on every run; slow; commits from automation |
| A hosted SaaS | Zero setup | Data leaves the organization; a vendor dependency the project does not have |
| Keep local only | Simplest | The owner's request is unmet |

## Decision rationale

| Criterion | Sinks | Collector | Git | SaaS | Local |
|---|---|---|---|---|---|
| Meets "all machines in one place" | yes | yes | yes | yes | no |
| Nothing new to host | yes (folder) | no | yes | yes | yes |
| Data stays in the organization | yes | yes | yes | no | yes |
| Safe with offline laptops | yes (outbox) | needs retry | conflicts | needs retry | n/a |
| Off by default | yes | n/a | n/a | n/a | yes |

## Consequences

- Positive: a team gets totals by machine, user, repository, workflow, executor and model, and a live list of what is running or waiting anywhere.
- Negative: hashed names make a shared view less readable until an operator opts into names.
- Risk: a copied `machine.json` makes two machines write one folder. Mitigation: readers warn on duplicate row ids with different content.

## Assumptions

- The owner's machines can share a folder (a synced drive, a network share or a mounted bucket), or already run an OTLP backend.
- Hashing with a per-sink salt is enough pseudonymity for an internal team view.

## Revisit when

More than about 20 machines share one sink, or a consumer needs queries a file scan cannot answer quickly.
