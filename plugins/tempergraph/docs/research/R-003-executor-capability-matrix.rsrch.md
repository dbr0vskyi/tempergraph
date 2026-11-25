# R-003 Executor capability matrix: Claude Code, Agent SDK, Messages API and Antigravity

## Problem statement

The [executor interface](../specs/executor-interface.spec.md) has executors **declare** what they can enforce, and the preflight refuses a workflow that needs a capability its executor lacks. This note sets the four executors side by side, capability by capability, from [R-001](R-001-claude-code-cli-headless.rsrch.md), [R-002](R-002-antigravity-cli-headless.rsrch.md), [R-004](R-004-anthropic-messages-api-executor.rsrch.md) and [R-005](R-005-claude-agent-sdk-executor.rsrch.md), so the declared values in the executor specs are traceable. It also lists what the engine must do itself because not every executor does it. The two library columns were added on 2026-11-19 with [ADR-0018](../adr/0018-add-messages-api-and-agent-sdk-executors.adr.md).

## Sources consulted

| Source | Type | Where |
|---|---|---|
| R-001 Claude Code CLI as a headless executor | Research note | [R-001](R-001-claude-code-cli-headless.rsrch.md) |
| R-002 Antigravity CLI as a headless executor | Research note | [R-002](R-002-antigravity-cli-headless.rsrch.md) |
| R-004 Messages API as an executor | Research note | [R-004](R-004-anthropic-messages-api-executor.rsrch.md) |
| R-005 Claude Agent SDK as an executor | Research note | [R-005](R-005-claude-agent-sdk-executor.rsrch.md) |

## Key findings

Capability names are those of the contracts spec ([SSN-B1 to SSN-B6](../specs/session-contract.spec.md)). "Engine" means the engine provides the behaviour for every executor, so the CLI's own support does not matter.

| Capability | Claude Code CLI | Agent SDK | Messages API | Antigravity CLI | Confidence (CC / SDK / API / AG) |
|---|---|---|---|---|---|
| `prompt_off_argv` (prompt on stdin) | yes: `-p` with the prompt on stdin | yes: worker stdin, then a typed argument (P-AS-3 for the CLI hop) | yes: worker stdin, then the request body | yes: `--input-format stream-json`, one user event, then close stdin | confirmed / supported / confirmed / supported |
| `streams_events` (parsable progress) | yes: `stream-json` with `--verbose` | yes: typed messages | yes: server-sent events | yes: `stream-json` (`init`, `step_update`, `result`) | confirmed / confirmed / confirmed / supported |
| `reports_actions` (tool names per call) | yes, full names, subagents included | yes, with `parent_tool_use_id` | yes: the engine runs every call | yes, in `step_update.tool_info` and `subagent_info` | supported / confirmed / confirmed / supported |
| `reports_tokens` | yes | yes, per model | yes, with cache read and write | yes (input, output, thinking, cache read) | confirmed ×4 |
| `reports_cost` | yes, a CLI-side estimate | yes, a client-side estimate | **no** | **no** | confirmed ×4 |
| `binds_aliases` (model families) | Claude families | Claude families | Claude families, ids per provider | Gemini families via slugs (`agy models`) | confirmed ×4 |
| `effort` session option | yes (`--effort`) | yes (`effort`) | yes (`output_config.effort`, values per model) | yes (`--effort`, range per model) | confirmed ×4 |
| `cost_cap` session option | yes (`--max-budget-usd`) | yes (`max_budget_usd`) | **engine**, between responses | **no** | confirmed / confirmed / n/a / supported |
| `fallback_model` session option | yes (`--fallback-model`) | yes (`fallback_model`) | **no** | **no** documented flag | confirmed / confirmed / n/a / supported |
| `turn_cap` session option | yes (`--max-turns`) | yes (`max_turns`) | **engine**, counted per response | **no** | confirmed / confirmed / n/a / supported |
| `enforces_step_tools` (hard cut of undeclared tools) | yes: `--tools`, `--disallowedTools`, `--strict-mcp-config` | yes: `tools`, `disallowed_tools`, in-process hook | yes, by construction | only through generated config | confirmed / confirmed / confirmed / inferred |
| `restricts_judge_tools` (judge holds read tools only) | yes: `--tools Read,Grep,Glob`, strict MCP config, `--bare`, `dontAsk` | yes: same tools, `setting_sources=[]`, hook deny in every mode | yes: only views are offered | **not by flag**; plausible with an isolated home, deny rules and a hook | supported / supported / confirmed / uncertain |
| `step_allow_rules` (pre-approve declared commands) | yes: `--allowedTools "Bash(cmd *)"` | yes: `allowed_tools` | yes: the tool host's prefix rule | yes in settings `permissions.allow`, print-mode honouring disputed | confirmed / confirmed / confirmed / uncertain |
| `judge_mcp` (one filtered MCP server for a judge) | yes: engine-written `--mcp-config` + `--strict-mcp-config` | yes: `mcp_servers` + `strict_mcp_config` | yes, local servers through the tool host | only by generated `mcp_config.json` in an isolated home | confirmed / confirmed / confirmed / inferred |
| `isolates_user_config` | yes: `--bare`, `--setting-sources` | yes: `setting_sources=[]` (P-AS-1) | yes: reads no configuration | only by an isolated home directory | supported / supported / confirmed / inferred |
| `hosts_authoring_surface` (instruction files, skills, agents) | yes | yes (project settings) | **no** | yes (`AGENTS.md`, `.agents/`) | confirmed / confirmed / confirmed / supported |
| `fresh_session` | yes (new session id unless `--resume`) | yes (one `query()` per session) | yes (stateless API) | stated stateless by default; one contrary report | confirmed / confirmed / confirmed / supported |
| `subagent` | yes (`Agent`) | yes (`Agent`) | **no** | yes | confirmed / confirmed / confirmed / supported |
| `timeout`, `idle_limit`, `kills_tree` | **engine** | **engine** (worker process) | **engine** (worker process) | **engine**; `--print-timeout` as a second bound | n/a |
| `failure_cause` classification | exit code, stream shape, retry category, exact "Request timed out" | typed result subtypes and error values | HTTP status and error type, stop reasons | exit code, `status`, absence of `result`, stderr notice shape | supported / confirmed / confirmed / inferred |

