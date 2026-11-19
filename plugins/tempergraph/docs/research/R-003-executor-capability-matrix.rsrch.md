# R-003 Executor capability matrix: Claude Code CLI against Antigravity CLI

## Problem statement

The [executor interface](../specs/10-executor-interface.spec.md) has executors **declare** what they can enforce, and the preflight refuses a workflow that needs a capability its executor lacks. This note sets the two required executors side by side, capability by capability, from [R-001](R-001-claude-code-cli-headless.rsrch.md) and [R-002](R-002-antigravity-cli-headless.rsrch.md), so the declared values in the two executor specs are traceable. It also lists what the engine must do itself because neither CLI, or only one, does it.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| R-001 Claude Code CLI as a headless executor | Research note | [R-001](R-001-claude-code-cli-headless.rsrch.md) |
| R-002 Antigravity CLI as a headless executor | Research note | [R-002](R-002-antigravity-cli-headless.rsrch.md) |

## Key findings

Capability names are those of the contracts spec ([CON §2.6](../specs/01-contracts.spec.md)). "Engine" means the engine provides the behaviour for every executor, so the CLI's own support does not matter.

| Capability | Claude Code CLI | Antigravity CLI | Confidence |
|---|---|---|---|
| `prompt_off_argv` (prompt on stdin) | yes: `-p` with the prompt on stdin | yes: `--input-format stream-json`, one user event, then close stdin | confirmed / supported |
| `streams_events` (parsable progress) | yes: `stream-json` with `--verbose` | yes: `stream-json` (`init`, `step_update`, `result`) | confirmed / supported |
| `reports_actions` (tool names per call) | yes, full names, subagents included | yes, in `step_update.tool_info` and `subagent_info` | supported / supported |
| `reports_tokens` | yes | yes (input, output, thinking, cache read) | confirmed / confirmed |
| `reports_cost` | yes, a CLI-side estimate | **no** | confirmed / confirmed |
| `binds_aliases` (model families) | Claude families (`haiku`, `sonnet`, `opus`, `fable`) | Gemini families via slugs (`agy models`) | confirmed / confirmed |
| `effort` session option | yes (`--effort`) | yes (`--effort`, range per model) | confirmed / confirmed |
| `cost_cap` session option | yes (`--max-budget-usd`) | **no** | confirmed / supported |
| `fallback_model` session option | yes (`--fallback-model`) | **no** documented flag | confirmed / supported |
| `turn_cap` session option | yes (`--max-turns`) | **no** | confirmed / supported |
| `structured_output` | yes (`--json-schema`) | yes (`--json-schema`; root-type rules disputed) | confirmed / supported |
| `enforces_step_tools` (hard cut of undeclared tools) | yes: `--tools`, `--disallowedTools`, `--strict-mcp-config` | only through generated config (rules, `enabledTools`, gatekeeper hook) | confirmed / inferred |
| `restricts_judge_tools` (judge holds read tools only) | yes: `--tools Read,Grep,Glob`, strict MCP config, `--bare`, `dontAsk` | **not by flag**; plausible with an isolated config home plus deny rules plus a deny-all-but-views hook | supported / uncertain |
| `step_allow_rules` (pre-approve declared commands) | yes: `--allowedTools "Bash(cmd *)"` | yes in settings `permissions.allow` (`command(prefix)`), print-mode honouring disputed | confirmed / uncertain |
| `judge_mcp` (one filtered MCP server for a judge) | yes: engine-written `--mcp-config` + `--strict-mcp-config` | only by generated `mcp_config.json` in an isolated home, with `enabledTools` | confirmed / inferred |
| `isolates_user_config` | yes: `--bare`, `--setting-sources`, `--settings` | only by an isolated home directory | supported / inferred |
| `fresh_session` (never continues another conversation) | yes (new session id unless `--resume`) | stated stateless by default; one contrary report | confirmed / supported |
| `subagent_model` | yes (environment variable; precedence unverified) | no documented control | supported / supported |
| `sandbox` (OS-level shell confinement) | not used by the engine | `--sandbox`, silent no-op where unsupported | n/a / confirmed |
| `timeout` | **engine**: wall-clock kill of the process tree | **engine**; `--print-timeout` set as a second bound | n/a |
| `idle_limit` | **engine**: no stream line for N seconds | **engine** | n/a |
| `kills_tree` | **engine**: job object or process group | **engine** | n/a |
| `failure_cause` classification | engine, from exit code, stream shape, `system/api_retry` category, exact "Request timed out" | engine, from exit code, `status`, absence of `result`, stderr denial notice shape | supported / inferred |

### What the engine must own

| Concern | Why the engine, not the CLI |
|---|---|
| Wall-clock timeout, idle watchdog, process-tree kill | Neither CLI's own limits cover all cases, and `agy` has no turn cap. One owner keeps behaviour equal across executors. |
| Cost estimate from tokens | `agy` reports no cost, and Claude Code's figure is itself an estimate. The engine's price table writes a separate estimated cost for both. |
| Independence guard | It compares tool names after the session; it does not depend on either CLI's permission layer. |
| Fresh session check | The engine compares the session id reported by a judge with the step's; a match discards the judgement. |
| Version stamp | Both CLIs change behaviour between releases (Claude's `-p` permission default, `agy` permission matching). Every session record carries the CLI version. |

## Conclusions

1. Both CLIs meet the **step executor** bar: prompt off argv, an event stream with tool names, token usage, model selection, effort and a session id.
2. Only Claude Code meets the **judge executor** bar by documented flags today. Antigravity can host judges only once the isolated-home probe (P-AG-1) and the hook probe (P-AG-2) pass; until then its declaration says `restricts_judge_tools: false` and the preflight sends its steps' judges to an executor that can restrict tools ([ADR-0013](../adr/0013-cross-executor-judging.adr.md)).
3. Session options are asymmetric. `cost_cap`, `fallback_model` and `turn_cap` exist on Claude Code only; a workflow that asks for them on an Antigravity step is refused before spend, while `effort` works on both.
4. Tool vocabularies differ (`Read`/`Bash` against `view_file`/`run_command`). Workflow data must declare tools in engine-neutral **capability names** that each executor maps to its own tool names ([CON §2.5](../specs/01-contracts.spec.md)).
5. Model families differ (Claude against Gemini). Workflow data names engine-neutral **aliases** (`small`, `medium`, `large`) or executor-qualified ones, and each executor binds them ([ADR-0008](../adr/0008-portable-model-aliases.adr.md)).

## Open questions

| Question | Owner | How to settle |
|---|---|---|
| Can `agy` host a judge at all, under an isolated home with deny rules and a gatekeeper hook? | Executor implementer | Probes P-AG-1 and P-AG-2. |
| Does an `agy` subagent inherit the parent's mode and hooks, and can `define_subagent` enable write tools a judge lacks? | Executor implementer | Probe P-AG-3. |
| Is the tool-name list of either CLI stable across releases? | Executor implementer | The conformance suite records the names it sees per CLI version and fails on an unknown name. |
