# ADR-0029 Ship tempergraph's own observability first, capture everything locally, and defer third-party telemetry export

| | |
|---|---|
| Status | accepted |
| Date | 2026-11-20 |
| Authors | Claude (design session), decided by the owner |
| Supersedes | — (defers the release of [ADR-0026](0026-telemetry-export-as-otel-genai-without-content.adr.md); its design stands) |

## Context

The design offers two ways out of a machine: tempergraph's own sinks and fleet copy ([CST](../specs/34-central-run-stats.spec.md)), and OTLP export to a backend such as Phoenix, Langfuse or LangSmith ([TEL](../specs/35-telemetry-export.spec.md)). Asked about using existing telemetry products locally, the owner decided on 2026-11-20: "for now stay with our own observability, gathering everything we could". No run data is to go to a third-party tool for now.

## Decision

We will ship the local store ([LOS](../specs/33-local-observability-store.spec.md)), the observer events and activity journal ([EVT](../specs/30-run-events.spec.md)), the detail document ([RDD](../specs/31-run-detail-document.spec.md)), the monitor and the directory sink with its home fleet copy ([CST](../specs/34-central-run-stats.spec.md)) in the first release, and **defer** the OTLP exporter. TEL stays as a written design, status `draft`, not built. Locally the engine captures everything it can see: every session's raw stream, every normalized event, check and hook output, the engine's code log and per-session resource samples, and a directory sink carries all three row kinds by default.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Own observability now, export later (chosen) | One stack to build and test; no data handed to any other tool; the monitor covers the live view | No third-party trace UI until TEL is built |
| Build both now | Teams with a backend served at once | Twice the surface; a mapping to a convention still in Development status |
| Export only, no own store | Reuse a product's UI | Needs a product running; loses full logs and the monitor's drill-down |

## Decision rationale

| Criterion | Own first | Both now | Export only |
|---|---|---|---|
| Owner's instruction | yes | no | no |
| Data stays in tempergraph's own files | yes | partly | no |
| Effort for the first release | lower | higher | lower, but loses features |

## Consequences

- Positive: every fact a later exporter would need is already captured locally, so TEL can be built later as a reader of the same records.
- Negative: no LangSmith-style trace browser for now; the monitor and `stats`, `report`, `events`, `logs` are the views.
- Risk: the local store grows faster with full capture. Mitigation: `store usage`, the size warning and manual `store prune` ([LOS-B16](../specs/33-local-observability-store.spec.md)).

## Assumptions

- "Gathering everything we could" means locally, on the machine that ran the run; only metadata rows cross machines, through the owner's own shared folder.

## Revisit when

The owner wants a trace browser, or a team member already runs an OTLP backend.
