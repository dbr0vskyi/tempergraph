---
title: Messages API executor
type: component
status: review
prefix: EMA
adrs: [0006, 0008, 0012, 0018, 0019, 0020]
---

# Messages API executor

## 1. Overview

The `messages-api` executor runs each step attempt and each judge run as one conversation on Anthropic's Messages API, driven by an engine-owned loop in an engine worker process ([ADR-0019](../adr/0019-in-process-executors-run-in-a-worker-process.adr.md), [ADR-0020](../adr/0020-engine-owned-tool-loop-for-the-messages-api.adr.md)). The API runs no client tool, so every file and command tool is executed by the engine's [tool host](22-tool-host.spec.md). It implements the [executor interface](10-executor-interface.spec.md); facts about the API come from [R-004](../research/R-004-anthropic-messages-api-executor.rsrch.md). It is the lightest executor to run in CI: one Python client library and an API or cloud credential.

## 2. Contract

### 2.1 Declared capabilities

| Capability | Value | Basis |
|---|---|---|
| `binds_aliases` | `small`, `medium`, `large`, `inherit` (bound to the table's `medium`), every `messages-api:<name>` in the binding table | [R-004 M12](../research/R-004-anthropic-messages-api-executor.rsrch.md) |
| `prompt_off_argv`, `streams_events`, `reports_actions`, `reports_tokens`, `fresh_session` | true | M1, M7, M11; the prompt travels in the worker's request document on stdin |
| `reports_cost` | false; the engine estimate is the only cost ([ADR-0012](../adr/0012-cost-when-executor-reports-tokens-only.adr.md)) | M7 |
| `enforces_step_tools`, `restricts_judge_tools`, `isolates_user_config`, `step_allow_rules` | true by construction: the session is offered only the declared tools and the engine runs every call | ADR-0020 |
| `judge_mcp` | true for local (stdio) servers through the tool host's MCP client | [THS §2.6](22-tool-host.spec.md) |
| `hosts_authoring_surface` | false: no instruction files, skills, agents or subagents | R-004 conclusion 4 |
| `session_options` | `effort`, `cost_cap_usd`, `turn_cap`; not `fallback_alias` | M9; caps enforced between responses |

### 2.2 Tool map

| Capability | Offered to the model | Executed by |
|---|---|---|
| `read` | `read_file` | Tool host |
| `search` | `search_files` | Tool host |
| `list` | `list_files` | Tool host |
| `edit` | `edit_file` | Tool host |
| `write` | `write_file` | Tool host |
| `shell` | `run_command` (declared prefixes only) | Tool host |
| `web_fetch` | server tool `web_fetch` (current version for the bound model) | Anthropic, where the model and platform offer it |
| `web_search` | server tool `web_search` | Anthropic, where offered |
| `subagent` | none | not in `tool_map`; preflight refuses a step that declares it |
| `mcp:<s>/<t>` | `mcp__<s>__<t>`, schema copied from the server | Tool host MCP client |

Server tool versions per model and platform live in the binding table, never in code: a platform without web fetch (for example Vertex AI, M4) simply has no `web_fetch` row and the preflight refuses the step.

### 2.3 Worker request document

The launcher starts `<engine python> -m tempergraph.executors.api_worker` with no other argument and writes one JSON document on stdin:

| Field | Source | Re-checked by the worker |
|---|---|---|
| `version` | constant | equals the worker's own |
| `kind` | `SessionRequest.kind` | enum |
| `prompt` | rendered prompt | string; never logged |
| `workdir` | state | absolute, exists, inside the state root's known workspaces |
| `model`, `provider`, `server_tools` | binding table entry selected by the alias | entry exists in the table the worker reads itself |
| `tools`, `commands` | declaration | each in the tool map; prefixes in the workflow allow-list |
| `views` | judge only | read-only capabilities and catalogued MCP views |
| `limits` | `timeout_s` (informational), `turn_cap`, `cost_cap_usd`, `max_tokens` | positive numbers |
| `effort` | option | enum, and listed for the model in the binding table |

The worker emits normalized events ([CON §2.7](01-contracts.spec.md)) as JSON lines on stdout and ends with exactly one `result` line.

### 2.4 The loop

1. Build the request: model, `max_tokens` from the binding table, the system text (a constant engine sentence: work in the given directory with the given tools), the tools of §2.2 in a fixed order so the prefix is cacheable ([R-004 M8](../research/R-004-anthropic-messages-api-executor.rsrch.md)), and the prompt as the first user message. Thinking and effort parameters are taken from the binding table's model row, because valid values differ by model (M9).
2. Send with streaming; translate stream events into normalized events (§2.5).
3. On `stop_reason`:

| Stop reason | Action |
|---|---|
| `end_turn` | Session ends `ok`; final text is the answer |
| `tool_use` | Run each `tool_use` block through the tool host in order; send all `tool_result` blocks in one user message, failed calls with `is_error: true`; continue |
| `pause_turn` | Resend the conversation unchanged; counts as a turn |
| `max_tokens` | Do not run any `tool_use` block of that response; end with `error_kind = model` and `partial = true` |
| `refusal` | Run no tool of that response; end with `error_kind = refused` |

4. After every response, add its usage to the running total, compute the estimate from the price table, and check the caps: turns above `turn_cap` end with `error_kind = turn_cap`; an estimate at or above `cost_cap_usd` ends with `error_kind = cap_reached` before the next request is sent.

### 2.5 Event mapping

| API stream | Normalized event |
|---|---|
| First `message_start` | `session_started` (`session_id` = first message id, `model`, `cli_version` = client library version and API version header, `tools` = offered names) |
| `content_block_delta` text | `model_delta` (count only) |
| Completed `tool_use` block | `tool_started` (`subagent = false`) |
| Tool host finishes the call | `tool_finished` (`ok`, `error_kind`) |
| Server tool use and its result block | `tool_started` and `tool_finished` with the server tool's name |
| Final text block | `text` (last line, scrubbed) |
| SDK retry of a 429, 5xx or 529 | `retrying` (`category` = `rate_limit`, `overloaded` or `server_error`) |
| Tool host refuses a call (path outside, undeclared prefix) | `denied` |
| Loop ends | `result` with summed `usage`, `reported_cost_usd = null`, `estimated_cost_usd` |

### 2.6 Failure classification

| Observed (structured) | `infra_cause` / `error_kind` |
|---|---|
| Worker spawn raised | `spawn_failed` |
| Worker ended with no line | `no_output` |
| Worker ended with no `result` line | `no_result` |
| Connection error type from the client after its retries | `connection` |
| Timeout error type from the client | `request_timed_out` |
| 429 with a `retry-after`, or 529, after the client's retries | `throttled` |
| 429 without `retry-after` (spend cap, M10) | `error_kind = cap_reached` |
| 401, 403 | `error_kind = auth` |
| 402 | `error_kind = auth` (billing), recorded with the status |
| 400, 404, 413 | `error_kind = model`, with the error type recorded |
| 500 after retries | `error_kind = model` |
| `stop_reason = refusal` | `error_kind = refused` |

The status code and the error `type` field are the only inputs; error message text is never read.

### 2.7 Providers and credentials

The binding table row names a `provider`: `anthropic`, `bedrock`, `vertex` or `foundry` (M12). The worker picks the matching client class by that constant. Model ids are per provider and live only in the table. Credentials resolve as the client library resolves them (M13); the engine passes a judge-only profile by laying its variables over the worker's environment. Keys never enter the request document, the log or the checkpoint ([SEC](14-security.spec.md)).

## 3. Behaviours

**EMA-B1 Judge offered only views.** Given a judge with views `read`, `search`, `list`, when its first request is built, then the `tools` array holds exactly `read_file`, `search_files` and `list_files`, and a `tool_use` naming any other tool returns an `is_error` result and a `denied` event without running anything.

**EMA-B2 Truncated tool input never runs.** Given a response with `stop_reason = max_tokens` whose last block is a `tool_use`, when the loop handles it, then no tool runs and the session ends `partial` with `error_kind = model`.

| Stop reason | Tools run | Outcome |
|---|---|---|
| `tool_use` | all blocks, in order | continue |
| `max_tokens` | none | `model`, partial |
| `refusal` | none | `refused` |
| `pause_turn` | none | resend |

**EMA-B3 Cost cap between responses.** Given `cost_cap_usd = 0.50` and an estimate of 0.48 after turn 4 and 0.53 after turn 5, when turn 5's usage is recorded, then no sixth request is sent and the result carries `error_kind = cap_reached` with the usage of five turns.

**EMA-B4 One message of results.** Given a response with three `tool_use` blocks, when they have run, then the next request carries one user message with three `tool_result` blocks matched by `tool_use_id`, failures marked `is_error`.

**EMA-B5 Unavailable server tool refused.** Given a step that declares `web_fetch` and a binding row whose provider has no web fetch, when the run is preflighted, then it exits 2 naming the step, the executor and `web_fetch`.

## 4. Error conditions

| Type | Handling |
|---|---|
| Client library not importable in the engine interpreter | Probe fails; exit 2 at preflight |
| No credential resolvable for the provider | Probe fails; exit 2 (the probe makes no model call) |
| A request document field fails re-validation | Worker writes a `result` with `infra_cause = prompt_not_delivered` and exits |
| Context window exceeded (400 of that type) | `error_kind = model`; peak context recorded ([R-004 open question](../research/R-004-anthropic-messages-api-executor.rsrch.md)) |
| An unknown stream event type | Skipped and counted |

## 5. Design notes

- A workflow that relies on CLAUDE.md, skills or subagents cannot move a step here without bringing that content into the prompt; the preflight warns when a step on this executor names a skill ([ADR-0016](../adr/0016-portable-authoring-surface.adr.md)).
- Effort and thinking parameters are binding-table facts per model, because a wrong value is a 400 on some models.
- No beta feature is used in the first release: no tool runner, no compaction, no context editing.

## 6. Acceptance criteria

- [ ] EMA-AC-1 Each row of §2.4 and §2.6 has a recorded-response fixture and a test.
- [ ] EMA-AC-2 A judge request never offers a write, edit or command tool (contract test over every view set).
- [ ] EMA-AC-3 The prompt and any key never appear in the worker's argv, environment listing or log (planted canary).
- [ ] EMA-AC-4 The worker passes the conformance suite of [EXI-B11](10-executor-interface.spec.md) against a recorded API stand-in.
- [ ] EMA-AC-5 Caps stop the loop before the next request, with a replaced price table.

## Open questions

| Question | Owner |
|---|---|
| Use server-side compaction for long steps, or end at the context window? First release ends; revisit with measured peak context. | Executor implementer |
| Does a judge on this executor grade as well as one on `claude`? Settle with calibration sets per gate ([LIF](18-lifecycle-and-evals.spec.md)). | Engine owner |

## References

[EXI](10-executor-interface.spec.md) · [THS](22-tool-host.spec.md) · [R-004](../research/R-004-anthropic-messages-api-executor.rsrch.md) · [R-003](../research/R-003-executor-capability-matrix.rsrch.md) · [ADR-0020](../adr/0020-engine-owned-tool-loop-for-the-messages-api.adr.md)
