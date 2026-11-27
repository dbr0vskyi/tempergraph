# State and run migration across releases

## Purpose

Runs outlive releases: a thread may sit paused for days, an orchestration supervises runs for hours, and every repository keeps a store of checkpoints and logs ([DUR](durability-and-resume.spec.md), [LOS](local-observability-store.spec.md)). This spec owns what happens to that state when the engine changes ([UPD](engine-update.spec.md)) or when a workflow's content changes under a thread (a plugin update, a merged upgrade, [WUP](workflow-upgrade.spec.md)). The rule is move at the resume boundary, pin only on a break ([ADR `threads-move-to-the-new-engine-at-resume-unless-a-release-pins-them`](../adr/threads-move-to-the-new-engine-at-resume-unless-a-release-pins-them.adr.md)): a running process is never touched; a paused, unfinished or stopped thread moves to the current engine at its next resume, because each resume is a new process at a checkpoint and every unit is a fresh session; only a release that cannot resume a thread's checkpoint format pins that thread to a kept engine that can. A workflow change is tested by the two things a checkpoint holds, unit names and state keys; edges may change freely ([research `updating-a-tool-with-long-lived-runs`](../research/updating-a-tool-with-long-lived-runs.rsrch.md) U13). People resuming threads, the update verb and the store's readers depend on it; design and build notes are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Depends on

- `contracts.spec.md`: persisted documents are versioned (CON-B14)
- `durability-and-resume.spec.md`: old checkpoints resume (DUR-B6); status document (DUR-B11)
- `engine-update.spec.md`: engine environments and the switch (UPD-B11); the update verb (UPD-B14); rollback (UPD-B17)
- `local-observability-store.spec.md`: state root top level (LOS-B7); manifest versions (LOS-B12)
- `orchestration.spec.md`: orchestration of runs
- `run-control.spec.md`: run control
- `run-events.spec.md`: run events for observers
- `security.spec.md`: security posture
- `self-improvement.spec.md`: self-improvement loop
- `version-metadata.spec.md`: engine release record (VER-B8); compatibility changelog entries (VER-B9); digests and the workflow version id (VER-B15)

## Behaviours

### MIG-B8 What a thread records

WHEN a run process starts or resumes THE engine SHALL add `engine_version`, `engine_digest` and `pid` to the lock file `locks/<workflow>/<task_id>.lock` ([LOS-B7](local-observability-store.spec.md)); keep `runs/<workflow>/<task_id>/engine.json` with `schema_version`, `started_on` (engine version and digest), `last_on` (the same, with the path of the program, [DUR-B11](durability-and-resume.spec.md)), `pinned` (null or `{engine, reason, since}`) and `history[]` (one entry per process: engine, `workflow_version`, `shape_digest`, started at, the latest entry also keeping each unit's digest, kind and produced keys, the list keeping its last 50); add `engine_version`, `shape_digest` and `moved_from` (the previous process's engine and workflow version, when they differ) to `run_started` ([EVT](run-events.spec.md)), its `workflow_version` in the form of [VER-B15](version-metadata.spec.md); and add `engine` and `engine_pin` to the status row ([DUR-B11](durability-and-resume.spec.md)), all optional keys that older readers skip ([CON-B14](contracts.spec.md)).

- GIVEN a thread resumed by a second process WHEN `engine.json` is read THEN `history` has two entries

### MIG-B9 Store layout steps

WHEN a release's `store_layout` is above a store's THE release SHALL ship one migration per step (`N → N+1`), each a pure function over the folder, `additive` (new files or folders an older engine still reads tolerantly) or `breaking` (a file moved, renamed or rewritten), and the engine SHALL run them in a state root at the first verb of the new engine that writes there (`run`, `resume`, `batch`, `orchestrate start`, `store prune`, `label` and the like) and in the home folder at the layout step of `update` ([UPD-B14](engine-update.spec.md)), never from a read-only verb, which reads older layouts tolerantly ([LOS-B12](local-observability-store.spec.md)).

- GIVEN a read-only verb against an older layout WHEN it runs THEN the layout is unchanged

### MIG-B10 Migration lock, backup and record

WHEN a layout step runs THE engine SHALL take `locks/.migrate` exclusively, a second process waiting up to 60 s and then exiting 2 naming the holder's pid; before a `breaking` step copy every file it will move or rewrite and the manifest to `backups/layout-<N>-<UTC timestamp>/`, never rewriting an append-only log; afterwards record in `manifest.json` the new layout, the engine that moved it and the backup path, with one `store_migrated` engine-log line; on a step that raises restore its backup, leave the manifest unchanged and exit 1; restore a backup only while no run has written to the root since the step ([UPD-B17](engine-update.spec.md)); list backups in `store usage` and remove them with `store prune --backups`.

- GIVEN a fault injected mid-step WHEN the step raises THEN the backup is restored, the manifest is unchanged and it exits 1

### MIG-B5 Breaking layout step waits for older runs

