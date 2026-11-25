# Claude Code executor

## Purpose

The `claude` executor runs each step attempt and each judge run as one headless Claude Code session: `claude -p` with the prompt on stdin and a `stream-json` event stream on stdout. It implements the executor interface ([EXI](executor-interface.spec.md)) and maps the engine's neutral contracts ([CON](contracts.spec.md)) to Claude Code's flags; facts about the CLI come from [research `claude-code-cli-headless`](../research/claude-code-cli-headless.rsrch.md). It is the default judge executor, because it can hold a session to an exact read-only tool set by absence ([ADR `judge-isolation-per-executor`](../adr/judge-isolation-per-executor.adr.md)). The runner, the judge ([JDG](judge-and-verdict.spec.md)), the guard ([GRD](independence-guard.spec.md)), packages ([PKG](workflow-package.spec.md)) and worktrees ([WTR](worktree-mode.spec.md)) depend on it; design notes and the probe history are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### ECC-B1 Declared shell

WHEN a step that declares `shell` with command prefixes launches in the engine's own worktree THE executor SHALL put one `Bash(<prefix> *)` rule per prefix in `--allowedTools`, use permission mode `acceptEdits`, and name no absolute path in any rule.

- GIVEN `shell` with prefixes `pytest` and `git status` WHEN the step launches in the engine's worktree THEN `--allowedTools` holds `Bash(pytest *)` and `Bash(git status *)` and the mode is `acceptEdits`

### ECC-B2 Tool names and rules stay apart

WHEN argv is built for any launch THE executor SHALL put tool names only in `--tools` or `--disallowedTools` and permission rules only in `--allowedTools`.

- GIVEN any step or judge launch WHEN its argv is read THEN no rule appears in `--tools` and no bare tool list in `--allowedTools`

### ECC-B3 Judge view

WHEN a judge launches with MCP views THE executor SHALL set `--tools` to the mapped built-in views, list in a private MCP config one filtering proxy per MCP view server offering only the viewed tools, and use mode `dontAsk`.

- GIVEN a view set `read`, `search`, `list` and `mcp:tracker/get_issue` WHEN the judge launches THEN `--tools` is `Read,Grep,Glob`, the private config lists one proxy in front of `tracker` offering only `get_issue`, and the mode is `dontAsk`
- GIVEN views `mcp:tracker/get_issue` and `mcp:tracker/get_comments` on `tracker` and `mcp:wiki/get_page` on `wiki` WHEN the judge launches THEN the private config lists two proxies, one in front of `tracker` offering the two viewed tools and one in front of `wiki` offering `get_page`
- GIVEN a stand-in `tracker` server that offers `get_issue` and `update_issue` and a view of `mcp:tracker/get_issue` only WHEN the proxy is asked to list its tools THEN it offers `get_issue` and not `update_issue`

### ECC-B4 Reported cost

WHEN a `result` event carries `total_cost_usd` THE executor SHALL record it as `reported_cost_usd` and store the engine's own estimate beside it, never summed.

- GIVEN `total_cost_usd = 1.73` WHEN usage is recorded THEN `reported_cost_usd` is 1.73 and the estimate is kept apart

### ECC-B5 Exact timeout text

WHEN a non-success `result.result` is classified THE executor SHALL give `request_timed_out` (infra) only when it equals `Request timed out` exactly, any other text being `error_kind = model`.

- GIVEN `Request timed out` WHEN classified THEN it is `request_timed_out`
- GIVEN `Request timed out.` or `The request timed out` WHEN classified THEN it is `error_kind = model`

### ECC-B6 Declared capabilities

WHEN the executor declares its capabilities THE executor SHALL declare `binds_aliases` (`small`, `medium`, `large`, `inherit` and every `claude:<name>` of the binding table, research `claude-code-cli-headless` F10, F11); `prompt_off_argv`, `streams_events`, `reports_actions`, `reports_tokens` and `reports_cost` true (F2 to F4, F8, F18); `enforces_step_tools`, `step_allow_rules`, `judge_mcp` and `fresh_session` true (F12, F13, F15, F20); `restricts_judge_tools` true (F12, F14, F15, the plugin-tool gap closed by `--bare` once P-CC-1 passes, else by the guard); `isolates_user_config` true only when P-CC-1 passes; and `session_options` `effort`, `cost_cap_usd`, `fallback_alias` and `turn_cap` (F9, F10).

