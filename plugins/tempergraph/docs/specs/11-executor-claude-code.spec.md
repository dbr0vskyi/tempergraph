---
title: Claude Code executor
type: component
status: review
prefix: ECC
adrs: [0006, 0007, 0008, 0010, 0012]
---

# Claude Code executor

## 1. Overview

The `claude` executor runs each step attempt and each judge run as one headless Claude Code session: `claude -p` with the prompt on stdin and a `stream-json` event stream on stdout. It implements the [executor interface](10-executor-interface.spec.md) and maps the engine's neutral contracts ([CON](01-contracts.spec.md)) to Claude Code's flags. Facts about the CLI come from [R-001](../research/R-001-claude-code-cli-headless.rsrch.md). This executor is the default **judge executor**: it can hold a session to an exact read-only tool set by absence.

## 2. Contract

### 2.1 Declared capabilities

| Capability | Value | Basis |
|---|---|---|
| `binds_aliases` | `small`, `medium`, `large`, `inherit`, every `claude:<name>` in the binding table | [R-001 F10, F11](../research/R-001-claude-code-cli-headless.rsrch.md) |
| `prompt_off_argv`, `streams_events`, `reports_actions`, `reports_tokens`, `reports_cost` | true | F2–F4, F8, F18 |
| `enforces_step_tools`, `step_allow_rules`, `judge_mcp`, `fresh_session` | true | F12, F13, F15, F20 |
| `restricts_judge_tools` | true | F12, F14, F15; the plugin-tool gap is closed by `--bare` once P-CC-1 passes, else by the guard |
| `isolates_user_config` | true when P-CC-1 passes, else false | F16, F17 |
| `session_options` | `effort`, `cost_cap_usd`, `fallback_alias`, `turn_cap` | F9, F10 |

### 2.2 Tool map

| Capability | Claude Code tool | Allow rule when declared |
|---|---|---|
| `read` | `Read` | `Read` |
| `search` | `Grep` | `Grep` |
| `list` | `Glob` | `Glob` |
| `edit` | `Edit` | `Edit(./**)` in the engine's own worktree only |
| `write` | `Write` | `Write(./**)` in the engine's own worktree only |
| `shell` | `Bash` | `Bash(<prefix> *)` per declared command prefix |
| `web_fetch` | `WebFetch` | `WebFetch` |
| `web_search` | `WebSearch` | `WebSearch` |
| `subagent` | `Agent` (reported as `Task` by older releases) | `Agent` |
| `mcp:<s>/<t>` | `mcp__<s>__<t>` | `mcp__<s>__<t>` |
| `skill:<p>:<n>` | `Skill` | `Skill(<p>:<n>)` once P-CC-8 confirms it, else `Skill`, with the called name checked in the tool record ([ADR-0078](../adr/0078-skills-are-a-declared-tool-capability.adr.md)) |

### 2.3 Step launch

Argv is assembled from the constants below; bracketed parts are added only when their condition holds. Values in angle brackets come from the binding table or from engine-checked numbers, never from typed text.

```text
claude -p --output-format stream-json --verbose
       --permission-mode <acceptEdits in engine worktree | default in place>
       --permission-prompts none                       [CLI supports it, per probe]
       --model <bound model>                           [alias is not inherit]
       --allowedTools <rules from §2.2>                [step declares tools]
       --tools <mapped built-ins>                      [operator enabled enforcement]
       --disallowedTools EnterWorktree,ExitWorktree    [always; the run's worktree is the engine's, WTR §2.9]
       --strict-mcp-config --mcp-config <engine file>  [enforcement and an MCP tool declared]
       --effort <level> | --max-budget-usd <n> | --fallback-model <bound> | --max-turns <n>   [option set]
```

Environment overlay: `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` unless the host already sets it; `CLAUDE_CODE_SUBAGENT_MODEL=<bound model>` unless the step names a subagent alias. Prompt: UTF-8 on stdin, then stdin closes.

### 2.4 Judge launch

```text
claude -p --output-format stream-json --verbose
       --bare                                         [P-CC-1 passed]
       --setting-sources ""                           [P-CC-1 not passed]
       --model <bound judge model>
       --tools <Read,Grep,Glob plus built-in views>
       --disallowedTools "mcp__*"                     [no MCP view]
       --strict-mcp-config --mcp-config <private file: filtering proxy per MCP view>   [MCP views]
       --permission-mode dontAsk
       --allowedTools <view rules, plus read-only command rules when opted in>
```

Never sent to a judge: `--fallback-model`, `--resume`, `--continue`, a write tool, a step's allow rules. Judge-only credentials are laid over the environment from the operator's credentials profile.

### 2.5 Stream mapping

