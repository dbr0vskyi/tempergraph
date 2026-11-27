# Compiler and flow

## Purpose

The compiler turns a validated workflow into a durable state graph with four nodes per unit (step, judge, gate, human), one finalizer node and static edges for every target the workflow names, so validation can check reachability and the diagram is drawn from the same model. Every unit kind keeps those four nodes; for a council or a contest the step node is a subgraph of sessions with an engine-owned barrier ([ADR `new-node-kinds-keep-the-gated-unit`](../adr/new-node-kinds-keep-the-gated-unit.adr.md)). Four nodes and not one, because the graph runtime restarts a paused node from its top on resume ([ADR `four-nodes-per-unit`](../adr/four-nodes-per-unit.adr.md)). Workflow authors, the diagram, the run log and resume depend on what the graph does. Gates, routes and joins are pure and safe to re-run, and the judge and the gate run once. Graph features left out on purpose (a node routing itself, retry policies on model nodes, deferred nodes, the functional API) are compared in [research `node-types-against-langgraph`](../research/node-types-against-langgraph.rsrch.md).

## Depends on

- `ask-unit.spec.md`: ask unit
- `contest-unit.spec.md`: contest unit
- `contracts.spec.md`: unit fields (CON-B5)
- `council-unit.spec.md`: council unit
- `flow-extensions.spec.md`: deadlines (FLX-B8)
- `gate-and-human.spec.md`: gate and human nodes
- `judge-and-verdict.spec.md`: the re-read of a judgement that marks its own reading (JDG-B17)
- `map-unit.spec.md`: map unit
- `measured-switches.spec.md`: measured switches
- `observability-and-cost.spec.md`: observability and cost
- `reruns-and-feedback.spec.md`: rewind (RRN-B16)
- `run-outcome.spec.md`: the outcome gate (OUT-B15); outcome gate failure (OUT-B16); outcome judge mode (OUT-B17)
- `script-units-and-hybrid-steps.spec.md`: script units and hybrid steps
- `workspace-and-concurrency.spec.md`: shapes of parallel work (WSP-B11)

## Behaviours

### CMP-B8 Node names and routing tokens

WHEN a workflow is compiled THE compiler SHALL name each unit's nodes `<unit>.step`, `<unit>.judge`, `<unit>.gate` and `<unit>.human`, add one `finalizer` node, and give each gate static edges per routing token: `PROCEED` to the next unit, route target, switch arm or finalizer; `RETRY` to the unit's step node; `BACK` to each listed earlier unit; `ESCALATE` to the unit's human node; `STOP` to the end; and give each human node the same edges without `ESCALATE`, plus `rewind:<unit>` to the step node of every earlier unit in `order` ([RRN-B16](reruns-and-feedback.spec.md)).

- GIVEN an order of two steps WHEN compiled THEN the graph has 8 nodes plus `finalizer`, and each gate has edges for `PROCEED`, `RETRY`, `ESCALATE` and `STOP`
- GIVEN `back_targets: [a]` on unit `b` WHEN compiled THEN `b.gate` has a `BACK` edge to `a`

### CMP-B9 What each node does

WHEN a unit runs THE engine SHALL let the step node render the prompt, resolve the alias and limits for this attempt, call the executor and record usage, never grading; let the judge node run the check, then, unless the check failed, the judge session and its one re-ask, then the guard, then at most one re-read of a judgement that marks its own reading ([JDG-B17](judge-and-verdict.spec.md)), then derive and store the verdict, never pausing; let the gate node read the stored judgement, apply budgets and policy and write a routing token and, when needed, a pause payload, never calling a model or pausing; and let the human node interrupt as its first statement, applying the decision once after it, with no log, spend or write before the interrupt.

- GIVEN a unit whose check fails WHEN its judge node runs THEN no judge session starts
- GIVEN a gate WHEN it routes THEN no executor is called

### CMP-B1 Retry is an edge

WHEN a gate derives RETRY with budget left THE compiler's graph SHALL return control to the unit's step node over a conditional edge, with no node looping inside.