- GIVEN P-CC-1 not confirmed WHEN `executors --json` runs THEN `isolates_user_config` is false

### ECC-B7 Tool map

WHEN a capability is mapped THE executor SHALL map `read` to `Read` with the rule `Read(./**)` on a step, plus a read rule for the workflow plugin's folder when the step is given one; `search` to `Grep` and `list` to `Glob` with no rule on a step, the CLI admitting them inside the workspace only; `web_fetch` to `WebFetch` and `web_search` to `WebSearch` with rules of the same name; `edit` and `write` to `Edit` and `Write` with `Edit(./**)` and `Write(./**)` in the engine's own worktree only; `shell` to `Bash` as ECC-B1; `subagent` to `Agent` (reported as `Task` by older releases); `mcp:<s>/<t>` to `mcp__<s>__<t>`; and `skill:<p>:<n>` to `Skill` with the rule `Skill(<p>:<n>)` once P-CC-8 confirms it, else `Skill` with the called name checked in the tool record ([ADR `skills-are-a-declared-tool-capability`](../adr/skills-are-a-declared-tool-capability.adr.md)).

- GIVEN a step declaring `edit` that runs in place WHEN it launches THEN no `Edit(./**)` rule is sent
- GIVEN a step declaring `read` and `search` WHEN it reads or searches a file outside its workspace THEN the call is refused
- GIVEN a step declaring `read` that is given a workflow plugin WHEN a skill of that plugin reads its own reference file THEN the read succeeds

### ECC-B8 Step launch

WHEN a step launches THE executor SHALL assemble argv only from constants, binding-table values and engine-checked numbers, never from typed text: `claude -p --output-format stream-json --verbose`; `--permission-mode` `acceptEdits` in the engine's worktree, else `default`; `--permission-prompts none` when the CLI lists it; `--model <bound model>` unless the alias is `inherit`; `--allowedTools` with the ECC-B7 rules when the step declares tools; `--tools` with the built-ins mapped from the step's declared tools on every launch, whether or not the operator's enforcement setting is on, the shell tool added when the step is granted the check preview command ([CHK-B17](check-contract-and-command-runs.spec.md)); always `--disallowedTools EnterWorktree,ExitWorktree`, the run's worktree being the engine's ([WTR-B25](worktree-mode.spec.md)); the MCP flags of ECC-B18; `--setting-sources project` and the plugin folders of ECC-B16; and `--effort`, `--max-budget-usd`, `--fallback-model` or `--max-turns` when that option is set.

- GIVEN a step with `effort: high` and alias `inherit` WHEN it launches THEN argv holds `--effort high` and no `--model`
- GIVEN a step declaring `read` and `shell` with prefix `pytest` and the enforcement setting off WHEN it launches THEN `--tools` is `Read,Bash`
- GIVEN a step declaring only `read` and granted the check preview command WHEN it launches THEN `--tools` is `Read,Bash` and the preview command is the only `Bash` rule in `--allowedTools`
- GIVEN a step declaring no tool and the enforcement setting off WHEN it launches THEN argv holds `--tools` with an empty value

### ECC-B9 Step environment and prompt

WHEN a step session starts THE executor SHALL overlay `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` unless the host already sets it and `CLAUDE_CODE_SUBAGENT_MODEL=<bound model>` unless the step names a subagent alias, write the prompt as UTF-8 on stdin, then close stdin, and never use a resumed session for a retry.

- GIVEN any step launch WHEN its argv is scanned THEN the prompt is not on it

### ECC-B10 Judge launch

WHEN a judge launches THE executor SHALL send `claude -p --output-format stream-json --verbose`; `--bare` when P-CC-1 passed, else `--setting-sources ""`; `--model <bound judge model>`; `--tools` with `Read,Grep,Glob` plus the built-in views; `--disallowedTools "mcp__*"` when there is no MCP view, else the private MCP config of ECC-B3; the MCP flags of ECC-B18; `--permission-mode dontAsk`; and `--allowedTools` with the view rules plus read-only command rules when opted in; lay judge-only credentials from the operator's credentials profile over the environment; and never send a judge `--fallback-model`, `--resume`, `--continue`, a write tool or a step's allow rules.

