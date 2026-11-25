# ADR-0026 Export telemetry as OpenTelemetry with the GenAI conventions, pinned, and never with content

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Teams that already run a tracing or metrics backend want tempergraph runs there, next to their other services ([ADR-0025](0025-cross-machine-stats-through-opt-in-sinks.adr.md)). The OpenTelemetry GenAI conventions define agent, model-call, tool and evaluation spans and token metrics, are in Development status, and renamed attributes three times in a year; they gate message content behind an opt-in ([R-020](../research/R-020-opentelemetry-genai-conventions.rsrch.md)). LangGraph-specific tracing products exist but tie the export to one vendor.

## Decision

We will ship an OTLP exporter as an in-process observer in an optional extra, mapping runs to `invoke_workflow`, `invoke_agent`, `execute_tool`, `chat` (Messages API only) and `gen_ai.evaluation.result`, with tempergraph-namespaced names for units, checks, gates and cost, a pinned semconv version, and content capture never on ([TEL](../specs/telemetry-export.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| OTLP with GenAI conventions, pinned, no content (chosen) | Any OTLP backend; standard names where they exist | Conventions move; cost needs custom names |
| A vendor SDK (a LangGraph tracing product) | Rich UI for graphs | One vendor; usually captures inputs and outputs by default |
| Custom JSON over HTTP | Full control | Every backend needs an adapter |
| OTLP with content opt-in | Debugging in the backend | Breaks the publish boundary (C9) as soon as one operator turns it on |

## Decision rationale

| Criterion | OTLP pinned | Vendor SDK | Custom JSON | OTLP with content |
|---|---|---|---|---|
| Backends reached | many | one | none without work | many |
| Keeps C9 by construction | yes | no | yes | no |
| Survives convention changes | pin and table | vendor's job | n/a | pin and table |

## Consequences

- Positive: a team sees runs, units, sessions and gates as traces, and tokens and cost as metrics, in a backend they already use.
- Negative: for the three agent executors a session is one span; per-request detail exists only for the Messages API. Stated in [R-150 TEL](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).
- Risk: the conventions change after the pin. Mitigation: the mapping table is the one place names live, with a drift test.

## Assumptions

- The owner wants a backend view as an addition to the monitor, not instead of it; the monitor reads local files and needs no backend.

## Revisit when

The GenAI conventions reach Stable status, or an executor exposes per-request events the engine can turn into `chat` spans.
