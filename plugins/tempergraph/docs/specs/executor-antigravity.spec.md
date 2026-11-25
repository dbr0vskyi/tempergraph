# Antigravity executor

## Purpose

The `antigravity` executor runs each step attempt as one headless Antigravity CLI session: `agy` in streaming mode, the prompt sent as one `stream-json` user event on standard input and the event stream read from standard output, under the [executor interface](executor-interface.spec.md). Facts about the CLI come from [R-002](../research/R-002-antigravity-cli-headless.rsrch.md). `agy` reports tokens but no cost, has no per-invocation flag for settings, permission rules or MCP servers, keeps its config home under `~/.gemini`, and its plan mode is not an enforcement boundary. So the executor restricts a session only through an isolated session home with generated configuration and an engine-owned gatekeeper hook ([ADR-0011](../adr/0011-isolated-config-home-for-antigravity.adr.md)), and declares judge restriction false until probes P-AG-1 to P-AG-3 confirm that design; until then its steps are judged on an executor that can restrict tools ([ADR-0013](../adr/0013-cross-executor-judging.adr.md)). The probes P-AG-1 to P-AG-10, none run yet, are listed in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md) under EAG. Workflow authors and operators who choose this executor depend on what it declares.

## Behaviours

### EAG-B8 Declared capabilities

WHEN the `antigravity` executor declares its capabilities THE executor SHALL declare `binds_aliases` (`small`, `medium`, `large`, `inherit` and every `antigravity:<name>` in the binding table), `prompt_off_argv`, `streams_events`, `reports_actions`, `reports_tokens` and `fresh_session` true, `reports_cost` false, `isolates_user_config`, `enforces_step_tools` and `judge_mcp` false until P-AG-1 and P-AG-2 are confirmed, `restricts_judge_tools` false until P-AG-1, P-AG-2 and P-AG-3 are confirmed, `step_allow_rules` true in isolated mode and best effort in user mode, and `session_options` `effort` only.

- GIVEN no probe confirmed WHEN `executors` lists `antigravity` THEN `restricts_judge_tools` and `enforces_step_tools` are false
- GIVEN a step with `turn_cap` on `antigravity` WHEN preflighted THEN it exits 2

### EAG-B9 Tool map

WHEN a step declares tools on `antigravity` THE executor SHALL map `read` to `view_file`, `search` to `grep_search`, `list` to `list_dir` and `find_by_name` (each allowed by `read_file(<workdir>/)`), `edit` to `replace_file_content` and `multi_replace_file_content` and `write` to `write_to_file` (allowed by `write_file(<workdir>/)`), `shell` to `run_command` (`command(<prefix>)` per declared prefix), `web_fetch` to `read_url_content` (`read_url(<domain>)` per declared domain), `web_search` to `search_web`, `subagent` to `invoke_subagent` (inheriting) and `mcp:<s>/<t>` by the name P-AG-6 sets (`mcp(<s>/<t>)`), refuse at preflight a step that declares `skill:` until P-AG-9 names the skill tool, and never grant `define_subagent`, `manage_subagents`, `send_message`, `schedule`, `ask_permission` or `ask_question` to any session.

- GIVEN a step declaring `skill:docs:review` on `antigravity` WHEN preflighted THEN it exits 2
- GIVEN any session WHEN its tool set is read THEN `ask_question` is absent, because nobody answers during a run

### EAG-B10 Isolated session home

