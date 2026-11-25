# Telemetry export

## Purpose

The `otlp` sink ([CST](central-run-stats.spec.md), [ADR-0025](../adr/0025-cross-machine-stats-through-opt-in-sinks.adr.md)) exports runs as OpenTelemetry traces and metrics to any OTLP receiver, so a team that already runs a tracing backend, or an operator who wants a local trace browser, can read runs there. It uses the GenAI semantic conventions where they fit and `tempergraph.*` names where they do not, under one pinned version ([R-020](../research/R-020-opentelemetry-genai-conventions.rsrch.md), [ADR-0026](../adr/0026-telemetry-export-as-otel-genai-without-content.adr.md)), and never exports content. What a backend itself sends to its vendor is that backend's setting, which the operator checks before use. The exporter is deferred ([ADR-0029](../adr/0029-own-observability-first-export-deferred.adr.md)): until it is built, nothing is sent to any third-party tool.

## Behaviours

### TEL-B1 One trace per segment

WHEN the segments of a thread are exported THE exporter SHALL send each segment, a start or a resume ([EVT](run-events.spec.md)), as a trace of its own.

- GIVEN a run that pauses once and is resumed WHEN both segments are exported THEN the receiver holds two traces
- GIVEN a run that never pauses WHEN its segment is exported THEN the receiver holds one trace

### TEL-B2 Mixed executors

WHEN a run mixes executors THE exporter SHALL describe each session by its own executor: its `gen_ai.provider.name`, its `tempergraph.cost.estimated_usd`, and `tempergraph.cost.reported_usd` only when that executor reported a cost ([OBS](observability-and-cost.spec.md)).

- GIVEN a step on `antigravity` and its judge on `claude` WHEN exported THEN the step's `invoke_agent` span has `gen_ai.provider.name` `gcp.gemini`, `tempergraph.cost.estimated_usd` set and `tempergraph.cost.reported_usd` absent, and the judge's span has both cost attributes

### TEL-B3 No content

WHEN a run is exported THE exporter SHALL carry no prompt, output, tool input or evidence in any span, event, metric or resource attribute.

- GIVEN the canary test ([SEC-B2](security.spec.md)) WHEN every span and metric of a run is captured by an in-memory exporter THEN no attribute value, event or resource holds the canary

### TEL-B4 Receiver down

WHEN the receiver refuses connections as a run ends THE exporter SHALL leave the run's exit code unchanged.

- GIVEN an endpoint that refuses connections WHEN a run ends THEN the run's exit code is unchanged

### TEL-B5 Semconv pin

WHEN a sink's `semconv` names a version other than the one the engine release pins THE exporter SHALL refuse to start for that run, with the refusal recorded, so the run proceeds unexported.

- GIVEN an engine release pinned to semconv version V WHEN a sink sets a different version THEN the exporter refuses to start, records it and the run proceeds unexported
- GIVEN the same release WHEN a sink sets V, or sets no `semconv`, THEN the exporter starts

### TEL-B6 Local only

WHEN a run is preflighted with `local_only` `true` and an `endpoint` that does not resolve to a loopback address (`localhost`, `127.0.0.0/8` or `::1`) THE engine SHALL refuse the sink with a warning that names the endpoint, so the run starts and exports nothing.

- GIVEN `local_only` left at its default and an endpoint `https://otel.example.com` WHEN a run is preflighted THEN the sink is refused with a warning naming the endpoint, the run starts and nothing is exported
- GIVEN `local_only` at its default and an endpoint on `localhost`, in `127.0.0.0/8` or at `::1` WHEN a run is preflighted THEN the sink is accepted
- GIVEN an operator who sends to a remote backend on purpose and sets `local_only` to `false` WHEN a run is preflighted with the endpoint `https://otel.example.com` THEN the sink is accepted

### TEL-B7 Off without an `otlp` sink

WHEN no sink of kind `otlp` is configured THE exporter SHALL send no span and no metric to any receiver.

- GIVEN a run with no sink, or with only a `directory` sink WHEN it ends THEN no OTLP request leaves the machine

### TEL-B8 Endpoint

WHEN a run is exported THE exporter SHALL send it to the sink's `endpoint`, over gRPC or HTTP/protobuf.