- GIVEN any judge launch WHEN its argv is read THEN it holds no write tool, no step rule, no `--fallback-model` and no `--resume`
- GIVEN a judge with no MCP view WHEN it launches THEN argv holds `--disallowedTools "mcp__*"`
- GIVEN a judge with an MCP view WHEN it launches THEN argv holds no `--disallowedTools "mcp__*"`

### ECC-B11 Stream mapping

WHEN stream lines arrive THE executor SHALL map `system`/`init` to `session_started` (session id, model, tools, and `mcp_server_errors` and `plugin_errors` as counts); an `assistant` `tool_use` block to `tool_started` (`name`, `subagent` when `parent_tool_use_id` is set); a `user` `tool_result` block to `tool_finished` (`ok` when not `is_error`); a `stream_event` text delta to `model_delta` (count only); an `assistant` text block to `text` (last line, scrubbed); `system`/`api_retry` to `retrying` (`category` the event's `error`); `system`/`permission_denied` to `denied`; and `result` to `result` (`total_cost_usd` as `reported_cost_usd`, `usage`, `modelUsage` as `by_model`, `num_turns` as `turns`, `session_id`), as normalized events ([SSN-B7](session-contract.spec.md)); and skip and count an unknown event type, never failing the session.

- GIVEN a recorded step stream from 2.1.330 WHEN it is mapped THEN every event normalizes and an unknown type is counted, not fatal

### ECC-B12 Failure classification

WHEN a session ends THE executor SHALL classify from structured facts only, besides the one exact match of ECC-B5: a spawn that raised with a resource errno as `spawn_failed`; a stdin write that raised broken pipe as `broken_pipe`; a process that ended with no stdout line as `no_output`; a stream that ended without `result` as `no_result`; a last `retrying` category `rate_limit` or `overloaded` with no `result` as `throttled`; `connection_error` or `network_error` with no `result` as `connection`; a `SIGKILL` the launcher did not send with no `result` as `out_of_memory`; `result.subtype` `error_max_turns` as `error_kind = turn_cap`; a session ended by `--max-budget-usd` (`error_max_budget_usd` until P-CC-3 sets the shape) as `cap_reached`; a `retrying` category `authentication_failed` as `auth`; and any other `result.is_error` as `model`.

- GIVEN a stream whose last `api_retry` is `rate_limit` and no `result` WHEN classified THEN it is `throttled`

### ECC-B17 A rejected rate limit report is a spent usage allowance

WHEN a `claude` session ends not ok and the last `rate_limit_event` of its stream has `rate_limit_info.status` `rejected` THE executor SHALL return `usage_limit` true and `usage_limit_resets_at` ([SSN-B11](session-contract.spec.md)) as the event's `resetsAt` read as epoch seconds, null when the event has no `resetsAt` or its `errorCode` is `credits_required`, leaving `infra_cause` and `error_kind` as ECC-B12 gives them.

- GIVEN a stream that ends with an error `result` after a `rate_limit_event` of status `rejected` and `resetsAt` 1795317000 WHEN classified THEN `usage_limit` is true and `usage_limit_resets_at` is 2026-11-22T03:10:00Z
- GIVEN a `rejected` event with `errorCode` `credits_required` WHEN classified THEN `usage_limit` is true and `usage_limit_resets_at` is null
- GIVEN a stream that ends with an error `result` and whose `rate_limit_event`s all have status `allowed` or `allowed_warning` WHEN classified THEN `usage_limit` is false and `infra_cause` and `error_kind` are what ECC-B12 gives

### ECC-B13 Probe and preflight

WHEN the executor is probed THE executor SHALL fail the probe with exit 2 at preflight when `claude` is not on the engine's resolved `PATH`, or `claude auth status` reports signed out with no gateway variables set; read `--permission-prompts` and other flags from `--help`, sending them only when listed; record a judge view server that `system/init` reports in `mcp_server_errors` as deferred, its criterion rendered out of reach; and rest no control on a live probe until its result is recorded `confirmed` with date and pinned CLI version: P-CC-1 (`--bare` removes user-level plugins and hooks while gateway credentials work, `@builtin` plugins staying listed), P-CC-2 (`--tools Read,Grep,Glob` with `--disallowedTools "mcp__*"` leaves exactly those tools), P-CC-3 (the stream shape at `--max-budget-usd`), P-CC-4 (precedence of `CLAUDE_CODE_SUBAGENT_MODEL` against an agent call's own model), P-CC-5 (a prompt on stdin with no positional prompt is accepted), P-CC-6 (`dontAsk` refuses an unlisted call and emits `permission_denied`), P-CC-7 (whether a session keeps a native transcript under the isolation flags, and where, [EVT-B20](run-events.spec.md)), P-CC-8 (a `Skill(<plugin>:<name>)` rule admits only that skill and the record names it), P-CC-9 (`--plugin-dir` loads a workflow plugin's skills and agents with a step's isolation flags) and P-CC-13 (ECC-B24).

