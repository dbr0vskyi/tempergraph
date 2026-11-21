---
title: Compiler and flow
type: component
status: ready-for-implementation
prefix: CMP
adrs: [0002, 0004, 0062, 0079]
---

# Compiler and flow

## 1. Overview

The compiler turns a validated workflow into a LangGraph `StateGraph` with **four nodes per unit** (step, judge, gate, human), one finalizer node and static edges for every target the workflow names. Every unit kind keeps those four nodes; for a council or a contest the step node is a compiled subgraph of sessions with an engine-owned barrier ([ADR-0062](../adr/0062-new-node-kinds-keep-the-gated-unit.adr.md)). The whole topology exists before the run, so validation can check reachability and the diagram can be drawn from the same model. Contract C5 is owned here: gates, routes and joins are pure and safe to re-run; the judge and the gate run once.

## 2. Contract

```python
def compile(spec: WorkflowSpec, checkpointer: BaseCheckpointSaver) -> CompiledGraph: ...
def successors(spec: WorkflowSpec, unit: str) -> SuccessorSet: ...   # one answer to "where can this unit go"
def node_names(unit: str) -> tuple[str, str, str, str]: ...           # shared by compiler and diagram model
```

`SuccessorSet` lists, per routing token, the target nodes: `PROCEED` → next unit, route target, switch arm or finalizer; `RETRY` → the unit's step node; `BACK` → each listed earlier unit; `ESCALATE` → the unit's human node; `STOP` → end. The human node's edges are the same without `ESCALATE`, plus `rewind:<unit>` → the step node of every earlier unit in `order` ([RRN §2.3](81-reruns-and-feedback.spec.md)). Node names are `<unit>.step`, `<unit>.judge`, `<unit>.gate`, `<unit>.human` and `finalizer`.

### 2.1 Nodes of one unit

| Node | Does | Never does |
|---|---|---|
| step | Renders the prompt, resolves alias and limits for this attempt, calls the executor, records usage | Grade the output |
| judge | Runs the check, then (if the check did not fail) the judge session and its one re-ask, then the guard, then derives and stores the verdict | Pause |
| gate | Reads the stored judgement, applies budgets and policy, writes a routing token and, when needed, a pause payload | Call a model, pause |
| human | First statement: `interrupt(payload)`. After it: applies the decision once | Log, spend or write before the interrupt |

### 2.2 Flow primitives

| Primitive | Behaviour and limits |
|---|---|
| Order | A pass goes to the next unit in `order`. |
| Route | A pure function of state picks one static forward target or the finalizer, in the gate node, before any approval pause. A raise or a non-target stops the run; it never falls back to `order`. |
| Switch | A named route with arms (unit, finalizer, map or parallel block) and a default arm taken on any predicate fault. The arm is sticky per visit or per run. An operator may pick the arm at start (`--arm <switch>=<arm>`), validated against the declared arms; every pick, by predicate, default or operator, is written as a `route` record ([OBS](15-observability-and-cost.spec.md)). Shadow mode, per-arm overrides and re-arming: [SWM](79-measured-switches.spec.md). |
| Back-edge | Starts a new visit of the target and of each unit after it on the path, clears their judgements and artifacts, and hands the target the reason. |
| Parallel | Two or more read-only branches and an engine-owned AND-join that fires only when every branch has passed. A branch declared as a writer runs in its own worktree and is merged at the join ([WSP](13-workspace-and-concurrency.spec.md)). |
| Map | One subgraph per item of a list artifact (default at most 20, at most 50), each item gated on its own, results collected by item id; no back-edge from an item. The sequential form runs items in turn in the run's own worktree, each in a fresh session. Declaration and per-item rules: [MAP](77-map-unit.spec.md). |
| Sub-workflow | A registered workflow compiled as a subgraph under the parent's checkpointer; its artifacts go to the unit's own gate; depth at most three; no recursion; no meta child. |
| Event wait | No model and no judge; arms once, then pauses until a delivered event passes its pure check. Main chain only. An optional deadline marks it overdue ([FLX §2.3](74-flow-extensions.spec.md)). |
| Selective parallel, mapped sub-workflow, fallback, breakpoint | [FLX](74-flow-extensions.spec.md). |
| Outcome gate | A reserved unit `outcome` compiled after every unit and before the finalizer, so every path to the finalizer passes it; its step node assembles the subject and starts no session; its back targets are derived from the outcome's `serves` links ([OUT §2.4](90-run-outcome.spec.md)). |

#### Step-node forms per kind

