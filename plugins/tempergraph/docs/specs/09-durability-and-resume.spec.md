---
title: Durability and resume
type: component
status: review
prefix: DUR
adrs: [0014, 0015]
---

# Durability and resume

## 1. Overview

A run is a LangGraph thread in a per-workflow SQLite checkpoint under the state root. Resume is defined for every thread state, and the engine reads that state before it spends anything. Status and wait are read-only, model-free observers. This spec owns contract C7 and the status document the `tempergraph-monitor` plugin reads; its per-thread detail form is [RDD](31-run-detail-document.spec.md).

## 2. Contract

```python
def classify(workflow: str, thread_id: str) -> ThreadState: ...       # read-only URI; creates nothing
def start(workflow: str, request: ResolveResult, options: RunOptions) -> ExitCode: ...
def resume(workflow: str, thread_id: str, decision: Decision | None, inputs: dict[str, str]) -> ExitCode: ...
def status(selector: Selector) -> StatusDocument: ...
def wait(selector: Selector, timeout_s: int) -> WaitOutcome: ...
```

### 2.1 Resume by thread state

| State, recognised by | Resume does |
|---|---|
| `none`: no checkpoint values | Refused (exit 2) |
| `paused`: a pending node with an interrupt | Delivers the decision to that gate |
| `unfinished`: pending nodes, no interrupt | Continues with a fresh attempt allowance; a decision or feedback is refused |
| `stopped`: nothing pending, ended at a gate | Re-opens with `retry` or `back`, through the human node's own update; other decisions refused |
| `finished`: every unit passed | Refused; start a new thread |
| `running`: lock held by a process | Refused (exit 2) |

### 2.2 Status document (schema version 1)

| Field | Meaning |
|---|---|
| `thread_id`, `workflow`, `state`, `alive` | `alive` from the lock probe |
| `attempt_in_flight` | unit, item, attempt number, executor, started at |
| `pending_gates` | unit, item, pause kind, resume command |
| `last_verdict`, `cost` | cost carries `reported`, `estimated`, `incomplete` |
| `executors` | executors used so far, with CLI versions |
| `log_path` | run log location (local only) |
| `alias` | optional short run name given at start (`--alias`), unique among live threads; status, resume and wait accept it in place of the thread id |
| `label` | optional free text given at start, scrubbed, at most 80 chars |
| `origin` | how the run started: `cli`, `skill`, `batch`, `self_improvement`, `hook` or `ci` |
| `resume_count` | number of resumes so far (the resume chain length) |

Adding these fields keeps schema version 1: readers ignore unknown keys and read a missing key as not recorded ([CON §2.10](01-contracts.spec.md)).

## 3. Behaviours

**DUR-B1 Fresh run never merges.** Given a thread in any state but `none`, when a fresh start is requested, then it is refused with exit 2 before the preflight, a worktree, the run log or any model call; the message names the resume command and a new thread id form.

**DUR-B2 Cut-off attempt.** Given an attempt whose start record no step record closed (the process was killed), when the run resumes, then the start becomes an interrupted record with one notice (output and cost not recorded, workspace changes unaccounted for) and the step runs again under the same attempt number without charging the budget.

**DUR-B3 Concurrency.** Given sixteen processes writing to one workflow's checkpoint, when they commit, then none loses a write: the saver waits up to 60 s for the lock, and creating an empty store is retried for 30 s.

**DUR-B4 Observer creates nothing.** Given a live run, when status or wait runs, then it opens the checkpoint read-only, probes the lock without creating it and for an instant only, and writes no file.

**DUR-B5 Wait.** Given `wait` on a thread, when the run pauses, completes, fails or records a new gate verdict, or the timeout passes, then wait exits with the outcome's code; it polls file sizes and times and rebuilds a row only when one moved.

WHEN `wait` names a thread THE engine SHALL exit when the run pauses, completes, fails or records a new gate verdict, or when the timeout passes, with the run's own exit code when it is recorded in the run folder's `exit.json` ([LOS §2.1](33-local-observability-store.spec.md)), else 3 paused, 0 finished, 4 stopped or unfinished, 0 with the row for a new verdict on a running thread, and 5 with state `running` at the timeout, rebuilding a row only when a file's size or time moved.

**DUR-B7 Executor change across resume.** Given a run paused after a step ran on `antigravity`, when the operator resumes with a per-step executor override to `claude`, then the next attempt uses `claude`; the override is recorded with the run options and reapplied on later resumes.

**DUR-B7 Run alias.** Given a start with `--alias auth-fix`, when another live thread already holds that alias, then the start is refused with exit 2 naming the holder; once the first thread is finished its alias is free, and a status by alias of a finished thread shows the latest one.

## 4. Error conditions

| Condition | Result |
|---|---|
| Lock held by another process | Exit 2 |
| Busy wait of 60 s runs out | The run fails and resumes from its last committed checkpoint |
| One thread unreadable in status | Only its row is marked unreadable |

## 5. Design notes

- A held lock reads `running` over any checkpoint state, so a just-started run shows as running.
- Executor identity is a per-call value, not graph state; only the operator's override is stored with the run options.

## 6. Acceptance criteria

- [ ] DUR-AC-1 Every row of §2.1 is tested, including refusals that write nothing.
- [ ] DUR-AC-2 A multi-process test with 16 writers loses no write.
- [ ] DUR-AC-3 Status and wait leave the state root unchanged (test with file hashes).
- [ ] DUR-AC-4 Fixture checkpoints from each earlier release resume in tests; the oldest is never regenerated.

## Open questions

None.

## References

