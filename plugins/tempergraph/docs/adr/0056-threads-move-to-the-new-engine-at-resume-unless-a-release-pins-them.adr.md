# ADR-0056 Threads move to the current engine at their next resume; only a checkpoint-format break pins them

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The engine update must say what happens to runs in flight. A run may be running, paused for days, unfinished or stopped; an orchestration supervisor may be mid-way; a detached self-improvement child may be running ([R-057](../research/R-057-engine-update-and-workflow-upgrade-gaps.rsrch.md) X6). The same question arises when a workflow's content changes under a paused thread (a plugin update or a merged upgrade, X8). LangGraph applies the newest graph to every thread and breaks only on a removed or renamed node or state key; Temporal lets a run be pinned to the code it started on or upgraded automatically, and retires a version once its pinned runs drain ([R-055](../research/R-055-updating-a-tool-with-long-lived-runs.rsrch.md) U12 to U16). The engine already resumes old checkpoints from fixtures ([DUR-B6](../specs/09-durability-and-resume.spec.md)).

## Decision

We will ([MIG](../specs/62-state-and-run-migration.spec.md)):

1. Never touch a running process: it finishes on the engine it started on, and so do the child runs a running supervisor starts.
2. Move a paused, unfinished or stopped thread to the current engine at its next resume, recorded on the thread.
3. Pin a thread to a kept older engine only when the current release cannot resume its checkpoint format, and give each later format its own checkpoint database.
4. Let a workflow change under a thread when the thread's pending unit, completed units, state keys and inputs still exist; refuse the resume otherwise, naming the breaks.
5. Migrate a store's layout at the first write of the new engine, with a backup, and never while an older engine's run is live in that store for a breaking step.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Move at resume, pin on a format break (chosen) | Matches LangGraph's own model; a resume is a new process at a checkpoint, the natural boundary; fixes reach paused runs; pins only where unavoidable | Mixed engines within one thread's history; an older engine kept for pinned threads |
| Pin every thread to its start engine (Temporal pinned) | Each thread runs one code version | Old engines kept for days per paused thread; a fix never reaches a paused run; every resume dispatches |
| Move everything, refuse old formats | No kept engines | A release that changes the format strands paused work |
| Drain before update | No mixed states | Blocks updates for days; a person must finish every pause in every repository |

## Decision rationale

| Criterion | Move, pin on break | Pin all | Move all | Drain |
|---|---|---|---|---|
| No paused thread stranded | yes | yes | no | yes |
| Fixes reach paused threads | yes | no | yes | n/a |
| Old engines kept | only for format breaks | for every live thread | none | none |
| Update can happen at any time | yes | yes | yes | no |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | Running a thread's later attempts on a newer engine than its earlier ones is acceptable, because each attempt is recorded with its engine and workflow version. | MIG §2.1 |
| A2 | Checkpoint-format breaks are rare (a release that renames the node scheme, a state key or the saver's tables), so pins are rare. | MIG §2.4 |
| A3 | A person who changes a workflow while a run waits wants the changed prompts on resume, as long as the path still exists. | MIG §2.5 |

## Consequences

- Positive: an update never blocks on runs; paused work resumes with fixes; the records say which engine and which workflow version each process ran.
- Negative: two checkpoint databases per workflow after a format break; a dispatch path in the shim.
- Risk: a behaviour change mid-thread surprises a person. Mitigation: `run_started` carries `moved_from`, the status shows the engine, and a `behaviour` changelog entry is listed in the update report.

## Revisit when

A format break strands a thread in practice, or the owner wants pinning per workflow as an option.
