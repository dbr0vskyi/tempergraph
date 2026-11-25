# Claude Agent SDK as an executor

## Problem statement

The owner asked for an executor on the "Claude SDK". Anthropic ships two SDK families: the client SDK (`anthropic`), which is a thin layer over the Messages API and is covered by [research `anthropic-messages-api-executor`](anthropic-messages-api-executor.rsrch.md), and the **Claude Agent SDK** (`claude-agent-sdk`), which is Claude Code packaged as a library. This note reads "Claude SDK" as the Agent SDK, and records how it behaves as a step and judge host for the [Agent SDK executor spec](../specs/executor-agent-sdk.spec.md).

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Agent SDK overview | Official documentation | https://code.claude.com/docs/en/agent-sdk (read in full) |
| Agent SDK Python reference | Official documentation | https://code.claude.com/docs/en/agent-sdk/python.md (options, permission types, message types; about 137 KB, read in two parts) |
| Agent SDK permissions | Official documentation | https://code.claude.com/docs/en/agent-sdk/permissions.md (read in full) |
| `claude-api` skill, "four approaches" table | Official guidance, local copy | Skill `SKILL.md` |

Read on 2026-11-19.

## Key findings

### Shape

| # | Finding | Confidence |
|---|---|---|
| S1 | The Agent SDK "runs the Claude Code binary" and exposes Claude Code's tools, permissions, hooks, subagents, MCP, sessions, skills and plugins to Python and TypeScript. The Python package bundles a Claude Code CLI; `cli_path` can point at another. | confirmed |
| S2 | `query(prompt, options)` starts a new session per call and yields typed messages; `ClaudeSDKClient` keeps a session across exchanges and supports `interrupt()`. | confirmed |
| S3 | Use is governed by Anthropic's Commercial Terms. Third-party products may not offer claude.ai login unless approved; API-key, Bedrock or Vertex credentials are the documented auth. | confirmed |

### Restricting a session

| # | Finding | Confidence |
|---|---|---|
| S4 | `tools` sets the built-in tool list (or the `claude_code` preset). `disallowed_tools` with a bare name removes a tool from the model's context; `"*"` and `"mcp__*"` globs are accepted in deny rules. | confirmed |
| S5 | `allowed_tools` only pre-approves; it does not restrict. Unlisted tools fall through to the permission mode. | confirmed |
| S6 | Permission modes: `default`, `acceptEdits`, `plan`, `dontAsk`, `bypassPermissions`, `auto`. `dontAsk` denies anything not pre-approved and never calls `can_use_tool`; calls that need no approval (reads inside the working directory, `Agent`) still run. | confirmed |
| S7 | Evaluation order: hooks, deny rules, ask rules, permission mode, allow rules, `can_use_tool`. A `PreToolUse` hook runs first and its deny applies even in `bypassPermissions`. Hooks are in-process Python callbacks (`hooks` option with `HookMatcher`). | confirmed |
| S8 | `setting_sources` defaults to `None`, which loads user, project and local settings like the CLI; `[]` loads none. | confirmed |
| S9 | `strict_mcp_config=True` uses only `mcp_servers` and ignores project `.mcp.json`, user settings, plugin servers and claude.ai connectors. `create_sdk_mcp_server` defines an MCP server in-process. | confirmed |
| S10 | A subagent runs in its parent's permission mode, unless its definition sets another mode and the parent is in `default`, `dontAsk` or `plan`. Whether a parent's `PreToolUse` hook sees a subagent's tool calls is not stated on the pages read. | supported / uncertain |

### Bounds, cost and messages

| # | Finding | Confidence |
|---|---|---|
| S11 | `max_turns`, `max_budget_usd` (stops at the client-side cost estimate), `model`, `fallback_model`, `effort`, `cwd`, `env` (merged over the inherited environment), `stderr` callback and `extra_args` are options. | confirmed |
| S12 | Message types: `SystemMessage` (with an init subtype), `AssistantMessage` (content blocks, `model`, `parent_tool_use_id`, `error`, `usage`, `stop_reason`), `UserMessage` (tool results), `StreamEvent` (raw API stream events, opt-in), `RateLimitEvent`, `ResultMessage`. | confirmed |
| S13 | `ResultMessage.subtype` is `success`, `error_during_execution`, `error_max_turns`, `error_max_budget_usd` or `error_max_structured_output_retries`; it carries `total_cost_usd`, `usage`, `model_usage` (per model, whole tree, with `costUSD` estimates), `num_turns`, `duration_ms`, `is_error`, `api_error_status`, `permission_denials`, `session_id` and `terminal_reason`. | confirmed |
| S14 | `AssistantMessage.error` takes typed values: `authentication_failed`, `billing_error`, `rate_limit`, `invalid_request`, `server_error`, `unknown`; the CLI can emit others, to be treated as `unknown`. | confirmed |
| S15 | Costs are client-side estimates, not billing figures. | confirmed |

## Conclusions

1. The Agent SDK meets the step and judge bars the Claude Code CLI meets ([research `claude-code-cli-headless`](claude-code-cli-headless.rsrch.md)), with the same tool names, so it can share Claude Code's tool map and view catalog rows.
2. It adds one control the CLI lacks: an **in-process `PreToolUse` hook** that sees every call before any rule and can deny it in every mode (S7). The engine can run its own gatekeeper in the worker process, with no hooks file on disk.
3. The judge launch must pass `setting_sources=[]` and `strict_mcp_config=True` explicitly, because the default loads the operator's settings (S8, S9).
4. Messages are typed, so the executor reads dataclass fields rather than parsing a JSON stream, which narrows the drift surface; the SDK and its bundled CLI version are both recorded.
5. It is the natural CI executor: a `pip` dependency with its own CLI, API-key or cloud credentials, and no interactive sign-in (S1, S3).
6. Because the SDK drives a child CLI process, the engine keeps its own launcher in front by running the SDK inside an engine worker process ([ADR `in-process-executors-run-in-a-worker-process`](../adr/in-process-executors-run-in-a-worker-process.adr.md)), so timeouts and the process-tree kill stay engine-owned.

## Open questions

| Question | Owner | How to settle |
|---|---|---|
| Does `setting_sources=[]` keep user-level plugin tools out of the session? | Executor implementer | Probe P-AS-1. |
| Does the session's `PreToolUse` hook see and deny a subagent's tool calls? | Executor implementer | Probe P-AS-2. |
| May an operator run the engine on their own subscription sign-in, or only on API or cloud credentials? | Owner | Read the terms (S3); the design assumes API or cloud credentials. |
