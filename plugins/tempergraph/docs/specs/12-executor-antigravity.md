---
title: Antigravity executor
type: component
status: review
prefix: EAG
adrs: [0006, 0007, 0008, 0010, 0011, 0012, 0013]
---

# Antigravity executor

## 1. Overview

The `antigravity` executor runs each step attempt as one headless Antigravity CLI session: `agy` in streaming mode, with the prompt delivered as one `stream-json` user event on stdin and the event stream read from stdout. It implements the [executor interface](10-executor-interface.md). Facts about the CLI come from [R-002](../research/R-002-antigravity-cli-headless.md).

Three properties of `agy` shape this spec. It reports **tokens but no cost**. It has **no per-invocation flag** for settings, permission rules or MCP servers, and its config home is fixed under `~/.gemini`. Its plan mode is **not an enforcement boundary**. The executor therefore restricts a session only through an **isolated session home** with generated configuration and an engine-owned **gatekeeper hook** ([ADR-0011](../adr/0011-isolated-config-home-for-antigravity.md)), and it declares judge restriction `false` until the probes in §2.7 confirm that design. Until then its steps are judged on an executor that can restrict tools ([ADR-0013](../adr/0013-cross-executor-judging.md)).

## 2. Contract

### 2.1 Declared capabilities

| Capability | Value | Basis |
|---|---|---|
| `binds_aliases` | `small`, `medium`, `large`, `inherit`, every `antigravity:<name>` in the binding table | [R-002 A10](../research/R-002-antigravity-cli-headless.md) |
| `prompt_off_argv` | true (stream-json input) | A2 |
| `streams_events`, `reports_actions`, `reports_tokens` | true | A4, A5 |
| `reports_cost` | **false** | A4, A11 |
| `fresh_session` | true, checked per judge by EXI-B9 | A22 |
| `isolates_user_config`, `enforces_step_tools`, `judge_mcp` | **false** until P-AG-1 and P-AG-2 are confirmed, then true | A15, A17, A19 |
| `restricts_judge_tools` | **false** until P-AG-1, P-AG-2 and P-AG-3 are confirmed, then true | A12, A13, A17 |
| `step_allow_rules` | true in isolated mode; best effort in user mode | A14, A16 |
| `session_options` | `effort` only | A9, A10 |

### 2.2 Tool map

| Capability | `agy` tool names | Permission rule when declared |
|---|---|---|
| `read` | `view_file` | `read_file(<workdir>/)` |
| `search` | `grep_search` | `read_file(<workdir>/)` |
| `list` | `list_dir`, `find_by_name` | `read_file(<workdir>/)` |
| `edit` | `replace_file_content`, `multi_replace_file_content` | `write_file(<workdir>/)` |
| `write` | `write_to_file` | `write_file(<workdir>/)` |
| `shell` | `run_command` | `command(<prefix>)` per declared prefix |
| `web_fetch` | `read_url_content` | `read_url(<domain>)` per declared domain, else none |
| `web_search` | `search_web` | none (ask) |
| `subagent` | `invoke_subagent` | inherits; `define_subagent` is never granted |
| `mcp:<s>/<t>` | name shape set by P-AG-6 | `mcp(<s>/<t>)` |

Tools never granted by the map, to any session: `define_subagent`, `manage_subagents`, `send_message`, `schedule`, `ask_permission`, `ask_question`. `ask_question` is removed because nobody answers during a run.

### 2.3 Session home

In **isolated mode** each session gets a private folder, created with owner-only permissions under the state root's scratch area and removed in a `finally` block. The child's `HOME` (and `USERPROFILE` on Windows) points at it. It holds only engine-written files:

| File in the session home | Content |
|---|---|
| `.gemini/antigravity-cli/settings.json` | `agentMode` `""`; `toolPermission` `request-review`; `allowNonWorkspaceAccess` false; `permissions.allow` from §2.2; `permissions.deny` the engine's constant deny list (`write_file(.git/)`, secrets paths); for a judge, `deny` of every write and command action |
| `.gemini/config/hooks.json` | One PreToolUse entry, matcher `*`, running the engine's gatekeeper with a timeout of 10 s |
| `.gemini/config/mcp_config.json` | Only the servers the session may use; for a judge, each behind the filtering proxy with `enabledTools` set to the view tools |
| Credentials | Per P-AG-1: API-key mode (`modelProvider: "gemini"` and `GEMINI_API_KEY` from the operator's credentials profile), or a copy of the operator's cached sign-in files; never a value in argv |

The **gatekeeper** is a small engine-owned program with no dependency on the engine package. It reads the session's allow-list (tool names from §2.2) from a file in the session home, answers `deny` with a fixed reason for any tool call outside it, answers nothing else (so `agy`'s own rules decide allowed calls), and appends one line per decision (tool name and decision word, no arguments) to a decision log the executor reads after the session.