- GIVEN a signed-out `claude` and no gateway variables WHEN preflight runs THEN it exits 2

### ECC-B14 Step reach inside a host session

WHEN a step session, a retry of it or a judge session launches THE executor SHALL leave `CLAUDECODE` and every name beginning `CLAUDE_` out of that session's environment, the `CLAUDE_CODE_*` names and the session and additional-directory names a host Claude Code session sets for its children among them, keeping `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR` with the value ECC-B9 gives it, the `CLAUDE_CODE_SUBAGENT_MODEL` ECC-B9 sets on a step, the credentials ECC-B10 lays on a judge, the provider switches `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX` and `CLAUDE_CODE_USE_FOUNDRY`, the operator's sign-in `CLAUDE_CODE_OAUTH_TOKEN` and config folder `CLAUDE_CONFIG_DIR`, `ANTHROPIC_*` and the proxy and certificate variables; send `--tools` with the mapped built-ins on every step launch, so a host's tools are never offered; and send no `--add-dir` on any step or judge launch, a session reaching only its workspace and the engine's scratch folder ([WSP-B5](workspace-and-concurrency.spec.md)); P-CC-10 (a step launched inside a host lists only its `--tools` and a read outside the workspace is refused) and P-CC-11 (`--bare` drops user-scope plugins on the pinned version) confirming it.

- GIVEN a step launched from inside a host session WHEN its `system/init` is read THEN it lists only the tools of its `--tools`
- GIVEN a host environment holding `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_SESSION_ID` and `CLAUDE_CODE_CHILD_SESSION` WHEN a step, a retry of it and a judge launch THEN none of the four names is in any of the three environments
- GIVEN a host environment holding `ANTHROPIC_API_KEY`, `CLAUDE_CODE_USE_BEDROCK`, `HTTPS_PROXY` and `SSL_CERT_FILE` WHEN a step and a judge launch THEN all four reach both sessions
- GIVEN a pipeline that signs `claude` in with `CLAUDE_CODE_OAUTH_TOKEN` and `CLAUDE_CONFIG_DIR` WHEN a step and a judge launch THEN both names reach both sessions
- GIVEN a host holding `CLAUDE_CODE_SUBAGENT_MODEL=haiku` and not `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR` WHEN a step bound to model `sonnet` launches THEN its environment holds `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` and `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1`
- GIVEN a judge credentials profile holding `CLAUDE_CODE_OAUTH_TOKEN` and a host holding `CLAUDE_CODE_SESSION_ID` WHEN the judge launches THEN its environment holds the profile's token and no `CLAUDE_CODE_SESSION_ID`
- GIVEN a retry of a step declaring `read` WHEN it launches THEN `--tools` is `Read`
- GIVEN any step or judge launch WHEN its argv is read THEN it holds no `--add-dir`

### ECC-B16 Steps are isolated from user-scope configuration

WHEN a step session or a retry of it launches THE executor SHALL load no user-scope setting, plugin, skill or hook of the machine it runs on, only the repository's project settings, and SHALL pass by path the workflow plugin ([PKG-B23](workflow-package.spec.md)) and each plugin that plugin's manifest names under `dependencies` that is found beside it, as a sibling folder of that name or as the newest version folder of that name in Claude Code's plugin cache; a dependency found nowhere is left out.

- GIVEN a machine with a plugin installed at user scope WHEN a step launches THEN its `system/init` lists neither that plugin nor its skills
- GIVEN a workflow plugin whose manifest depends on `tempergraph` and a `tempergraph` plugin folder beside it WHEN a step launches THEN both plugins are passed by path and listed in its `system/init`
- GIVEN a workflow plugin with a dependency found in no folder beside it WHEN a step launches THEN only the workflow plugin is passed by path and the launch goes ahead

