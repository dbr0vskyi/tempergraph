# R-060 Node types: the design and LangGraph

## Problem statement

The owner asked on 2026-11-20 which node (unit) types the engine has in this design, said the engine should support what LangGraph supports, and asked for higher-level nodes "like a council node etc". This note answers three questions:

1. Which unit kinds and flow primitives does this design have, and which shapes does it leave out?
2. Which of LangGraph's current graph capabilities does the design cover, which are missing, and which does it leave out on purpose, and why?
3. Which higher-level node kinds fit a verification-first engine that runs on four executors?

"Support what LangGraph supports" is read as **expressive parity**: a workflow author can express every graph shape LangGraph can (sequence, branching, fan-out, map-reduce, sub-graphs, human input, retries, caching, timeouts, error routing), through declared workflow data. It is not read as exposing LangGraph's Python API to workflows, which [ADR-0003](../adr/0003-workflows-as-data.adr.md) rules out. That reading is assumption A1 of [ADR-0062](../adr/0062-new-node-kinds-keep-the-gated-unit.adr.md).

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S3 | This design: CON-B4, CON-B5, CON-B6, CON-B7, CMP-B10 to CMP-B16, HUM, ORC, ADR-0040, R-150 JDG, JCL-B9 | Design set on `main` | [CON](../specs/contracts.spec.md), [CMP](../specs/compiler-and-flow.spec.md), [HUM](../specs/gate-and-human.spec.md), [ORC](../specs/orchestration.spec.md), [ADR-0040](../adr/0040-take-script-steps-attention-and-composition-from-archon.adr.md) |
| S4 | LangGraph "Use the graph API" | Official docs | https://docs.langchain.com/oss/langgraph/use-graph-api |
| S5 | LangGraph changelog (v1.0.0 2025-10-20, v1.1.0 2026-03-10, v1.2.0 2026-05-12) | Official docs | https://docs.langchain.com/oss/python/releases/changelog.md |
| S6 | LangGraph fault tolerance (retry, per-node timeouts, error handlers, `set_node_defaults`, graceful drain; `langgraph>=1.2`) | Official docs | https://docs.langchain.com/oss/python/langgraph/fault-tolerance.md |
| S7 | LangGraph interrupts (`interrupt`, `Command(resume=…)`, static breakpoints, `response_schema` from 1.2.12) | Official docs | https://docs.langchain.com/oss/python/langgraph/interrupts.md |
| S8 | LangGraph subgraphs; checkpointers (durability modes, time travel, fork) ; Pregel channels (DeltaChannel) | Official docs | https://docs.langchain.com/oss/python/langgraph/use-subgraphs.md, https://docs.langchain.com/oss/python/langgraph/checkpointers.md, https://docs.langchain.com/oss/python/langgraph/pregel.md |
| S9 | LangGraph "Thinking in the graph API" | Official docs | https://docs.langchain.com/oss/python/langgraph/thinking-in-graph-api.md |
| S10 | LangGraph 1.2 deep dive (dev.to, third party, automated) | Secondary; conflicts with S6 in three places, not relied on | https://dev.to/x4nent/langgraph-12-deep-dive-per-node-timeouts-error-handlers-graceful-shutdown-deltachannel--2mp2 |
| S11 | Anthropic, "Building effective agents" (2024-12-19) | Vendor engineering guidance | https://www.anthropic.com/research/building-effective-agents |

Council-specific sources (debate, voting, conformity) are in [R-061](R-061-councils-debate-and-voting.rsrch.md).

## Key findings

### Unit kinds in this design

| # | Finding | Confidence |
|---|---|---|
| F1 | The design has one gated unit (four nodes: step, judge, gate, human), one finalizer and eight flow primitives: order, route, switch, back-edge, parallel (engine-owned AND-join, writer branches), map (parallel or sequential, at most 50 items, per-item model), sub-workflow (depth three) and event wait. The unit stays closed: a new flow shape decides only where PROCEED goes (S3). | confirmed |
| F2 | Shapes the design does **not** support: writing branches inside a sub-workflow, a map inside a map, an event wait inside a branch, and a timeout or trigger for a wait. A voting panel of judges is deferred, since it multiplies the cost of every judged gate (S3). | confirmed |
| F4 | This design's `UnitSpec.kind` lists `step`, `route`, `switch`, `parallel`, `map`, `subworkflow`, `wait`, plus an operator switch-arm override (CMP-B7) and a sampled audit judge that records only (JDG-B7) (S3). | confirmed |
| F5 | [ADR-0040](../adr/0040-take-script-steps-attention-and-composition-from-archon.adr.md) (accepted) adds a `script` unit and `before`/`after` scripts on a model step, but no spec carries them yet: `UnitSpec.kind` in CON-B4, CON-B5, CON-B6, CON-B7 has no `script` and `StepSpec` has no `before`/`after` (S3). | confirmed |
| F6 | The orchestration layer has its own node kinds (`run`, `map`, `approval`) over whole runs (ORC); they are not graph units and are out of scope here (S3). | confirmed |
| F7 | A person can supply input only at the start (`ResolveResult.needs`) or as a decision at a gate pause (`proceed`, `retry`, `back`, `stop`, `event`). No unit asks a person mid-run for data that becomes an artifact (S3). | confirmed |

