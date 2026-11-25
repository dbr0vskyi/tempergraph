# OpenTelemetry GenAI conventions as an export format for run telemetry

## Problem statement

Point 4 of the owner's request asks for run stats and numbers from every machine in one place. The engine records everything locally ([OBS](../specs/observability-and-cost.spec.md)) and, until now, sent nothing anywhere. If a run is to reach a shared backend (a tracing store, a metrics system, an LLM observability product), the engine needs one export format that many backends read, and that format must not carry prompts, outputs or secrets (OVR-B11). This note records what the OpenTelemetry (OTel) generative-AI semantic conventions offer, how stable they are, and what that means for [TEL](../specs/telemetry-export.spec.md).

## Sources consulted

| Source | Type | Where |
|---|---|---|
| "OpenTelemetry GenAI semantic conventions" (Greptime blog, 2026-05) | Secondary article summarising semconv v1.36 to v1.41 | https://www.greptime.com/blogs/2026-05-09-opentelemetry-genai-semantic-conventions |
| LangSmith "trace with OpenTelemetry" page | Vendor documentation | https://docs.langchain.com/langsmith/trace-with-opentelemetry/index.html (fetch failed; not read) |
| Search results naming OTel-based LangGraph integrations (AWS Bedrock AgentCore, Google Cloud, Azure AI Foundry, Coralogix, Splunk) | Search listing only, pages not read | web search, 2026-11-19 |
| LangSmith self-hosting docs and license article | Vendor documentation | https://docs.langchain.com/langsmith/self-hosted.md, https://kb.langchain.com/articles/7011309930-how-do-i-obtain-a-self-hosted-langsmith-license-key |
| Langfuse OpenTelemetry integration | Vendor documentation | https://langfuse.com/integrations/native/opentelemetry.md |
| Phoenix environments and terminal deployment | Vendor documentation | https://www.arize.com/docs/phoenix/environments.md, https://arize.com/docs/phoenix/self-hosting/deployment-options/terminal.md |

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
| F9 | Self-hosted LangSmith is "an add-on to the Enterprise plan" and needs a license key from sales; its docs say trace data stays in your environment, but do not say what usage metadata leaves it. | supported |
| F10 | Langfuse accepts OTLP over HTTP (JSON or protobuf, not gRPC) at `/api/public/otel` (traces at `/api/public/otel/v1/traces`), including a local deployment at `http://localhost:3000/api/public/otel` (v3.22.0 or later), with Basic auth from a project key pair; it "aims to be compliant" with the GenAI conventions and maps `gen_ai.request.model`, `gen_ai.usage.*` and tool attributes. Its open-source license and compose setup were not read. | supported |
| F11 | Phoenix runs locally with `pip install arize-phoenix` and `phoenix serve`, UI and OTLP/HTTP on `http://localhost:6006` (`/v1/traces`), and needs no account or API key locally. Its license was not read. | supported |
| F8 | Names changed between minor versions three times in a year (v1.37 provider rename, v1.41 tool name in the span name and agent span kind). | supported |

## Conclusions

1. OTel with the GenAI conventions is the export format with the widest reach; nothing in tempergraph's records needs a vendor format.
2. The conventions are not stable, so the engine pins one semconv version, keeps every name in one mapping table ([TEL-B12 to TEL-B33](../specs/telemetry-export.spec.md)) and records the pinned version on every exported resource.
3. Cost has no convention: estimated and reported cost go out as tempergraph-namespaced attributes and metrics, kept apart as [ADR `cost-when-executor-reports-tokens-only`](../adr/cost-when-executor-reports-tokens-only.adr.md) requires.
4. Content capture is a convention option the engine never turns on; tool spans carry the tool name only. This matches the publish boundary ([SEC-B8 to SEC-B11](../specs/security.spec.md)).
5. Only the Messages API executor sees each model request; for the three agent executors the engine sees a session, not its requests, so a session is an `invoke_agent` span and per-request `chat` spans exist only for `messages-api`.
6. A fully local backend is possible today without LangSmith: Phoenix (one Python process, no account) or a self-hosted Langfuse both receive the engine's OTLP export on localhost. LangSmith itself runs locally only under an Enterprise license, so it is not the default. [TEL-B6, TEL-B8](../specs/telemetry-export.spec.md) adds a loopback-only mode so nothing can leave the machine by mistake.

## Open questions

| Question | Owner |
|---|---|
| Which backends the owner wants to read the export (a self-hosted tracing store, LangSmith, another product)? The design assumes "any OTLP receiver". | Owner |
| Does LangSmith's OTLP ingestion accept the pinned semconv version? Not read (fetch failed). | Engine implementer, before naming it in docs |
