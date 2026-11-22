# ADR-0004 Four nodes per unit; retries are edges; one interrupt per gate

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

LangGraph restarts a paused node from its top on resume, not from the interrupt call. Anything costly, logged or external placed before an interrupt runs again on every resume. A retry loop inside one node with an interrupt in it re-runs the whole node on every resume.

## Decision

We will compile each unit into four nodes: **step** (runs the session), **judge** (check, judge session, guard, verdict), **gate** (pure routing, never pauses) and **human** (whose first statement is the only interrupt). Retry, back and escalation are graph edges; budgets are counted in state.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Four nodes, edges for repeats (chosen) | A resume replays only the human node; the judge never runs twice; the diagram shows every path | More nodes per unit |
| One node per unit with an internal loop | Compact | Quadratic replay on resume; hidden control flow |
| Judge as an ordinary next step | Reuses the step machinery | Authors wire it by hand; a rejection retries the judging step, not the producer |

## Decision rationale

| Criterion | Four nodes | One node | Judge as step |
|---|---|---|---|
| Resume cost | one node | whole unit | one node |
| Judge runs once per attempt | yes | no | yes |
| Verdict derived by the engine | yes | yes | no |
| Topology visible to validation | yes | no | partly |

## Consequences

- Positive: pauses are cheap and correct; a gate is pure and safe to re-run (OVR-B7).
- Negative: per-unit state channels and reducers are needed so parallel units do not collide.
- Risk: someone adds logging before the interrupt. Mitigation: a source test asserts the interrupt is first.

## Revisit when

LangGraph offers resume from the interrupt call itself.