WHEN a `breaking` layout step would run while a run lock in the root names an older engine THE engine SHALL refuse with exit 2 naming the live run and `stop --drain` ([RCT](run-control.spec.md)), and an `additive` step SHALL proceed.

- GIVEN a live run on 1.4.0 and a 1.5.0 whose step is `breaking` WHEN a second run starts on 1.5.0 THEN it exits 2 naming the live run and `stop --drain`, and once that run exits the next start migrates with a backup

### MIG-B11 Running processes keep their engine

WHEN `update` switches engines while a process holds a run lock THE process SHALL keep the engine it started on until it exits, loaded from its own environment folder that `update` neither changes nor removes ([UPD-B11](engine-update.spec.md)); executor child sessions are not engine processes and are unaffected, and the detached self-improvement child ([SIL](self-improvement.spec.md)) keeps the engine that started it.

- GIVEN a run in progress on 1.4.0 WHEN 1.5.0 becomes current THEN the run finishes on 1.4.0 and records it

### MIG-B12 A thread at its next resume

WHEN a thread resumes THE engine SHALL read `engine.json` and the checkpoint's format before anything else, the CLI deciding before the runner and the runner itself refusing a pinned thread with `engine_pinned`, and then: where `pinned` is set, dispatch, the shim re-executing the pinned engine's interpreter with the same constants-only argv and the decision and inputs passing by the usual hand-off ([SEC](security.spec.md)); where the format is in `resumes_checkpoint_formats` ([VER-B8](version-metadata.spec.md)), move, updating `last_on` and `history` and putting `moved_from` on `run_started`; where it is not, pin to the newest kept engine that resumes it with reason `checkpoint_format` and dispatch; and where no kept engine resumes it, exit 2 naming the engine version needed and write nothing, or naming the pinned engine whose folder is gone, which `update` from a plugin copy of that version reinstalls beside the current one.

- GIVEN a thread paused on 1.4.0 and 1.5.0 resuming the same format WHEN resumed THEN 1.5.0 resumes it, `run_started` carries `moved_from: 1.4.0` and status shows `engine: 1.5.0`
- GIVEN a pinned engine's folder removed WHEN its thread resumes THEN it exits 2 naming that engine

### MIG-B1 A paused thread moves

WHEN a thread paused on an older engine resumes on an engine that resumes its checkpoint format THE engine SHALL resume it on the current engine and record the move.

- GIVEN thread format 2 and a current engine resuming 2 and 3 WHEN resumed THEN it moves

### MIG-B2 A format break pins

WHEN a thread's checkpoint format is not resumed by the current engine THE engine SHALL pin it to a kept engine that resumes the format, and start new threads of the same workflow on the current engine.

- GIVEN a thread on 1.6.2 (format 2), an engine at 2.0.0 resuming format 3 only and 1.6.2 kept WHEN resumed THEN `engine.json` records `pinned: 1.6.2, reason: checkpoint_format`, it resumes on 1.6.2, and a new thread starts on 2.0.0 in `checkpoints/<workflow>.f3.sqlite`
- GIVEN thread format 2, a current engine resuming 3 and no kept engine resuming 2 WHEN resumed THEN it exits 2 naming an engine that resumes format 2

### MIG-B13 One database per checkpoint format

WHEN a release changes the checkpoint format THE engine SHALL start new threads in `checkpoints/<workflow>.f<format>.sqlite`, format 1 keeping `checkpoints/<workflow>.sqlite`, so engines of two formats never open one file; a thread keeps its format for life, every reader of one thread opens that format's database, and a listing reads the databases of every format the engine resumes.

- GIVEN threads of formats 1 and 2 in one state root WHEN both engines run THEN neither opens the other's database

### MIG-B14 Clearing a pin

WHEN a pinned thread finishes, or a person runs `resume --unpin` after the pinned engine is gone THE engine SHALL clear the pin, `--unpin` restarting the thread from its last unit boundary under the current engine's format only where the release ships a converter for that format or the current engine resumes it, and refused otherwise.

- GIVEN no converter and a format the current engine does not resume WHEN `resume --unpin` runs THEN it is refused

### MIG-B15 A workflow changed under a thread

WHEN a thread resumes and the workflow's current `content_digest` differs from the last `history` entry's (the declared version where no package is loaded) THE engine SHALL test that the pending unit (the one paused at or entered next) exists with the same name and kind, every completed unit still exists so a `back` decision or loop-back can find it, every artifact key a completed unit produced and every one a pending or later unit reads is still declared or recorded (a unit whose artifacts a trip back cleared is not a completed unit for this test: it runs again before any reader of its keys), and every input parameter the new version requires has a value in the resolved input; when all pass, resume on the new content with `moved_from` carrying both workflow versions and one `workflow_changed` notice naming the units whose prompts, gates or limits changed, edges, routes, prompts, criteria, limits and new units after the pending one free to differ; when any fails, exit 2 listing the breaks, naming as remedies starting a new thread and, for a workflow loaded from a package registered from a local folder, reinstalling the content version the thread ran on from that folder, and write nothing; an unreadable file is validation's own error and the resume exits 2.