- GIVEN a receiver that speaks OTLP over gRPC WHEN its address is the sink's `endpoint` THEN the run's data arrives there over gRPC
- GIVEN a local Phoenix and a sink with no `headers_profile` WHEN the sink's `endpoint` is `http://localhost:6006/v1/traces` THEN the run's traces arrive there over HTTP
- GIVEN a self-hosted Langfuse and a `headers_profile` holding its project key pair WHEN the sink's `endpoint` is `http://localhost:3000/api/public/otel` THEN the run's traces arrive there over HTTP, never gRPC
- GIVEN another OTLP collector, such as Jaeger or the Grafana stack WHEN the sink's `endpoint` is its OTLP/HTTP address THEN the run's traces arrive there

### TEL-B9 Header profile sent

WHEN a sink names a `headers_profile` THE exporter SHALL send the header lines of that operator file with every export request.

- GIVEN a `headers_profile` whose file holds the line `x-api-key: k-123` WHEN a run is exported THEN every request the receiver gets carries that header line

### TEL-B10 Header values are never logged

WHEN a sink uses a `headers_profile` THE engine SHALL write no header value to any log, record or error text.

- GIVEN a `headers_profile` whose file holds the planted value `k-canary-9` WHEN a run is exported, including to a receiver that rejects the key, THEN no log, record or error text holds `k-canary-9`

### TEL-B11 Signals

WHEN a run is exported THE exporter SHALL send only the signals the sink's `signals` lists, `traces`, `metrics` or both, and both when `signals` is not set.

- GIVEN `signals` set to `traces` WHEN a run is exported THEN the receiver gets spans and no metric
- GIVEN `signals` set to `metrics` WHEN a run is exported THEN the receiver gets metrics and no span
- GIVEN a sink that sets no `signals` WHEN a run is exported THEN the receiver gets spans and metrics

### TEL-B12 Segments share the thread hash

WHEN the segments of one thread are exported THE exporter SHALL give their traces the same `tempergraph.thread_hash`.

- GIVEN a run that pauses once and is resumed WHEN both segments are exported THEN the receiver holds two traces sharing `tempergraph.thread_hash`

### TEL-B13 A resumed segment links back

WHEN a resumed segment is exported THE exporter SHALL link the first span of its trace to the last span of the previous segment's trace.

- GIVEN a run that pauses at a gate and is resumed WHEN both segments are exported THEN the second trace's root is linked to the first trace's last `gate` span

### TEL-B14 Segment span

WHEN a segment is exported THE exporter SHALL send the segment span, named `invoke_workflow {workflow}`, of kind INTERNAL, with `tempergraph.thread_hash`, `tempergraph.segment`, `tempergraph.workflow.version`, `tempergraph.origin`, `tempergraph.exit_code` and `tempergraph.exit_reason`.

- GIVEN the second segment of workflow `release-notes`, ended with exit code 0 WHEN it is exported THEN its span is `invoke_workflow release-notes` of kind INTERNAL with `tempergraph.segment` 1 and `tempergraph.exit_code` 0

### TEL-B15 Unit span

WHEN a unit visit is exported THE exporter SHALL send a span named `unit {name}`, of kind INTERNAL, with `tempergraph.unit`, `tempergraph.visit` and `tempergraph.entered_from`.

- GIVEN the second visit of unit `code`, entered by a trip back from unit `plan` WHEN it is exported THEN the span is `unit code` with `tempergraph.unit` `code`, `tempergraph.visit` 2 and `tempergraph.entered_from` `back:plan`

### TEL-B16 Session span