- GIVEN a gate that derives RETRY with budget left WHEN it routes THEN the next node run is the unit's step node

### CMP-B2 Resume replays only the human node

WHEN a run paused at a gate is resumed THE engine SHALL run only the human node again from its top, without re-entering the judge and gate nodes or starting a judge session.

- GIVEN a run paused at a gate WHEN it is resumed THEN no judge session starts and no log record is written twice

### CMP-B10 Order and routes

WHEN a unit passes THE engine SHALL go to the next unit in `order`, unless a route, a pure function of state run in the gate node before any approval pause, picks one static forward target or the finalizer; position in `order` is never a fallback.

- GIVEN a route on `a` to `{b, finalizer}` WHEN compiled THEN `a.gate` has `PROCEED` edges to `b` and to `finalizer`
- GIVEN a route that picks the finalizer WHEN `a` passes THEN no later unit starts

### CMP-B3 Route fault stops

WHEN a route function raises or returns a name that is not one of its targets THE engine SHALL stop the run with exit 4 naming the route.

- GIVEN a route function that raises WHEN the gate runs it THEN the run stops with exit 4 naming the route and the next unit in `order` does not start

### CMP-B11 Switches

WHEN a switch is reached THE engine SHALL take the arm (a unit, the finalizer, a map or a parallel block) its predicate picks, the default arm on any predicate fault, keep the arm sticky per visit or per run as declared, and write every pick as a `route` record ([OBS](observability-and-cost.spec.md)); shadow mode, per-arm overrides and re-arming are [SWM](measured-switches.spec.md).

- GIVEN a switch whose predicate raises WHEN it is reached THEN the default arm runs and the `route` record says the default was taken
- GIVEN `sticky: run` WHEN the unit is visited again THEN the first arm runs again

### CMP-B7 Operator arm override

WHEN a run starts with `--arm <switch>=<arm>` THE engine SHALL take that arm and record `chosen_by = operator`, and refuse an arm the switch does not declare with exit 2 before spend.

- GIVEN a switch `mode` with arms `light` and `full` whose predicate would pick `full` WHEN the run starts with `--arm mode=light` THEN `light` runs and the route record says `chosen_by = operator`
- GIVEN `--arm mode=medium` WHEN the run is checked THEN it exits 2 before spend

### CMP-B12 Back-edges

WHEN a gate routes `BACK` THE engine SHALL start a new visit of the target and of each unit after it on the path, clear their judgements and artifacts from state (an artifact written as nothing is removed), and hand the target the reason.

- GIVEN `c` sending the run back to `a` WHEN `a` starts again THEN `a`, `b` and `c` have no judgement in state and `a`'s prompt carries the reason

### CMP-B4 AND-join waits for passes

WHEN a parallel block's branches run THE engine SHALL fire the engine-owned join once, only after every branch has passed, and stop the block when a branch stops.

- GIVEN branches A and B WHEN A passes and B retries THEN the join does not fire until B passes
- GIVEN a branch B that stops WHEN the block is decided THEN the block stops

### CMP-B13 Parallel blocks

WHEN a unit of kind `parallel` names its branches, which stand just before it in `order` THE compiler SHALL add `<join>.fork` and one `<branch>.done` node per branch, run a branch that declares neither `write` nor `edit` as a read-only step and fail one that changes the workspace with `branch_changed_the_workspace`, run a branch that declares one in its own worktree ([WSP-B11](workspace-and-concurrency.spec.md)), give the join no check or judge, merge branch state by reducers (path union, cost by delta), and on a trip back to the block clear and run every branch again.

- GIVEN a branch that declares neither `write` nor `edit` and changes a file WHEN it ends THEN it fails with `branch_changed_the_workspace`
- GIVEN a trip back into the block WHEN it runs again THEN both branches run again

### CMP-B14 Maps, sub-workflows and waits

