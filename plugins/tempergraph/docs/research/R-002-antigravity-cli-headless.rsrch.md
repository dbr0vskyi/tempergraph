# R-002 Antigravity CLI as a headless executor

## Problem statement

The design must support the Antigravity CLI (`agy`), Google's terminal agent, as a second executor beside Claude Code. tempergraph starts one fresh headless session per step attempt and one fresh **read-only** session per judge run, and it relies on the executor to restrict tools, report actions and usage, honour a timeout and die with the engine. This note records what `agy` documents and what the community reports about those needs, so the [Antigravity executor spec](../specs/executor-antigravity.spec.md) and [ADR-0010](../adr/0010-judge-isolation-per-executor.adr.md) and [ADR-0011](../adr/0011-isolated-config-home-for-antigravity.adr.md) rest on evidence.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Antigravity CLI headless mode | Official documentation | https://antigravity.google/docs/cli/headless/ (first ~40 KB verbatim, tail summarized) |
| Antigravity CLI commands reference | Official documentation | https://antigravity.google/docs/cli/reference (first ~40 KB verbatim, tail summarized) |
| Agent permissions (App and CLI) | Official documentation | https://antigravity.google/docs/permissions.md |
| Settings | Official documentation | https://antigravity.google/docs/settings.md |
| CLI modes | Official documentation | https://antigravity.google/docs/cli/modes/ |
| MCP, hooks, sandbox (CLI tabs) | Official documentation | https://antigravity.google/docs/mcp?tab=cli, https://antigravity.google/docs/hooks?tab=cli, https://antigravity.google/docs/sandbox?tab=cli (MCP and hooks tails summarized) |
| Feature overview | Official documentation | https://antigravity.google/docs/features/ |
| Two CLI cheat sheets | Third-party articles | https://computingforgeeks.com/antigravity-cli-cheat-sheet/ (tested on 1.2.4), https://www.scriptbyai.com/antigravity-cli-cheatsheet/ |
| Issue #548, print mode and `permissions.allow` | Community issue | https://github.com/google-antigravity/antigravity-cli/issues/548 |
| `agy-headless` helper gist | Community code (Windows) | https://gist.github.com/allahsan/a9a9e9c8a49aecede67ce974e64ef3cf |
| Forum: external orchestration with account-based usage | Community forum | https://discuss.ai.google.dev/t/is-external-orchestration-of-antigravity-cli-headless-mode-supported-with-account-based-usage/183051 |

Read on 2026-11-19. Versions cited across sources range from 1.1.8 to 1.5.7, and the official pages carry no dates. The binary updates itself in the background (third-party report), so the executor must record `agy --version` with every session.

## Key findings

### Invocation and I/O

| # | Finding | Confidence |
|---|---|---|
| A1 | `agy -p "<prompt>"` (aliases `--print`, `--prompt`) runs headless; the response goes to stdout, diagnostics and permission notices to stderr. Headless uses cached credentials from an interactive login, and an unauthenticated non-TTY run exits with "authentication required" instead of hanging. | confirmed (official) |
| A2 | No plain-text stdin prompt is documented for `-p`. Instead, `--input-format stream-json --output-format stream-json` reads one JSON object per line (`{"event":"user","message":{"content":"..."}}`), keeps one conversation across turns, ends each turn with a `result` event, and exits 0 after the current turn when stdin closes. A `-p` prompt is dropped in that mode. | confirmed (official) |
| A3 | An open, idle stdin pipe blocked startup on Windows; a helper runs `-p` with stdin closed. | supported (one community source) |
| A4 | `--output-format json` prints one envelope: `conversation_id`, `status`, `response`, `error` (on failure), `duration_seconds`, `num_turns`, `structured_output` and `json_schema` (with `--json-schema`), and `usage` with `input_tokens`, `output_tokens`, `thinking_tokens`, `cache_read_tokens`, `total_tokens`. **No cost field.** Status values: SUCCESS, ERROR, CANCELED, INTERRUPTED, INVALID, WAITING, RUNNING. | confirmed (official; status list from the summarized tail) |
| A5 | `stream-json` emits `init` (`cwd`, `tools`, `permission_mode`, `model`), `step_update` (`step_index`, `state`, `step_type`, `tool_name`, `text_delta`, `usage`, `tool_info` with name, parameters, output and error, `subagent_info`) and `result` (same shape as the json envelope). Observed step types: user_input, agent_response, tool, checkpoint. The schema's stability is not documented. | supported (official, schema not versioned) |
| A6 | Exit 0 on success, a clean stream close, and also when a tool approval was soft-denied. Non-zero when no response was produced; 1 for an unknown `--model` or bad stream input; 2 for control messages on the stream; 3 reported for a timed-out turn or model error. | supported (official for 0/1/2; 3 from a third party) |
| A7 | Piped stdout was reported silent on Windows (and quota errors silent), with the answer only in the local conversation store. | uncertain (community, platform-specific, conflicts with official docs) |

