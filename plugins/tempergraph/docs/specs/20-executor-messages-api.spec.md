# Messages API executor

## Purpose

The `messages-api` executor runs each step attempt and each judge run as one conversation on Anthropic's Messages API, driven by an engine-owned loop in an engine worker process ([ADR-0019](../adr/0019-in-process-executors-run-in-a-worker-process.adr.md), [ADR-0020](../adr/0020-engine-owned-tool-loop-for-the-messages-api.adr.md)). The API runs no client tool, so every file and command tool is executed by the engine's [tool host](22-tool-host.spec.md). It implements the [executor interface](10-executor-interface.spec.md); facts about the API come from [R-004](../research/R-004-anthropic-messages-api-executor.rsrch.md). It is the lightest executor to run in CI: one client library and an API or cloud credential. A workflow that relies on CLAUDE.md, skills or subagents cannot move a step here without bringing that content into the prompt ([ADR-0016](../adr/0016-portable-authoring-surface.adr.md)). No beta feature is used: no tool runner, no compaction, no context editing. Operators and workflow authors who choose it depend on what it declares and does.

## Behaviours

### EMA-B6 Declared capabilities

WHEN the `messages-api` executor declares its capabilities THE executor SHALL declare `binds_aliases` (`small`, `medium`, `large`, `inherit` bound to the table's `medium`, and every `messages-api:<name>` in the binding table), `prompt_off_argv`, `streams_events`, `reports_actions`, `reports_tokens` and `fresh_session` true, `reports_cost` false (the engine estimate is the only cost, [ADR-0012](../adr/0012-cost-when-executor-reports-tokens-only.adr.md)), `enforces_step_tools`, `restricts_judge_tools`, `isolates_user_config` and `step_allow_rules` true by construction, `judge_mcp` true for local stdio servers through the tool host's MCP client ([THS §2.6](22-tool-host.spec.md)), `hosts_authoring_surface` false, and `session_options` `effort`, `cost_cap_usd` and `turn_cap` but not `fallback_alias`.

- GIVEN a step with `fallback_alias` on `messages-api` WHEN preflighted THEN it exits 2
- GIVEN a step on `messages-api` whose template names a skill WHEN preflighted THEN a warning is recorded

### EMA-B7 Tool map

WHEN a step declares tools on `messages-api` THE executor SHALL offer `read_file`, `search_files`, `list_files`, `edit_file`, `write_file` and `run_command` (declared prefixes only) for `read`, `search`, `list`, `edit`, `write` and `shell`, all run by the tool host; the server tools `web_fetch` and `web_search` at the version the binding table gives for the bound model and platform, run by Anthropic where offered; `mcp__<s>__<t>` with the server's schema for `mcp:<s>/<t>`, run by the tool host's MCP client; and nothing for `subagent` or `skill:`, which preflight refuses.

- GIVEN a step declaring `subagent` WHEN preflighted on `messages-api` THEN it exits 2

### EMA-B5 Unavailable server tool refused

WHEN a step declares a server tool the binding row's provider does not offer THE engine SHALL exit 2 at preflight naming the step, the executor and the tool.

- GIVEN a step declaring `web_fetch` and a Vertex AI binding row with no web fetch WHEN preflighted THEN it exits 2 naming the step, `messages-api` and `web_fetch`

### EMA-B8 Worker request document

WHEN the launcher starts the worker THE launcher SHALL run the engine interpreter with the constant API worker module and no other argument, and write one JSON document on standard input with `version` (equal to the worker's own), `kind`, `prompt` (never logged), `workdir` (absolute, existing, inside the state root's known workspaces), `model`, `provider` and `server_tools` (an entry the worker finds in the binding table it reads itself), `tools` and `commands` (each in the tool map, prefixes in the workflow allow-list), `views` for a judge (read-only capabilities and catalogued MCP views), `limits` (`timeout_s`, `turn_cap`, `cost_cap_usd`, `max_tokens`, positive numbers) and `effort` (listed for the model in the binding table), and the worker SHALL re-check each field, emit normalized events ([SSN-B7](25-session-contract.spec.md)) as JSON lines on standard output and end with exactly one `result` line.

- GIVEN a request document whose `workdir` is outside the known workspaces WHEN the worker reads it THEN it writes a `result` with `infra_cause = prompt_not_delivered` and exits

### EMA-B9 The request

WHEN the loop builds a request THE worker SHALL send the model, `max_tokens` from the binding table, a constant engine system sentence, the tools in a fixed order so the prefix is cacheable ([R-004 M8](../research/R-004-anthropic-messages-api-executor.rsrch.md)), thinking and effort parameters from the binding table's model row (valid values differ by model), and the prompt as the first user message, streaming.

- GIVEN two attempts of one step WHEN their first requests are compared THEN the tools array is in the same order

### EMA-B10 Stop reasons

WHEN a response ends THE worker SHALL end the session `ok` on `end_turn`; run each `tool_use` block through the tool host in order and continue on `tool_use`; resend the conversation unchanged, counting a turn, on `pause_turn`; run no tool and end with `error_kind = model` and `partial = true` on `max_tokens`; and run no tool and end with `error_kind = refused` on `refusal`.

- GIVEN `stop_reason = refusal` WHEN handled THEN no tool runs and the result is `refused`
- GIVEN `stop_reason = pause_turn` WHEN handled THEN the same conversation is sent again

### EMA-B2 Truncated tool input never runs

WHEN a response with `stop_reason = max_tokens` ends in a `tool_use` block THE worker SHALL run no tool and end the session `partial` with `error_kind = model`.

- GIVEN a response cut off inside a `tool_use` input WHEN handled THEN the tool host is not called

### EMA-B4 One message of results

WHEN a response's `tool_use` blocks have run THE worker SHALL send one user message with one `tool_result` per block, matched by `tool_use_id`, failures marked `is_error: true`.

- GIVEN three `tool_use` blocks, one failing WHEN they have run THEN the next request has one user message with three results and one `is_error`

### EMA-B3 Caps between responses

WHEN a response's usage is added to the running total THE worker SHALL compute the estimate from the price table and end with `error_kind = turn_cap` when turns pass `turn_cap`, or `error_kind = cap_reached` when the estimate reaches `cost_cap_usd`, before the next request is sent.

- GIVEN `cost_cap_usd = 0.50` and estimates of 0.48 after turn 4 and 0.53 after turn 5 WHEN turn 5's usage is recorded THEN no sixth request is sent and the result carries `cap_reached` with five turns of usage

### EMA-B1 Judge offered only views

WHEN a judge's request is built THE worker SHALL offer only the tools of its views, and answer a `tool_use` naming any other tool with an `is_error` result and a `denied` event, running nothing.

- GIVEN a judge with views `read`, `search` and `list` WHEN its first request is built THEN `tools` holds exactly `read_file`, `search_files` and `list_files`

### EMA-B11 Event mapping

WHEN the worker reads the API stream THE worker SHALL map the first `message_start` to `session_started` (`session_id` the first message id, `model`, `cli_version` the client library version and API version header, `tools` the offered names), text deltas to `model_delta` counts, a completed `tool_use` block to `tool_started` with `subagent` false, the tool host's finish to `tool_finished`, a server tool's use and result to `tool_started` and `tool_finished` with its name, the final text block to `text`, a client retry of a 429, 5xx or 529 to `retrying` (`rate_limit`, `overloaded` or `server_error`), a tool host refusal to `denied`, and the loop's end to `result` with summed usage, `reported_cost_usd` null and `estimated_cost_usd`, skipping and counting an unknown event type.

- GIVEN a 529 retried by the client WHEN read THEN a `retrying` event with `overloaded` is pushed

### EMA-B12 Failure classification

WHEN a session fails THE worker SHALL classify by the status code and the error `type` field only, never the message text: spawn raised `spawn_failed`, no line `no_output`, no `result` line `no_result`, a connection error after retries `connection`, a timeout error `request_timed_out`, a 429 with `retry-after` or a 529 after retries `throttled`, a 429 without `retry-after` (a spend cap) `cap_reached`, 401, 403 and 402 `auth` (402 recorded as billing), 400, 404, 413 and a 500 after retries `model` with the error type recorded, and a context window exceeded `model` with the peak context recorded.

- GIVEN a 429 with no `retry-after` WHEN classified THEN `error_kind` is `cap_reached`, not throttled

### EMA-B13 Providers and credentials

WHEN the worker starts a conversation THE worker SHALL pick the client class by the binding row's `provider` (`anthropic`, `bedrock`, `vertex` or `foundry`), take model ids only from the table, and let credentials resolve as the client library resolves them, a judge-only profile laid over the worker's environment, with keys never in the request document, the log or the checkpoint ([SEC](14-security.spec.md)).

- GIVEN a `bedrock` row WHEN a session starts THEN the Bedrock client is used with the row's model id

### EMA-B14 Probe refusals

WHEN the client library cannot be imported in the engine interpreter, or no credential resolves for the provider THE probe SHALL fail with no model call and preflight SHALL exit 2.

- GIVEN no API key and no cloud credential WHEN preflighted THEN it exits 2 and no request was sent

## Acceptance criteria

- EMA-AC1 (EMA-B10, EMA-B12, EMA-B2): Each stop reason and each failure classification has a recorded-response fixture and a test
- EMA-AC2 (EMA-B1): A judge request never offers a write, edit or command tool, by a contract test over every view set
- EMA-AC3 (EMA-B8, EMA-B13): The prompt and any key never appear in the worker's argv, environment listing or log, by a planted canary
- EMA-AC4 (EMA-B6, EMA-B11): The worker passes the conformance suite of [EXI-B11](10-executor-interface.spec.md) against a recorded API stand-in
- EMA-AC5 (EMA-B3): Caps stop the loop before the next request, with a replaced price table
- EMA-AC6 (EMA-B7, EMA-B5, EMA-B14): Each capability maps to its offered tool, and an unavailable server tool, `subagent`, `skill:` or a missing client or credential is refused at preflight
- EMA-AC7 (EMA-B4, EMA-B9): Tool results go back in one message matched by id, and the tools array keeps one order across attempts

## Open questions

- Use server-side compaction for long steps, or end at the context window? First release ends; revisit with measured peak context. Owner: executor implementer.
- Does a judge on this executor grade as well as one on `claude`? Settle with calibration sets per gate ([LIF](18-lifecycle-and-evals.spec.md)). Owner: engine owner.
