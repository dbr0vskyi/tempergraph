---
title: Durability and resume
type: component
status: review
prefix: DUR
adrs: [0014, 0015, 0072, 0073]
---

# Durability and resume

## 1. Overview

A run is a LangGraph thread in a per-workflow SQLite checkpoint under the state root. Resume is defined for every thread state, and the engine reads that state before it spends anything. Status and wait are read-only, model-free observers. This spec owns contract C7 and the status document the `tempergraph-monitor` plugin reads; its per-thread detail form is [RDD](31-run-detail-document.spec.md).

## 2. Contract

```python
def classify(workflow: str, thread_id: str) -> ThreadState: ...       # read-only URI; creates nothing
def start(workflow: str, request: ResolveResult, options: RunOptions) -> ExitCode: ...
def resume(workflow: str, thread_id: str, decision: Decision | None, inputs: dict[str, str],
           feedback: Feedback | None, options: RunOptions) -> ExitCode: ...   # RRN §2; RunOptions in CON §2.12
def status(selector: Selector) -> StatusDocument: ...
def wait(selector: Selector, timeout_s: int) -> WaitOutcome: ...
```

### 2.1 Resume by thread state

| State, recognised by | Resume does |
|---|---|
| `none`: no checkpoint values | Refused (exit 2) |
| `paused`: a pending node with an interrupt | Delivers the decision to that gate; `rewind:<unit>` closes the pause and goes back ([RRN §2.3](81-reruns-and-feedback.spec.md)) |
| `unfinished`: pending nodes, no interrupt | Continues with a fresh attempt allowance; feedback goes to the pending unit; `rewind:<unit>` is the only decision accepted ([RRN §2.5](81-reruns-and-feedback.spec.md)) |
| `stopped`: nothing pending, ended at a gate | Re-opens with `retry`, `back` or `rewind`, through the human node's own update; other decisions refused |
| `finished`: every unit passed | Refused; `rerun` starts a new linked thread from any unit ([RRN §2.4](81-reruns-and-feedback.spec.md)) |
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
| `origin` | how the run started: `cli`, `skill`, `batch`, `orchestration`, `self_improvement`, `upgrade` ([UWF](64-upgrade-workflow.spec.md)), `hook`, `ci` or `rerun` |
| `rerun_of`, `reruns` | the source thread of a rerun, and the reruns made from this thread ([RRN §2.4](81-reruns-and-feedback.spec.md)) |
| `settings_digest`, `overridden_keys`, `settings_stale` | the thread's resolved settings ([RST §2.7](80-run-settings-and-overrides.spec.md)); `settings_stale` is true when the files now resolve differently from the thread's snapshot |
| `parent` | for a run an orchestration started: orchestration id, node id and item ([ORC](45-orchestration.spec.md)) |
| `resume_count` | number of resumes so far (the resume chain length) |
| `engine`, `engine_pin` | the engine version of the last process, and the engine the thread is pinned to, if any ([MIG §2.4](62-state-and-run-migration.spec.md)) |

Adding these fields keeps schema version 1: readers ignore unknown keys and read a missing key as not recorded ([CON §2.10](01-contracts.spec.md)).

## 3. Behaviours

**DUR-B1 Fresh run never merges.** Given a thread in any state but `none`, when a fresh start is requested, then it is refused with exit 2 before the preflight, a worktree, the run log or any model call; the message names the resume command and a new thread id form.

**DUR-B2 Cut-off attempt.** Given an attempt whose start record no step record closed (the process was killed), when the run resumes, then the start becomes an interrupted record with one notice (output and cost not recorded, workspace changes unaccounted for) and the step runs again under the same attempt number without charging the budget.

**DUR-B3 Concurrency.** Given sixteen processes writing to one workflow's checkpoint, when they commit, then none loses a write: the saver waits up to 60 s for the lock, and creating an empty store is retried for 30 s.

**DUR-B4 Observer creates nothing.** Given a live run, when status or wait runs, then it opens the checkpoint read-only, probes the lock without creating it and for an instant only, and writes no file.

**DUR-B5 Wait.** Given `wait` on a thread, when the run pauses, completes, fails or records a new gate verdict, or the timeout passes, then wait exits with the outcome's code; it polls file sizes and times and rebuilds a row only when one moved.

WHEN `wait` names a thread THE engine SHALL exit when the run pauses, completes, fails or records a new gate verdict, or when the timeout passes, with the run's own exit code when it is recorded in the run folder's `exit.json` ([LOS §2.1](33-local-observability-store.spec.md)), else 3 paused, 0 finished, 4 stopped or unfinished, 0 with the row for a new verdict on a running thread, and 5 with state `running` at the timeout, rebuilding a row only when a file's size or time moved.

**DUR-B7 Settings change across resume.** Given a run paused after a step ran on `antigravity`, when the operator resumes with `--set code.executor=claude` (or `--step-executor code=claude`), then the next attempt uses `claude`; the override is stored in the thread's settings snapshot and reapplied on later resumes. Any catalog key changes the same way ([RST §2.6](80-run-settings-and-overrides.spec.md)).

**DUR-B8 Run alias.** Given a start with `--alias auth-fix`, when another live thread already holds that alias, then the start is refused with exit 2 naming the holder; once the first thread is finished its alias is free, and a status by alias of a finished thread shows the latest one.

## 4. Error conditions

| Condition | Result |
|---|---|
| Lock held by another process | Exit 2 |
| Busy wait of 60 s runs out | The run fails and resumes from its last committed checkpoint |
| One thread unreadable in status | Only its row is marked unreadable |

## 5. Design notes

- A held lock reads `running` over any checkpoint state, so a just-started run shows as running.
- Executor identity is a per-call value, not graph state; only the operator's settings snapshot is stored with the run options ([ADR-0072](../adr/0072-threads-snapshot-settings-and-reapply-them-on-resume.adr.md)).

## 6. Acceptance criteria

- [ ] DUR-AC-1 Every row of §2.1 is tested, including refusals that write nothing.
- [ ] DUR-AC-2 A multi-process test with 16 writers loses no write.
- [ ] DUR-AC-3 Status and wait leave the state root unchanged (test with file hashes).
- [ ] DUR-AC-4 Fixture checkpoints from each earlier release resume in tests; the oldest is never regenerated.

## Open questions

None.

## References

