# Claude Agent SDK executor

## Purpose

The `agent-sdk` executor runs each step attempt and each judge run as one `query` session of the Claude Agent SDK, inside an engine worker process ([ADR `in-process-executors-run-in-a-worker-process`](../adr/in-process-executors-run-in-a-worker-process.adr.md)). The SDK drives a bundled Claude Code CLI, so tool names, permission rules and the authoring surface are Claude Code's; what changes is that options are typed, messages are typed, and the engine can install an in-process `PreToolUse` gatekeeper. It implements the [executor interface](executor-interface.spec.md); facts come from [research `claude-agent-sdk-executor`](../research/claude-agent-sdk-executor.rsrch.md), and its probes and design notes are kept in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md). It is the planned CI executor. Operators running unattended and workflow authors who move a step here depend on what it declares and does.

## Behaviours

### EAS-B5 Declared capabilities

WHEN the `agent-sdk` executor declares its capabilities THE executor SHALL declare `binds_aliases` (`small`, `medium`, `large`, `inherit` and every `agent-sdk:<name>` in the binding table), `prompt_off_argv` (the prompt reaches the worker on standard input and the SDK as a typed argument, confirmed for its CLI by P-AS-3), `streams_events`, `reports_actions`, `reports_tokens`, `reports_cost`, `fresh_session`, `enforces_step_tools`, `step_allow_rules`, `judge_mcp` and `restricts_judge_tools` true, `isolates_user_config` true only when P-AS-1 passes, `hosts_authoring_surface` true (Claude Code's), and `session_options` `effort`, `cost_cap_usd`, `fallback_alias` and `turn_cap`.

- GIVEN P-AS-1 not passed WHEN `executors` shows `agent-sdk` THEN `isolates_user_config` is false

### EAS-B6 Tool map

WHEN a step declares tools on `agent-sdk` THE executor SHALL use the tool map and allow rules of the `claude` executor ([ECC](executor-claude-code.spec.md)) (`Read`, `Grep`, `Glob`, `Edit`, `Write`, `Bash`, `WebFetch`, `WebSearch`, `Agent`, `mcp__<s>__<t>`, `Skill`), share Claude Code's view catalog rows ([GRD](independence-guard.spec.md)), and grant a `skill:` capability only with the workflow's plugin among the step's setting sources.

- GIVEN a step declaring `read` and `shell` with prefix `pytest` WHEN its options are built THEN they hold `Read` and `Bash(pytest *)`

### EAS-B7 Worker request document

WHEN the launcher starts the worker THE launcher SHALL run the engine interpreter with the constant SDK worker module and no other argument, and write on standard input one JSON document with the fields of the Messages API worker ([EMA-B8](executor-messages-api.spec.md)) less `server_tools`, plus `cli_path` from the binding table when the operator pins a CLI other than the bundled one, and the worker SHALL re-validate every field, build the SDK options from constants and those fields only, and emit normalized events as JSON lines.

- GIVEN a request document whose `cli_path` is not in the binding table WHEN the worker reads it THEN it writes a `result` with `infra_cause = prompt_not_delivered` and exits

### EAS-B8 Step options

WHEN a step session's options are built THE worker SHALL set `cwd` to the workdir, the bound model (omitted for `inherit`), the mapped built-ins as `tools` when the operator enabled enforcement and else the `claude_code` preset, the allow rules of EAS-B6, `permission_mode` `acceptEdits` in the engine's own worktree and `default` in place (never `bypassPermissions` or `auto`), `setting_sources` `["project"]` so the repository's CLAUDE.md and skills load and user settings do not, the engine's MCP file with `strict_mcp_config` when enforcement is on and an MCP tool is declared, `disallowed_tools` `EnterWorktree` and `ExitWorktree` (the run's worktree is the engine's, [WTR](worktree-mode.spec.md)), the gatekeeper hook (EAS-B10), `max_turns`, `max_budget_usd`, `fallback_model` and `effort` from the session options when set, the environment overlay of the `claude` executor ([ECC](executor-claude-code.spec.md)), and no `can_use_tool` callback, so an unlisted call in `default` mode is denied, never prompted.

- GIVEN a step running in place WHEN its options are built THEN `permission_mode` is `default` and `disallowed_tools` holds `EnterWorktree` and `ExitWorktree`

### EAS-B9 Judge options

WHEN a judge session's options are built THE worker SHALL set `tools` to `Read`, `Grep`, `Glob` plus the built-in views, `disallowed_tools` `["mcp__*"]` when the judge has no MCP view, `setting_sources` `[]`, `strict_mcp_config` with only the filtering proxy per MCP view in `mcp_servers`, `permission_mode` `dontAsk`, the view rules (plus read-only command rules when opted in) as `allowed_tools`, and the gatekeeper with the view set as its allow list, and SHALL never set `fallback_model`, `resume`, `continue_conversation`, `fork_session`, a write tool or a step allow rule.

- GIVEN any judge WHEN its options are built THEN they hold no write tool, no step rule, no `fallback_model` and no resume option

### EAS-B1 Judge loads nothing of the operator's

WHEN a judge session starts for an operator with user-level settings, plugins and MCP servers THE worker SHALL pass `setting_sources=[]`, `strict_mcp_config=True` and only the judge's proxies, so the init message lists only the view tools.

- GIVEN an operator with a user-level MCP server WHEN a judge session starts THEN the init message lists only the view tools

### EAS-B10 The gatekeeper rule

WHEN the model calls a tool THE gatekeeper SHALL allow the call only when the tool's name is in the session's mapped set and, for `Bash`, the command's first words match a declared prefix and contain no shell metacharacter of the tool host ([THS](tool-host.spec.md)), and otherwise deny it with a fixed reason while the worker emits `denied`; as the first rule evaluated it is the step's enforcement when the operator enabled it.

- GIVEN a call to a tool outside the mapped set WHEN the gatekeeper decides THEN it denies with the fixed reason

### EAS-B2 Gatekeeper holds in every mode

WHEN a step in `acceptEdits` that declares `shell` with prefix `pytest` calls `Bash` THE gatekeeper SHALL decide by EAS-B10 whatever the mode, and deny an `Agent` call that asks for worktree isolation.

- GIVEN `pytest -q` WHEN decided THEN it is allowed
- GIVEN `pytest; rm x` WHEN decided THEN it is denied for the metacharacter
- GIVEN `rm -rf build` WHEN decided THEN it is denied for the prefix, nothing runs and a `denied` event is emitted

### EAS-B14 Subagents wait for P-AS-2

WHEN a step that declares `subagent` with enforcement on is preflighted on `agent-sdk` before P-AS-2 passes THE engine SHALL refuse it with exit 2.

- GIVEN P-AS-2 not passed and a step declaring `subagent` with enforcement on WHEN preflighted THEN it exits 2

### EAS-B11 Message mapping

WHEN the worker reads the SDK's messages THE worker SHALL map the init system message to `session_started` (session id, model, tools, `cli_version`), a tool-use block to `tool_started` (`subagent` true when `parent_tool_use_id` is set), a tool-result block to `tool_finished` (`ok` when not `is_error`), a streamed text delta to `model_delta`, an assistant text block to `text`, a rate-limit event or an assistant error `rate_limit` to `retrying` (`rate_limit`), a gatekeeper deny or an entry of the result's `permission_denials` to `denied`, and the result message to `result` (`total_cost_usd` as `reported_cost_usd`, `usage`, `model_usage` as `by_model`, `num_turns` as `turns`, `session_id`), skipping and counting an unknown message type.

- GIVEN a tool-use block with `parent_tool_use_id` set WHEN mapped THEN `tool_started` has `subagent` true

### EAS-B4 Both versions stamped

WHEN any session is recorded THE worker SHALL put in `cli_version` the SDK version and the bundled or pinned CLI version, so a change in either is visible.

- GIVEN SDK 0.2.0 with bundled CLI 2.1.330 WHEN a session is recorded THEN `cli_version` names both

### EAS-B12 Failure classification

WHEN a session fails THE worker SHALL classify by typed values only: worker spawn raised, or the SDK raised its CLI-not-found or connection error, `spawn_failed`; no `result` line or no result message before the stream closed `no_result`; a last assistant error `rate_limit` or `server_error` with no result message `throttled`; subtype `error_max_turns` `error_kind = turn_cap`; subtype `error_max_budget_usd` `error_kind = cap_reached`; an assistant error `authentication_failed` or `billing_error` `error_kind = auth`; subtype `error_during_execution`, or `is_error` otherwise, `error_kind = model` with `api_error_status` and `terminal_reason` recorded; and an `error` value the SDK does not list `error_kind = unknown`.

- GIVEN a result with `subtype = error_max_turns` WHEN classified THEN `error_kind` is `turn_cap`

### EAS-B3 Typed subtypes, not text

WHEN a result message is classified THE worker SHALL read its subtype and never its `result` text.

- GIVEN a result with `subtype = error_max_budget_usd` WHEN classified THEN `error_kind = cap_reached` and the `result` text is not read

### EAS-B13 Probe refusals

WHEN the SDK cannot be imported or its CLI is missing, or only a claude.ai sign-in is available with no API or cloud credential THE probe SHALL fail and preflight SHALL exit 2, the second with reason `credential` ([research `claude-agent-sdk-executor`](../research/claude-agent-sdk-executor.rsrch.md) S3).

- GIVEN only a claude.ai sign-in WHEN preflighted THEN it exits 2 with reason `credential`

### EAS-B15 Init outside the views

WHEN a judge session's init message lists a tool outside the judge's views THE engine SHALL discard the judgement as an unresolved gap ([GRD](independence-guard.spec.md)).

- GIVEN a judge init listing `Write` WHEN read THEN the judgement is discarded as an unresolved gap

## Acceptance criteria

- EAS-AC1 (EAS-B7, EAS-B8, EAS-B9): Options for every launch shape are built from constants and the binding table only, by source-scan and planted-canary tests
- EAS-AC2 (EAS-B11, EAS-B12, EAS-B3, EAS-B4): Each message mapping and each failure classification has a recorded-message fixture, and every recorded session names both versions
- EAS-AC3 (EAS-B9, EAS-B1, EAS-B15): A judge's options never contain a write tool, a step rule, `fallback_model` or a resume option, and a judge whose init lists a tool outside its views is discarded
- EAS-AC4 (EAS-B2, EAS-B10, EAS-B6): The gatekeeper follows the scenarios of EAS-B2 in a unit test without the SDK, and each capability maps to its tool and rule
- EAS-AC5 (EAS-B5, EAS-B14, EAS-B13): The probe table in research `rationale-carried-from-the-engine-specs` is filled for the pinned SDK and CLI versions before the executor is marked live-proven

## Open questions

- May an operator run this executor on a subscription sign-in? The design assumes API or cloud credentials only ([research `claude-agent-sdk-executor`](../research/claude-agent-sdk-executor.rsrch.md) S3). Owner: owner.
