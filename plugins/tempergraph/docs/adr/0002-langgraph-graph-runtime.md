# ADR-0002 Use LangGraph as the graph runtime

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

tempergraph needs explicit state machines with conditional edges and first-class cycles (retries, trips back), durable human pauses that survive days, and the same graph running locally and headless. The README fixes LangGraph as the base. LangGraph was compared with the OpenAI Agents SDK, Burr, the Claude Agent SDK, Temporal, XState, PydanticAI graphs, CrewAI, Google ADK and a script loop.

## Decision

We will compile every workflow to a LangGraph `StateGraph` with a checkpointer, and take the graph, the checkpointer and the interrupt from LangGraph, while the gate funnel, executors, registry and input resolution stay tempergraph's own ("ecosystem for mechanism, bespoke for policy").

## Options considered

| Option | Pros | Cons |
|---|---|---|
| LangGraph (chosen) | Nodes, conditional edges, cycles; durable interrupt and resume keyed by thread id; maintained checkpointers | Resume replays a paused node from its top; private internals move between releases |
| OpenAI Agents SDK | Serializable run state | No declared graph; cycles are plain control flow |
| Burr | Explicit state machines | Retry and exception handling were roadmap only; no MCP bridge |
| Temporal | Strong durability | A server to run; heavy for a laptop tool |
| Hand-rolled loop | Full control | Re-implements checkpointing, iteration bounds and parsing |

## Decision rationale

| Criterion | LangGraph | Agents SDK | Burr | Temporal | Hand-rolled |
|---|---|---|---|---|---|
| Declared graph with cycles | yes | no | yes | via code | yes |
| Durable human pause | yes | partial | partial | yes | build it |
| Runs locally with no server | yes | yes | yes | no | yes |
| Named by the owner | yes | no | no | no | no |

## Consequences

- Positive: the compiler, validation and diagram share one topology; pauses are free and durable.
- Negative: the replay-from-top rule forces the four-node unit ([ADR-0004](0004-four-nodes-per-unit.md)).
- Risk: a LangGraph release moves an internal the engine or its tests use. Mitigation: depend only on public API; tests that touch internals skip loudly; pin a tested range.

## Revisit when

LangGraph changes its interrupt or checkpoint semantics, or runs must span hosts.
