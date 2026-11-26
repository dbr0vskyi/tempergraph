# Flow extensions

## Purpose

Five additions to the flow primitives of [CMP](compiler-and-flow.spec.md) that give a workflow every graph shape LangGraph 1.2 can express ([research `node-types-against-langgraph`](../research/node-types-against-langgraph.rsrch.md), [ADR `flow-extensions-for-langgraph-parity`](../adr/flow-extensions-for-langgraph-parity.adr.md)): a parallel block that picks its branches at run time, a map whose item is a sub-workflow, deadlines on waits and asks, a fallback target on a gate, and operator breakpoints. Each keeps static, validated targets, pure routing (OVR-B7) and one interrupt per gate (C6), so validation checks reachability and the diagram draws every edge ([ADR `new-node-kinds-keep-the-gated-unit`](../adr/new-node-kinds-keep-the-gated-unit.adr.md)). Workflow authors, operators and the compiler depend on it; design and build notes are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Depends on

- `ask-unit.spec.md`: defaults at a deadline (ASK-B10); a list needs defaults for a defaults deadline (ASK-B13)
- `budgets-and-failures.spec.md`: budgets, failures and timeouts
- `compiler-and-flow.spec.md`: state channels (CMP-B17)
- `gate-and-human.spec.md`: approval is not friction (HUM-B5); intervention row (HUM-B6)
- `observability-and-cost.spec.md`: observability and cost
- `workspace-and-concurrency.spec.md`: shapes of parallel work (WSP-B11)

## Behaviours

### FLX-B6 Selective parallel

WHEN a `parallel` unit declares `select` (a pure function of state returning a non-empty subset of its branch names) THE engine SHALL wait at the join for the selected branches only, record each unselected branch `skipped` in a `route` record ([OBS](observability-and-cost.spec.md)), allow a selection of one branch, and on a raise, an empty set or an unknown name apply `on_select_fault` (`all` runs every branch, `stop`, the default, stops the run with exit 4 naming the block), the `select` code calling no model or executor ([CMP-AC5](compiler-and-flow.spec.md)); this is LangGraph's router returning several destinations (L4).

- GIVEN `select` returning `{security}` WHEN the block runs THEN one branch runs and the join fires on its pass
- GIVEN `select` returning `{}` under `stop` WHEN the block runs THEN the run stops with exit 4 naming the block
- GIVEN `select` raising under `all` WHEN the block runs THEN every branch runs
- GIVEN `select` returning `{unknown}` under `stop` WHEN the block runs THEN the run stops with exit 4

### FLX-B1 Selective join

WHEN a `select` picks some branches and they pass THE engine SHALL fire the join, never start the unselected branches and record them `skipped`.

- GIVEN branches `security`, `perf`, `docs` and `select` returning `{security, docs}` WHEN both pass THEN the join fires and `perf` never starts and is recorded `skipped`

### FLX-B7 Map over a sub-workflow

WHEN a `map` unit names `subworkflow: <name>` in place of `step` THE engine SHALL run the registered child for each item with the item as its input, take the child's last unit's artifacts as the item's result and grade the collected results with the map's gate, the child holding no `map`, `wait` or `ask`, counting toward the depth limit of three, its writing units needing the map's writer or sequential form ([WSP-B11](workspace-and-concurrency.spec.md)), and a child item's pause addressed by unit and item ([CMP-B17](compiler-and-flow.spec.md)); this is LangGraph's `Send` to a subgraph (L7).

- GIVEN a mapped child holding a `wait` WHEN validated THEN it is refused

### FLX-B2 Mapped child

WHEN a mapped child item escalates THE engine SHALL pause the parent with the pause addressed by unit and item, keeping the other items' results.

- GIVEN a map over three tickets whose item is a two-step child WHEN item 2's second step escalates THEN the parent pauses addressed `triage.t2` and items 1 and 3 keep their results

### FLX-B8 Deadlines