| CLI event | Normalized event ([CON §2.7](01-contracts.spec.md)) |
|---|---|
| `system` / `init` | `session_started` (session id, model, tools, plus `mcp_server_errors`, `plugin_errors` kept as counts) |
| `assistant` content block `tool_use` | `tool_started` (`name`, `subagent` = `parent_tool_use_id` is set) |
| `user` content block `tool_result` | `tool_finished` (`ok` = not `is_error`) |
| `stream_event` text delta | `model_delta` (count only) |
| `assistant` text block | `text` (last line, scrubbed) |
| `system` / `api_retry` | `retrying` (`category` = the event's `error` value) |
| `system` / `permission_denied` | `denied` |
| `result` | `result` with `total_cost_usd` → `reported_cost_usd`, `usage`, `modelUsage` → `by_model`, `num_turns` → `turns`, `session_id` |

### 2.6 Failure classification

| Observed (structured) | `infra_cause` / `error_kind` |
|---|---|
| Spawn raised with a resource errno | `spawn_failed` |
| Write to stdin raised broken pipe | `broken_pipe` |
| Process ended, no stdout line | `no_output` |
| Stream ended without a `result` event | `no_result` |
| `result.subtype` is not `success` and `result.result == "Request timed out"` exactly | `request_timed_out` |
| Last `retrying` category is `rate_limit` or `overloaded` and no `result` | `throttled` |
| `result.subtype == "error_max_turns"` | `error_kind = turn_cap` |
| Session ended by `--max-budget-usd` (shape set by P-CC-3) | `error_kind = cap_reached` |
| `retrying` category `authentication_failed` | `error_kind = auth` |
| `result.is_error` otherwise | `error_kind = model` |

### 2.7 Probes

Each probe is run by the owner against the pinned CLI version with an isolated config folder; its result is written into this table with the date and version. Until a row says `confirmed`, no control rests on it.

| Id | Fact to confirm | Used by | Result |
|---|---|---|---|
| P-CC-1 | `--bare` removes tools registered by user-level plugins and hooks from a headless session, and the gateway credentials still work | `isolates_user_config`, judge launch | not run |
| P-CC-2 | `--tools Read,Grep,Glob` plus `--disallowedTools "mcp__*"` leaves exactly those tools in `system/init` | `restricts_judge_tools` | not run |
| P-CC-3 | The stream shape when `--max-budget-usd` ends a session | `cap_reached` classification | not run |
| P-CC-4 | Precedence of `CLAUDE_CODE_SUBAGENT_MODEL` against an agent call's own model | subagent alias | not run |
| P-CC-5 | A prompt on stdin with `-p` and no positional prompt is accepted on the pinned version | `prompt_off_argv` | not run |
| P-CC-6 | `dontAsk` refuses an unlisted call without a prompt and emits `permission_denied` | judge launch | not run |
| P-CC-7 | Whether an engine-launched session keeps a native transcript under its isolation flags, and at which path | transcript locator ([EVT §2.4](30-run-events.spec.md)) | not run |
| P-CC-8 | A `Skill(<plugin>:<name>)` allow rule admits only that skill in a headless session, and the tool record names the skill called | `skill:` capability | not run |
| P-CC-9 | `claude -p --plugin-dir <package root>` loads the workflow plugin's skills and agents in a headless step session (listed in `system/init`), together with the isolation flags of a step launch | workflow skills and agents on step sessions ([PKG §2.6](88-workflow-package.spec.md)) | not run |

## 3. Behaviours

**ECC-B1 Declared shell.** Given a step that declares `shell` with command prefixes `pytest` and `git status`, when it launches in the engine's own worktree, then `--allowedTools` holds `Bash(pytest *)` and `Bash(git status *)`, the permission mode is `acceptEdits`, and no rule names an absolute path.

**ECC-B2 Tool names and rules stay apart.** Given any launch, when argv is built, then tool names go only to `--tools` or `--disallowedTools` and permission rules only to `--allowedTools`.

**ECC-B3 Judge view.** Given a judge whose view set is `read`, `search`, `list` and `mcp:tracker/get_issue`, when it launches, then `--tools` is `Read,Grep,Glob`, the private MCP config lists one server, the filtering proxy in front of `tracker`, which offers only `get_issue`, and the mode is `dontAsk`.

**ECC-B4 Reported cost.** Given a `result` event with `total_cost_usd = 1.73`, when usage is recorded, then `reported_cost_usd = 1.73` and the engine's own estimate is stored beside it, never summed.

**ECC-B5 Exact timeout text.** Given `result.result` is "Request timed out." with a trailing period, when the cause is classified, then it is not `request_timed_out`, because only exact equality counts.

| `result.result` | Class |
|---|---|
| `Request timed out` | `request_timed_out` (infra) |
| `Request timed out.` | `error_kind = model` |
| `The request timed out` | `error_kind = model` |

## 4. Error conditions

| Type | Handling |
|---|---|
| `claude` not on the engine's resolved PATH | Probe fails; exit 2 at preflight |
| `claude auth status` reports signed out and no gateway variables are set | Probe fails; exit 2 |
| A `system/init` reporting `mcp_server_errors` for a judge view server | The view is recorded as deferred; the dependent criterion renders as out of reach |
| An unknown event type in the stream | Skipped and counted; never fails the session |

## 5. Design notes

- The permission mode is always passed explicitly because the `-p` default has changed between releases ([R-001 F14](../research/R-001-claude-code-cli-headless.rsrch.md)).
- A resumed session is never used for a retry: a fresh session told the last report was measured cheaper ([R-001 F20](../research/R-001-claude-code-cli-headless.rsrch.md)).

## 6. Acceptance criteria

- [ ] ECC-AC-1 Argv for every launch shape is built from constants and the binding table only (source-scan and planted-canary tests).
- [ ] ECC-AC-2 Each row of §2.5 is covered by a recorded-stream fixture that yields the normalized event.
- [ ] ECC-AC-3 Each row of §2.6 is covered by a fixture and classified without reading prose beyond the one exact match.
- [ ] ECC-AC-4 A judge launch never contains a write tool, a step allow rule, `--fallback-model` or `--resume`.
- [ ] ECC-AC-5 The probe table is filled for the pinned CLI version before the executor is marked live-proven.

## Open questions

| Question | Owner |
|---|---|
| Use `--input-format stream-json` for the prompt instead of plain stdin, to share framing with the Antigravity executor? Decide after P-CC-5. | Executor implementer |

## References

[EXI](10-executor-interface.spec.md) · [R-001](../research/R-001-claude-code-cli-headless.rsrch.md) · [R-003](../research/R-003-executor-capability-matrix.rsrch.md) · [GRD](06-independence-guard.spec.md)