### ECC-B15 A judge view server with no working proxy is out of reach

WHEN a judge view names an MCP server that is not in the operator's own MCP configuration, that the operator's configuration defines by a URL, or whose filtering proxy fails to start THE executor SHALL report that server's views as deferred for the attempt, so that the engine renders the artifact out of reach ([GRD-B5](independence-guard.spec.md)).

- GIVEN a judge view of `mcp:tracker/get_issue` and a `tracker` server that exits at start WHEN the judge launches THEN the view is recorded as deferred for that attempt, no tool of `tracker` is in the judge's session and the judge prompt names the artifact out of reach
- GIVEN a judge view of `mcp:wiki/get_page` and no `wiki` server in the operator's own MCP configuration WHEN the judge launches THEN the view is deferred for that attempt
- GIVEN a judge view of a server that the operator's configuration defines by a URL WHEN the judge launches THEN the view is deferred for that attempt

### ECC-B18 A session is offered only the MCP servers it declares

WHEN a step session, a retry of it or a judge session launches THE executor SHALL offer it no MCP server of the account, the user or the repository other than those the step's declared MCP tools or the judge's MCP views name, passing `--strict-mcp-config` on every such launch and `--mcp-config` only when the step declares an MCP tool or the judge has an MCP view.

- GIVEN a step declaring `read` and no MCP tool and the enforcement setting off WHEN it launches THEN argv holds `--strict-mcp-config` and no `--mcp-config`
- GIVEN a step declaring `mcp:tracker/get_issue`, a `tracker` server in the operator's own MCP configuration and the enforcement setting off WHEN it launches or is retried THEN each argv holds `--strict-mcp-config` and `--mcp-config`
- GIVEN a judge with no MCP view WHEN it launches THEN argv holds `--strict-mcp-config` and no `--mcp-config`

### ECC-B19 A step is offered the servers of its declared MCP tools

WHEN a step declares an MCP tool THE executor SHALL pass `--mcp-config` naming a private config ([WSP-B5](workspace-and-concurrency.spec.md), [SEC-B12](security.spec.md)) that lists every server the declared MCP tools name, as the operator's own MCP configuration defines it, and no other server.

- GIVEN a step declaring `mcp:tracker/get_issue` and a `tracker` server in the operator's own MCP configuration WHEN it launches THEN the private config lists `tracker` as that configuration defines it and no other server
- GIVEN a step declaring `mcp:tracker/get_issue` and `mcp:wiki/get_page` and both servers in the operator's own MCP configuration WHEN it launches THEN the private config lists `tracker` and `wiki`, each as that configuration defines it
- GIVEN a `mailer` server in the operator's own MCP configuration and a step declaring only `mcp:tracker/get_issue` WHEN it launches THEN the private config does not list `mailer`

### ECC-B20 The account's MCP servers are switched off

WHEN a step session, a retry of it or a judge session starts THE executor SHALL set `ENABLE_CLAUDEAI_MCP_SERVERS` to `false` in its environment, whatever value the host's environment or a judge's credentials profile holds.

- GIVEN a host environment without `ENABLE_CLAUDEAI_MCP_SERVERS` WHEN a step launches THEN its environment holds `ENABLE_CLAUDEAI_MCP_SERVERS=false`
- GIVEN a host environment holding `ENABLE_CLAUDEAI_MCP_SERVERS=true` WHEN a step, a retry of it and a judge launch THEN all three environments hold `ENABLE_CLAUDEAI_MCP_SERVERS=false`
- GIVEN a judge credentials profile holding `ENABLE_CLAUDEAI_MCP_SERVERS=true` WHEN the judge launches THEN its environment holds `ENABLE_CLAUDEAI_MCP_SERVERS=false`

### ECC-B21 A CLI without the MCP isolation flag is refused

WHEN the executor is probed and `claude --help` does not list `--strict-mcp-config` THE executor SHALL fail the probe at preflight with exit 2, reason `probe_failed` and a message that names `--strict-mcp-config`.

