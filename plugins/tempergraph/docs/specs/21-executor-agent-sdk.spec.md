---
title: Claude Agent SDK executor
type: component
status: review
prefix: EAS
adrs: [0006, 0008, 0010, 0012, 0018, 0019]
---

# Claude Agent SDK executor

## 1. Overview


## 2. Contract

### 2.1 Declared capabilities

| Capability | Value | Basis |
|---|---|---|
| `binds_aliases` | `small`, `medium`, `large`, `inherit`, every `agent-sdk:<name>` in the binding table | S11 |
| `prompt_off_argv` | true: the prompt reaches the worker on stdin and the SDK as a typed argument; P-AS-3 confirms how the SDK passes it to its CLI | S2 |
| `streams_events`, `reports_actions`, `reports_tokens`, `reports_cost`, `fresh_session` | true | S12, S13 |
| `enforces_step_tools`, `step_allow_rules`, `judge_mcp` | true | S4, S5, S9 |
| `restricts_judge_tools` | true: `tools` plus `disallowed_tools` plus the gatekeeper hook, whose deny holds in every mode | S4, S7 |
| `isolates_user_config` | true when P-AS-1 passes, else false | S8 |
| `hosts_authoring_surface` | true (Claude Code's) | S1 |
| `session_options` | `effort`, `cost_cap_usd`, `fallback_alias`, `turn_cap` | S11 |

### 2.2 Tool map

The same as [ECC §2.2](11-executor-claude-code.spec.md): `Read`, `Grep`, `Glob`, `Edit`, `Write`, `Bash`, `WebFetch`, `WebSearch`, `Agent`, `mcp__<s>__<t>`, with the same allow rules. The view catalog shares Claude Code's rows ([GRD](06-independence-guard.spec.md)).

### 2.3 Worker request document

The launcher starts `<engine python> -m tempergraph.executors.sdk_worker` and writes one JSON document on stdin with the fields of [EMA §2.3](20-executor-messages-api.spec.md) (minus `server_tools`, plus `cli_path` from the binding table when the operator pins a CLI other than the bundled one). The worker re-validates every field, builds `ClaudeAgentOptions` from constants and those fields, and emits normalized events as JSON lines.

### 2.4 Step options

| Option | Value |
|---|---|
| `cwd` | `workdir` |
| `model` | bound model, omitted for `inherit` |
| `tools` | mapped built-ins, when the operator enabled enforcement; else the `claude_code` preset |
| `allowed_tools` | the rules of §2.2 |
| `permission_mode` | `acceptEdits` in the engine's own worktree, `default` in place; never `bypassPermissions` or `auto` |
| `setting_sources` | `["project"]`, so the repository's CLAUDE.md and skills load and user settings do not |
| `mcp_servers`, `strict_mcp_config` | the engine's file and `True`, when enforcement is on and an MCP tool is declared |
| `hooks` | the gatekeeper `PreToolUse` hook (§2.6) |
| `max_turns`, `max_budget_usd`, `fallback_model`, `effort` | from options, when set |
| `env` | the overlay of [ECC §2.3](11-executor-claude-code.spec.md) |
| `can_use_tool` | none: an unlisted call in `default` mode is denied by the gatekeeper, never prompted |

### 2.5 Judge options

| Option | Value |
|---|---|
| `tools` | `Read`, `Grep`, `Glob` plus built-in views |
| `disallowed_tools` | `["mcp__*"]` when the judge has no MCP view |
| `setting_sources` | `[]` |
| `strict_mcp_config` | `True`, with only the filtering proxy per MCP view in `mcp_servers` |
| `permission_mode` | `dontAsk` |
| `allowed_tools` | view rules, plus read-only command rules when opted in |
| `hooks` | the gatekeeper with the view set as its allow list |
| never set | `fallback_model`, `resume`, `continue_conversation`, `fork_session`, a write tool, a step allow rule |

### 2.6 Gatekeeper hook

An in-process `PreToolUse` callback built by the worker from the declaration. It allows a call when the tool's name is in the session's mapped set and, for `Bash`, when the command's first words match a declared prefix and contain no shell metacharacter of [THS §2.5](22-tool-host.spec.md); otherwise it denies with a fixed reason and the worker emits `denied`. It is the first rule evaluated (S7), so it holds whatever the mode, and it is the step's enforcement when the operator enabled it.

### 2.7 Message mapping

| SDK message | Normalized event |
|---|---|
| `SystemMessage`, init subtype | `session_started` (session id, model, tools; `cli_version` = SDK version plus bundled CLI version) |
| `AssistantMessage` `ToolUseBlock` | `tool_started` (`subagent` = `parent_tool_use_id` is set) |
| `UserMessage` `ToolResultBlock` | `tool_finished` (`ok` = not `is_error`) |
| `StreamEvent` text delta (partial messages on) | `model_delta` |
| `AssistantMessage` text block | `text` |
| `RateLimitEvent`, or `AssistantMessage.error = rate_limit` | `retrying` (`category = rate_limit`) |
| Gatekeeper deny, or an entry of `ResultMessage.permission_denials` | `denied` |
| `ResultMessage` | `result`: `total_cost_usd` → `reported_cost_usd`, `usage`, `model_usage` → `by_model`, `num_turns` → `turns`, `session_id` |

### 2.8 Failure classification

| Observed (typed) | `infra_cause` / `error_kind` |
|---|---|
| Worker spawn raised | `spawn_failed` |
| SDK raised its CLI-not-found or connection error type | `spawn_failed` |
| Worker ended with no `result` line | `no_result` |
| No `ResultMessage` before the stream closed | `no_result` |
| Last `AssistantMessage.error` is `rate_limit` or `server_error` and no `ResultMessage` | `throttled` |
| `subtype = error_max_turns` | `error_kind = turn_cap` |
| `subtype = error_max_budget_usd` | `error_kind = cap_reached` |
| `AssistantMessage.error` is `authentication_failed` or `billing_error` | `error_kind = auth` |
| `subtype = error_during_execution`, or `is_error` otherwise | `error_kind = model`, with `api_error_status` and `terminal_reason` recorded |
| An `error` value the SDK does not list | `error_kind = unknown` |

### 2.9 Probes

| Id | Fact to confirm | Used by | Result |
|---|---|---|---|
| P-AS-1 | `setting_sources=[]` keeps user-level plugin tools, hooks and MCP servers out of the session (seen in the init message) | `isolates_user_config` | not run |
| P-AS-2 | The session's `PreToolUse` hook sees and can deny a subagent's tool calls | gatekeeper on steps that declare `subagent` | not run |
| P-AS-3 | The SDK hands the prompt to its CLI off argv on the pinned version | `prompt_off_argv` | not run |

Until P-AS-2 passes, a step that declares `subagent` with enforcement on is refused at preflight on this executor.

## 3. Behaviours

**EAS-B1 Judge loads nothing of the operator's.** Given an operator with user-level settings, plugins and MCP servers, when a judge session starts, then the options carry `setting_sources=[]`, `strict_mcp_config=True` and only the judge's proxies, and the init message lists only the view tools.

**EAS-B2 Gatekeeper holds in every mode.** Given a step in `acceptEdits` that declares `shell` with prefix `pytest`, when the model calls `Bash` with `rm -rf build`, then the hook denies it, nothing runs, and a `denied` event is emitted.

| Command | Decision |
|---|---|
| `pytest -q` | allow |
| `pytest; rm x` | deny (metacharacter) |
| `rm -rf build` | deny (prefix) |

**EAS-B3 Typed subtypes, not text.** Given a `ResultMessage` with `subtype = error_max_budget_usd`, when the outcome is classified, then `error_kind = cap_reached` and `result` text is not read.

**EAS-B4 Both versions stamped.** Given any session, when it is recorded, then `cli_version` holds the SDK version and the bundled or pinned CLI version, so a change in either is visible.

## 4. Error conditions

| Type | Handling |
|---|---|
| SDK not importable, or its CLI missing | Probe fails; exit 2 |
| Only a claude.ai sign-in available, no API or cloud credential | Probe fails; exit 2 with reason `credential` ([R-005 S3](../research/R-005-claude-agent-sdk-executor.rsrch.md)) |
| Init message lists a tool outside the judge's views | Judgement discarded as an unresolved gap ([GRD](06-independence-guard.spec.md)) |
| Unknown message type | Skipped and counted |

## 5. Design notes

- Steps load project settings only, so a repository's CLAUDE.md and skills work as on `claude` while the operator's user settings stay out of CI.
- The executor never uses `ClaudeSDKClient`: one `query()` per session matches the fresh-session rule, and a retry is a new session told the last report.
- Because the SDK's own CLI is a child of the worker, the launcher's tree kill ends it with the worker ([EXI-B5](10-executor-interface.spec.md)).

## 6. Acceptance criteria

- [ ] EAS-AC-1 Options for every launch shape are built from constants and the binding table only (source-scan and planted-canary tests).
- [ ] EAS-AC-2 Each row of §2.7 and §2.8 has a recorded-message fixture.
- [ ] EAS-AC-3 A judge's options never contain a write tool, a step rule, `fallback_model` or a resume option.
- [ ] EAS-AC-4 The gatekeeper follows the table of EAS-B2 in a unit test without the SDK.
- [ ] EAS-AC-5 The probe table is filled for the pinned SDK and CLI versions before the executor is marked live-proven.

## Open questions

| Question | Owner |
|---|---|
| May an operator run this executor on a subscription sign-in? The design assumes API or cloud credentials only ([R-005 S3](../research/R-005-claude-agent-sdk-executor.rsrch.md)). | Owner |

## References

[EXI](10-executor-interface.spec.md) · [ECC](11-executor-claude-code.spec.md) · [R-005](../research/R-005-claude-agent-sdk-executor.rsrch.md) · [ADR-0019](../adr/0019-in-process-executors-run-in-a-worker-process.adr.md)
