# R-035 Claude Code dynamic workflows as a model for orchestrating runs

## Problem statement

The owner asked for an orchestrator skill that manages many tempergraph runs "similar to dynamic workflows graphs": start, watch, sequence and parallelise runs, handle pauses and failures, and report. Claude Code's **dynamic workflows** are the reference. This note records how they behave, from public documentation, and what a Claude session that orchestrates runs by hand costs and gets wrong, so the [orchestration spec](../specs/45-orchestration.spec.md), the [orchestrator skill spec](../specs/46-orchestrator-skill.spec.md) and ADRs [0035](../adr/0035-orchestration-is-data-run-by-a-model-free-supervisor.adr.md) to [0039](../adr/0039-pauses-stay-with-the-person-failures-follow-node-policy.adr.md) rest on findings, not memory.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| "Orchestrate subagents at scale with dynamic workflows" | Official documentation | https://code.claude.com/docs/en/workflows.md (read in full) |
| "Introducing dynamic workflows in Claude Code" | Vendor blog, 2026-05-28 | https://claude.com/blog/introducing-dynamic-workflows-in-claude-code |
| "A harness for every task: dynamic workflows in Claude Code" | Vendor blog, 2026-06-02 | https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code |
| "Writing workflows in Claude Code: what they unlock and where they can bite you" | Third-party article | https://dev.to/tundraray/writing-workflows-in-claude-code-what-they-unlock-and-where-they-can-bite-you-7oo |
| Workflow tool description as served to a Claude Code session | Product text, local | This design session's tool list (2026-11-19) |

Read on 2026-11-19. Where the official page and a blog or article disagree, the official page is taken. Version numbers quoted by the documentation (for example v2.1.305) are minimum versions for a feature and were not checked against a changelog.

## Key findings

### What a dynamic workflow is

| # | Finding | Confidence |
|---|---|---|
| D1 | A dynamic workflow is a JavaScript script that orchestrates many subagents; Claude writes it and a **runtime executes it in the background**, apart from the conversation. Intermediate results stay in script variables, not in Claude's context. "A workflow moves the plan into code." | confirmed (docs, both blogs) |
| D2 | The script starts with `export const meta = { name, description, phases? }`, a pure object literal; each `phases` title must match a `phase()` call. The body uses `agent(prompt, opts)`, `parallel(tasks)` (a barrier: run all, wait for all), `pipeline(items, ...stages)` (each item moves through the stages without waiting for the whole list), `phase(title)`, `log(msg)` and a global `args`. | confirmed (docs, tool text) |
| D3 | `agent()` takes a `label`, an optional JSON `schema` for structured output (checked before start; a call fails after five invalid outputs) and a per-agent stall window `stallMs`. It resolves to `null` when stopped or on an unrecoverable API error; inside `parallel` and `pipeline` a failed slot is `null` and the run goes on, awaited directly it ends the run. | confirmed (docs) |
| D4 | The script has no filesystem, shell, network or module loading; agents do all tool work. `Date.now()`, `Math.random()` and `new Date()` throw, so a relaunch replays the same calls. There is **no user input mid-run**; the third-party article recommends returning a `needs_input` status instead. | confirmed (docs); `needs_input` supported (article) |

### Running, watching, stopping

| # | Finding | Confidence |
|---|---|---|
| D5 | `/workflows` lists running and finished runs and drills down: run, phase with agent counts, one agent's prompt, recent tool calls with their state, task list and result. Keys pause or resume the run, stop an agent or the whole run, restart a running agent, filter by status and save the run's script as a command. Token use per agent is shown live. | confirmed (docs) |
| D6 | Defaults: at most 16 agents at once (fewer on small machines; configurable 1 to 256), at most 4,096 items per `parallel` or `pipeline` call, at most 1,000 agents per run. | confirmed (docs) |
| D7 | A **size guideline** (small under 5 agents, medium under 10, large under 50, or unrestricted) is advice to the planner, not a cap. A "large workflow" warning appears above 25 agents or 1.5 million projected tokens; it does not pause the run. | confirmed (docs) |
| D8 | Starting a workflow shows an approval prompt with the planned phases and a "view raw script" choice; in non-interactive modes it goes through ordinary permission rules. A workflow runs only when the person asked for one or turned on a mode that plans them. | confirmed (docs, tool text) |
| D9 | Saved workflows live in a project folder (shared through git), a personal folder, or a plugin's `workflows/` folder, and run as a slash command with arguments. | confirmed (docs) |

### Failures, resume and cost

