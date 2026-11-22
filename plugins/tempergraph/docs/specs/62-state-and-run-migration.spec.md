---
title: State and run migration across releases
type: component
status: review
prefix: MIG
adrs: [0056, 0055, 0014, 0024]
---

# State and run migration across releases

## 1. Overview

Runs outlive releases: a thread may sit paused for days, an orchestration supervises runs for hours, and every repository keeps a store of checkpoints and logs ([DUR](09-durability-and-resume.spec.md), [LOS](33-local-observability-store.spec.md)). This spec owns what happens to that state when the engine changes ([UPD](60-engine-update.spec.md)) or when a workflow's content changes under a thread (a plugin update, a merged upgrade, [WUP](63-workflow-upgrade.spec.md)).

The rule is **move at the resume boundary, pin only on a break** ([ADR-0056](../adr/0056-threads-move-to-the-new-engine-at-resume-unless-a-release-pins-them.adr.md)). A running process is never touched. A paused, unfinished or stopped thread moves to the current engine at its next resume, because each resume is a new process at a checkpoint and every unit is a fresh session. Only a release that cannot resume a thread's checkpoint format pins that thread to an engine that can, which is kept for it. A workflow change is tested by the two things a checkpoint holds, unit names and state keys; edges may change freely ([R-055](../research/R-055-updating-a-tool-with-long-lived-runs.rsrch.md) U13).

## 2. Contract

### 2.1 What a thread records

| Record | Where | Fields |
|---|---|---|
| Lock file | `locks/<workflow>/<task_id>.lock` ([LOS §2.1](33-local-observability-store.spec.md)) | Adds `engine_version`, `engine_digest`, `pid`; read by `update` and `--prune-engines` |
| Engine file | `runs/<workflow>/<task_id>/engine.json`, new | `schema_version`, `started_on` (engine version and digest), `last_on`, `pinned` (null or `{engine, reason, since}`), `history[]` (one entry per process: engine, `workflow_version`, `shape_digest`, started at) |
| `run_started` | Run log ([EVT §2.2](30-run-events.spec.md)) | Adds `engine_version`, `shape_digest` and `moved_from` (the engine and workflow version of the previous process, when they differ); its existing `workflow_version` takes the form of [VER §2.4](61-version-metadata.spec.md) |
| Status row | [DUR §2.2](09-durability-and-resume.spec.md) | Adds `engine` (last engine) and `engine_pin` |

All additions are optional keys under the current schema versions; readers that do not know them skip them ([CON §2.10](01-contracts.spec.md)).

### 2.2 Store layout migration

A release whose `store_layout` is above a store's ships one migration per step (`N → N+1`), each a pure function over the folder.

| Rule | Value |
|---|---|
| Kinds | `additive` (new files or folders; an older engine still reads the store tolerantly) or `breaking` (a file moved, renamed or rewritten) |
| When | State root: the first verb of the new engine that writes there (`run`, `resume`, `batch`, `orchestrate start`, `store prune`, `label` and the like). Home folder: `update` step 5 ([UPD §2.3](60-engine-update.spec.md)). Read-only verbs never migrate; they read older layouts tolerantly ([LOS §4](33-local-observability-store.spec.md)). |
| Lock | A migration lock `locks/.migrate`, created exclusively; a second process waits up to 60 s, then refuses with exit 2 |
| Live older processes | An `additive` step proceeds. A `breaking` step is refused while any run lock in the root names an older engine: the verb exits 2 naming the live run and `stop --drain` ([RCT](32-run-control.spec.md)) |
| Backup | Before a `breaking` step, every file it will move or rewrite and the manifest are copied to `backups/layout-<N>-<UTC timestamp>/`; append-only logs are never rewritten, only left in place for tolerant readers |
| After | `manifest.json` records the new layout, the engine that moved it and the backup path; one `store_migrated` engine-log line |
| Rollback | A backup restores only while no run has written to the root since the step ([UPD §2.6](60-engine-update.spec.md)); `store usage` lists backups; `store prune --backups` removes them |

### 2.3 Running processes

A process that holds a run lock keeps the engine it started on until it exits: it was loaded from its own environment folder, which `update` neither changes nor removes ([UPD §2.2](60-engine-update.spec.md)). Child sessions are executor processes, not engine processes, and are unaffected. The detached self-improvement child ([SIL](16-self-improvement.spec.md)) is a process of its own and keeps the engine that started it.

### 2.4 A thread at its next resume

The current engine reads `engine.json` and the checkpoint's format before anything else, and decides:

| Condition | Result |
|---|---|
| `pinned` is set | Dispatch: the shim re-executes the pinned engine's interpreter with the same constants-only argv; the decision and inputs pass by the usual hand-off ([SEC](14-security.spec.md)). The pinned engine resumes the thread. |
| The checkpoint format is in `resumes_checkpoint_formats` ([VER §2.2](61-version-metadata.spec.md)) | Move: the thread resumes on the current engine; `last_on` and `history` are updated; `run_started` carries `moved_from` |
| The checkpoint format is not | Pin: `pinned` is set to the newest kept engine that resumes the format, with reason `checkpoint_format`; then dispatch as above |
| No kept engine resumes the format | Refused, exit 2, naming the engine version needed; nothing written |

A release that changes the checkpoint format starts new threads in a separate database, `checkpoints/<workflow>.f<format>.sqlite`, so engines of two formats never open one file. Format 1 keeps the name `checkpoints/<workflow>.sqlite`. A pin is cleared only when the thread finishes or a person runs `resume --unpin` after the pinned engine is gone, which restarts the thread from its last unit boundary under the current engine's format only where the release ships a converter for that format; otherwise `--unpin` is refused.

### 2.5 A workflow changed under a thread

At each resume the engine compares the workflow's current `content_digest` with the one in `history`'s last entry. When they differ:

| Test | Passes when |
|---|---|
| Pending unit | The unit the thread is paused at, or would enter next, exists with the same name and kind |
| Units behind | Every unit the thread has completed still exists, so a `back` decision or a loop-back can still find it |
| State keys | Every artifact key a completed unit produced, and every one a pending or later unit reads, is still declared or still recorded |
| Inputs | Every input parameter the new version requires has a value in the thread's resolved input |

All pass: the thread resumes on the new content, `run_started` carries `moved_from` with both workflow versions, and the run log records one `workflow_changed` notice naming the units whose prompts, gates or limits changed. Edges, routes, prompts, criteria, limits and new units after the pending one may differ. Any test fails: the resume is refused with exit 2 and a list of the breaks; the remedies named are to reinstall the workflow version the thread started on (its `workflow_version` is in `history`) and resume, or to start a new thread.

### 2.6 Orchestrations and batches

| Case | Engine |
|---|---|
| A running supervisor ([ORC](45-orchestration.spec.md)) or batch parent | Keeps its engine; the child runs it starts use the supervisor's own environment, not the shim's current pointer, so one supervising process runs one engine ([R-055](../research/R-055-updating-a-tool-with-long-lived-runs.rsrch.md) U16) |
| `orchestrate resume` after the supervisor exited | The current engine supervises; each child thread follows §2.4 on its own resume |
| Mixed engines across an orchestration's nodes | Allowed; each node's status shows its run's engine |
| An orchestration file or event log of an older schema | Read tolerantly; written in the new schema only from the next event, never rewritten |

### 2.7 Documents read by integrations

Hooks, sinks and the monitor read engine documents with tolerant readers ([CON §2.10](01-contracts.spec.md)). A release with an `integration`-audience entry ([VER §2.3](61-version-metadata.spec.md)) is listed by `update`'s report; the engine keeps writing every key an older reader needs until the entry's `removal_in` release.

## 3. Behaviours

**MIG-B1 A paused thread moves.** Given a thread paused on 1.4.0 and an engine now at 1.5.0 that resumes the same checkpoint format, when the person resumes it, then 1.5.0 resumes it, `run_started` carries `moved_from: 1.4.0`, and status shows `engine: 1.5.0`.

**MIG-B2 A format break pins.** Given a thread paused on 1.6.2 (format 2) and an engine now at 2.0.0 that resumes format 3 only, with 1.6.2 kept, when the person resumes it, then `engine.json` records `pinned: 1.6.2, reason: checkpoint_format`, the thread resumes on 1.6.2, and a new thread of the same workflow starts on 2.0.0 in `checkpoints/<workflow>.f3.sqlite`.

| Thread format | Current resumes | Kept engines | Result |
|---|---|---|---|
| 2 | 2, 3 | — | move |
| 2 | 3 | 1.6.2 (resumes 2) | pin to 1.6.2 |
| 2 | 3 | none resumes 2 | exit 2, names an engine that resumes format 2 |

**MIG-B3 A workflow change that keeps the path.** Given a thread paused at `review` and a workflow upgrade that rewrote the `review` judge brief and added a unit after it, when the thread resumes, then it resumes on the new content with one `workflow_changed` notice naming `review`.

**MIG-B4 A workflow change that breaks the path.** Given a thread paused at `expand` and a new workflow version that renamed `expand` to `elaborate`, when the thread resumes, then it is refused with exit 2, the message names the missing unit and the workflow version the thread started on, and nothing is written.