### Limits, cost and models

| # | Finding | Confidence |
|---|---|---|
| A8 | `--print-timeout <dur>` bounds a headless turn; sources disagree on its default (0 s unlimited, or 5 m). A timed-out turn returns partial output. | uncertain (sources conflict) |
| A9 | No max-turns flag and no cost-cap flag are documented. | supported (absence in official reference) |
| A10 | `--model <slug>` selects a model; `agy models` lists the slugs available to the signed-in account (for example `gemini-4-neon-high`). An unknown slug fails rather than falling back. `--effort` takes a level whose range depends on the model. | confirmed (official) |
| A11 | Tokens are reported, cost is not; billing is by account entitlement or by API key (`modelProvider: "gemini"` with `GEMINI_API_KEY`). | confirmed (official) |

### Permissions, modes and isolation

| # | Finding | Confidence |
|---|---|---|
| A12 | `--mode` takes `accept-edits`, `auto`, `plan`; the default mode is set by `agentMode` in settings. **Plan mode prepends a planning instruction; the docs do not say it blocks edits or commands.** It is not an enforcement boundary. | confirmed (official, by omission) |
| A13 | `toolPermission` takes `request-review` (default), `proceed-in-sandbox`, `strict` (prompt before every action, reads included) and `always-proceed` (`--dangerously-skip-permissions`). In headless mode an approval that cannot be obtained is **soft-denied**: the run continues and exits 0, and stderr names the tool. | supported (official; headless detail from the summarized tail) |
| A14 | Rules live in `permissions.allow`, `ask`, `deny` as `action(target)`: `read_file`, `write_file` (implies read), `read_url`, `execute_url`, `command` (word prefix, or `regex:` anchored per token), `mcp(server/tool)`. Precedence is deny over ask over allow. Shell constructs (substitution, redirection, brace expansion) disable prefix matching and fall back to ask. | confirmed (official) |
| A15 | Rules are read from `~/.gemini/antigravity-cli/settings.json`, combined with undocumented project and shared scopes. **No flag or environment variable passes a settings file or permission rules per invocation, and none relocates the config home.** | confirmed (official, by omission) |
| A16 | In print mode on 1.1.x, `permissions.allow` entries for commands were reported as not consulted, narrow rules failing and only `command(*)` working; a PreToolUse hook's `allow` was ignored but its `deny` honoured. Later versions changed some of this. | uncertain (community, version-specific) |
| A17 | Hooks are read from `~/.gemini/config/hooks.json`, `<workspace>/.agents/hooks.json` and plugin folders. Events: `SessionStart`, `PreToolUse`, `PostToolUse`, `PreInvocation`, `PostInvocation`, `Stop`. A PreToolUse hook receives `toolCall` (`name`, `args`) on stdin and answers a `decision`: `allow`, `auto_approve`, `deny` ("hard blocks execution immediately"), `ask`, `force_ask`, `deny_unless_prior_grant`, plus optional `permissionOverrides` that can widen access. Whether hooks run in headless mode is not stated. | supported (official schema; headless behaviour uncertain) |
| A18 | Tool names seen by hooks: `run_command`, `write_to_file`, `replace_file_content`, `multi_replace_file_content`, `view_file`, `list_dir`, `find_by_name`, `grep_search`, `search_web`, `read_url_content`, `invoke_subagent`, `define_subagent`, `send_message`, `ask_question` and others. The mapping from these names to permission actions is not documented. | supported (official list) |
| A19 | MCP servers come from `~/.gemini/config/mcp_config.json`, `<workspace>/.agents/mcp_config.json` and plugin folders; each entry may set `disabled`, `enabledTools` (allow-list) and `disabledTools`. **No flag limits a session to chosen servers.** | confirmed (official, by omission) |
| A20 | A terminal sandbox (`--sandbox`) confines shell commands (project folders read-write, network off) on Linux, macOS and recent Windows, and silently does nothing where the host blocks it (for example unprivileged namespaces in containers). It covers terminal commands, not the file tools. | confirmed (official) |
| A21 | Rules, skills and instructions load from `GEMINI.md`, `AGENTS.md`, `.agents/rules/`, `.agents/skills/<name>/SKILL.md` and global equivalents; custom agents from `.agents/agents/`; plugins from `~/.gemini/antigravity-cli/plugins/`. `--disable-slash-commands` turns off skill expansion in print mode. | supported (official + third party) |