Sources for the two library columns: [R-004](R-004-anthropic-messages-api-executor.rsrch.md) and [R-005](R-005-claude-agent-sdk-executor.rsrch.md).

### What the engine must own

| Concern | Why the engine, not the CLI |
|---|---|
| Wall-clock timeout, idle watchdog, process-tree kill | Neither CLI's own limits cover all cases, and `agy` has no turn cap. One owner keeps behaviour equal across executors. |
| Cost estimate from tokens | `agy` and the Messages API report no cost, and the Claude Code and SDK figures are themselves estimates. The engine's price table writes a separate estimated cost for every executor. |
| The agent loop and tools for the Messages API | The API runs no client tool; the engine's tool host does ([ADR-0020](../adr/0020-engine-owned-tool-loop-for-the-messages-api.adr.md)). |
| Independence guard | It compares tool names after the session; it does not depend on either CLI's permission layer. |
| Fresh session check | The engine compares the session id reported by a judge with the step's; a match discards the judgement. |
| Version stamp | Every executor changes behaviour between releases (Claude's `-p` permission default, `agy` permission matching, the SDK's bundled CLI, API tool versions). Every session record carries the version. |

## Conclusions

1. All four meet the **step executor** bar: prompt off argv, an event stream with tool names, token usage, model selection, effort and a session id.
2. Claude Code, the Agent SDK and the Messages API meet the **judge executor** bar today (the API by construction); Antigravity does not by documented flags. Antigravity can host judges only once the isolated-home probe (P-AG-1) and the hook probe (P-AG-2) pass; until then its declaration says `restricts_judge_tools: false` and the preflight sends its steps' judges to an executor that can restrict tools ([ADR-0013](../adr/0013-cross-executor-judging.adr.md)).
3. Session options are asymmetric. `cost_cap` and `turn_cap` exist on Claude Code and the SDK and are engine-enforced on the Messages API; `fallback_model` exists on Claude Code and the SDK only. A workflow that asks for a missing one is refused before spend, while `effort` works on all four.
4. Tool vocabularies differ (`Read`/`Bash`, `read_file`/`run_command`, `view_file`/`run_command`). Workflow data must declare tools in engine-neutral **capability names** that each executor maps to its own tool names ([CON-B11](../specs/contracts.spec.md)).
5. Model families differ (Claude against Gemini). Workflow data names engine-neutral **aliases** (`small`, `medium`, `large`) or executor-qualified ones, and each executor binds them ([ADR-0008](../adr/0008-portable-model-aliases.adr.md)).

## Open questions

| Question | Owner | How to settle |
|---|---|---|
| Can `agy` host a judge at all, under an isolated home with deny rules and a gatekeeper hook? | Executor implementer | Probes P-AG-1 and P-AG-2. |
| Does an `agy` subagent inherit the parent's mode and hooks, and can `define_subagent` enable write tools a judge lacks? | Executor implementer | Probe P-AG-3. |
| Is the tool-name list of each executor stable across releases? | Executor implementer | The conformance suite records the names it sees per CLI version and fails on an unknown name. |
