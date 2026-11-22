# Session contract

## Purpose

What the engine and every executor exchange for one session: the executor's surface, the session request and its options, the capabilities an executor declares, the session result and its usage, the normalized event stream ([ADR-0009](../adr/0009-normalized-session-event-stream.adr.md)), and the judgement and check result a gate reads. Executor implementations ([EXI](10-executor-interface.spec.md)), the gate funnel ([JDG](05-judge-and-verdict.spec.md), [CHK](75-check-contract-and-command-runs.spec.md)), the run log and observers depend on these exact names. Split from the shared contracts ([CON](01-contracts.spec.md)) when the specs moved to temperspec's format; the behaviour CON-B2 kept its id.

## Behaviours

### SSN-B1 The executor surface

WHEN the engine uses an executor THE executor SHALL offer a constant `name` (`claude`, `agent-sdk`, `messages-api` or `antigravity`), `capabilities()`, a read-only, model-free `probe()` that reports its version and facts, `run_step(request, sink)` and `run_judge(request, views, sink)`, and neither run method SHALL raise for a session failure: failure is a field of the result.

- GIVEN a session whose CLI exits with an error WHEN `run_step` returns THEN it returns a result with `ok` false and does not raise
- GIVEN `probe()` WHEN it runs THEN no model is called and nothing is written

### SSN-B2 Session request

WHEN the engine starts a session THE engine SHALL send a request with `kind` (`step`, `retry`, `judge`, `judge_reask`, `grouping`, `member`, `member_reask` or `chair`, the last three run by executors as step sessions with read-only tools, [CNL](71-council-unit.spec.md)), `prompt` (rendered text, delivered off argv), `workdir` (the absolute workspace path from state), `alias` (resolved, [CON-B3](01-contracts.spec.md)), the step's declared `tools` and `commands`, `timeout_s` and `idle_s` with their sources, `options`, and for a judge an optional `credentials_profile`.

- GIVEN a step session WHEN its process is started THEN the prompt is not on the argv
- GIVEN a council member session WHEN the executor starts it THEN it runs with read-only tools

### SSN-B3 Session options

WHEN a request carries options THE engine SHALL send only `effort` (`low`, `medium`, `high`, `xhigh` or `max`), `cost_cap_usd`, `fallback_alias` (never for a judge) and `turn_cap`, and refuse at preflight with exit 2 an option outside the executor's `session_options`, except `effort`, which only warns.

- GIVEN `turn_cap` on an executor that does not declare it WHEN the run is preflighted THEN it exits 2 before spend
- GIVEN `effort: high` on an executor that does not declare `effort` WHEN the run is preflighted THEN a warning is recorded and the run starts
- GIVEN a judge with `fallback_alias` WHEN it is validated THEN it fails

### SSN-B4 Declared capabilities