WHEN a map, sub-workflow or event wait is compiled THE compiler SHALL compile a map as one subgraph per item of a list artifact (at most 20 by default, at most 50), each item gated on its own and collected by item id, with no back-edge from an item ([MAP](map-unit.spec.md)); a sub-workflow as a registered workflow under the parent's checkpointer, its artifacts going to the unit's own gate, at most three deep, with no recursion and no meta child; and an event wait with no model and no judge, on the main chain only, that arms once and then pauses until a delivered event passes its pure check ([FLX-B8](flow-extensions.spec.md)).

- GIVEN a map over 51 items WHEN it fans out THEN it is refused
- GIVEN a sub-workflow four levels deep WHEN the workflow is validated THEN it fails
- GIVEN a paused sub-workflow child WHEN the status is read THEN the parent is paused and the pause is addressed by unit and item

### CMP-B15 The outcome gate

WHEN a workflow is compiled THE compiler SHALL add the reserved unit `outcome` after every unit and before the finalizer, so every path to the finalizer passes it, its step node assembling the subject and starting no session, and its back targets derived from the outcome's `serves` links ([OUT-B15, OUT-B16, OUT-B17](run-outcome.spec.md)).

- GIVEN a route straight to the finalizer WHEN it is taken THEN the `outcome` unit runs first

### CMP-B16 Step-node forms

WHEN a unit's step node runs THE engine SHALL run one step session for `step`, one per item for `map` and the child graph for `subworkflow`; a command or callable with no session for `script` ([SCR](script-units-and-hybrid-steps.spec.md)); member sessions per round, a round barrier, a pure tally and a chair for `council` ([CNL](council-unit.spec.md)); candidate slots as items, each checked and judged, then a pure pick for `contest` ([CTS](contest-unit.spec.md)); and nothing for `ask` and `wait`, whose human node pauses ([ASK](ask-unit.spec.md), [HUM](gate-and-human.spec.md)).

- GIVEN a council unit WHEN it is drawn THEN the diagram shows one unit with its member count
- GIVEN an `ask` unit WHEN it runs THEN no session starts and the run pauses

### CMP-B5 Attempt cap in nodes

WHEN the attempts counted in an invocation (CMP-B19) have reached the attempt cap THE engine SHALL stop the run before its next attempt with exit 4, reason `attempt_cap` and no engine-error record, leaving the thread resumable, the graph's recursion limit being only a backstop.

- GIVEN an attempt cap of 15 and 15 attempts counted WHEN the next attempt would start THEN the run stops before it with exit 4 and reason `attempt_cap`
- GIVEN an attempt cap of 15 and 14 attempts counted WHEN a retry starts THEN it runs, and the run stops before the attempt that follows it
- GIVEN a run stopped at its attempt cap WHEN it is resumed THEN its count starts at 0

### CMP-B19 What the attempt cap counts

WHEN a step, a council, a sub-workflow, a map item or a contest slot starts an attempt THE engine SHALL count the attempt against the attempt cap only when that unit, item or slot has made an attempt earlier in the thread, as a retry or in a visit begun by a trip back (CMP-B12) or a rewind ([RRN-B16](reruns-and-feedback.spec.md)).

- GIVEN a workflow of thirty units, among them a council, a sub-workflow and a map of twenty items, each attempt passing at its first try WHEN it runs under the default cap THEN no attempt is counted and the run finishes with exit 0
- GIVEN a step whose gate retries it twice before it passes WHEN it runs THEN two attempts are counted
- GIVEN units `a` and `b` that have passed and a gate that sends the run back to `a` WHEN `a` and `b` run their next visits THEN two attempts are counted

### CMP-B20 The exit at the attempt cap says what repeated

WHEN a run stops at the attempt cap THE engine SHALL give its `run_exit` record, and the `payload` of the JSON document `run` or `resume` prints with `--json`, the keys `attempts_counted` and `trips_back` (the attempts counted and the trips back made in the invocation) and `repeated` (for each unit, map item or contest slot with a counted attempt: `unit`, `item`, the `attempts` it started in the invocation and the `trips_back` that entered it).