- GIVEN a `claude` whose `--help` does not list `--strict-mcp-config` WHEN the run is preflighted THEN it exits 2 with a message naming `--strict-mcp-config` and no session launches
- GIVEN a `claude` whose `--help` lists `--strict-mcp-config` WHEN the run is preflighted THEN the probe does not fail on that flag

### ECC-B22 A step's declared MCP servers must be defined before the run starts

WHEN a run is preflighted and a step declares an MCP tool of a server the operator's own MCP configuration does not define (a configuration that cannot be read defines none) THE executor SHALL refuse the run with exit 2 before any session starts, naming the step and each such server.

- GIVEN a step declaring `mcp:tracker/get_issue` and `mcp:wiki/get_page` and only a `tracker` server in the operator's own MCP configuration WHEN the run is preflighted THEN it exits 2 naming the step and `wiki`, not `tracker`, and no session starts
- GIVEN a step declaring `mcp:wiki/get_page` and an operator MCP configuration file that cannot be read WHEN the run is preflighted THEN it exits 2 naming the step and `wiki`

### ECC-B23 A step is never launched without a server it declares

WHEN a step session or a retry of it would launch without a server its declared MCP tools name, because the operator's own MCP configuration does not define the server or no scratch folder ([WSP-B5](workspace-and-concurrency.spec.md)) can hold the private config, THE executor SHALL start no session and fail the attempt, the reason naming each such server.

- GIVEN a step declaring `mcp:tracker/get_issue` and an operator MCP configuration without a `tracker` server at launch WHEN it launches THEN no session starts and the attempt fails with a reason naming `tracker`
- GIVEN a step declaring `mcp:tracker/get_issue`, a `tracker` server in the operator's own MCP configuration and no scratch folder WHEN it launches THEN no session starts and the attempt fails with a reason naming `tracker`
- GIVEN the same step and server with a scratch folder WHEN it launches THEN a session starts with a private config that lists `tracker`

### ECC-B24 The MCP isolation probe reads a turn after the servers connect

WHEN P-CC-13 is run THE probe SHALL pass only when, at the second turn of a session launched as ECC-B18 and ECC-B20 say, the tools the session is offered or the size of its context show that it is offered the tools of each MCP server it declares and no tool of any other MCP server.

- GIVEN an account that has MCP servers and a session launched as ECC-B18 and ECC-B20 say WHEN the probe reads its second turn THEN it finds no tool of an undeclared server and passes
- GIVEN the same account and a session launched with neither `--strict-mcp-config` nor `ENABLE_CLAUDEAI_MCP_SERVERS=false` WHEN the probe reads its second turn THEN it finds tools of the account's MCP servers and fails

## Acceptance criteria