### LangGraph capabilities against the design

LangGraph's latest documented release line is 1.2 (1.2.0 on 2026-05-12; the interrupts page names 1.2.12). v1.0 kept the graph API stable; 1.1 added the v2 output and stream format; 1.2 added per-node timeouts, node error handlers, `set_node_defaults`, graceful drain, `DeltaChannel` (beta) and stream v3 (beta) (S5, S6). The table sets each capability against the design. *Covered* means a workflow can express it today; *added* means this change set adds it; *excluded* means left out on purpose.

| # | LangGraph capability (source) | In the design | Status | Confidence |
|---|---|---|---|---|
| L1 | Function node, callable-class node (S4) | Script unit ([ADR-0040](../adr/0040-take-script-steps-attention-and-composition-from-archon.adr.md)), now specified | added ([SCR](../specs/script-units-and-hybrid-steps.spec.md)) | confirmed |
| L2 | Normal edges, `add_sequence`, `START` entry (S4) | Order | covered | confirmed |
| L3 | Conditional edges with a path map (S4) | Route, switch | covered | confirmed |
| L4 | Conditional edge returning **several** destinations; list edge waiting for all (S4) | Parallel has a fixed branch set; no run-time choice of a subset | added: selective parallel ([FLX](../specs/flow-extensions.spec.md)) | confirmed |
| L5 | Conditional entry point (S4) | A switch as the first unit, with the operator arm override | covered | inferred |
| L6 | `Send` map-reduce to one node per item, with per-push timeout (S4, S6) | Map over a list artifact, results collected by item id | covered | confirmed |
| L7 | `Send` to a compiled subgraph per item (S4, S8) | Map of a single step only; sub-workflow is a separate unit | added: map over a sub-workflow ([FLX](../specs/flow-extensions.spec.md)) | inferred |
| L8 | `Command(update, goto)`: a node routes itself (S4, S9) | Only a gate routes, over static edges; a judged step emits a choice and a pure route reads it | excluded ([ADR-0062](../adr/0062-new-node-kinds-keep-the-gated-unit.adr.md)) | confirmed |
| L9 | `Command(graph=PARENT)`: a child routes its parent (S4) | A child's artifacts go to the unit's own gate | excluded | confirmed |
| L10 | `interrupt()` with `Command(resume)`; several parallel interrupts resumed by id (S7) | Human node, one interrupt per gate; several pending gates answered by unit and item (HUM-B3) | covered | confirmed |
| L11 | `interrupt()` for **free-form human input** that the graph then uses (S7) | Pause decisions only; no mid-run input artifact | added: ask unit ([ASK](../specs/ask-unit.spec.md)) | confirmed |
| L12 | `interrupt` `response_schema` validation of the resume value (S7, 1.2.12) | Decision grammar validated; wait value checked by a pure check | covered; the ask unit validates answers by declared kind | confirmed |
| L13 | Static breakpoints `interrupt_before` / `interrupt_after`, per call (S7) | Approval pause after a pass; nothing before a step | added: operator breakpoint before a unit ([FLX](../specs/flow-extensions.spec.md)); `interrupt_after` is covered by approval | confirmed |
| L14 | Subgraph as a node; per-invocation, per-thread or stateless subgraph checkpoints (S8) | Sub-workflow under the parent's checkpointer, depth three | covered (per-invocation only, on purpose) | confirmed |
| L15 | `RetryPolicy` re-running a node on exceptions, at-least-once (S6) | RETRY is a gate edge with a budget; infra failures follow BUD | excluded for model and judge nodes (a re-run node would re-spend a session and break C5); BUD keeps its own infra handling | confirmed |
| L16 | `CachePolicy` on a node keyed by input (S4, summary only) | None | added for model-free script units only, per thread ([SCR](../specs/script-units-and-hybrid-steps.spec.md)); excluded for steps and judges | supported |
| L17 | `defer=True`: run a node when nothing else is pending (S4, summary only) | Engine-owned AND-join, because a deferred node cannot tell a stopped branch from a finished one (S3) | excluded | confirmed |
| L18 | Per-node `timeout` with run and idle limits, async nodes only (S6, 1.2) | Session `timeout_s` and `idle_s` enforced by the executor layer | covered (a mechanism LangGraph's timeout may implement, not a design change) | confirmed |
| L19 | Node `error_handler` after retries, may return a `Command` to a fallback node (S6, 1.2) | `on_fail: retry\|stop`; `on_budget_spent: stop\|ask` | added: a declared fallback target ([FLX](../specs/flow-extensions.spec.md)) | confirmed |
| L20 | Graceful drain between supersteps (`RunControl.request_drain`, 1.2) (S6) | Drain requested by the scheduling node (CMP-B5) and the `stop` verb ([RCT](../specs/run-control.spec.md)) | covered; 1.2's drain is a candidate mechanism | confirmed |
| L21 | Reducers per key, `Overwrite`, `DeltaChannel` (beta) (S4, S8) | Per-unit channels with two-writer reducers; one deleting reducer | covered; DeltaChannel not needed (state is small JSON, and it makes checkpoints unreadable on downgrade, S8) | confirmed |
| L22 | Recursion limit (S4) | Attempt cap enforced in nodes; recursion limit only a backstop | covered | confirmed |
| L23 | Durability modes `exit`, `async`, `sync` (S8) | Checkpoint per superstep ([DUR](../specs/durability-and-resume.spec.md)) | covered (not a node type) | confirmed |
| L24 | Time travel: replay or fork from a checkpoint (S8) | A person's `back:<unit>` re-runs from a unit; no fork of a thread | not a node type; left to the improvement trials, which may later fork a thread for a paired case ([PRP](../specs/improvement-proposals.spec.md)) | inferred |
| L25 | Functional API `@entrypoint` / `@task` (S8) | Workflows are data ([ADR-0003](../adr/0003-workflows-as-data.adr.md)) | excluded | confirmed |
| L26 | Streaming v2/v3 projections (S5) | Run events and the activity journal ([EVT](../specs/run-events.spec.md)) | covered (not a node type) | confirmed |
| L27 | Prebuilt tool node and agent loop (S4, S5) | The step session is the agent loop, inside the executor | covered by the executors | confirmed |
| L28 | Private per-node input schema, runtime context (S4) | Declared artifact keys, judge references and engine keys | covered | confirmed |

### Higher-level patterns

| # | Finding | Confidence |
|---|---|---|
| H1 | Anthropic's guidance names five workflow patterns: prompt chaining, routing, parallelization (sectioning and voting), orchestrator-workers, and evaluator-optimizer, and advises adding complexity "only when it demonstrably improves outcomes" (S11). | supported |
| H2 | Prompt chaining is order; routing is route and switch; sectioning is parallel; orchestrator-workers is a planning step whose list artifact a map fans out; evaluator-optimizer is step, judge and RETRY with notes. Only **voting** (several independent answers combined) has no unit today. | inferred |
| H3 | Two shapes of "several models on one question" are distinct. A **council** combines several perspectives into one answer or one decision (synthesis, vote or ranking). A **contest** keeps one of several alternative full outputs, chosen by grading each. The first needs a combiner; the second needs only the gate's own judge per candidate. | inferred |
| H4 | A voting panel of **judges** is deferred by this design until single judges are calibrated (JCL-B9, R-045 F3, F9). A council as a **step** is different: its output still goes to one independent, calibratable judge, so it does not reopen that decision. | inferred |

## Conclusions

1. The design has seven unit kinds around one gated unit (F1, F4), plus an accepted but unspecified script unit; that unit is now specified ([SCR](../specs/script-units-and-hybrid-steps.spec.md)).
2. Against LangGraph 1.2, the design already covers 15 of the 28 capabilities listed, this change set adds 7 (L1, L4, L7, L11, L13, L16, L19), 5 are excluded on purpose (L8, L9, L15 for model nodes, L17, L25), and one (L24, time travel) is not a node type and stays open. Each exclusion protects a contract: static edges and pure gates (C5), one interrupt per gate (C6), workflows as data (C8, ADR-0003) and judge independence (C4).
3. Four higher-level kinds are added: **script** (model-free work), **council** (several members, one combined answer or decision; [CNL](../specs/council-unit.spec.md)), **contest** (best of several candidates by the gate's own judge; [CTS](../specs/contest-unit.spec.md)) and **ask** (a person's mid-run input as an artifact; [ASK](../specs/ask-unit.spec.md)). Every one compiles to the gated unit's step, judge, gate and human nodes, so verdicts stay engine-derived ([ADR-0062](../adr/0062-new-node-kinds-keep-the-gated-unit.adr.md)).
4. Five flow extensions close the remaining shape gaps: selective parallel, map over a sub-workflow, deadlines on waits and asks, a fallback target, and operator breakpoints ([FLX](../specs/flow-extensions.spec.md)).
5. A judge panel stays deferred; a council is a step whose output one judge grades.

## Open questions

| Question | Owner |
|---|---|
| Should a thread fork (L24) become an operator verb for trying a variant from a checkpoint, or stay inside improvement trials? | Owner, after the first paired trial |
| Is LangGraph 1.2's error handler or drain used as the mechanism for the fallback target and the stop verb? An implementation choice; the specs fix behaviour only. | Implementer of CMP |