In **user mode** (isolation not confirmed) the child keeps the operator's own home. The executor adds no configuration, enforcement is off, and the record says `isolation = user`.

### 2.4 Launch

```text
agy --input-format stream-json --output-format stream-json
    --model <bound slug>                   [alias is not inherit]
    --effort <level>                       [option set]
    --mode accept-edits                    [step, engine worktree, edit or write declared]
    --print-timeout <timeout_s + 30>s      [always; the engine's own timeout fires first]
    --add-dir <workdir>
    --disable-slash-commands               [judge]
```

The working directory is the workspace. stdin receives exactly one line, `{"event":"user","message":{"content":"<prompt>"}}`, and then closes, which ends the session after its turn. Never passed: `--dangerously-skip-permissions`, `--mode auto`, `--continue`, `--conversation`, `-p`.

### 2.5 Stream mapping

| CLI event | Normalized event |
|---|---|
| `init` | `session_started` (`tools`, `model`, `permission_mode`; `cwd` checked against the workspace) |
| `step_update`, `step_type` tool, `state` ACTIVE | `tool_started` (`name` = `tool_name`; `subagent` when `subagent_info` is present) |
| `step_update`, `step_type` tool, `state` DONE | `tool_finished` (`ok` = no `tool_info.error`) |
| `step_update` with `text_delta` | `model_delta` (count); `text` (last line, scrubbed) |
| gatekeeper decision log line `deny` | `denied` |
| `result` | `result` (`status`, `usage` mapped field by field, `reported_cost_usd = null`, `conversation_id` → `session_id`) |

### 2.6 Failure classification

| Observed (structured) | `infra_cause` / `error_kind` |
|---|---|
| Spawn raised | `spawn_failed` |
| Write of the user event raised broken pipe | `broken_pipe` |
| No `init` event before exit | `no_output` |
| `init` seen, no `result` before exit | `no_result` |
| `result.status` SUCCESS | ok |
| `result.status` CANCELED or INTERRUPTED | `partial = true`, `error_kind = unknown` |
| `result.status` ERROR with a structured `error.type` (values set by P-AG-7) | mapped per P-AG-7; otherwise `error_kind = model` |
| Exit 1 before `init` on a model slug the probe listed | `error_kind = model` (binding drift) |
| Engine timeout or idle kill | `timed_out` or `stalled` (engine-owned) |

### 2.7 Probes

Run by the owner on the pinned version with a throwaway workspace; results are written here with date and version.

| Id | Fact to confirm | Unlocks | Result |
|---|---|---|---|
| P-AG-1 | With `HOME` pointed at a session home, `agy` reads settings, hooks and MCP config only from there, and authenticates (API-key mode or copied sign-in) | isolated mode | not run |
| P-AG-2 | A PreToolUse hook runs in headless stream mode and its `deny` blocks every tool, subagent tools included | gatekeeper | not run |
| P-AG-3 | A subagent inherits the session's rules and hooks, and cannot be given write tools by the model | `restricts_judge_tools` | not run |
| P-AG-4 | Default and behaviour of `--print-timeout`; status and exit of a timed-out turn | timeout layering | not run |
| P-AG-5 | A stream-json session never continues an earlier conversation of the workspace | `fresh_session` | not run |
| P-AG-6 | The tool name `agy` reports for an MCP tool, in `init.tools` and `step_update.tool_name` | MCP view catalog | not run |
| P-AG-7 | The values of `result.error.type` for auth, quota and model errors | classification | not run |
| P-AG-8 | `permissions.allow` `command(<prefix>)` entries are honoured in stream mode on the pinned version | `step_allow_rules` | not run |

## 3. Behaviours

**EAG-B1 Prompt framing.** Given a rendered prompt containing quotes and newlines, when it is sent, then it is JSON-encoded inside one user event line, no `-p` is passed, and stdin closes after that line.