- ECC-AC1 (ECC-B1, ECC-B2, ECC-B7, ECC-B8, ECC-B9): Argv for every launch shape is built from constants and the binding table only (source-scan and planted-canary tests)
- ECC-AC2 (ECC-B4, ECC-B11): Each stream mapping is covered by a recorded-stream fixture that yields the normalized event
- ECC-AC3 (ECC-B5, ECC-B12): Each failure classification is covered by a fixture and classified without reading prose beyond the one exact match
- ECC-AC4 (ECC-B3, ECC-B10): A judge launch never contains a write tool, a step allow rule, `--fallback-model` or `--resume`
- ECC-AC5 (ECC-B6, ECC-B13, ECC-B14): The probe results are recorded for the pinned CLI version before the executor is marked live-proven
- ECC-AC6 (ECC-B7, ECC-B8, ECC-B14): Argv and environment scans of a step, a retry and a judge launch from a planted host environment find `--tools` on the step and the retry, `--add-dir` on none of the three, no planted `CLAUDECODE` or `CLAUDE_*` name in any of the three environments except the ones ECC-B14 keeps, and the planted `ANTHROPIC_*`, proxy and certificate names present in each; the step's read rule is `Read(./**)` with no bare `Read`, `Grep` or `Glob` rule
- ECC-AC7 (ECC-B3, ECC-B10): Against stand-in MCP servers, a judge launch whose view set holds `mcp:<server>/<tool>` views has `--tools` of the mapped built-in views only, `--strict-mcp-config` with a private `--mcp-config` that lists exactly one filtering proxy per viewed server, mode `dontAsk` and no `--disallowedTools "mcp__*"`, and each proxy offers only the viewed tools of its server when asked to list its tools
- ECC-AC8 (ECC-B15): Against stand-in MCP servers, a judge view of a server that exits at start, of a server missing from the operator's MCP configuration and of a server that configuration defines by a URL is each recorded as deferred for the attempt, no tool of that server is in the judge's session and the judge prompt names the artifact out of reach (a scripted judge that follows the prompt grades its criterion UNVERIFIABLE, never MET)
- ECC-AC9 (ECC-B6): `executors --json` declares `judge_mcp` true for `claude`
- ECC-AC10 (ECC-B16): Argv of a step and a retry launch holds `--setting-sources project` and one `--plugin-dir` for the workflow plugin and for each dependency found beside it, none for a dependency found nowhere; and live, with a plugin installed at user scope, a step's `system/init` lists the workflow plugin and its dependency and not the user-scope plugin
- ECC-AC11 (ECC-B17): Recorded-stream fixtures give `usage_limit` true with the instant read as epoch seconds for a `rejected` event, true with a null instant for `credits_required` and false for `allowed` events, each with `infra_cause` and `error_kind` as ECC-B12 gives them
- ECC-AC12 (ECC-B8, ECC-B18): Argv of a step and of a retry of it holds `--strict-mcp-config` with the enforcement setting on and off, and holds `--mcp-config` when the step declares an MCP tool and not when it declares none
- ECC-AC13 (ECC-B10, ECC-B18): Argv of a judge launch with no MCP view holds `--strict-mcp-config` and `--disallowedTools "mcp__*"` and no `--mcp-config`
- ECC-AC14 (ECC-B19): Against a stand-in operator MCP configuration, the config that a step's `--mcp-config` names lists exactly the servers the step's declared MCP tools name, each as that configuration defines it, and is gone when the session ends
- ECC-AC15 (ECC-B20): The environments of a step, a retry of it and a judge launch from a planted host environment each hold `ENABLE_CLAUDEAI_MCP_SERVERS=false` when the host environment holds `true`, and the judge's does when its credentials profile holds `true`
- ECC-AC16 (ECC-B21): Against a stand-in `claude` whose `--help` lists no `--strict-mcp-config`, preflight exits 2 with reason `probe_failed` and a message naming the flag, and no session launches; against one that lists it, the probe passes
- ECC-AC17 (ECC-B22): Against a stand-in operator MCP configuration, a step declaring a server that configuration does not define, or a configuration file that cannot be read, exits 2 at preflight naming the step and each such server with no session started; the same step with every declared server defined passes
- ECC-AC18 (ECC-B23): Against stand-ins of the operator's MCP configuration and of `claude`, a step launch whose declared server is not defined, or that has no scratch folder, starts no session and fails with a reason naming the server; with the server defined and a scratch folder it starts one
- ECC-AC19 (ECC-B24): The live probe for P-CC-13 reads the second turn of a step session and of a judge session launched as ECC-B18 and ECC-B20 say and passes, and fails when the launch omits `--strict-mcp-config` and `ENABLE_CLAUDEAI_MCP_SERVERS=false` in an account that has MCP servers

## Open questions

- Use `--input-format stream-json` for the prompt instead of plain stdin, to share framing with the Antigravity executor? Until answered: plain UTF-8 on stdin, then stdin closes; decided after P-CC-5. Owner: executor implementer.
- Not built yet: probes P-CC-1 to P-CC-12 have not been confirmed on the owner's machine. Owner: engine owner.
- Does a rejected `rate_limit_event` carry `resetsAt` in epoch seconds, as the `allowed` events of the recorded 2.1.330 streams do? Until answered: read as seconds, from the Agent SDK reference and those recordings, since no recorded stream holds a rejection ([the research note](../research/what-a-claude-session-reports-when-its-usage-allowance-is-spent.rsrch.md)); a value that is really milliseconds then reads as a reset far ahead, which the loop does not wait for. Owner: engine owner.
- Not built yet: the filtering proxy of ECC-B3 has run live on 2.1.330 only against the suite's stand-in server (live row L-33: only the viewed tool listed, a proxied call ran under `dontAsk` with no prompt, a server that cannot start or is missing deferred before the launch); no live run against a real tracker or wiki server and no whole workflow run grading the deferred criterion has been made. Owner: engine owner.
