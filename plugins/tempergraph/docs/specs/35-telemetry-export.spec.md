---
title: Telemetry export
type: component
status: review
prefix: TEL
adrs: [0025, 0026, 0027]
---

# Telemetry export

## 1. Overview

The `otlp` sink ([CST §2.3](34-central-run-stats.spec.md)): runs exported as OpenTelemetry traces and metrics to any OTLP receiver, using the GenAI semantic conventions where they fit and `tempergraph.*` names where they do not ([R-020](../research/R-020-opentelemetry-genai-conventions.rsrch.md)). It is an in-process observer ([EVT §2.6](30-run-events.spec.md)) shipped in the optional `tempergraph[otel]` extra, off unless a sink of kind `otlp` is configured. Content capture is never turned on: no prompt, output, tool input or evidence is exported.

## 2. Contract

### 2.1 Sink fields (in addition to CST §2.3)

| Field | Meaning |
|---|---|
| `endpoint` | OTLP endpoint (gRPC or HTTP/protobuf) |
| `headers_profile` | Name of an operator file of header lines (for an API key); values never logged |
| `signals` | Subset of `traces`, `metrics`; default both |
| `semconv` | Pinned semantic-convention version; default the engine release's pin |
| `local_only` | `true` (default): the endpoint must resolve to a loopback address (`localhost`, `127.0.0.0/8`, `::1`), else the sink is refused at preflight; `false` only when the operator sends to a remote backend on purpose |

### 2.2 Mapping

One trace per segment (start or resume) of a thread; segments of one thread share `tempergraph.thread_hash` and the first span of a resume links to the last span of the previous segment.

| Engine thing | Span name | Kind | Key attributes |
|---|---|---|---|
| Segment of a run | `invoke_workflow {workflow}` | INTERNAL | `tempergraph.thread_hash`, `tempergraph.segment`, `tempergraph.workflow.version`, `tempergraph.origin`, `tempergraph.exit_code`, `tempergraph.exit_reason` |
| Unit visit | `unit {name}` | INTERNAL | `tempergraph.unit`, `tempergraph.visit`, `tempergraph.entered_from` |
| Step or judge session | `invoke_agent {kind}` | INTERNAL (CLI executors are children of the engine) | `gen_ai.agent.name` = `<workflow>.<unit>.<kind>`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.usage.*`, `tempergraph.executor`, `tempergraph.cli_version`, `tempergraph.cost.reported_usd`, `tempergraph.cost.estimated_usd`, `tempergraph.outcome` |
| A model request (`messages-api` only) | `chat {model}` | CLIENT | `gen_ai.usage.*`, `gen_ai.response.finish_reasons` |
| Tool call | `execute_tool {name}` | INTERNAL | `gen_ai.tool.name`, `tempergraph.tool.capability`, `tempergraph.tool.ok`; never arguments or results |
| Check | `check {unit}` | INTERNAL | `tempergraph.check.result`, `tempergraph.check.environmental` |
| Gate | `gate {unit}` | INTERNAL | `tempergraph.verdict`, `tempergraph.route_target`, event `gen_ai.evaluation.result` with `gen_ai.evaluation.score.value` = judge confidence and `gen_ai.evaluation.score.label` = verdict; `tempergraph.criteria.met`, `tempergraph.criteria.total` |
| Pause | event `tempergraph.pause` on the segment span | | kind, `tempergraph.decisions` |

`gen_ai.provider.name` per executor: `anthropic` for `claude`, `agent-sdk` and `messages-api` (the cloud provider's name when the binding routes through one), `gcp.gemini` for `antigravity`.

| Metric | Instrument | Attributes |
|---|---|---|
| `gen_ai.client.token.usage` | histogram | `gen_ai.token.type`, provider, model, `tempergraph.executor`, `tempergraph.kind` |
| `gen_ai.client.operation.duration` | histogram | as above |
| `tempergraph.cost.estimated` | counter, USD | workflow, executor, kind |
| `tempergraph.cost.reported` | counter, USD | workflow, executor, kind; only for sessions that reported one |
| `tempergraph.gate.verdicts` | counter | workflow, unit, verdict |
| `tempergraph.runs` | counter | workflow, exit reason |
| `tempergraph.runs.live` | up-down counter | workflow, state |

Resource attributes: `service.name = tempergraph`, `service.version`, `tempergraph.machine_id`, `tempergraph.semconv`, and `tempergraph.user`, `tempergraph.repo_id` per the sink's privacy settings ([CST §2.4](34-central-run-stats.spec.md)).

### 2.3 Delivery

Spans and metrics are batched by the observer thread and sent by the OTel SDK's exporter with a bounded queue (2 048 spans) and a 10 s export timeout. A full queue drops and counts the drop on the segment span. Spans of a segment that the process could not export before exit are written to the sink's outbox as OTLP JSON and sent by the next flush.

### 2.4 Local backends

The first supported use is a backend on the operator's own machine, so traces can be browsed in a LangSmith-like interface while no data leaves it ([R-020](../research/R-020-opentelemetry-genai-conventions.rsrch.md) F9 to F11).

| Backend | Start | Sink `endpoint` | Notes |
|---|---|---|---|
| Phoenix (default suggestion) | `pip install arize-phoenix`, `phoenix serve` | `http://localhost:6006/v1/traces` | No account; one process |
| Langfuse, self-hosted | its own local deployment | `http://localhost:3000/api/public/otel` | HTTP only, no gRPC; project key pair via `headers_profile` |
| LangSmith, self-hosted | Enterprise licence only | its local OTLP endpoint | Not the default: needs a licence |
| Any OTLP collector (Jaeger, Grafana stack) | as documented by it | its OTLP/HTTP endpoint | Generic traces, no LLM-specific views |

