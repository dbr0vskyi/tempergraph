# Independence guard and judge views

## Purpose

A judge can read every system its step can change and can change nothing. The engine derives each judge attempt's view set from the step's declared and actually called tools, using an engine-owned catalog keyed per executor; the judge executor enforces the set as far as it declares it can, and after the session the guard compares what the judge called and changed with what it was allowed and discards the judgement on any difference, without depending on any executor's permission layer ([ADR-0010](../adr/0010-judge-isolation-per-executor.adr.md), [ADR-0013](../adr/0013-cross-executor-judging.adr.md)). The judge ([JDG](judge-and-verdict.spec.md)), the executors and security ([SEC](security.spec.md)) depend on it; design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### GRD-B1 Derived, not authored

WHEN a judge's view set is built THE engine SHALL compute it with `view_set(step, step_calls, judge_executor) -> ViewSet` (`tools` as executor tool names, `deferred` with reasons) from the always-present base of read, search and list capabilities plus the read views of every write tool the step declared or actually called, an author's `judge.tools` only removing entries, an entry outside the derived set being a validation error.

- GIVEN a step that declared `edit` and, undeclared, called a tracker update tool WHEN its judge's view set is built THEN it holds the base read views and the tracker's read view

### GRD-B2 Outside call discards

WHEN a judge's tool log shows a name outside its view set, including a subagent call, a failed or refused call or an unnamed call THE guard SHALL discard the judgement as an unresolved gap at confidence 0.0 and the run SHALL escalate, a log with no actions because the executor reports none being `unavailable`, recorded and not discarded.

- GIVEN a view set `Read, Grep, Glob` WHEN the judge called `Read` and `Grep` THEN the guard is `clean`
- GIVEN the same view set WHEN the judge called a plugin-registered status tool or a call with no name THEN the judgement is discarded
- GIVEN an executor that reports no actions WHEN the guard runs THEN it is `unavailable` and the judgement stands

### GRD-B3 Workspace fingerprint

WHEN the workspace's head and status differ before and after the judge THE guard SHALL discard the judgement in an engine worktree and only warn in place, where another writer may exist.

- GIVEN an engine worktree whose status changed during the judge WHEN guarded THEN the judgement is discarded

### GRD-B4 Same session

WHEN a judge result's session id equals the step attempt's THE guard SHALL discard it.

- GIVEN a judge result reusing the step's session id WHEN guarded THEN it is discarded

### GRD-B5 Out of reach

WHEN an artifact kind's read view cannot be given by the judge executor (for example an MCP view deferred by `judge_mcp = false`, or a filtering MCP proxy that fails to start, recorded for that attempt) THE engine SHALL render the artifact out of reach with a fixed reason, the dependent criterion only UNVERIFIABLE or N/A, never MET.

- GIVEN a deferred tracker view WHEN the judge renders THEN the tracker artifact is out of reach and its criterion cannot be MET

### GRD-B6 Preflight reports deferrals

WHEN `validate` runs THE engine SHALL list per step which views are deferred on which judge executor and why, refuse a step that changes a system its judge cannot see unless its criteria mark that system unverified, and refuse a judge executor that declares `restricts_judge_tools = false`, the judge having to move.

- GIVEN a step that updates a wiki on a judge executor with no wiki view WHEN validated THEN it is refused unless its criterion marks the wiki unverified

### GRD-B7 View catalog

WHEN read views are looked up THE engine SHALL use a constant table per executor keyed by full tool name, no entry inferred from a name pattern or an MCP hint, mapping `edit`, `write` and workspace `shell` to `Read`, `Grep`, `Glob` on `claude` and `agent-sdk` (which shares Claude Code's rows), `read_file`, `search_files`, `list_files` on `messages-api` and `view_file`, `grep_search`, `list_dir`, `find_by_name` on `antigravity`; a tracker create or update tool to its `get_issue` read view, a wiki update tool to its `get_page` read view (on `messages-api` through the tool host, on `antigravity` per P-AG-6); and a `pull_request` artifact to read-only GitHub commands, opt-in, on each; add newer tracker and wiki tool names beside the old ones, never renaming, so a workflow pinned to an older server keeps its views; and map a generic write tool that can write to several systems to the union of their read views marked `partial`, its criterion MET only if every system it may have changed is in the view set; workflow data narrowing a view set and never widening it.

- GIVEN a generic tracker tool that can update two systems WHEN its views are looked up THEN both read views are listed and marked `partial`
- GIVEN a step that declares an MCP tool the catalog does not list WHEN its judge's view set is built THEN the set holds no view of that tool and the tool is recorded as deferred

### GRD-B8 Enforcement layers

WHEN a judge session starts THE engine SHALL apply, strongest first, judge-only credentials laid over the judge's environment on every executor (on `antigravity` a credentials profile in the session home); write tools absent from the session (`--tools`, strict MCP config and `--bare` on `claude`; `tools`, `strict_mcp_config` and `setting_sources=[]` on `agent-sdk`; only views offered on `messages-api`; an isolated home and deny rules on `antigravity`, probe-gated); calls refused by rule (`dontAsk` with allow rules on `claude`; an in-process gatekeeper hook with `dontAsk` on `agent-sdk`; the tool host refusing any other name on `messages-api`; a gatekeeper hook `deny` on `antigravity`, probe-gated); and always the guard after the session, `guard(views, judge_calls, before, after, workspace_mode, step_session_id, judge_session_id) -> GuardResult` with `status` `clean`, `discarded`, `warned` or `unavailable` and a reason; discarding a judgement that used a read-only command outside the engine's exact-option allow-list, the read-only GitHub commands needing operator opt-in, an executor that can restrict the shell and report actions, a judge-only token and an engine worktree.

- GIVEN a judge that ran `gh pr view --web` WHEN guarded THEN the judgement is discarded for an option outside the allow-list

### GRD-B9 Guard records

WHEN a judgement is guarded THE engine SHALL record in the run log the view set used and the guard status, and a discarded judgement SHALL never route PROCEED.

- GIVEN a discarded judgement WHEN the gate decides THEN the verdict is ESCALATE and the run log holds the view set and `discarded`

## Acceptance criteria

- GRD-AC1 (GRD-B1, GRD-B7): Every catalog entry is keyed by full executor tool name; a source test forbids pattern matching in the catalog
- GRD-AC2 (GRD-B2, GRD-B3, GRD-B4, GRD-B5, GRD-B6, GRD-B8): Each guard case is covered for every executor's tool names
- GRD-AC3 (GRD-B9): A discarded judgement never routes PROCEED
- GRD-AC4 (GRD-B9): The run log records, per judgement, the view set used and the guard status
- GRD-AC5 (GRD-B2): A planted subagent call in a judge stream is detected on the stream fixtures of every executor that maps `subagent`
- GRD-AC6 (GRD-B1, GRD-B7): A step that declares an MCP write tool the view catalog lists gives its judge that tool's read view and never the write tool itself, and a declared MCP tool the catalog does not list gives its judge no view and is recorded as deferred

## Open questions

- Should a refused (not executed) outside call void a complete verdict? Until answered: yes, any outside call voids the judgement, because the engine cannot always tell refused from executed across executors. Owner: engine owner.
- Not built yet: GRD-AC5 holds for `claude` on streams recorded on 2.1.330; the other executors are not built. Owner: engine owner.
