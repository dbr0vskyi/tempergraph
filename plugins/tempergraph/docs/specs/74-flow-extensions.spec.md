---
title: Flow extensions
type: component
status: review
prefix: FLX
adrs: [0062, 0066]
---

# Flow extensions

## 1. Overview

Five additions to the flow primitives of [CMP §2.2](03-compiler-and-flow.spec.md) that give a workflow every graph shape LangGraph 1.2 can express ([R-060](../research/R-060-node-types-against-langgraph.rsrch.md), [ADR-0066](../adr/0066-flow-extensions-for-langgraph-parity.adr.md)): a parallel block that picks its branches at run time, a map whose item is a sub-workflow, deadlines on waits and asks, a fallback target on a gate, and operator breakpoints. Each keeps static, validated targets, pure routing (contract C5) and one interrupt per gate (C6).

## 2. Contract

### 2.1 Selective parallel

| Field (on a `parallel` unit) | Kind | Meaning |
|---|---|---|
| `select` | callable ref, optional | Pure function of state returning a non-empty subset of the declared branch names. |
| `on_select_fault` | `all` \| `stop`, default `stop` | What a raise, an empty set or an unknown name does. |

The join waits for the selected branches only; each unselected branch is recorded `skipped` in a `route` record ([OBS](15-observability-and-cost.spec.md)). A selection of one branch is allowed. LangGraph's router returning several destinations (L4).

### 2.2 Map over a sub-workflow

A `map` unit may name `subworkflow: <name>` in place of `step`. Each item runs the registered child with the item as its input; the child's last unit's artifacts are the item's result; the map's gate grades the collected results as today. The child may contain no `map`, `wait` or `ask`, its depth counts toward the limit of three, and its writing units need the map's writer form or the sequential form ([WSP §2.1](13-workspace-and-concurrency.spec.md)). A child item's pause is addressed by unit and item, as for any child (CMP §4). LangGraph's `Send` to a subgraph (L7).

### 2.3 Deadlines

| Field (on `wait` and `ask`) | Kind | Meaning |
|---|---|---|
| `deadline_s` | positive int | Seconds from the pause's start. |
| `on_deadline` | `escalate` \| `stop` \| `<forward unit>` | Applied only by `resume <thread> --apply-deadline` once the deadline has passed. |


### 2.4 Fallback target

| Field (on `GateSpec`) | Kind | Meaning |
|---|---|---|
| `fallback` | forward unit name or `finalizer`, optional | Where the run goes instead of stopping or asking. |
| `on_budget_spent` | adds `fallback` | Use `fallback` when the retry or loop budget is spent. |
| `on_fail` | adds `fallback` | Use `fallback` on a hard failure. |

The failed unit's artifacts are kept and marked `failed`, not cleared, so the fallback can read them; the fallback's prompt receives the reason as a trip back would. The run's final status carries `degraded: true` and the unit, and its exit code stays 0 only if the rest passes. Infra failures never take the fallback ([BUD](08-budgets-and-failures.spec.md)). LangGraph's node error handler routing to a fallback node (L19).

### 2.5 Operator breakpoints

`run` and `resume` accept `--pause-before <unit>` (repeatable; `<unit>` or `<unit>.<item>`). The compiled graph is invoked with LangGraph's `interrupt_before` on those units' step nodes, so nothing of the unit runs before the pause. The pause has kind `breakpoint`, prints the rendered prompt's location (never its text on the terminal beyond the first line) and accepts `proceed` and `stop`. A breakpoint is not an escalation and not friction for self-improvement, like an approval (HUM-B5). LangGraph's static `interrupt_before` (L13).

### 2.6 What is refused

| Refused before a run (`error`) |
|---|
| A `select` on a block with fewer than two branches; `select` not importable |
| A mapped sub-workflow containing a map, a wait or an ask, or exceeding depth three |
| `deadline_s` on a unit that is not a wait or an ask; an `on_deadline` target that is not forward |
| `fallback` naming a unit not after this one in every path, or the unit itself; `on_fail: fallback` or `on_budget_spent: fallback` with no `fallback` |
| `--pause-before` naming a unit or item the workflow does not have (exit 2 before spend) |

## 3. Behaviours

**FLX-B1 Selective join.** Given a parallel block with branches `security`, `perf`, `docs` and a `select` returning `{security, docs}`, when both pass, then the join fires; `perf` never starts and is recorded `skipped`.

| `select` returns | `on_select_fault` | Result |
|---|---|---|
| `{security}` | — | one branch runs; join fires on its pass |
| `{}` | stop | run stops, exit 4, naming the block |
| raises | all | every branch runs |
| `{unknown}` | stop | run stops, exit 4 |

**FLX-B2 Mapped child.** Given a map over three tickets whose item is a two-step child workflow, when item 2's second child step escalates, then the parent pauses and the pause is addressed `triage.t2`; items 1 and 3 keep their results.

**FLX-B3 Overdue wait.** Given a wait with `deadline_s: 86400` and `on_deadline: escalate`, when two days pass, then `attention` lists it `overdue`; nothing changes until `resume --apply-deadline`, which turns it into an escalation a person answers.

**FLX-B4 Fallback.** Given a gate with `retry_budget: 2`, `on_budget_spent: fallback` and `fallback: manual_brief`, when the third attempt fails, then the run goes to `manual_brief` with the reason and the failed artifacts, and the final status is `finished` with `degraded: true`.

**FLX-B5 Breakpoint.** Given `run --pause-before plan`, when the run reaches `plan`, then it exits 3 with kind `breakpoint` before any session starts; `resume --decision proceed` runs `plan` normally.

## 4. Error conditions

| Type | Result |
|---|---|
| A `select` that calls a model or an executor | Source-scan failure (CMP-AC-5 extends to `select`) |
| `--apply-deadline` on a thread with no overdue pause | Exit 2, nothing written |

## 5. Design notes

- Every target stays a declared name, so validation checks reachability and the diagram draws every edge ([ADR-0062](../adr/0062-new-node-kinds-keep-the-gated-unit.adr.md)).
- Deadlines need no resident process: the engine still exits at a pause, and an owner who wants deadlines to act on time schedules `resume --apply-deadline` from their own scheduler; the schedule tick is the engine's candidate for that job in a later slice ([TCK §5](84-schedule-ticks-and-unattended-fires.spec.md)).
- Breakpoints fit the local stage of a workflow's life, when a person still reviews each step before it spends ([ADR-0041](../adr/0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md)).

## 6. Acceptance criteria

- [ ] FLX-AC-1 Every row of §2.6 has a fixture that fails validation (or preflight) with its own finding code.
- [ ] FLX-AC-2 Every row of the FLX-B1 table holds offline.
- [ ] FLX-AC-3 A breakpoint pause starts no session and writes no attempt record.
- [ ] FLX-AC-4 A degraded run is never reported `finished` without `degraded: true` in the status document and the stats rows.
- [ ] FLX-AC-5 The diagram model draws `select`, fallback and deadline edges, and the diagram-currency test covers them.

## Open questions

None.

## References

[CMP](03-compiler-and-flow.spec.md) · [HUM](07-gate-and-human.spec.md) · [BUD](08-budgets-and-failures.spec.md) · [WSP](13-workspace-and-concurrency.spec.md) · [ADR-0066](../adr/0066-flow-extensions-for-langgraph-parity.adr.md)
