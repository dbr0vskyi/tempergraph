---
title: Independence guard and judge views
type: component
status: review
prefix: GRD
adrs: [0010, 0011, 0013, 0020]
---

# Independence guard and judge views

## 1. Overview

A judge can read every system its step can change and can change nothing. The engine derives each judge attempt's **view set** from the step's declared and actually called tools, using an engine-owned catalog keyed per executor. The judge executor enforces the set as far as it declares it can; after the session the **guard** compares what the judge called and changed with what it was allowed, and discards the judgement on any difference. The guard does not depend on any executor's permission layer.

## 2. Contract

```python
def view_set(step: StepSpec, step_calls: list[ToolCall], judge_executor: str) -> ViewSet: ...
def guard(views: ViewSet, judge_calls: list[ToolCall], before: Fingerprint, after: Fingerprint,
          workspace_mode: str, step_session_id: str, judge_session_id: str) -> GuardResult: ...
class ViewSet: tools: list[str]; deferred: list[Deferred]   # executor tool names
class GuardResult: status: Literal["clean", "discarded", "warned", "unavailable"]; reason: str | None
```

### 2.1 View catalog

A constant table, one per executor, keyed by full tool name. Each write tool maps to the read tools that show what it changed. No entry is inferred from a name pattern or an MCP hint.

| Write capability | claude and agent-sdk views | messages-api views | antigravity views |
|---|---|---|---|
| `edit`, `write`, `shell` (workspace) | `Read`, `Grep`, `Glob` | `read_file`, `search_files`, `list_files` | `view_file`, `grep_search`, `list_dir`, `find_by_name` |
| `mcp:<tracker>/<create or update issue>` | `mcp__<tracker>__get_issue` | `mcp__<tracker>__get_issue` (tool host) | `mcp(<tracker>/get_issue)` name per P-AG-6 |
| `mcp:<wiki>/<update page>` | `mcp__<wiki>__get_page` | `mcp__<wiki>__get_page` (tool host) | same, per P-AG-6 |
| `pull_request` artifact | read-only GitHub commands (opt-in) | read-only GitHub commands through `run_command` (opt-in) | read-only GitHub commands (opt-in) |

`agent-sdk` shares Claude Code's rows because it runs the same tools. Newer tracker and wiki tool names are **added** beside the old ones, never renamed, so a workflow pinned to an older server keeps its views. A generic write tool that can write to several systems (for example one tool that updates any tracker field) maps to the union of their read views and is marked `partial`: its criterion can be MET only if every system it may have changed is in the view set.

The always-present base is the read, search and list capabilities. Workflow data may narrow a view set and never widen it.

### 2.2 Enforcement layers, strongest first

| Layer | claude | agent-sdk | messages-api | antigravity |
|---|---|---|---|---|
| 1 Judge-only credentials laid over the judge's environment | yes | yes | yes | yes (credentials profile into the session home) |
| 2 Write tools absent from the session | `--tools`, strict MCP config, `--bare` | `tools`, `strict_mcp_config`, `setting_sources=[]` | only views are offered (by construction) | not by flag; isolated home + deny rules (probe-gated) |
| 3 Calls refused by rule | `dontAsk` + allow rules | in-process gatekeeper hook + `dontAsk` | tool host refuses any other name | gatekeeper hook `deny` (probe-gated) |
| 4 Guard after the session | always | always | always | always |

## 3. Behaviours

**GRD-B1 Derived, not authored.** Given a step that declared `edit` and, undeclared, called a tracker update tool, when its judge's view set is built, then it holds the base read views and the tracker's read view; an author's `judge.tools` may remove entries but an entry outside the derived set is a validation error.

**GRD-B2 Outside call discards.** Given a judge whose view set is `Read, Grep, Glob`, when its tool log shows any other name, including a subagent call, a failed call or an unnamed call, then the judgement is discarded as an unresolved gap at confidence 0.0 and the run escalates.

| Judge called | In view set | Result |
|---|---|---|
| `Read`, `Grep` | yes | clean |
| `Read`, a plugin-registered status tool | no | discarded |
| a call with no name | no | discarded |
| nothing (executor reports no actions) | — | `unavailable`, recorded, not discarded |

**GRD-B3 Workspace fingerprint.** Given the head and status of the workspace before and after the judge, when they differ, then the judgement is discarded in an engine worktree and only warned about in place, where another writer may exist.

**GRD-B4 Same session.** Given a judge result whose session id equals the step attempt's, when guarded, then it is discarded.

**GRD-B5 Out of reach.** Given an artifact kind whose read view the judge executor cannot give (for example an MCP view deferred by `judge_mcp = false`), when the judge renders, then the artifact is marked out of reach with a fixed reason, and the dependent criterion can only be UNVERIFIABLE or N/A, never MET.

**GRD-B6 Preflight reports deferrals.** Given a workflow, when `validate` runs, then it lists per step which views are deferred on which judge executor and why, and refuses a step that changes a system its judge cannot see unless its criteria mark that system unverified.

## 4. Error conditions

| Condition | Result |
|---|---|
| Judge executor declares `restricts_judge_tools = false` | Preflight refusal; the judge must move ([ADR-0013](../adr/0013-cross-executor-judging.adr.md)) |
| Filtering MCP proxy fails to start | The view is deferred for that attempt and recorded; the criterion renders out of reach |
| Read-only command used outside the engine's exact-option allow-list | Judgement discarded |

## 5. Design notes

- Absent beats denied: where an executor can, a write tool is not in the session at all. On `messages-api` the engine offers the tools, so absence is a fact of the request, tested by contract. Antigravity cannot remove tools by flag, so it sits on layers 3 and 4 until probes confirm layer 2 ([ADR-0010](../adr/0010-judge-isolation-per-executor.adr.md), [ADR-0011](../adr/0011-isolated-config-home-for-antigravity.adr.md)).
- The read-only GitHub commands need four conditions: operator opt-in, an executor that can restrict the shell and report actions, a judge-only token, and an engine worktree.

## 6. Acceptance criteria

- [ ] GRD-AC-1 Every catalog entry is keyed by full executor tool name; a source test forbids pattern matching in the catalog.
- [ ] GRD-AC-2 Each row of the GRD-B2 table is covered for every executor's tool names.
- [ ] GRD-AC-3 A discarded judgement never routes PROCEED.
- [ ] GRD-AC-4 The run log records, per judgement, the view set used and the guard status.
- [ ] GRD-AC-5 A planted subagent call in a judge stream is detected on the stream fixtures of every executor that maps `subagent`.

## Open questions

| Question | Owner |
|---|---|
| Should a refused (not executed) outside call void a complete verdict? Today yes, because the engine cannot always tell refused from executed across executors. | Engine owner |

## References