**EAG-B2 Cost is never zero.** Given a `result` with `usage.input_tokens = 12000` and no cost, when it is recorded, then `reported_cost_usd` is null and `estimated_cost_usd` comes from the binding table's prices; with no price for the slug, both are null and the run's usage line is marked incomplete.

**EAG-B3 Judge refused in user mode.** Given P-AG-1 not confirmed and a gate whose judge names executor `antigravity`, when the run is preflighted, then it exits 2 naming the capability `restricts_judge_tools`.

**EAG-B4 Judge moved.** Given a step on `antigravity`, no judge executor named and `claude` registered, when the judge executor is selected, then the judge runs on `claude` ([EXI-B10](10-executor-interface.md)).

**EAG-B5 Gatekeeper denies.** Given an isolated step session whose allow-list holds `view_file` and `run_command`, when the model calls `write_to_file`, then the gatekeeper answers `deny`, the decision log records `write_to_file deny`, a `denied` event is emitted and the call is recorded as outside the declaration.

| Call | Allow-list | Gatekeeper | Then decided by |
|---|---|---|---|
| `view_file` | yes | no answer | `agy` rules (`read_file` allow) |
| `run_command pytest -q` | yes | no answer | `agy` rules (`command(pytest)`) |
| `write_to_file` | no | `deny` | blocked |
| `define_subagent` | never | `deny` | blocked |

**EAG-B6 Soft denial is not success.** Given a session that exits 0 with `status` SUCCESS but whose decision log holds denials, when the step is checked, then the denials are recorded as refused calls and reach the friction signals; the exit code alone never marks the step clean.

**EAG-B7 Version drift.** Given the probe reports a version outside the range the probe table was filled for, when the run starts, then a warning names both versions and every capability that rests on a probe is reported as projected for this run.

## 4. Error conditions

| Type | Handling |
|---|---|
| `agy` missing, or the probe's model listing fails because the account is signed out | Exit 2 at preflight |
| A slug in the binding table missing from `agy models` | Exit 2 at preflight, naming the alias |
| Session home cannot be created with owner-only permissions | Session fails with `spawn_failed`; nothing launched |
| `init.cwd` differs from the workspace | Session killed; `infra_cause = spawn_failed`; recorded |
| Unknown stream event or step type | Skipped and counted |

## 5. Design notes

- Plan mode is only a prompt prefix in the docs, so the executor never relies on it for a read-only judge ([R-002 A12](../research/R-002-antigravity-cli-headless.md)).
- An isolated home is inferred from the documented fixed paths, not documented as supported; that is why it is a probe-gated capability ([ADR-0011](../adr/0011-isolated-config-home-for-antigravity.md)).
- The gatekeeper answers only `deny`: an `allow` from a hook was reported ignored in print mode, while `deny` was honoured ([R-002 A16](../research/R-002-antigravity-cli-headless.md)).
- The engine's timeout is the bound; `--print-timeout` is set slightly above it only as a second stop if the engine dies.
- `--sandbox` is not used by default: it confines only shell commands and silently does nothing where the host blocks it ([R-002 A20](../research/R-002-antigravity-cli-headless.md)). An operator may opt in for step sessions; the record states whether `init` reported it active.

## 6. Acceptance criteria

- [ ] EAG-AC-1 The prompt is never on argv or in the environment (planted-canary test).
- [ ] EAG-AC-2 A session home is owner-only, holds only the files of §2.3, and is removed after the session on every exit path.
- [ ] EAG-AC-3 Each row of §2.5 and §2.6 is covered by a recorded-stream fixture.
- [ ] EAG-AC-4 No record shows a cost of 0 for an `agy` session.
- [ ] EAG-AC-5 While any of P-AG-1..3 is unconfirmed, a judge on `antigravity` is refused at preflight.
- [ ] EAG-AC-6 The gatekeeper denies every tool outside its allow-list in a stand-in test and writes no argument text to its log.
- [ ] EAG-AC-7 Every session record carries the `agy` version and the isolation mode.

## Open questions

| Question | Owner |
|---|---|
| Is account-based use as a child process permitted for the operator's account type, or must API-key mode be the only supported auth? | Owner |
| Should the executor use the Agent Client Protocol server (`agy acp`) instead of stream-json once its contract is read? | Executor implementer |

## References

[EXI](10-executor-interface.md) · [R-002](../research/R-002-antigravity-cli-headless.md) · [R-003](../research/R-003-executor-capability-matrix.md) · [GRD](06-independence-guard.md) · [ECC](11-executor-claude-code.md)