WHEN a session runs in isolated mode THE executor SHALL create a private folder with owner-only permissions under the state root's scratch area, point the child's `HOME` (and `USERPROFILE` on Windows) at it, write there only `.gemini/antigravity-cli/settings.json` (`agentMode` `""`, `toolPermission` `request-review`, `allowNonWorkspaceAccess` false, `permissions.allow` from EAG-B9, `permissions.deny` the engine's constant deny list with `write_file(.git/)` and secrets paths, and for a judge a deny of every write and command action), `.gemini/config/hooks.json` (one PreToolUse entry, matcher `*`, running the gatekeeper with a 10 s timeout), `.gemini/config/mcp_config.json` (only the servers the session may use, for a judge each behind the filtering proxy with `enabledTools` set to the view tools) and the credentials of P-AG-1 (API-key mode or a copy of the cached sign-in, never a value on argv), and remove the folder on every exit path.

- GIVEN an isolated session WHEN it ends by a timeout THEN its session home is gone
- GIVEN a session home that cannot be made owner-only WHEN the session starts THEN it fails with `spawn_failed` and nothing is launched

### EAG-B11 User mode

WHEN isolation is not confirmed THE executor SHALL keep the operator's own home, add no configuration, enforce nothing, and record `isolation = user`.

- GIVEN P-AG-1 not confirmed WHEN a step session is recorded THEN its record says `isolation = user`

### EAG-B5 Gatekeeper denies

WHEN a model in an isolated session calls a tool outside the session's allow-list THE gatekeeper SHALL answer `deny` with a fixed reason, answer nothing for an allowed call (so `agy`'s own rules decide it), and append one line per decision with the tool name and decision word and no arguments to a decision log the executor reads after the session, each `deny` becoming a `denied` event.

- GIVEN an allow-list of `view_file` and `run_command` WHEN the model calls `write_to_file` THEN the gatekeeper answers `deny`, the log records `write_to_file deny` and a `denied` event is emitted
- GIVEN that allow-list WHEN the model calls `run_command pytest -q` THEN the gatekeeper answers nothing and `agy`'s `command(pytest)` rule decides
- GIVEN any allow-list WHEN the model calls `define_subagent` THEN the gatekeeper answers `deny`

### EAG-B6 Soft denial is not success

WHEN a session exits 0 with status SUCCESS but its decision log holds denials THE executor SHALL record the denials as refused calls that reach the friction signals, never marking the step clean by the exit code alone.

- GIVEN a SUCCESS result and two denials in the log WHEN the step is recorded THEN two refused calls are recorded

### EAG-B12 Launch

WHEN a session is launched THE executor SHALL run `agy --input-format stream-json --output-format stream-json --add-dir <workdir> --print-timeout <timeout_s + 30>s`, adding `--model <bound slug>` unless the alias is `inherit`, `--effort <level>` when set, `--mode accept-edits` for a step in an engine worktree that declares `edit` or `write`, and `--disable-slash-commands` for a judge, in the workspace as working directory, and never pass `--dangerously-skip-permissions`, `--mode auto`, `--continue`, `--conversation` or `-p`.

- GIVEN a judge session WHEN its argv is read THEN it holds `--disable-slash-commands` and no `--mode accept-edits`
- GIVEN `timeout_s = 600` WHEN launched THEN `--print-timeout 630s` is passed and the engine's own timeout fires first

### EAG-B1 Prompt framing

WHEN a prompt is sent THE executor SHALL write it JSON-encoded inside one line `{"event":"user","message":{"content":"<prompt>"}}` on standard input and then close it, which ends the session after its turn.

- GIVEN a prompt containing quotes and newlines WHEN it is sent THEN standard input receives one line that decodes to the prompt, and no `-p` is passed

### EAG-B13 Stream mapping

WHEN the executor reads the stream THE executor SHALL map `init` to `session_started` (`tools`, `model`, `permission_mode`, with `cwd` checked against the workspace), a tool `step_update` in state ACTIVE to `tool_started` (`name` from `tool_name`, `subagent` when `subagent_info` is present), in state DONE to `tool_finished` (`ok` when no `tool_info.error`), a `step_update` with `text_delta` to `model_delta` and `text`, a gatekeeper `deny` line to `denied`, and `result` to `result` (`usage` field by field, `reported_cost_usd` null, `conversation_id` as `session_id`), skipping and counting an unknown event or step type.

- GIVEN an `init` whose `cwd` differs from the workspace WHEN read THEN the session is killed with `infra_cause = spawn_failed` and the mismatch is recorded
- GIVEN an unknown event type WHEN read THEN it is skipped and counted

### EAG-B14 Failure classification

WHEN an `agy` session fails THE executor SHALL classify a raised spawn as `spawn_failed`, a broken pipe on the user event as `broken_pipe`, no `init` before exit as `no_output`, `init` without `result` as `no_result`, status CANCELED or INTERRUPTED as `partial = true` with `error_kind = unknown`, status ERROR by its structured `error.type` per P-AG-7 and otherwise `error_kind = model`, and exit 1 before `init` on a slug the probe listed as `error_kind = model` (binding drift).

