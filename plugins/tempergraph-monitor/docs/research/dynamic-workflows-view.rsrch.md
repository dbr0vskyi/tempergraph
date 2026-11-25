# Claude Code's dynamic workflows view, and what tempergraph adds to it

## Problem statement

The owner wants the monitor to show a tempergraph run "in same way how it is done for dynamic workflows" and to "combine the best sides of both". This note records how Claude Code shows a running dynamic workflow, then sets that view beside what a tempergraph run has, so the monitor's design borrows the interaction and adds only what tempergraph needs.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Claude Code docs, workflows | Vendor documentation | https://code.claude.com/docs/en/workflows.md |
| "A harness for every task: dynamic workflows in Claude Code" (2026-06-02) | Vendor blog | https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code |
| The workflow-authoring reference bundled with Claude Code 2.1.329 | Vendor reference shipped with the build | Read in the design session, 2026-11-19 |
| Engine design set | This repository | [engine overview](../../../tempergraph/docs/specs/overview.spec.md), [OBS](../../../tempergraph/docs/specs/observability-and-cost.spec.md) |

## Key findings

### How the workflows view works

| # | Finding | Confidence |
|---|---|---|
| F1 | `/workflows` opens the view; with one run it opens directly, otherwise a run list. A one-line summary sits under the prompt in a task panel. | supported |
| F2 | The progress view shows "each phase with its agent counts"; drilling in shows a phase's agents and results; agent detail shows "the agent's prompt, its recent tool calls, and its result", each call with its state. | supported |
| F3 | Keys: `↑/↓` select, `Enter`/`→` drill in, `Esc`/`←` back, `j/k` scroll, `f` filter by status, `p` pause or resume, `x` stop the agent or the run, `r` restart an agent, `s` save the script as a command. | supported |
| F4 | A script's `log()` writes a line above the phases; `phase()` groups agents; `agent(…, {label})` names a row. | confirmed |
| F5 | Token usage per agent is shown as the run progresses; no money figure or elapsed time per agent is described. | supported |
| F6 | Scripts and saved results are kept under the session's directory in `~/.claude/projects/`; resume replays completed agents up to the first changed or failed one. | supported |
| F7 | On desktop the progress view appears in a background tasks side pane. | supported |
| F8 | The docs describe no event or hook API for workflow progress, no gates or judges as runtime parts, no cost in money and no cross-machine view. | supported |

### Side by side

| Concern | Workflows view | A tempergraph run | Monitor takes |
|---|---|---|---|
| Entry and navigation | Run list, drill with arrows, Esc back | — | The same keys and levels ([MRV §2.2](../specs/run-view.spec.md)) |
| Structure shown | Phases with agent counts | A declared graph: units in order, loop-backs, maps, forks, switches, human gates | The graph in plan order, with trips back drawn |
| One step's anatomy | An agent: prompt, tool calls, result | Four nodes: step session, deterministic check, judge session, gate verdict | A node strip `S C J G` per unit and per attempt |
| Why work repeats | Restart by a person, or the script's loop | A judge's blockers and the engine's verdict, bounded by budgets | Judge criteria, blockers with evidence and fix, budgets |
| Narration | `log()` lines | Gate verdicts, routes, retries, pauses as run-log records | Narrator lines from the detail document's events tail |
| Live tool view | Recent tool calls | Activity journal with command summaries; process group | Calls tab, Now tab, Processes tab |
| Cost | Tokens per agent | Reported and estimated cost apart, completeness, caps | Cost tab and `est`/`rep` everywhere |
| Control | Pause, stop, restart, from the view | Pauses only at gates and only a person decides; no skip | Prompt fills for resume and stop; no pause, skip or restart |
| Durability | Resume by relaunch within the session | Checkpointed threads that survive days, any session, any machine | Runs listed from engine documents, independent of the session |
| Scope | One session | Many runs, repositories, machines | Repo, machine and fleet scopes |

## Conclusions

1. The workflows view's navigation (levels, arrow keys, filter, narrator lines, per-agent recent calls) is the part to copy unchanged; a person who knows one knows the other.
2. tempergraph's additions are structural (graph, four nodes, trips back), evaluative (checks, judges, verdicts, budgets), economic (money, honesty flags) and spatial (many runs, machines).
3. Controls are where the two differ by principle: tempergraph has no pause, skip or restart for an observer, because decisions belong to gates and to people ([engine ADR `stop-verb-as-the-only-observer-control`](../../../tempergraph/docs/adr/stop-verb-as-the-only-observer-control.adr.md)).
4. The workflows view's data lives in the session; tempergraph's lives in the engine's store, so the monitor works across sessions and after a crash.

## Open questions

| Question | Owner |
|---|---|
| Should the monitor offer "save as command" analogous to `s`, e.g. saving a run's options as a reusable start command? Not designed. | Owner |