| Kind | Step node runs | Owner |
|---|---|---|
| `step`, `map`, `subworkflow` | One step session (per item for a map; the child graph for a sub-workflow) | this spec |
| `script` | A command or callable, no session; hybrid steps run scripts around the session | [SCR](70-script-units-and-hybrid-steps.spec.md) |
| `council` | Subgraph: member sessions per round, a round barrier, a pure tally, a chair | [CNL](71-council-unit.spec.md) |
| `contest` | Subgraph: candidate slots as items, each checked and judged, then a pure pick | [CTS](72-contest-unit.spec.md) |
| `ask`, `wait` | Nothing; the human node pauses | [ASK](73-ask-unit.spec.md), [HUM](07-gate-and-human.spec.md) |

### 2.3 State

State is JSON, one level deep, merged by reducers ([DUR](09-durability-and-resume.spec.md)). Channels written by units that can run in one superstep (routing token, pause payload, judge notes, human feedback) are keyed by unit. One reducer deletes: an artifact written as nothing is removed, which is how a trip back clears.

## 3. Behaviours

**CMP-B1 Retry is an edge.** Given a gate that derives RETRY with budget left, when it routes, then control returns to the unit's step node over a conditional edge; no node loops internally.

**CMP-B2 Resume replays only the human node.** Given a run paused at a gate, when it is resumed, then only the human node runs again from its top; the judge and gate nodes are not re-entered and no judge session starts.

**CMP-B3 Route fault stops.** Given a route function that raises, when the gate runs it, then the run stops with exit 4 naming the route, and the next unit in `order` does not start.

**CMP-B4 AND-join waits for passes.** Given a parallel block with branches A and B, when A passes and B retries, then the join does not fire until B passes; a B that stops stops the block.

**CMP-B5 Attempt cap in nodes.** Given an attempt cap of 15 per invocation, when the 16th attempt would start, then the scheduling node requests a drain and the run stops cleanly before that attempt; the recursion limit is only a backstop.

**CMP-B6 Diagram equals graph.** Given a compiled workflow, when the diagram model is generated, then its nodes and edges equal the compiled graph's in both directions.

| Workflow declares | Nodes | Conditional edges from gate |
|---|---|---|
| Order of 2 steps | 8 + finalizer | PROCEED, RETRY, ESCALATE, STOP per unit |
| + `back_targets: [a]` on b | same | + BACK b→a |
| + route on a to {b, finalizer} | same | PROCEED a→b, a→finalizer |

**CMP-B7 Operator arm override.** Given a switch `mode` with arms `light` and `full` whose predicate would pick `full`, when the run starts with `--arm mode=light`, then `light` runs, the route record says `chosen_by = operator`, and an arm name not declared is refused with exit 2 before spend.

## 4. Error conditions

| Type | Handling |
|---|---|
| Two writes to a single-value channel in one superstep | Prevented by per-unit channels; a test fails if any channel lacks a two-writer reducer |
| Unknown routing token from a gate | Engine error record; exit 1 |
| Sub-workflow child paused | The parent is paused; the pause is addressed by unit and item |

## 5. Design notes

- Four nodes, not one, because LangGraph restarts a paused node from its top on resume ([ADR-0004](../adr/0004-four-nodes-per-unit.adr.md)).
- Edges are static so the engine never pays for work the author did not choose; position in `order` is never a fallback.
- An engine-owned join replaces LangGraph's deferred node, which cannot tell a stopped branch from a finished one.
- LangGraph features left out on purpose: a node routing itself or its parent with `Command`, `RetryPolicy` on model and judge nodes, `defer`, and the functional API; each conflicts with C4, C5, C6 or workflows as data. The capability-by-capability comparison is [R-060](../research/R-060-node-types-against-langgraph.rsrch.md).
- Per-call values (alias, timeout, session options) go to the executor for that call only, never into graph state or the checkpoint.
- **As built (R2-T7).** A parallel block is a unit of kind `parallel` naming its branches, which stand just before it in `order`. The compiler adds `<join>.fork` and one `<branch>.done` per branch, and the join's step node waits on every `done` node, so it fires once, after every branch has passed (CMP-B4). Branches are read-only steps: a branch that changes the workspace fails `branch_changed_the_workspace`. The join is engine-owned and takes no check or judge; a trip back to the block clears and runs every branch again. Branch state is merged by reducers (path union, cost by delta). Writer branches and selective parallel are release 3.

## 6. Acceptance criteria

- [ ] CMP-AC-1 Every unit compiles to exactly four nodes named by `node_names`.
- [ ] CMP-AC-2 A resume of a paused run starts no judge session and writes no duplicate log record.
- [ ] CMP-AC-3 Each primitive of §2.2 has an offline test with scripted executors and a scratch git repository.
- [ ] CMP-AC-4 The diagram-currency test fails when the committed diagram differs from the compiled graph.
- [ ] CMP-AC-5 No routing decision calls a model or an executor (source-scan of route, gate, join, `select`, tally and pick code).
- [ ] CMP-AC-6 Every unit kind of CON §2.1 compiles to exactly four nodes, and the diagram draws a council or contest as one unit with its member or slot count.

## Open questions

None.

## References