**MIG-B5 Breaking layout step waits for older runs.** Given a state root with a live run on 1.4.0 and a 1.5.0 whose layout step is `breaking`, when a second run starts on 1.5.0 in that root, then it exits 2 naming the live run and `stop --drain`; once the run exits, the next start migrates with a backup.

**MIG-B6 Supervisor keeps its engine.** Given an orchestration supervised on 1.4.0 and an update to 1.5.0 mid-way, when the supervisor starts its next node's run, then that run starts on 1.4.0; after the supervisor exits, `orchestrate resume` supervises on 1.5.0.

**MIG-B7 Old checkpoints resume, as before.** Given the fixture checkpoints of every earlier release of the same format ([DUR-B6](09-durability-and-resume.spec.md)), when the current engine resumes each, then every one moves and is answered correctly.

## 4. Error conditions

| Condition | Result |
|---|---|
| `engine.json` missing (a thread from before this spec) | Read as `started_on` unknown, not pinned; written at the next resume with `started_on: {engine_version: null, engine: unknown}`, and that resume's `run_started` carries `moved_from: {engine_version: unknown}` with no `workflow_changed` notice (live check L-27 found it recorded as started on the resuming engine) |
| The pinned engine's folder is gone | Exit 2 naming it; `update` from a plugin copy of that version reinstalls it beside the current one |
| A migration step raises | The step's backup is restored, the manifest unchanged, exit 1 |
| Migration lock held past 60 s | Exit 2 naming the holder's pid |
| A workflow's `content_digest` cannot be computed (unreadable file) | Validation's own error; resume exit 2 |

## 5. Design notes

- LangGraph applies the latest graph to every thread ([R-055](../research/R-055-updating-a-tool-with-long-lived-runs.rsrch.md) U12), which is the default here; pinning, taken from Temporal's model (U15), is kept for the one case LangGraph cannot handle, a checkpoint the new code cannot read ([ADR-0056](../adr/0056-threads-move-to-the-new-engine-at-resume-unless-a-release-pins-them.adr.md)).
- The engine names compiled nodes after unit names ([CMP](03-compiler-and-flow.spec.md)); renaming that scheme is a checkpoint-format change by definition, so it pins rather than breaks.
- A workflow change is never blocked for what a checkpoint does not hold: a person who improves a prompt while a run waits for their decision gets the improved prompt on resume, recorded.
- Migrations run on first write, not in `update`, because `update` cannot reach repositories that are not checked out, and a store must never be half-moved under a live run of an older engine.
- **As built (R2-T6.2).** `durability/engine_file.py` holds the engine file, the decision of §2.4 as a pure function, and the four tests of §2.5; `store/migrate.py` holds the layout steps. The latest history entry also keeps a digest, the kind and the produced keys of each unit, which is what the tests of §2.5 and the `workflow_changed` notice compare; earlier entries drop it, and the history keeps its last 50 entries. A thread keeps the checkpoint format it was written in for as long as it lives, and every reader of one thread opens that format's database; a listing reads the databases of every format the engine resumes. The CLI decides before anything else and hands a pinned thread to its engine's interpreter with the argv it was given; the runner itself refuses such a thread with `engine_pinned`, so no path resumes it on the wrong engine. This release ships layout 1, checkpoint format 1 and no converter: `resume --unpin` clears a pin only when this engine resumes the thread's format. The engine file travels with a carried thread ([CAR](96-run-state-on-a-branch.spec.md)). The workflow version compared is the version with its content digest for a loaded package, and the declared version otherwise. Open: MIG-AC-6 waits for orchestration; MIG-B7's fixture checkpoints of earlier releases start with the first release that follows this one.

## 6. Acceptance criteria

- [x] MIG-AC-1 Every row of §2.4's table and of MIG-B2's table is a test with fixture checkpoints.
- [x] MIG-AC-2 Each test of §2.5 has a failing fixture that refuses with its own message and writes nothing, and a passing fixture that records `workflow_changed`.
- [x] MIG-AC-3 Every layout migration step has a before and after fixture tree, is idempotent, and a fault injected mid-step restores the backup.
- [x] MIG-AC-4 A read-only verb run against an older layout leaves it unchanged (hash test).
- [x] MIG-AC-5 Two engines of different checkpoint formats never open the same database file (test with both formats in one state root).
- [ ] MIG-AC-6 A supervisor started before an update starts every child on its own engine (two-process test).

## Open questions

| Question | Owner |
|---|---|
| Should a release that breaks the checkpoint format ship a thread converter, so pinned threads can be moved and old engines retired sooner? The design allows one (`resume --unpin`) but does not require it. | Owner |

## References