### Sessions and lifetime

| # | Finding | Confidence |
|---|---|---|
| A22 | Headless runs are stateless by default; `--conversation <id>` or `-c` resumes. One community report says print mode may continue the workspace's last conversation. | supported (official), conflicting report uncertain |
| A23 | Conversations persist under `~/.gemini/antigravity-cli/` (per-conversation SQLite files and transcript logs, undocumented). | uncertain (reverse-engineered) |
| A24 | `--add-dir` adds a workspace directory; no `--cwd` flag. One report says the launch directory was not adopted as the workspace without `--add-dir`, so `AGENTS.md` and `.agents/hooks.json` were not loaded. | supported (flag official; behaviour one report) |
| A25 | Whether launching `agy` as a child process of another program is permitted under account-based (consumer) entitlements is not answered by Google in the sources read. | uncertain |

## Conclusions

1. `agy` can serve as a **step executor**: prompt off argv through `--input-format stream-json`, a parsable event stream with tool names and token usage, model slugs, effort, a session id, and an exit status plus a `status` field.
2. It reports **actions** (tool calls in `step_update`), so the independence guard is available, but tool names differ from Claude Code's, so the engine's view catalog must key tools per executor.
3. It reports **tokens, not cost**. Every session's cost is `unmeasured` as reported and estimated from the engine's price table ([ADR-0012](../adr/0012-cost-when-executor-reports-tokens-only.adr.md)).
4. It cannot restrict tools **per invocation by flag**. Restriction requires engine-generated configuration: permission rules, `enabledTools` and a PreToolUse gatekeeper hook. Because the documented config home is fixed under `~/.gemini`, the only per-session lever is an isolated home directory for the child process, which is inferred, not documented ([ADR-0011](../adr/0011-isolated-config-home-for-antigravity.adr.md)). Until a probe confirms it, the Antigravity executor declares `restricts_judge_tools = false`, and judges for steps on Antigravity run on an executor that can restrict tools ([ADR-0013](../adr/0013-cross-executor-judging.adr.md)).
5. There is no turn cap and no cost cap; the engine's wall-clock timeout and idle watchdog are the only bounds, and both are engine-owned.
6. A soft-denied tool exits 0, so success must be read from `status` and from the denial notices, not from the exit code.

## Open questions

| Question | Owner | How to settle |
|---|---|---|
| Does `agy` honour a `HOME` (or `USERPROFILE`) pointed at a private folder for settings, hooks and MCP, and can it still authenticate there (API key, or copied credentials)? | Executor implementer | Probe P-AG-1 in the [Antigravity executor spec](../specs/executor-antigravity.spec.md). |
| Do PreToolUse hooks run in headless mode on the pinned version, and is `deny` enforced for every tool including subagent tools? | Executor implementer | Probe P-AG-2. |
| Is `--print-timeout` unlimited by default on the pinned version, and what exit and `status` does a timed-out turn give? | Executor implementer | Probe P-AG-4. |
| Is a fresh `-p` session guaranteed, or can it continue a workspace conversation? | Executor implementer | Probe P-AG-5. |
| Is automated child-process use permitted for the account type the operator uses? | Owner | Read the Antigravity terms for the account type; record the answer in [ADR-0007](../adr/0007-two-first-class-executors.adr.md). |