WHEN an executor declares its capabilities THE executor SHALL state `binds_aliases`, `families` (alias to model family label, read by council diversity checks), the booleans `prompt_off_argv`, `streams_events`, `reports_actions`, `reports_tokens`, `reports_cost`, `enforces_step_tools`, `restricts_judge_tools`, `step_allow_rules`, `judge_mcp`, `isolates_user_config`, `fresh_session` and `hosts_authoring_surface` ([ADR-0016](../adr/0016-portable-authoring-surface.adr.md)), `session_options`, `tool_map` (capability to its tool names) and `version` (the CLI's, or a library's plus any bundled CLI's).

- GIVEN the `antigravity` executor WHEN its capabilities are read THEN `restricts_judge_tools` is false
- GIVEN `executors` WHEN it prints an executor THEN every field of SSN-B4 is shown

### SSN-B5 Session result

WHEN a session ends THE executor SHALL return `ok`, `text` (the final answer), `session_id`, `usage`, `tool_calls` (each `{name, ok, subagent}` in call order), `timed_out`, `stalled`, `partial`, `infra_cause` (`spawn_failed`, `prompt_not_delivered`, `no_output`, `no_result`, `broken_pipe`, `connection`, `out_of_memory`, `request_timed_out`, `slow_host`, `throttled` or null), `error_kind` (`model`, `refused`, `cap_reached`, `turn_cap`, `denied`, `auth`, `unknown` or null; `refused` is a typed model refusal from a stop reason, never from text), `applied_options` and `cli_version`.

- GIVEN a session whose stream ends with no result WHEN it is returned THEN `infra_cause` is `no_result`
- GIVEN a Messages API response with `stop_reason` `refusal` WHEN it is returned THEN `error_kind` is `refused`

### SSN-B6 Usage

WHEN usage is recorded THE engine SHALL record `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `thinking_tokens`, `turns` and `peak_context_tokens` as integers or null, `by_model` (model name to partial usage), `reported_cost_usd` (never 0 when unknown) and `estimated_cost_usd` (from the engine price table), the two costs kept apart and never summed into one figure ([ADR-0012](../adr/0012-cost-when-executor-reports-tokens-only.adr.md)).

- GIVEN a session with tokens unknown WHEN it is recorded THEN the token fields are null, not 0

### CON-B2 Unknown cost

WHEN an executor reports tokens but no cost THE engine SHALL record `reported_cost_usd` as null and compute `estimated_cost_usd` from the price table.

- GIVEN `claude` reporting tokens and a cost of 0.42 WHEN recorded THEN `reported_cost_usd` is 0.42 and `estimated_cost_usd` comes from the table
- GIVEN `agent-sdk` reporting tokens and 0.40 WHEN recorded THEN `reported_cost_usd` is 0.40
- GIVEN `messages-api` or `antigravity` reporting tokens and no cost WHEN recorded THEN `reported_cost_usd` is null and `estimated_cost_usd` comes from the table
- GIVEN any executor reporting neither WHEN recorded THEN both are null

### SSN-B7 Normalized session events

WHEN an executor reads its session's stream THE executor SHALL push only these events to the sink: `session_started` (`session_id`, `model`, `cli_version`, `tools` as listed by the CLI), `model_delta` (`chars`, a count only), `tool_started` (`name`, `subagent`, `call_id`, and `input_summary`, a scrubbed one-line summary kept in local records only, [EVT-B21](30-run-events.spec.md)), `tool_finished` (`call_id`, `ok`, `error_kind`), `text` (`last_line`, scrubbed and clipped to 200 characters), `retrying` (`category` from the CLI's retry event), `denied` (`name` of a refused or soft-denied tool) and `result` (`ok`, `usage`).

- GIVEN a model reply of 5000 characters WHEN the stream is read THEN `model_delta` events carry counts and no text
- GIVEN a text line of 300 characters WHEN a `text` event is pushed THEN `last_line` holds 200 characters

### SSN-B8 Judgement block

WHEN the engine reads a judge's answer THE engine SHALL take the last fenced JSON block as the judgement, with `criteria[]` (each `{n, id, status, evidence, place, fix, defect_in, no_change}`, `status` one of `MET`, `PARTIAL`, `UNMET`, `N/A` or `UNVERIFIABLE`, `defect_in` an earlier artifact key, `no_change` true when the step's own output cannot fix it), `coverage` (`requirements`, `traced`, `orphans`), `gap` (a source is missing or the task is unclear), `confidence` (0 to 1, anchors 0.95 verified, 0.85 checked, 0.7 partly inferred, 0.5 contested, with `source` `judge` or `engine_placeholder`) and a one-line `summary`.

- GIVEN an answer with two fenced JSON blocks WHEN it is read THEN the second is the judgement
- GIVEN a criterion with `no_change` true WHEN the gate reads it THEN the blocker is one the step's own output cannot fix

### SSN-B9 Verdicts

WHEN a gate decides THE engine SHALL derive one verdict of `PROCEED`, `RETRY`, `BACK`, `ESCALATE` or `STOP`, and only the engine derives it ([JDG](05-judge-and-verdict.spec.md)).

- GIVEN a judgement that writes `"verdict": "PROCEED"` WHEN the gate reads it THEN the field is ignored and the engine derives the verdict from the criteria

### SSN-B10 Check result

WHEN a check returns THE engine SHALL read `result` (`PASS`, `MAYBE` or `FAIL`), `evidence` (bounded text), `environmental`, `untracked_only`, `findings` (each `{criterion, status, place, fix, message, kind}`, `status` one of `pass`, `maybe`, `fail` or `n_a`, `kind` one of `substance`, `output_contract` or `other`, the default), `facts` (at most 20 slugs to strings of at most 200 characters), and add `runs` (the check's command runs); the rules are [CHK-B14](75-check-contract-and-command-runs.spec.md).

- GIVEN a finding with no `kind` WHEN it is read THEN its kind is `other`

## Acceptance criteria

- SSN-AC1 (SSN-B1): A conformance fixture of every executor returns a failed result, never an exception, for each failure shape
- SSN-AC2 (SSN-B2, SSN-B3): Every session request of a fixture run holds the fields of SSN-B2, with the prompt off argv, and an undeclared option other than `effort` is refused at preflight
- SSN-AC3 (SSN-B4): Every executor's declared capabilities hold every field of SSN-B4
- SSN-AC4 (SSN-B5, SSN-B6, CON-B2): No recorded usage or cost is 0 when the executor did not report it, and the reported and estimated costs are never summed
- SSN-AC5 (SSN-B7): Every executor's recorded fixture stream normalizes to the events of SSN-B7 only, with no model text in `model_delta`
- SSN-AC6 (SSN-B8, SSN-B9): A judgement is read from the last fenced block, and the verdict comes from the engine whatever the block holds
- SSN-AC7 (SSN-B10): A check result is read with the fields of SSN-B10, and `runs` is added by the engine
