# R-020 OpenTelemetry GenAI conventions as an export format for run telemetry

## Problem statement

Point 4 of the owner's request asks for run stats and numbers from every machine in one place. The engine records everything locally ([OBS](../specs/15-observability-and-cost.spec.md)) and, until now, sent nothing anywhere. If a run is to reach a shared backend (a tracing store, a metrics system, an LLM observability product), the engine needs one export format that many backends read, and that format must not carry prompts, outputs or secrets (contract C9). This note records what the OpenTelemetry (OTel) generative-AI semantic conventions offer, how stable they are, and what that means for [TEL](../specs/35-telemetry-export.spec.md).

## Sources consulted

| Source | Type | Where |
|---|---|---|
| "OpenTelemetry GenAI semantic conventions" (Greptime blog, 2026-05) | Secondary article summarising semconv v1.36 to v1.41 | https://www.greptime.com/blogs/2026-05-09-opentelemetry-genai-semantic-conventions |
| LangSmith "trace with OpenTelemetry" page | Vendor documentation | https://docs.langchain.com/langsmith/trace-with-opentelemetry/index.html (fetch failed; not read) |
| Search results naming OTel-based LangGraph integrations (AWS Bedrock AgentCore, Google Cloud, Azure AI Foundry, Coralogix, Splunk) | Search listing only, pages not read | web search, 2026-11-19 |

## Key findings

| # | Finding | Confidence |
|---|---|---|
| F1 | The GenAI and MCP conventions are in **Development** status (semconv v1.41.0 at the time of the article), with no public date for stability. `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` selects the latest attribute set. | supported |
| F2 | Span shapes: a model call is `chat {model}` (kind CLIENT); a tool run is `execute_tool {gen_ai.tool.name}` (INTERNAL); an agent run is `invoke_agent {name}` (INTERNAL for in-process frameworks such as LangGraph, CLIENT for remote agents); `invoke_workflow` was added in v1.41 for predefined paths. | supported |
| F3 | Attributes the engine can fill from its own records: `gen_ai.operation.name`, `gen_ai.provider.name` (replaced `gen_ai.system` in v1.37), `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.cache_read.input_tokens`, `gen_ai.usage.cache_creation.input_tokens`, `gen_ai.usage.reasoning.output_tokens`, `gen_ai.response.finish_reasons`, `gen_ai.agent.name`, `gen_ai.tool.name`. | supported |
| F4 | Evaluation results are an event, `gen_ai.evaluation.result`, with `gen_ai.evaluation.score.value` and `gen_ai.evaluation.score.label`. A judge's confidence and the engine's verdict fit this event. | supported |
| F5 | Message content is **off by default**: instrumentations gate it (commonly `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`), and full content goes on an opt-in event. Tool call arguments and results are recorded "only where privacy policy permits". | supported |
| F6 | Metrics: `gen_ai.client.operation.duration` and `gen_ai.client.token.usage` (with `gen_ai.token.type`). There is no cost metric in the conventions. | supported |
| F7 | Several vendors advertise OTel ingestion for LangGraph traces. Which of them accept which semconv version was not checked. | uncertain |
| F8 | Names changed between minor versions three times in a year (v1.37 provider rename, v1.41 tool name in the span name and agent span kind). | supported |

## Conclusions

1. OTel with the GenAI conventions is the export format with the widest reach; nothing in tempergraph's records needs a vendor format.
2. The conventions are not stable, so the engine pins one semconv version, keeps every name in one mapping table ([TEL §2.2](../specs/35-telemetry-export.spec.md)) and records the pinned version on every exported resource.
3. Cost has no convention: estimated and reported cost go out as tempergraph-namespaced attributes and metrics, kept apart as [ADR-0012](../adr/0012-cost-when-executor-reports-tokens-only.adr.md) requires.
4. Content capture is a convention option the engine never turns on; tool spans carry the tool name only. This matches the publish boundary ([SEC §2.3](../specs/14-security.spec.md)).
5. Only the Messages API executor sees each model request; for the three agent executors the engine sees a session, not its requests, so a session is an `invoke_agent` span and per-request `chat` spans exist only for `messages-api`.

## Open questions

| Question | Owner |
|---|---|
| Which backends the owner wants to read the export (a self-hosted tracing store, LangSmith, another product)? The design assumes "any OTLP receiver". | Owner |
| Does LangSmith's OTLP ingestion accept the pinned semconv version? Not read (fetch failed). | Engine implementer, before naming it in docs |