WHEN a step or judge session is exported THE exporter SHALL send a span named `invoke_agent {kind}`, of kind INTERNAL, with `gen_ai.agent.name` set to `<workflow>.<unit>.<kind>`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.usage.*`, `tempergraph.executor`, `tempergraph.cli_version`, `tempergraph.cost.estimated_usd`, `tempergraph.cost.reported_usd` when the executor reported a cost, and `tempergraph.outcome`.

- GIVEN the judge session of unit `plan` in workflow `release-notes` on `claude` WHEN it is exported THEN the span is `invoke_agent judge` with `gen_ai.agent.name` `release-notes.plan.judge` and `tempergraph.executor` `claude`

### TEL-B17 Model request span

WHEN a model request of a `messages-api` session is exported THE exporter SHALL send a span named `chat {model}`, of kind CLIENT, with `gen_ai.usage.*` and `gen_ai.response.finish_reasons`.

- GIVEN a `messages-api` step session that made two model requests WHEN it is exported THEN the trace holds two `chat` spans of kind CLIENT

### TEL-B18 An agent session is one span

WHEN a session on `claude`, `agent-sdk` or `antigravity` is exported THE exporter SHALL send it as one `invoke_agent` span and no `chat` span.

- GIVEN a `claude` step session that made 12 model requests WHEN it is exported THEN the trace holds one `invoke_agent step` span for it and no `chat` span

### TEL-B19 Tool span

WHEN a tool call is exported THE exporter SHALL send a span named `execute_tool {name}`, of kind INTERNAL, with `gen_ai.tool.name`, `tempergraph.tool.capability` and `tempergraph.tool.ok`, never the call's arguments or results.

- GIVEN a shell call `echo canary` that succeeds WHEN it is exported THEN the span is `execute_tool Bash` with `tempergraph.tool.capability` `shell` and `tempergraph.tool.ok` true, and holds neither the command nor its output

### TEL-B20 Check span

WHEN a check is exported THE exporter SHALL send a span named `check {unit}`, of kind INTERNAL, with `tempergraph.check.result` and `tempergraph.check.environmental`.

- GIVEN a check of unit `plan` that fails because a tool is missing on the machine WHEN it is exported THEN the span is `check plan` with `tempergraph.check.result` `FAIL` and `tempergraph.check.environmental` true

### TEL-B21 Gate span

WHEN a gate is exported THE exporter SHALL send a span named `gate {unit}`, of kind INTERNAL, with `tempergraph.verdict`, `tempergraph.route_target`, `tempergraph.criteria.met` and `tempergraph.criteria.total`.

- GIVEN a gate of unit `plan` that derived `PROCEED` with 4 of 4 criteria met and routed to unit `code` WHEN it is exported THEN the span is `gate plan` with `tempergraph.verdict` `PROCEED`, `tempergraph.route_target` `code`, `tempergraph.criteria.met` 4 and `tempergraph.criteria.total` 4

### TEL-B22 Gate evaluation event

WHEN a gate is exported THE exporter SHALL add the event `gen_ai.evaluation.result` to the gate's span, with `gen_ai.evaluation.score.value` set to the judge's confidence and `gen_ai.evaluation.score.label` set to the verdict.

- GIVEN a gate whose judge reported confidence 0.85 and whose verdict is `RETRY` WHEN it is exported THEN its span holds one `gen_ai.evaluation.result` event with `gen_ai.evaluation.score.value` 0.85 and `gen_ai.evaluation.score.label` `RETRY`

### TEL-B23 Pause event

WHEN a run pauses THE exporter SHALL add the event `tempergraph.pause` to the segment span, with the pause kind and `tempergraph.decisions`.

- GIVEN a run that pauses at a gate for a person WHEN its segment is exported THEN the segment span holds one `tempergraph.pause` event with the pause kind and `tempergraph.decisions`

### TEL-B24 Provider names

WHEN a session is exported THE exporter SHALL set `gen_ai.provider.name` to `anthropic` for `claude`, `agent-sdk` and `messages-api`, to the cloud provider's name when the executor's binding routes through one, and to `gcp.gemini` for `antigravity`.

- GIVEN an `antigravity` session WHEN it is exported THEN `gen_ai.provider.name` is `gcp.gemini`
- GIVEN a `messages-api` session whose binding routes through a cloud provider WHEN it is exported THEN `gen_ai.provider.name` is that provider's name

### TEL-B25 Token usage

WHEN a session is exported THE exporter SHALL record its tokens in the histogram `gen_ai.client.token.usage`, with `gen_ai.token.type`, the provider, the model, `tempergraph.executor` and `tempergraph.kind`.

- GIVEN a `claude` step session with input and output tokens WHEN it is exported THEN the histogram holds a measurement per `gen_ai.token.type` with `tempergraph.executor` `claude` and `tempergraph.kind` `step`

### TEL-B26 Operation duration

WHEN a session is exported THE exporter SHALL record its duration in the histogram `gen_ai.client.operation.duration`, with the same attributes as the token histogram.

- GIVEN a `claude` judge session that ran 42 s WHEN it is exported THEN the histogram holds a measurement of 42 s with `tempergraph.kind` `judge`

### TEL-B27 Estimated cost counter

WHEN a session is exported THE exporter SHALL add its estimated cost in USD to the counter `tempergraph.cost.estimated`, with the attributes workflow, executor and kind.

- GIVEN an `antigravity` step session with an estimated cost of 0.31 USD WHEN it is exported THEN `tempergraph.cost.estimated` gains 0.31 with executor `antigravity` and kind `step`

### TEL-B28 Reported cost counter

WHEN a session is exported THE exporter SHALL add its reported cost in USD to the counter `tempergraph.cost.reported` only if its executor reported one, with the attributes workflow, executor and kind.

- GIVEN a `claude` judge session that reported 0.22 USD and an `antigravity` step session that reported none WHEN they are exported THEN `tempergraph.cost.reported` gains 0.22 for executor `claude` and nothing for `antigravity`

### TEL-B29 Gate verdict counter

WHEN a gate derives a verdict THE exporter SHALL add 1 to the counter `tempergraph.gate.verdicts`, with the attributes workflow, unit and verdict.

- GIVEN two gates of unit `plan` that derived `RETRY` and then `PROCEED` WHEN they are exported THEN `tempergraph.gate.verdicts` holds 1 for `RETRY` and 1 for `PROCEED` under unit `plan`

### TEL-B30 Run counter

WHEN a run exits THE exporter SHALL add 1 to the counter `tempergraph.runs`, with the attributes workflow and exit reason.

- GIVEN a run that exits with reason `stopped_by_request` WHEN it is exported THEN `tempergraph.runs` gains 1 with that exit reason

### TEL-B31 Live run counter

WHEN a run starts, changes state or exits THE exporter SHALL keep the up-down counter `tempergraph.runs.live` equal to the live runs, with the attributes workflow and state.

- GIVEN two live runs of one workflow, one running and one paused WHEN the counter is read THEN it holds 1 for state `running` and 1 for state `paused`

### TEL-B32 Resource identity

WHEN a run is exported THE exporter SHALL attach the resource attributes `service.name` set to `tempergraph`, `service.version`, `tempergraph.machine_id` and `tempergraph.semconv` to every export.

- GIVEN a sink that sets no `semconv` and an engine release pinned to version V WHEN a run is exported THEN `tempergraph.semconv` is V
- GIVEN any exported run WHEN its resource is read THEN `service.name` is `tempergraph` and `service.version` and `tempergraph.machine_id` are set

### TEL-B33 User and repository on the resource

WHEN a run is exported THE exporter SHALL set the resource attributes `tempergraph.user` and `tempergraph.repo_id` as the sink's `user` and `repo` settings say ([CST](central-run-stats.spec.md)).

- GIVEN a sink that leaves `user` and `repo` at their defaults WHEN a run is exported THEN `tempergraph.user` and `tempergraph.repo_id` hold hashes, not names
- GIVEN a sink whose `user` is `none` WHEN a run is exported THEN the resource has no `tempergraph.user`

### TEL-B34 A full queue drops spans

WHEN more than 2 048 spans are waiting to be exported THE exporter SHALL drop the spans that do not fit, counting the drop on the segment span.

- GIVEN a receiver that answers no request WHEN a run makes 3 000 spans THEN the spans beyond the 2 048 waiting are dropped and the segment span records how many

### TEL-B35 Export timeout

WHEN a receiver has not answered an export request after 10 seconds THE exporter SHALL stop waiting for that request.

- GIVEN a receiver that accepts the connection and never answers WHEN a run ends THEN the exporter stops waiting for it after 10 seconds

### TEL-B36 Unsent spans go to the outbox

WHEN a segment's spans could not be exported before the process exits THE exporter SHALL write them to the sink's outbox as OTLP JSON ([CST](central-run-stats.spec.md)).

- GIVEN an endpoint that refuses connections WHEN a run ends THEN the segment's spans are in the sink's outbox as OTLP JSON

### TEL-B37 A flush sends the outbox

WHEN the sink is flushed THE exporter SHALL send the OTLP JSON spans waiting in its outbox to the receiver.

- GIVEN spans in the sink's outbox and a receiver that is reachable again WHEN `stats flush` runs THEN the receiver gets those spans

### TEL-B38 Missing extra

WHEN an `otlp` sink is configured and `tempergraph[otel]` is not installed THE engine SHALL start the run with a recorded preflight warning, exporting nothing.

- GIVEN an `otlp` sink and an install without the `tempergraph[otel]` extra WHEN a run is preflighted THEN a warning says the extra is missing, the warning is recorded, the run starts and nothing is exported

### TEL-B39 Missing header file

WHEN the file a sink's `headers_profile` names is missing THE engine SHALL disable the sink for the run, recording that.

- GIVEN a `headers_profile` that names no existing file WHEN a run starts THEN the sink is disabled for that run and the disabling is recorded

### TEL-B40 Long values are cut

WHEN an attribute value is longer than 256 characters THE exporter SHALL send no more than 256 characters of it.

- GIVEN an attribute value of 300 characters WHEN it is exported THEN the receiver gets at most 256 characters of it

## Acceptance criteria

- TEL-AC1 (TEL-B1, TEL-B2, TEL-B12, TEL-B13, TEL-B14, TEL-B15, TEL-B16, TEL-B17, TEL-B18, TEL-B19, TEL-B20, TEL-B21, TEL-B22, TEL-B23, TEL-B24, TEL-B32, TEL-B33): An in-memory exporter test reproduces the traces, spans, events, attributes and resource attributes these behaviours name, for a fixture run on each executor
- TEL-AC2 (TEL-B3): A run with the canary of [SEC-B2](security.spec.md) planted in every free-text field it lists exports no span, event, metric or resource attribute that holds the canary
- TEL-AC3 (TEL-B4): A failure injected into the exporter leaves the run's exit code unchanged
- TEL-AC4 (TEL-B14, TEL-B15, TEL-B16, TEL-B17, TEL-B19, TEL-B20, TEL-B21, TEL-B22, TEL-B23, TEL-B24, TEL-B25, TEL-B26, TEL-B27, TEL-B28, TEL-B29, TEL-B30, TEL-B31, TEL-B32, TEL-B33): A drift test compares every span, event, attribute, metric and resource-attribute name in these behaviours with the names a fixture run exports, and fails when either side holds a name the other lacks
- TEL-AC5 (TEL-B25, TEL-B26, TEL-B27, TEL-B28, TEL-B29, TEL-B30, TEL-B31): An in-memory metric reader over a fixture run holds each of the seven metrics with the instrument and attributes its behaviour names
- TEL-AC6 (TEL-B7, TEL-B8, TEL-B11): A stub receiver gets no request from a run with no `otlp` sink, and from a run with one gets what the sink's `endpoint` and `signals` select, over gRPC and over HTTP/protobuf
- TEL-AC7 (TEL-B9, TEL-B10): A stub receiver sees the header lines of the `headers_profile` on every request, and a header value planted there is in no log, record or error text, also when the receiver rejects the request
- TEL-AC8 (TEL-B5, TEL-B6): A preflight with a `semconv` other than the engine release's pin, or with an `endpoint` that is not loopback under `local_only` `true`, refuses the sink, starts the run and exports nothing, while the pinned `semconv` and a loopback `endpoint` are accepted
- TEL-AC9 (TEL-B38, TEL-B39): A run with an `otlp` sink and no `tempergraph[otel]`, or with a `headers_profile` that names a missing file, starts, exports nothing to that sink and records why
- TEL-AC10 (TEL-B34, TEL-B35): Against a receiver that answers no request, a run that makes more than 2 048 spans drops the surplus and records the number on its segment span, and the exporter gives up on a request after 10 seconds
- TEL-AC11 (TEL-B36, TEL-B37): After a run ends against a receiver that refuses connections, its spans are in the sink's outbox as OTLP JSON, and `stats flush` sends them once the receiver is back
- TEL-AC12 (TEL-B40): An attribute value of 300 characters reaches the receiver as at most 256 characters

## Open questions

- Which backend does the owner read the export in first? The design names none and assumes any OTLP receiver ([R-020](../research/R-020-opentelemetry-genai-conventions.rsrch.md)). Owner: owner. Until it is answered the exporter prefers no backend.