WHEN a `wait` or `ask` declares `deadline_s` (seconds from the pause's start) and `on_deadline` (`escalate`, `stop`, a forward unit, a static edge validated like a route target, or `defaults` on an `ask`) THE engine SHALL show the pause `overdue` in `status`, `attention` and the run detail once the deadline has passed and nobody applied it; apply it only by `resume <thread> --apply-deadline`, refused with exit 2 and nothing written before the deadline or with no overdue pause; turn it on `escalate` into an `escalation` a person answers with the usual decisions and on `defaults` into the ask's answers completed from their defaults ([ASK-B10](ask-unit.spec.md)); record the applier as `deadline` in the intervention row ([HUM-B6](gate-and-human.spec.md)); and never let the orchestration supervisor apply it (C16); this gives a wait a timeout ([research `node-types-against-langgraph`](../research/node-types-against-langgraph.rsrch.md) F2).

- GIVEN `--apply-deadline` before the deadline WHEN resumed THEN it exits 2 and nothing is written
- GIVEN an ask with `deadline_s: 86400` and `on_deadline: defaults` WHEN `resume --apply-deadline` runs before the deadline THEN it exits 2 and no answers file is written
- GIVEN that ask WHEN two days pass and `resume --apply-deadline` runs THEN the ask takes its defaults as ASK-B10 states and the intervention row records `deadline`

### FLX-B3 Overdue wait

WHEN a wait's deadline passes THE engine SHALL list it `overdue` and change nothing until `resume --apply-deadline`.

- GIVEN `deadline_s: 86400` and `on_deadline: escalate` WHEN two days pass THEN `attention` lists it `overdue` and only `resume --apply-deadline` turns it into an escalation

### FLX-B9 Fallback target

WHEN a gate declares `fallback` (a forward unit name or `finalizer`) and `on_budget_spent: fallback` or `on_fail: fallback` THE engine SHALL go to the fallback instead of stopping or asking when the retry or loop budget is spent or on a hard failure, keep the failed unit's artifacts marked `failed` so the fallback can read them, give the fallback's prompt the reason as a trip back would, and carry `degraded: true` and the unit on the exit file, the ledger, the status row and `RunOutcome`, the exit code staying 0 only if the rest passes; an infra failure never takes the fallback ([BUD](budgets-and-failures.spec.md)); this is LangGraph's node error handler routing to a fallback node (L19).

- GIVEN an infra failure on a gate with a fallback WHEN routed THEN the fallback is not taken

### FLX-B4 Fallback

WHEN a gate's budget is spent and its policy is `fallback` THE engine SHALL route to the fallback with the reason and the failed artifacts and finish the run degraded.

- GIVEN `retry_budget: 2`, `on_budget_spent: fallback` and `fallback: manual_brief` WHEN the third attempt fails THEN the run goes to `manual_brief` and the final status is `finished` with `degraded: true`

### FLX-B10 Operator breakpoints

WHEN `run` or `resume` takes `--pause-before <unit>` (repeatable; `<unit>.<item>` too) THE engine SHALL invoke the compiled graph with LangGraph's `interrupt_before` on those units' step nodes and write a marker `breakpoint.json` beside the run log, so nothing of the unit runs and no attempt record is written before the pause; give the pause kind `breakpoint`, print the rendered prompt's location (never its text beyond the first line) and accept `proceed` and `stop`, `stop` leaving the thread stopped and resumable; not pause again in the same segment the unit a breakpoint released; refuse an unknown unit `breakpoint_unknown` with exit 2 before any spend; and count a breakpoint as neither an escalation nor friction for self-improvement, like an approval ([HUM-B5](gate-and-human.spec.md)); this is LangGraph's static `interrupt_before` (L13).

- GIVEN `--pause-before nosuch` WHEN the run starts THEN it exits 2 `breakpoint_unknown` and nothing is spent

### FLX-B5 Breakpoint

WHEN a run reaches a unit named by `--pause-before` THE engine SHALL exit 3 with kind `breakpoint` before any session starts, and `resume --decision proceed` SHALL run the unit normally.

- GIVEN `run --pause-before plan` WHEN the run reaches `plan` THEN it exits 3 with kind `breakpoint` and `resume --decision proceed` runs `plan`

### FLX-B11 What is refused

WHEN a workflow with flow extensions is validated THE engine SHALL refuse with an `error` a `select` on a block with fewer than two branches or one not importable; a mapped sub-workflow holding a map, a wait or an ask or exceeding depth three; `deadline_s` on a unit that is not a wait or an ask, or an `on_deadline` target that is not forward; `on_deadline: defaults` on a unit that is not an ask, or on an ask whose declared questions hold a required question with no `default`, whether or not `deadline_s` is declared (a list read from a step is checked when the ask is entered, [ASK-B13](ask-unit.spec.md)); `fallback` naming a unit not after this one on every path or the unit itself; and `on_fail: fallback` or `on_budget_spent: fallback` with no `fallback`; and the diagram model SHALL draw `select`, fallback and deadline edges, covered by the diagram-currency test.

- GIVEN `fallback` naming the unit itself WHEN validated THEN it is refused with its own finding code
- GIVEN a wait with `on_deadline: defaults` WHEN validated THEN it is refused with its own finding code
- GIVEN an ask with `on_deadline: defaults`, no `deadline_s` and a declared required question with no `default` WHEN validated THEN it is refused with its own finding code naming the question
- GIVEN an ask with `on_deadline: defaults` whose declared required questions all have a `default` WHEN validated THEN it is accepted

## Acceptance criteria

- FLX-AC1 (FLX-B11, FLX-B7): Every refusal of FLX-B11 and the unknown breakpoint of FLX-B10 has a fixture that fails validation (or preflight) with its own finding code
- FLX-AC2 (FLX-B6, FLX-B1, FLX-B2): Every scenario of FLX-B6 holds offline
- FLX-AC3 (FLX-B10, FLX-B5): A breakpoint pause starts no session and writes no attempt record
- FLX-AC4 (FLX-B9, FLX-B4): A degraded run is never reported `finished` without `degraded: true` in the status document and the stats rows
- FLX-AC5 (FLX-B11, FLX-B8, FLX-B3): The diagram model draws `select`, fallback and deadline edges, and the diagram-currency test covers them
- FLX-AC6 (FLX-B8): On an ask with `on_deadline: defaults`, `resume --apply-deadline` before the deadline exits 2 and writes no answers file, and after the deadline it takes the defaults as ASK-B10 states and the intervention row records `deadline`
- FLX-AC7 (FLX-B11): Validation accepts `on_deadline: defaults` on an ask whose declared required questions all have a `default`, and refuses it, each with its own finding code, on a wait and on an ask with a declared required question that has no `default`

## Open questions

- Not built yet: selective parallel (FLX-B6, FLX-B1), a map over a sub-workflow (FLX-B7, FLX-B2) and `--pause-before <unit>.<item>` stay in release 3 and are refused `not_in_release`; `select` edges in the diagram come with them. Owner: engine owner.