- GIVEN a passing fixture for each test WHEN resumed THEN `workflow_changed` is recorded
- GIVEN a failing fixture for each test WHEN resumed THEN it refuses with its own message and writes nothing
- GIVEN a thread of three units where the third reads a key the second produces, a BACK from the third to the first, and the workflow content changed before the second ran again WHEN resumed THEN it resumes with one `workflow_changed` notice and is not refused for the second unit's unrecorded key

### MIG-B3 A workflow change that keeps the path

WHEN a changed workflow passes every test of MIG-B15 THE engine SHALL resume on the new content with one `workflow_changed` notice.

- GIVEN a thread paused at `review` and an upgrade that rewrote the `review` brief and added a unit after it WHEN resumed THEN it resumes on the new content with one `workflow_changed` notice naming `review`

### MIG-B4 A workflow change that breaks the path

WHEN a changed workflow fails a test of MIG-B15 THE engine SHALL refuse the resume and write nothing.

- GIVEN a thread paused at `expand` and a version that renamed `expand` to `elaborate` WHEN resumed THEN it exits 2 naming the missing unit and the version the thread started on, and nothing is written

### MIG-B16 A thread from before the engine file

WHEN a thread with no `engine.json` resumes THE engine SHALL read it as started on an unknown engine and not pinned, write `started_on: {engine_version: null, engine: unknown}`, and put `moved_from: {engine_version: unknown}` on that resume's `run_started` with no `workflow_changed` notice.

- GIVEN a thread from before the engine file WHEN resumed THEN it is recorded as started on an unknown engine, not on the resuming one

### MIG-B17 Orchestrations and batches

WHEN a supervisor ([ORC](orchestration.spec.md)) or batch parent runs across an update THE engine SHALL start its child runs from the supervisor's own environment, not the shim's current pointer, so one supervising process runs one engine ([research `updating-a-tool-with-long-lived-runs`](../research/updating-a-tool-with-long-lived-runs.rsrch.md) U16); after it exits, `orchestrate resume` supervises on the current engine and each child thread follows MIG-B12 on its own resume; mixed engines across nodes are allowed and each node's status shows its run's engine; and an orchestration file or event log of an older schema is read tolerantly and written in the new schema only from the next event, never rewritten.

- GIVEN an orchestration event log of an older schema WHEN the current engine appends THEN earlier lines are unchanged

### MIG-B6 Supervisor keeps its engine

WHEN a supervisor started on one engine starts a node's run after an update THE engine SHALL start that run on the supervisor's engine.

- GIVEN an orchestration supervised on 1.4.0 and an update to 1.5.0 mid-way WHEN the next node's run starts THEN it starts on 1.4.0, and after the supervisor exits `orchestrate resume` supervises on 1.5.0

### MIG-B18 Documents read by integrations

WHEN a release has an `integration`-audience changelog entry ([VER-B9](version-metadata.spec.md)) THE engine SHALL list it in `update`'s report and keep writing every key an older tolerant reader ([CON-B14](contracts.spec.md)) needs until the entry's `removal_in` release.

- GIVEN a key deprecated with `removal_in: 3.0.0` WHEN 2.5.0 writes the document THEN the key is still written

### MIG-B7 Old checkpoints resume, as before

WHEN the current engine resumes the fixture checkpoints of every earlier release of the same format ([DUR-B6](durability-and-resume.spec.md)) THE engine SHALL move each and answer it correctly.

- GIVEN the fixture checkpoints of each earlier release WHEN resumed THEN every one moves and is answered correctly

## Acceptance criteria

- MIG-AC1 (MIG-B12, MIG-B1, MIG-B2, MIG-B8, MIG-B16): Every case of MIG-B12 and MIG-B2 is a test with fixture checkpoints
- MIG-AC2 (MIG-B15, MIG-B3, MIG-B4): Each test of MIG-B15 has a failing fixture that refuses with its own message and writes nothing, and a passing fixture that records `workflow_changed`; a trip-back-cleared unit's unrecorded key does not refuse the resume
- MIG-AC3 (MIG-B9, MIG-B10, MIG-B5): Every layout migration step has a before and after fixture tree, is idempotent, and a fault injected mid-step restores the backup
- MIG-AC4 (MIG-B9): A read-only verb run against an older layout leaves it unchanged (hash test)
- MIG-AC5 (MIG-B13, MIG-B14): Two engines of different checkpoint formats never open the same database file (test with both formats in one state root)
- MIG-AC6 (MIG-B6, MIG-B11, MIG-B17, MIG-B18, MIG-B7): A supervisor started before an update starts every child on its own engine (two-process test), and fixture checkpoints of each earlier release resume

## Open questions

- Should a release that breaks the checkpoint format ship a thread converter, so pinned threads can be moved and old engines retired sooner? The design allows one (`resume --unpin`) but does not require it. Owner: owner.
- Not built yet: MIG-AC6 waits for orchestration, and the fixture checkpoints of earlier releases start with the first release after release 2, which ships layout 1, checkpoint format 1 and no converter. Owner: engine owner.
