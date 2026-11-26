# Tool surface audit

## Purpose

Tool access is the cause family most visible before a run ([research `why-runs-fail-stall-repeat-or-overspend`](../research/why-runs-fail-stall-repeat-or-overspend.rsrch.md) C4): most refused calls need no new permission, undeclared-tool calls are common, and one tool a user-level plugin puts into a judge session can void a complete verdict and pause a run. This spec defines how the [workflow audit](workflow-audit.spec.md) compares, for every step session and every judge session, three views of its tools ([ADR `tool-audit-compares-grant-need-and-use`](../adr/tool-audit-compares-grant-need-and-use.adr.md)): the grant (what the session can call), the need (what the work asks for) and the use (what sessions called and what was refused). A finding is a mismatch between two views; the rules join the catalog of [ARC](audit-rule-catalog.spec.md) under family C4. Judges matter most: a step's undeclared call costs a turn, a judge's voids a verdict, so judge rules use the session's own start tool list and fire before the first harmful call. Need is read by prompt lint's reader, so the audit and prompt lint never disagree on what a prompt asks for. The audit reads names only, sends nothing anywhere and writes nothing ([research `prior-art-for-workflow-audits`](../research/prior-art-for-workflow-audits.rsrch.md) P6). Workflow authors and the audit depend on it.

## Behaviours

### TSA-B6 Session surface

WHEN the audit builds a session's surface for a step or judge THE audit SHALL record `executor` (after cross-executor judging, [ADR `cross-executor-judging`](../adr/cross-executor-judging.adr.md)); `granted` (declared capabilities through the executor's tool map, declared commands and resolver output, MCP tools as `mcp:<server>/<tool>`, and for a judge the derived view set, [GRD](independence-guard.spec.md)); `commands` (declared prefixes and any resolver argv for the target); `ambient` (names the session would hold that nobody granted: plugin-registered tools and user MCP servers seen by the host probe, and any name in a recorded `session_started.tools` outside `granted`, a recorded name unknown to the tool map shown as `ambient`); `needed` (names in the session's template, brief, criteria and named skills, read by prompt lint's reader ([LIF-B12](lifecycle-and-evals.spec.md)), and those implied by artifact kinds produced and referenced, each with where it was found); `used` (per tool name: calls, ok, refused or denied, subagent calls, from history, [SSN](session-contract.spec.md)); `refusals` per class; and `enforced` (`enforces_step_tools` with enforcement on, or `restricts_judge_tools`).

- GIVEN a recorded tool name the tool map does not know WHEN the surface is built THEN it is `ambient`

### TSA-B7 Refusal classes