- GIVEN `init` seen and no `result` before exit WHEN classified THEN `infra_cause` is `no_result`
- GIVEN status ERROR with no known `error.type` WHEN classified THEN `error_kind` is `model`

### EAG-B2 Cost is never zero

WHEN a result reports tokens and no cost THE executor SHALL record `reported_cost_usd` null and `estimated_cost_usd` from the binding table's prices, and with no price for the slug record both as null and mark the run's usage line incomplete.

- GIVEN `usage.input_tokens = 12000` and a price for the slug WHEN recorded THEN `estimated_cost_usd` is computed and `reported_cost_usd` is null
- GIVEN no price for the slug WHEN recorded THEN both are null and the usage line is incomplete

### EAG-B3 Judge refused in user mode

WHEN a gate's judge names executor `antigravity` while P-AG-1 is not confirmed THE engine SHALL exit 2 at preflight naming the capability `restricts_judge_tools`.

- GIVEN a gate judge on `antigravity` WHEN preflighted THEN it exits 2 naming `restricts_judge_tools`

### EAG-B4 Judge moved

WHEN a step on `antigravity` names no judge executor and `claude` is registered THE engine SHALL run the judge on `claude` ([EXI-B10](executor-interface.spec.md)).

- GIVEN a step on `antigravity` WHEN its judge executor is selected THEN it is `claude`

### EAG-B7 Version drift

WHEN the probe reports a version outside the range the probe results were recorded for THE executor SHALL warn naming both versions and report every capability that rests on a probe as projected for the run.

- GIVEN results recorded for 1.4 and a probe reporting 1.6 WHEN the run starts THEN a warning names both and probe-based capabilities show as projected

### EAG-B15 Preflight refusals

WHEN `agy` is missing, its model listing fails because the account is signed out, or a slug in the binding table is missing from `agy models` THE engine SHALL exit 2 at preflight, naming the alias for a missing slug.

- GIVEN a binding of `large` to a slug `agy models` does not list WHEN preflighted THEN it exits 2 naming `large`

### EAG-B16 Sandbox is opt-in

WHEN an operator opts in to `--sandbox` for step sessions THE executor SHALL pass it and record whether `init` reported it active, and pass it in no other case, because it confines only shell commands and does nothing where the host blocks it ([R-002 A20](../research/R-002-antigravity-cli-headless.rsrch.md)).

- GIVEN no opt-in WHEN a step launches THEN `--sandbox` is not on its argv

## Acceptance criteria

- EAG-AC1 (EAG-B1, EAG-B12): The prompt is never on argv or in the environment, by a planted-canary test
- EAG-AC2 (EAG-B10): A session home is owner-only, holds only the files of EAG-B10, and is removed after the session on every exit path
- EAG-AC3 (EAG-B13, EAG-B14): Each mapping of EAG-B13 and each classification of EAG-B14 is covered by a recorded-stream fixture
- EAG-AC4 (EAG-B2): No record shows a cost of 0 for an `agy` session
- EAG-AC5 (EAG-B3, EAG-B8): While any of P-AG-1 to P-AG-3 is unconfirmed, a judge on `antigravity` is refused at preflight
- EAG-AC6 (EAG-B5): The gatekeeper denies every tool outside its allow-list in a stand-in test and writes no argument text to its log
- EAG-AC7 (EAG-B11, EAG-B7): Every session record carries the `agy` version and the isolation mode
- EAG-AC8 (EAG-B9): Each declared capability maps to the tool names and rule of EAG-B9, and the never-granted tools are in no session's tool set
- EAG-AC9 (EAG-B6): A SUCCESS result with denials in the log records refused calls
- EAG-AC10 (EAG-B4, EAG-B15, EAG-B16): A step on `antigravity` gets its judge on `claude`, each preflight refusal exits 2, and `--sandbox` appears only with the operator's opt-in

## Open questions

- Is account-based use as a child process permitted for the operator's account type, or must API-key mode be the only supported auth? Owner: owner.
- Should the executor use the Agent Client Protocol server (`agy acp`) instead of stream-json once its contract is read? Owner: executor implementer.