| # | Finding | Confidence |
|---|---|---|
| D10 | An agent whose output stops for its stall window is restarted from the same prompt, at most five times; the new attempt starts with a fresh transcript and files it already changed stay changed. | confirmed (docs) |
| D11 | Resume is **positional replay**: each `agent()` call either returns its saved result or runs again. The first call whose prompt differs from the previous run, and every call after it, runs again. A failed agent reruns together with every agent started after it, finished ones included; reordering two calls reruns both and everything after. | confirmed (docs) |
| D12 | A run does not continue after its session ends; it is relaunched by a new call with the same script, from results saved under the session directory. With no saved results a relaunch is refused. | confirmed (docs) |
| D13 | On a usage limit the run pauses (no new agents start) and continues by itself after the reset, under narrow conditions (interactive subscription session, reset within 24 h, at most two waits). | confirmed (docs) |
| D14 | Workflows "can use meaningfully more tokens" than the same task in conversation; the documentation advises trying a small slice first. | confirmed (docs, both blogs) |
| D15 | Agents with the same model, tools, schema and directory share a prompt-cache prefix; agent starts are staggered so later ones read the first one's cache. | confirmed (docs) |

### When a Claude session orchestrates runs by hand

| # | Finding | Confidence |
|---|---|---|
| B1 | One orchestrating session over five days (92 h, 1,372 calls) cost about $130, and its 19 helper agents about $147, $135 of it for merges: roughly 15 to 18% on top of about $1.5K of run cost. | supported (earlier runs, one session; only 12 of 30 runs fully priced) |
| B2 | 270 notifications woke that session; 148 calls came after five idle minutes and re-wrote its 117K-token context into the cache, about 62% of its own cost. | supported (earlier runs) |
| B3 | Parallel runs took the same new ids and version bumps: 33 conflict operations and 28 hand version bumps. | supported (earlier runs) |
| B4 | With the person away, the orchestrating session answered all 16 pauses; 13 were verify-and-continue, 3 were real decisions about intent, and one plan was resumed with proceed after its judge failed to start. | supported (earlier runs) |
| B5 | The accepted batch design keeps **intent** in a versioned file and **truth** in the engine's status, with an append-only event file, and re-attaches to live runs through the lock probe. | supported (earlier runs) |
| B6 | Three live runs in worktrees looked alike in the monitor; a person matched thread ids to worktrees from memory. | supported (earlier runs) |

## Conclusions

1. **Borrow: the plan lives outside the conversation and a runtime, not the model, drives it** (D1, B1, B2). The orchestrating conversation's cost comes from being woken and re-reading its context, not from deciding. An orchestration of tempergraph runs is data executed by a model-free engine process; the skill writes the plan, gets approval and reacts only when a person is needed.
2. **Borrow the vocabulary of the graph**: nodes with labels, phases that group nodes for display, a sequential dependency, a parallel barrier and a per-item pipeline (D2). In tempergraph they become `after` edges, `phase` labels and `map` nodes over a target list.
3. **Borrow the watching surface**: list, drill down, filter by status, per-node cost while running, pause intake, stop one node or all, save as a reusable template (D5, D9). The monitor plugin renders it; the engine must publish an orchestration status document for it.
4. **Borrow the advisory size guideline and large-run warning, but make the cap real** (D7, D14). tempergraph already has a run cost cap; an orchestration adds an aggregate cap checked before every node start, and a projected cost from past runs shown before approval.
5. **Borrow approval before start with the raw plan viewable** (D8), and saved templates with arguments (D9).
6. **Do not borrow positional replay** (D11). A failed or reordered call reruns finished work after it; for tempergraph a rerun is a paid run with a branch. Node identity is a stable node id mapped to a thread id, and a re-run skips nodes whose thread exists, as the batch already does ([WSP-B7](../specs/13-workspace-and-concurrency.spec.md)).
7. **Do not borrow "no input mid-run"** (D4, D12). tempergraph runs pause for people by design and may wait days ([DUR](../specs/09-durability-and-resume.spec.md)). The supervisor keeps independent nodes moving while one waits, and a pause is answered on that node alone.
8. **Do not borrow silent `null` slots** (D3). A failed tempergraph run has a cause and an exit code; each node declares what its failure does to its dependants, and the report never counts a failed node as done.
9. **Do not let an orchestrator answer gates** (B4). The person decides every pause; the orchestration records who answered, and an unattended mode stays reserved until the delegation policy exists ([HUM](../specs/07-gate-and-human.spec.md)).
10. **Restarts are the engine's, not the orchestrator's** (D10). Stalls and infra retries already live in the engine's budgets ([BUD](../specs/08-budgets-and-failures.spec.md)); the orchestrator only re-opens a run that ended on an infra cause, and only within a count the person set in advance.
11. **Shared resources need claims** (B3). Concurrent runs in one repository need a reservation for counters and version fields; this is deferred, and the orchestration refuses two concurrent nodes that declare the same exclusive resource.

## Open questions

| Question | Owner | How to settle |
|---|---|---|
| Should an orchestration also be startable from a Claude Code dynamic workflow (a plugin `workflows/` script that calls the engine)? Rejected for driving runs (ADR-0035); possibly useful as a thin launcher. | Owner | Revisit when the plugin ships its first workflow script. |
| What is the measured operator cost of the orchestrator skill, as a share of the run cost it orchestrates? | Implementer | First live orchestration of three or more runs; [OSK-AC4](../specs/46-orchestrator-skill.spec.md). |
| Does the default stall window of dynamic workflows matter for any part of this design? Not stated in the docs; the engine's own idle limit applies to tempergraph sessions. | — | No action. |