WHEN a refused call is classified THE audit SHALL use only its tool name and, where recorded, its scrubbed input summary, never model text: `shell_for_read` (a shell call whose program is `cat`, `head`, `tail`, `grep`, `rg`, `find`, `ls` or `sed -n` while file tools are granted), `dir_change_then_command` (a shell call starting with a directory change and running another program), `outside_workspace` (a path argument resolving outside the workspace), `undeclared_tool` (a name not in `granted`), `needed_command` (any other refused program the step's text asks for), and `unclassified` when no input summary was recorded, never dropped.

- GIVEN refusals with no input summary WHEN classified THEN they count as `unclassified`

### TSA-B8 The matrix

WHEN `audit tools <workflow> [--executor <name>]` runs THE audit SHALL print instead of findings one row per session (`<unit>` or `<unit>:judge`) and tool (executor tool name and capability), with `Granted` (`yes`, `no`, `ambient`), `Needed` (`yes` with the place, or `no`), `Used` (calls and refused, or `—` without history) and `Verdict` (`ok`, `missing`, `unused`, `exposed`, `refused`, `drift`).

- GIVEN a granted tool never named or called WHEN the matrix prints THEN its verdict is `unused`

### TSA-B5 Without history

WHEN `audit tools` runs for a new workflow THE audit SHALL show `—` in every `Used` cell and list the history rules as skipped.

- GIVEN no runs WHEN `audit tools` runs THEN every `Used` cell is `—`

### TSA-B3 Same matrix on every executor

WHEN `audit tools --executor <name>` runs for each executor on a step declaring `read`, `search` and `shell` with prefix `pytest` THE audit SHALL produce rows that differ only in the executor tool names of each tool map, with the same capability-only findings.

- GIVEN `claude` WHEN the matrix prints THEN `shell` maps to `Bash`, enforced only with `--enforce-tools`, and `not-enforced` fires without it
- GIVEN `agent-sdk` WHEN the matrix prints THEN `shell` maps to `Bash`, enforced
- GIVEN `messages-api` WHEN the matrix prints THEN `shell` maps to `run_command` of the tool host, enforced by construction
- GIVEN `antigravity` WHEN the matrix prints THEN `shell` maps to `run_command`, enforced per probe

### TSA-B9 Judge rules

WHEN judge surfaces are audited THE audit SHALL fire `judge-exposed-tool` (history, error/high, `judge_exposed`) when a judge session's reported start tool list holds a name outside its view set, called or not (remove the source: disable the plugin's tool in headless sessions or narrow the judge's setting sources; F4.5); `judge-ambient-tool` (host, warning/medium, `judge_exposed`) when the host probe lists a plugin tool or user MCP server a judge on this executor would hold, skipped with reason `probe cannot list` when the probe cannot list plugin tools; and render `judge-view-missing` from validation ([WFM](workflow-model.spec.md)) when a referenced artifact kind or declared MCP tool has no read view for the judge's executor.

- GIVEN a probe that cannot list plugin tools WHEN the host layer runs THEN `judge-ambient-tool` is skipped with `probe cannot list` and history rules still run

### TSA-B1 A judge exposed before any call

WHEN the audit runs history for a judge on `claude` whose recorded `session_started.tools` in two runs include `mcp__monitor__status`, outside its view set, with no call to it THE audit SHALL fire `judge-exposed-tool` at `error` with the tool name and the two runs.

- GIVEN that ambient tool never called WHEN audited THEN `judge-exposed-tool` fires naming it and both runs

### TSA-B10 Grant and need rules

WHEN the definition layer runs THE audit SHALL fire `mcp-tool-not-in-catalog` (warning/high, `unknown_tool_name`) for a declared `mcp:<server>/<tool>` the view catalog does not classify (its judge gets no view; F4.6); render `needed-not-granted` from validation (an error in `stable` mode); fire `artifact-needs-write` (error/high, `grant_missing`) when a step produces `tracker_issue`, `wiki_page` or `pull_request` and declares no tool that can write it (F4.4); `shell-without-commands` (error/high, `grant_missing`) when `shell` is declared with no prefix; `dir-change-in-commands` (error/high, `dir_change`) when a prefix, a resolver argv or the text tells the step to change directory before a command (`cd … &&`; use `git -C`; F4.2, 58 of 59 refused); `shell-for-read-likely` (warning/medium, `shell_for_read`) when `shell` is declared beside `read` or `search` and the text says to read or search through shell programs; `path-outside-workspace` (warning/medium, `outside_workspace`) for an absolute or parent path outside the workspace in the text or a prefix; `granted-not-needed` (info/low, `over_grant`) for a capability or MCP tool named nowhere and implied by no artifact kind (F4.9); and `not-enforced` (info/high, `not_enforced`) when a step's executor cannot enforce its grant and the workflow does not ask for strict permissions.

- GIVEN `shell` declared with no prefix WHEN audited THEN `shell-without-commands` fires

### TSA-B4 Need comes from text and artifacts

WHEN the definition layer runs on a step that produces `tracker_issue` and declares only `read` and `edit` THE audit SHALL fire `artifact-needs-write` naming the artifact key.

- GIVEN that step WHEN audited THEN `artifact-needs-write` names the key

### TSA-B11 Use rules

WHEN the history layer runs THE audit SHALL fire `granted-never-used` (warning/high, `over_grant`, `min_n` 10 runs) for a declared tool or MCP server with no call in the window; `undeclared-calls` (warning/high, `undeclared_tool`, `min_n` 5 runs) when calls outside `granted` average at least 0.25 per run, naming the tool and steps (F4.3); `refusals-by-class` (warning/high, per class, `min_n` 5 runs) when a session's refusals average at least 1 per run, the evidence counting each class and the remedy giving per class: file tools, explicit directory, workspace paths, declare the command, declare the tool; and `granted-at-run` (warning/high, `grant_missing`, `min_n` 2) when a person's tool grant ([RST](run-settings-and-overrides.spec.md)) was given and then used on the step in at least 2 runs, so the package should declare it.

- GIVEN a grant used on one step in 2 runs WHEN audited THEN `granted-at-run` fires

### TSA-B2 Refusals sorted, not just counted

WHEN the audit runs over 10 runs of step `discovery` with 14 refusals whose summaries are 7 `grep` calls, 4 `cd … && git` calls and 3 `npm run build` THE audit SHALL fire `refusals-by-class` with `shell_for_read` 7, `dir_change_then_command` 4 and `needed_command` 3, listing the fixes in that order.

- GIVEN those refusals WHEN audited THEN the remedy says to use the file tools, then `git -C <dir>`, then to declare `npm run build` or add it to the resolver

### TSA-B12 Host rules

WHEN the host layer runs THE audit SHALL fire `skill-name-clash` (warning/high, `skill_clash`) when a skill or agent the step names by bare name exists in more than one installed plugin (name it by plugin path; F4.8); `mcp-server-not-configured` (error/high, `environment_missing`) when a declared `mcp:<server>` has no entry of that exact name in the operator's own configuration, a project file never being read; `declared-tool-stale` (warning/high, `unknown_tool_name`) when a declared `mcp:` tool or mapped executor tool is marked renamed or retired by the view catalog or the executor's compatibility table, giving the new name (text still using the old name being [PRA](prompt-audit.spec.md)'s `tool-name-stale`); and `tool-set-drift` (warning/medium, `unknown_tool_name`) when the names an executor or MCP server exposes now differ from those recorded at the last stamp ([SIL-B4](self-improvement.spec.md)).

- GIVEN a declared `mcp:tracker` missing from the operator's configuration WHEN audited THEN `mcp-server-not-configured` fires

### TSA-B13 Widening is marked

WHEN a remedy would add a grant (a new command or tool) THE audit SHALL mark it as widening in the report for a person to decide, a remedy that removes a grant being plain advice.

- GIVEN `artifact-needs-write` WHEN reported THEN its remedy is marked widening

### TSA-B14 An undeclared skill call is friction

WHEN a step session calls a skill that its step does not declare, whether the session ran it or the CLI refused it THE session digest SHALL list the skill under `skills_undeclared`, and the session review SHALL report the cause `skill_undeclared:<skill>` as a fault of the workflow, of the same class as a refused permission.

- GIVEN a step declaring `skill:notes:alpha` whose session calls `notes:alpha` and a skill bundled with the CLI WHEN the digest is built THEN `skills_undeclared` lists only the bundled skill and the review reports its cause
- GIVEN a judge session WHEN its digest is built THEN `skills_undeclared` is empty

## Acceptance criteria

- TSA-AC1 (TSA-B9, TSA-B10, TSA-B11, TSA-B12): Every C4 rule has a fixture that raises it and a clean fixture that does not
- TSA-AC2 (TSA-B1, TSA-B6): TSA-B1 holds on a recorded fixture with an ambient tool that was never called
- TSA-AC3 (TSA-B7, TSA-B2): Refusal classification uses only tool names and scrubbed input summaries; a source test fails if it reads model text
- TSA-AC4 (TSA-B3, TSA-B8): The matrix of TSA-B3 is produced for all four executors from their tool map alone
- TSA-AC5 (TSA-B13): Each widening remedy is marked as widening in the report
- TSA-AC6 (TSA-B4, TSA-B5): A step producing a tracker issue with no write tool is found, and a workflow with no history shows `—` and skipped history rules

- TSA-AC7 (TSA-B14): A fixture step session that calls one declared and one undeclared skill gives a digest whose `skills_undeclared` holds only the undeclared one and a `skill_undeclared:<skill>` cause

## Open questions

- Can the `claude` and `agent-sdk` probes list plugin-registered tools without starting a model session? `judge-ambient-tool` (TSA-B9) waits on this probe fact. Owner: executor implementer ([ECC](executor-claude-code.spec.md)).
- Should `granted-never-used` become `error` in `stable` mode, as the prompt-tool check does? Owner: owner.