- GIVEN a unit `b` with a loop budget of 5 whose gate sends the run back to unit `a` each time, and an attempt cap of 3 WHEN the run stops at the cap THEN `attempts_counted` is 3, `trips_back` is 2, and `repeated` holds `a` with `attempts` 3 and `trips_back` 2 and `b` with `attempts` 2 and `trips_back` 0
- GIVEN a step with a retry budget of 5 whose gate retries it every time, and an attempt cap of 2 WHEN the run stops at the cap THEN `repeated` holds the step with `attempts` 3 and `trips_back` 0
- GIVEN either stop WHEN `run --json` prints it THEN its `payload` holds the same three keys with the same values as the `run_exit` record

### CMP-B6 Diagram equals graph

WHEN the diagram model is generated THE engine SHALL produce nodes and edges equal to the compiled graph's in both directions.

- GIVEN a compiled workflow WHEN its diagram model is generated THEN every node and edge of one is in the other

### CMP-B17 State channels

WHEN units that can run in one superstep write state THE engine SHALL key the routing token, pause payload, judge notes and human feedback by unit, and keep per-call values (alias, timeout, session options) out of graph state and the checkpoint.

- GIVEN two parallel branches that both write a routing token WHEN the superstep ends THEN both tokens are kept under their units
- GIVEN a checkpoint WHEN it is read THEN it holds no alias or timeout of a call

### CMP-B18 An unknown routing token

WHEN a gate writes a routing token that has no edge THE engine SHALL write an engine-error record and exit 1.

- GIVEN a gate that returns `SKIP` WHEN it routes THEN the run exits 1 with an engine-error record

## Acceptance criteria

- CMP-AC1 (CMP-B8, CMP-B9): Every unit compiles to exactly four nodes with the names of CMP-B8
- CMP-AC2 (CMP-B2): A resume of a paused run starts no judge session and writes no duplicate log record
- CMP-AC3 (CMP-B1, CMP-B3, CMP-B4, CMP-B10, CMP-B11, CMP-B12, CMP-B13, CMP-B14, CMP-B15): Each flow primitive has an offline test with scripted executors and a scratch git repository
- CMP-AC4 (CMP-B6): The diagram-currency test fails when the committed diagram differs from the compiled graph
- CMP-AC5 (CMP-B9, CMP-B10, CMP-B11): No routing decision calls a model or an executor, by a source scan of route, gate, join, select, tally and pick code
- CMP-AC6 (CMP-B16): Every unit kind of [CON-B5](contracts.spec.md) compiles to exactly four nodes, and the diagram draws a council or contest as one unit with its member or slot count
- CMP-AC7 (CMP-B7): An operator arm override is taken and recorded, and an undeclared arm exits 2 before spend
- CMP-AC8 (CMP-B5): A fixture run at its attempt cap stops before the next attempt with exit 4 and reason `attempt_cap`, writes one `run_exit` record and no engine-error record, never reaches the graph's recursion limit, and its resume counts from none
- CMP-AC9 (CMP-B17): A test fails if any state channel two units can write in one superstep lacks a two-writer reducer
- CMP-AC10 (CMP-B18): A gate's unknown routing token ends the run with exit 1 and an engine-error record
- CMP-AC11 (CMP-B19): A fixture run of one step, a map of twenty items and three further steps, each passing at its first attempt, ends with exit 0 under the default settings and counts no attempt
- CMP-AC12 (CMP-B19, CMP-B5): A fixture in which a unit sends the run back to an earlier unit until the cap, and a fixture whose step fails its gate until the cap under a retry budget above it, each stop before the next attempt with exit 4 and reason `attempt_cap`, with as many attempts counted as the cap
- CMP-AC13 (CMP-B19): A fixture council and a fixture sub-workflow whose child units pass at their first attempt count no attempt at their own first attempt, and a retry of either counts one attempt, however many member sessions or child units it runs
- CMP-AC14 (CMP-B20): The `run_exit` record and the `payload` of `run --json` of each stop of CMP-AC12 hold equal `attempts_counted`, `trips_back` and `repeated`, whose `attempts` and `trips_back` for each listed unit equal what the run log shows
