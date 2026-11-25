# Claude Code CLI as a headless executor

## Problem statement

tempergraph runs every step and every judge as a headless agent session started by an executor (see the [executor interface spec](../specs/executor-interface.spec.md)). This note records how the Claude Code CLI (`claude`) behaves when it is driven non-interactively as a child process, so that the [Claude Code executor spec](../specs/executor-claude-code.spec.md) rests on documented facts and not on memory. Behaviour observed in headless runs is folded in where it confirms or refines a documented fact.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Claude Code CLI reference | Official documentation | https://code.claude.com/docs/en/CLI-reference (first ~40 KB read verbatim, rest summarized) |
| Claude Code headless / programmatic use | Official documentation | https://code.claude.com/docs/en/headless.md (read in full) |

Read on 2026-11-19. Several flags carry minimum-version notes; the executor must record `claude --version` with every session.

## Key findings

### Invocation and I/O

| # | Finding | Confidence |
|---|---|---|
| F1 | `-p` / `--print` runs one non-interactive turn and exits; exit 0 on success, non-zero on failure. An invalid flag errors on stderr before the run starts; a failure inside the run (for example missing auth) is printed as the result. | confirmed |
| F2 | The prompt may be piped on stdin (capped at 10 MB), and stdin alone, never argv, can carry every prompt. The CLI waits about 3 s for stdin data and then exits with an error. | supported (observed; docs show stdin as data, not the sole prompt) |
| F3 | `--output-format` takes `text`, `json` or `stream-json` (newline-delimited events). `--input-format` takes `text` or `stream-json`. Every documented `stream-json` example passes `--verbose`. | confirmed |
| F4 | The last `stream-json` line is a `result` event with the final text, cost, session id and permission denials (`permission_denials`). Denials also appear as `permission_denied` system events. Messages from subagents carry `parent_tool_use_id`. | confirmed |
| F5 | A `system/init` event lists plugins, MCP servers and their errors (`plugin_errors`, `mcp_server_errors`), and may carry a `capabilities` array for feature detection. A `system/api_retry` event names each retry with an error category (`rate_limit`, `overloaded`, `authentication_failed`, `server_error` and others). | confirmed |
| F6 | `--json-schema` validates a final structured answer into `structured_output` (print mode only); when the session ends without valid output the field is absent. | confirmed |
| F7 | SIGINT ends the turn cleanly with a result; SIGTERM exits 143 with no result. After the turn a `-p` run waits for background work up to `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` (default 10 minutes). | supported (one doc page) |

### Limits, cost and models

| # | Finding | Confidence |
|---|---|---|
| F8 | Cost is reported per session (`total_cost_usd`, with a per-model breakdown). Both figures are client-side estimates. On `--resume` the reported cost is the whole conversation's total. | confirmed |
| F9 | `--max-turns N` ends the session with an error at the limit. `--max-budget-usd` caps spend (subagents included) in print mode; enforcement needs a recent CLI. | confirmed |
| F10 | `--model` accepts an alias (`sonnet`, `opus`, `haiku`, `fable`) or a full name; `--fallback-model` takes an ordered list; `--effort` takes `low`, `medium`, `high`, `xhigh`, `max` (availability depends on the model). | confirmed |
| F11 | On a model gateway (Amazon Bedrock and similar) an alias must be bound to a deployment id per machine; an alias the gateway refuses fails inside the child, not at start. | supported (observed) |

### Tools, permissions and isolation

| # | Finding | Confidence |
|---|---|---|
| F12 | `--tools` restricts the built-in tool set (`""` none, names such as `Read,Grep,Glob`). It does not affect MCP tools. A bare name in `--disallowedTools` removes the tool from context; `mcp__*` removes all MCP tools. | confirmed |
| F13 | `--allowedTools` auto-approves matching calls in permission-rule syntax (for example `Bash(git diff *)`); it does not restrict the set. Tool names and permission rules are separate arguments: rules written into a tool-name flag lose the shell entirely. | confirmed (docs + observed) |
| F14 | `--permission-mode` takes `default`, `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions` (and `manual` as an alias of `default`). `dontAsk` denies every call that would prompt. `--permission-prompts none` tells the model nobody can approve. The default mode for `-p` has changed between releases. | confirmed (docs disagree on the default; pin it explicitly) |
| F15 | `--mcp-config` loads servers from files or JSON strings; `--strict-mcp-config` uses only those. Invalid entries are skipped and reported in `system/init`. | confirmed |
| F16 | `--bare` skips discovery of hooks, skills, commands, subagents, plugins, MCP servers, memory and CLAUDE.md; it needs an API key or an `apiKeyHelper`, and is meant for scripted calls. `--settings` takes a file or JSON; `--setting-sources` selects which setting layers load. | supported (bare: docs; `--setting-sources`: flag listed, text not read) |
| F17 | A tool registered by a user-level plugin can reach a judge despite a built-in tool list and a strict MCP config; the guard then voids a complete verdict. `--bare` would plausibly close this. | supported (observed failure; the `--bare` remedy is inferred) |
| F18 | The CLI reports tool calls under their full names in the stream, including subagent calls, so an after-the-fact guard can compare names exactly. | supported (observed) |
| F19 | Each shell call starts in the project directory only when a host switch is set (`CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR`); a `cd` before `git` is refused by the CLI's own guard regardless of rules. | supported (observed) |

### Sessions and lifetime

| # | Finding | Confidence |
|---|---|---|
| F20 | Every run gets a session id; `--resume <id>` continues it. A resumed retry carries the whole conversation so far, so it costs more than a fresh session told the last report. | supported (session ids and resume: docs; the cost comparison is inferred) |
| F21 | A stalled model request is re-sent by the CLI for close to an hour and then ends as a success-typed error whose text is exactly "Request timed out". | supported (observed) |
| F22 | A child left running after its parent dies keeps spending and writing; the process tree must be tied to the parent (job object or process group). | supported (observed) |

## Conclusions

1. The CLI supports everything the executor interface needs from a step executor: stdin prompt, a structured event stream with tool names, reported cost, model aliases, effort, a per-session cost cap, a fallback model, a turn cap and session ids.
2. The CLI can **restrict** a judge's tools by absence: `--tools` for built-ins, `--strict-mcp-config` with an engine-written config for MCP, and `--bare` for plugins and hooks. With `--permission-mode dontAsk` anything left outside the allow rules is refused without a prompt. Judge capability `restricts_tools` is therefore declared `true`, conditional on the probe of [research `executor-capability-matrix`](executor-capability-matrix.rsrch.md).
3. The CLI reports its actions (tool names in the stream), so the independence guard is available.
4. Cost is reported but is an estimate by the CLI; the engine records it as `reported` and keeps its own price-table estimate apart.
5. The prompt must go on stdin and the writer must start immediately after spawn, inside the 3 s window.
6. Because flag defaults move between releases, the executor passes every behaviour-relevant flag explicitly (permission mode, output format, setting sources) and records the CLI version.

## Open questions

| Question | Owner | How to settle |
|---|---|---|
| Does `--bare` remove tools registered by user-level plugins from a headless session? | Executor implementer | Probe P-CC-1 in the [Claude Code executor spec](../specs/executor-claude-code.spec.md). |
| Which wins for a subagent's model: `CLAUDE_CODE_SUBAGENT_MODEL` or the model named in an agent call? | Executor implementer | Probe P-CC-4. |
| What does the stream show when `--max-budget-usd` ends a session? | Executor implementer | Probe P-CC-3. |
| How many concurrent sessions does the model gateway accept before throttling, and how does `system/api_retry` report it? | Operator | Live batch at 1, 3, 5, 8 sessions. |