A backend's own telemetry to its vendor, if any, is that backend's setting; the operator checks it before use. The engine never sends content to any of them (§1).

## 3. Behaviours

**TEL-B1 One trace per segment.** Given a run that pauses once and is resumed, when both segments are exported, then the receiver holds two traces sharing `tempergraph.thread_hash`, the second's root linked to the first's last gate span.

**TEL-B2 Mixed executors.** Given a step on `antigravity` and its judge on `claude`, when exported, then the step's `invoke_agent` span has `gen_ai.provider.name = gcp.gemini`, `tempergraph.cost.estimated_usd` set and `tempergraph.cost.reported_usd` absent; the judge's span has both.

**TEL-B3 No content.** Given the canary test, when every span and metric of a run is captured by an in-memory exporter, then no attribute value, event or resource holds the canary.

**TEL-B4 Receiver down.** Given an endpoint that refuses connections, when a run ends, then the run's exit code is unchanged, and the segment's spans are in the outbox as OTLP JSON.

**TEL-B6 Local only.** Given `local_only` left at its default and an endpoint `https://otel.example.com`, when a run is preflighted, then the sink is refused with a warning naming the endpoint, the run starts, and nothing is exported.

**TEL-B5 Semconv pin.** Given an engine release pinned to semconv version V, when a sink sets a different version, then the observer refuses to start, records it, and the run proceeds unexported.

## 4. Error conditions

| Condition | Result |
|---|---|
| `tempergraph[otel]` not installed but an `otlp` sink configured | Preflight warning, recorded; the run starts |
| Header file missing | The sink is disabled for the run, recorded |
| Attribute value longer than 256 characters | Cut, never sent whole |

## 5. Design notes

- OTLP reaches the most backends with one exporter; the engine needs no vendor client ([ADR-0026](../adr/0026-telemetry-export-as-otel-genai-without-content.adr.md)).
- The GenAI conventions are in Development status and renamed attributes three times in a year, so every name lives in the table of §2.2 and the pinned version travels on the resource.
- A CLI session is a span, not a set of `chat` spans: only the Messages API executor sees individual requests. This is stated so a reader of the backend does not expect per-turn spans for the other executors.
- Cost has no convention; it is exported in the engine's namespace with reported and estimated apart.

## 6. Acceptance criteria

- [ ] TEL-AC-1 An in-memory exporter test reproduces the span tree and attributes of §2.2 for a fixture run on each executor.
- [ ] TEL-AC-2 TEL-B3 passes with every row of [SEC-B2](14-security.spec.md)'s canary fields.
- [ ] TEL-AC-3 A failure injected into the exporter leaves the run's exit code unchanged.
- [ ] TEL-AC-4 The mapping table is generated from the observer's constants and checked by a drift test.

## Open questions

| Question | Owner |
|---|---|
| Which backend the owner reads first; the design names none ([R-020](../research/R-020-opentelemetry-genai-conventions.rsrch.md)). | Owner |

## References

[CST](34-central-run-stats.spec.md) · [EVT](30-run-events.spec.md) · [OBS](15-observability-and-cost.spec.md) · [R-020](../research/R-020-opentelemetry-genai-conventions.rsrch.md)
