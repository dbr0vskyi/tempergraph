---
title: Tool surface audit
type: component
status: review
prefix: TSA
adrs: [0052, 0051, 0013]
---

# Tool surface audit

## 1. Overview

Tool access is the cause family most visible before a run ([R-050 C4](../research/R-050-why-runs-fail-stall-repeat-or-overspend.rsrch.md)): of 190 recorded refusals, 72% needed no new permission, 43 undeclared-tool calls came in 14 days, and one tool a user-level plugin put into a judge session voided a complete verdict and paused a run at $24.37. This spec defines how the [workflow audit](55-workflow-audit.spec.md) compares, for **every step session and every judge session**, three views of its tools ([ADR-0052](../adr/0052-tool-audit-compares-grant-need-and-use.adr.md)):

| View | Question | Source |
|---|---|---|
| **Grant** | What can the session call? | Declared capabilities through the executor's `tool_map`, declared commands and resolver output, MCP tools; for a judge, the derived view set ([GRD](06-independence-guard.spec.md)); plus what the host adds that nobody declared |
| **Need** | What does the work ask for? | Tool, command, skill and MCP names in the template, brief, criteria and the skills the step names (prompt lint's reader, [LIF](18-lifecycle-and-evals.spec.md)); artifact kinds produced (a `tracker_issue` needs a tracker write) and referenced (a judge needs a read view) |
| **Use** | What did sessions actually call, and what was refused? | Recorded `tool_calls`, `denied` events and the tool list each session reported at start ([CON §2.6, §2.7](01-contracts.spec.md)); refusal shapes from the activity journal where present (spec 30, PR 7) |

A finding is a mismatch between two views. The rules are in §2.4; they join the catalog of [ARC](56-audit-rule-catalog.spec.md) under family C4.

## 2. Contract

### 2.1 Session surface

```python
def surface(unit: str, role: Literal["step", "judge"], spec: WorkflowSpec, ctx: AuditContext) -> Surface: ...
```

| Field | Meaning |
|---|---|
| `executor` | The executor the session binds to, after cross-executor judging ([ADR-0013](../adr/0013-cross-executor-judging.adr.md)) |
| `granted` | Set of `(capability, executor tool name)`; MCP tools as `mcp:<server>/<tool>` |
| `commands` | Declared prefixes and, where a resolver exists, the argv it returns for the target |
| `ambient` | Tool names the session would hold that nobody granted: plugin-registered tools and user MCP servers seen by the host probe, and any name in a recorded `session_started.tools` outside `granted` |
| `needed` | Names found in the session's model-facing text and implied by artifact kinds, each with where it was found |
| `used` | Per tool name: calls, ok, refused or denied, subagent calls; from history |
| `refusals` | Count per refusal class (§2.2) |
| `enforced` | Whether the executor enforces the grant for this session (`enforces_step_tools` with enforcement on, or `restricts_judge_tools`) |

### 2.2 Refusal classes

Classified from the refused call's tool name and, where recorded, its scrubbed input summary; never from model text.

| Class | Shape | R-050 share |
|---|---|---|
| `shell_for_read` | A shell call whose program is a reader or searcher (`cat`, `head`, `tail`, `grep`, `rg`, `find`, `ls`, `sed -n`) while file tools are granted | 43% |
| `dir_change_then_command` | A shell call that starts with a directory change and runs another program | 18% |
| `outside_workspace` | A path argument that resolves outside the workspace | 11% |
| `undeclared_tool` | A call to a tool name not in `granted` | 9% |
| `needed_command` | A refused program not in the above, that the step's text asks for | 19% |
| `unclassified` | No input summary recorded | — |

### 2.3 The matrix (`audit tools`)

`audit tools <workflow>` prints one row per session and tool name instead of findings:

| Column | Values |
|---|---|
| Session | `<unit>` or `<unit>:judge` |
| Tool | Executor tool name and its capability |
| Granted | `yes`, `no`, `ambient` |
| Needed | `yes` with the place, or `no` |
| Used | calls / refused, or `—` without history |
| Verdict | `ok`, `missing`, `unused`, `exposed`, `refused`, `drift` |

### 2.4 Rules (family C4)

| id | layer | sev / conf | cause | Fires when | Remedy |
|---|---|---|---|---|---|
| `judge-exposed-tool` | history | error / high | `judge_exposed` *new* | A judge session's reported start tool list holds a name outside its view set, whether or not it was called | Remove the source (disable the plugin's tool in headless sessions, or narrow the judge's setting sources); one call voids the verdict (F4.5) |
| `judge-ambient-tool` | host | warning / medium | `judge_exposed` *new* | The host probe lists a plugin-registered tool or user MCP server that a judge session on this executor would hold | As above, before any run |
| `judge-view-missing` | definition | per owner | — | A referenced artifact kind or a declared MCP tool has no read view for the judge's executor | owner: [WFM §2.1](02-workflow-model.spec.md) judge view rows |
| `mcp-tool-not-in-catalog` | definition | warning / high | `unknown_tool_name` | A step declares `mcp:<server>/<tool>` that the view catalog does not classify | Use a catalogued name or add it to the catalog; until then its judge gets no view and dependent criteria are UNVERIFIABLE (F4.6) |
| `needed-not-granted` | definition | per owner | — | The text names a tool or command the step does not declare | owner: [WFM §2.2](02-workflow-model.spec.md) (error in `stable` mode) |
| `artifact-needs-write` | definition | error / high | `grant_missing` *new* | A step produces an artifact kind (`tracker_issue`, `wiki_page`, `pull_request`) and declares no tool that can write it | Declare the system's write tool (F4.4: tracker tool not granted, escalation loop) |
| `shell-without-commands` | definition | error / high | `grant_missing` *new* | `shell` is declared and no command prefix is | Declare the prefixes the step runs, or drop `shell`; every call would be refused |
| `dir-change-in-commands` | definition | error / high | `dir_change` *new* | A declared prefix, a resolver argv or the template text tells the step to change directory before a command (`cd … &&`, "change directory, then run") | Run with an explicit directory option (`git -C`), never a directory change (F4.2: 58 of 59 refused) |
| `shell-for-read-likely` | definition | warning / medium | `shell_for_read` *new* | `shell` is declared beside `read` or `search`, and the text tells the step to read or search through shell programs | Tell it to use the file tools; keep shell for the declared commands (F4.1: 43%) |
| `path-outside-workspace` | definition | warning / medium | `outside_workspace` *new* | The text or a prefix holds an absolute path or a parent path outside the workspace | Use workspace-relative paths; reads and writes outside are refused (F4.1: 11%) |
| `granted-not-needed` | definition | info / low | `over_grant` *new* | A declared capability or MCP tool is named nowhere in the step's text and implied by no artifact kind | Drop it if nothing needs it: each MCP server costs start time and context (F4.9) |
| `granted-never-used` | history | warning / high | `over_grant` *new* | A declared tool or MCP server had no call in the window; `min_n` 10 runs | Drop it; least privilege and a lighter session |
| `undeclared-calls` | history | warning / high | `undeclared_tool` | Calls outside `granted` average ≥ 0.25 per run; `min_n` 5 runs | Declare the tool or forbid it in the text; the report names the tool and steps (F4.3: 0.75 per run) |
| `refusals-by-class` | history | warning / high | per class | A session's refusals average ≥ 1 per run; `min_n` 5 runs. Evidence lists counts per §2.2 class | Per class: file tools, explicit directory, workspace paths, declare the command, declare the tool |
| `skill-name-clash` | host | warning / high | `skill_clash` *new* | A skill or agent the step names by bare name exists in more than one installed plugin | Name it by plugin path (F4.8) |
| `mcp-server-not-configured` | host | error / high | `environment_missing` *new* | A declared `mcp:<server>` has no entry of that exact name in the operator's own configuration | Add the server; a project file is never read |
| `tool-set-drift` | host | warning / medium | `unknown_tool_name` | The tool names an executor or MCP server exposes now differ from those recorded when the workflow was last stamped | Re-run validation and the stamp; a renamed tool loses its judge view (SIL-B4) |
| `not-enforced` | definition | info / high | `not_enforced` *new* | A step's executor cannot enforce its grant and the workflow does not ask for strict permissions | Expect undeclared calls to run and be recorded; consider `--strict-permissions` ([CLI §2.1](17-engine-cli.spec.md)) |

## 3. Behaviours

**TSA-B1 A judge exposed before any call.** Given a judge on `claude` whose recorded `session_started.tools` in two runs include `mcp__monitor__status`, outside its view set, and no call to it, when the audit runs history, then `judge-exposed-tool` fires at `error` with the tool name and the two runs.

**TSA-B2 Refusals sorted, not just counted.** Given 10 runs of step `discovery` with 14 refusals whose summaries are 7 `grep` calls, 4 `cd … && git` calls and 3 `npm run build`, when the audit runs, then `refusals-by-class` fires with `shell_for_read` 7, `dir_change_then_command` 4, `needed_command` 3, and the remedy lists the three fixes in that order.

| Class | Count | Remedy |
|---|---|---|
| `shell_for_read` | 7 | Say to use the file tools |
| `dir_change_then_command` | 4 | Use `git -C <dir>` |
| `needed_command` | 3 | Declare `npm run build` or add it to the resolver |

**TSA-B3 Same matrix on every executor.** Given a step declaring `read`, `search`, `shell` with prefix `pytest`, when `audit tools --executor <name>` runs for each executor, then the rows differ only in the executor tool names from each `tool_map`; findings that depend only on capabilities are the same.

| Executor | `shell` maps to | Enforced | `not-enforced` |
|---|---|---|---|
| claude | `Bash` | with `--enforce-tools` | yes, without it |
| agent-sdk | `Bash` | yes | no |
| messages-api | `run_command` (tool host) | yes, by construction | no |
| antigravity | `run_command` | per probe | per probe |

**TSA-B4 Need comes from text and artifacts.** Given a step that produces `tracker_issue` and declares only `read` and `edit`, when the definition layer runs, then `artifact-needs-write` fires naming the artifact key.

**TSA-B5 Without history.** Given a new workflow, when `audit tools` runs, then the `Used` column is `—` for every row and the history rules are listed as skipped.

## 4. Error conditions

| Condition | Result |
|---|---|
| An executor's probe cannot list plugin tools | `judge-ambient-tool` skipped with reason `probe cannot list`; history rules still run |
| A recorded tool name is unknown to the executor's `tool_map` | Shown as `ambient`; `tool-set-drift` may fire |
| No input summaries recorded | Refusals counted as `unclassified`; never dropped |

## 5. Design notes

- **Judges matter most.** A step's undeclared call costs a turn; a judge's voids a verdict and pauses a run. So the judge rules use the session's own start tool list, which every executor reports ([CON §2.7](01-contracts.spec.md)), and fire before the first harmful call ([ADR-0052](../adr/0052-tool-audit-compares-grant-need-and-use.adr.md)).
- **Need is read, not guessed.** The names in a template come from prompt lint's reader, so the audit and prompt lint never disagree on what a prompt asks for.
- **No content leaves the machine.** Unlike scanners that send tool descriptions to a service ([R-051 P6](../research/R-051-prior-art-for-workflow-audits.rsrch.md)), the audit reads names only and writes nothing.

## 6. Acceptance criteria

- [ ] TSA-AC-1 Every rule in §2.4 has a fixture that raises it and a clean fixture that does not.
- [ ] TSA-AC-2 TSA-B1 holds on a recorded fixture with an ambient tool that was never called.
- [ ] TSA-AC-3 Refusal classification uses only tool names and scrubbed input summaries; a source test fails if it reads model text.
- [ ] TSA-AC-4 The matrix of TSA-B3 is produced for all four executors from their `tool_map` alone.
- [ ] TSA-AC-5 Each widening remedy is marked as widening in the report.

## Open questions

| Question | Owner |
|---|---|
| Should `granted-never-used` become `error` in `stable` mode, as the prompt-tool check does? | Owner |

## References

