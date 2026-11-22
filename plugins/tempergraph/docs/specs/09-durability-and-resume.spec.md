# Durability and resume

## Purpose

A run is a durable thread in a per-workflow SQLite checkpoint under the state root ([ADR-0014](../adr/0014-sqlite-checkpointer.adr.md); Postgres stays a seam for many hosts or about 50 concurrent runs). Resume is defined for every thread state, and the engine reads that state before it spends anything. Status and wait are read-only, model-free observers. Operators, skills, CI and the `tempergraph-monitor` plugin depend on the thread states, the resume rules and the status document; its per-thread detail form is [RDD](31-run-detail-document.spec.md). State is JSON merged by reducers under a stable thread id, and a fresh run never merges into a thread.

## Behaviours

### DUR-B1 Fresh run never merges

WHEN a fresh start names a thread in any state but `none` THE engine SHALL refuse it with exit 2 before the preflight, a worktree, the run log or any model call, naming the resume command and a new thread id form.

- GIVEN a `paused` thread WHEN `run` names its request again THEN it exits 2 and the message names `resume` and the new id form

### DUR-B9 Resume by thread state

WHEN `resume` names a thread THE engine SHALL read its state first and act by it: `none` (no checkpoint values) and `running` (lock held) are refused with exit 2; `paused` (a pending node with an interrupt) delivers the decision to that gate, and `rewind:<unit>` closes the pause and goes back ([RRN §2.3](81-reruns-and-feedback.spec.md)); `unfinished` (pending nodes, no interrupt) continues with a fresh attempt allowance, feedback going to the pending unit and `rewind:<unit>` the only decision accepted ([RRN §2.5](81-reruns-and-feedback.spec.md)); `stopped` (nothing pending, ended at a gate) re-opens with `retry`, `back` or `rewind` through the human node's own update and refuses other decisions; and `finished` is refused, `rerun` starting a new linked thread instead ([RRN §2.4](81-reruns-and-feedback.spec.md)).

- GIVEN a `stopped` thread WHEN `resume --decision proceed` runs THEN it exits 2 and nothing is written
- GIVEN an `unfinished` thread WHEN it is resumed with feedback THEN the pending unit gets the feedback
- GIVEN a thread whose lock is held WHEN it is classified THEN it reads `running` whatever its checkpoint holds

### DUR-B2 Cut-off attempt

WHEN a run resumes after an attempt whose start record no step record closed THE engine SHALL turn the start into an interrupted record with one notice (output and cost not recorded, workspace changes unaccounted for) and run the step again under the same attempt number without charging the budget.

- GIVEN a process killed during attempt 2 WHEN the run resumes THEN attempt 2 runs again and the retry budget is unchanged

### DUR-B3 Concurrency

WHEN many processes write to one workflow's checkpoint THE engine SHALL lose no write, waiting up to 60 s for the lock and retrying the creation of an empty store for 30 s.

- GIVEN sixteen processes writing to one checkpoint WHEN they commit THEN every write is present
- GIVEN a busy wait of 60 s that runs out WHEN the run fails THEN it resumes from its last committed checkpoint

### DUR-B10 One process per thread

WHEN a process asks for a thread's lock held by another process THE engine SHALL exit 2.

- GIVEN a running thread WHEN a second `resume` names it THEN it exits 2

### DUR-B4 Observer creates nothing

WHEN `status` or `wait` runs THE engine SHALL open the checkpoint read-only, probe the lock without creating it and for an instant only, and write no file: with no write-ahead log beside the store the store opens `immutable`, and with one `mode=ro`.

- GIVEN a live run WHEN `status` runs THEN the state root's file hashes are unchanged

### DUR-B11 Status document

WHEN `status` prints a thread THE engine SHALL write one row, under schema version 1, with `thread_id`, `workflow`, `state`, `alive` (from the lock probe), `attempt_in_flight` (unit, item, attempt number, executor, start time), `pending_gates` (unit, item, pause kind, resume command), `carry` for a carried thread (`on`, `pushed`, `pulled`, `unpushed` or `delete_failed`, [CAR](96-run-state-on-a-branch.spec.md)), `engine` and `engine_pin` (`{engine, reason, since}`, [MIG §2.1, §2.4](62-state-and-run-migration.spec.md)), `last_verdict`, `cost` (`reported`, `estimated`, `incomplete`), `executors` with CLI versions, `log_path` (local only), `alias`, `label`, `origin` (`cli`, `skill`, `batch`, `orchestration`, `self_improvement`, `upgrade`, `hook`, `ci`, `schedule` or `rerun`), `rerun_of`, `reruns` (with `same_branch: true` on a `--same-branch` one) and `superseded_by` ([RRN §2.4](81-reruns-and-feedback.spec.md)), `settings_digest`, `overridden_keys` and `settings_stale` (true when the settings files now resolve differently from the snapshot, null while one cannot be read, [RST §2.7](80-run-settings-and-overrides.spec.md)), `parent` ([ORC](45-orchestration.spec.md)), `schedule` (`schedule_id`, `fire_id`, `slot`, and `declared: true` for a pipeline export, [TCK §2.7](84-schedule-ticks-and-unattended-fires.spec.md)) and `resume_count`.

- GIVEN a thread started by a schedule WHEN `status` prints it THEN `origin` is `schedule` and `schedule` holds its ids and slot
- GIVEN a status reader of an earlier version WHEN it reads a row with a field it does not know THEN it ignores the field ([CON-B1](01-contracts.spec.md))
- GIVEN one thread whose checkpoint cannot be read WHEN `status` runs THEN only its row is marked unreadable

### DUR-B5 Wait

WHEN `wait` names a thread THE engine SHALL exit when the run pauses, completes, fails or records a new gate verdict, or when the timeout passes, with the run's own exit code when it is recorded in the run folder's `exit.json` ([LOS §2.1](33-local-observability-store.spec.md)), else 3 paused, 0 finished, 4 stopped or unfinished, 0 with the row for a new verdict on a running thread, and 5 with state `running` at the timeout, rebuilding a row only when a file's size or time moved.

- GIVEN a run that pauses WHEN `wait` is waiting on it THEN `wait` exits 3
- GIVEN `wait --timeout 5` on a running thread with no change WHEN 5 s pass THEN it exits 5 with state `running`

### DUR-B6 Old checkpoints resume

WHEN the current engine resumes a checkpoint written by an earlier release THE engine SHALL answer it correctly for each of paused, stopped, unfinished, fork, map and wait.

- GIVEN binary fixture checkpoints from each earlier release WHEN they are resumed THEN each continues as its state says

### DUR-B7 Settings change across resume

WHEN a resume carries `--set` or a named option THE engine SHALL apply it to the next attempt and store it in the thread's settings snapshot, reapplied on later resumes ([RST §2.6](80-run-settings-and-overrides.spec.md), [ADR-0072](../adr/0072-threads-snapshot-settings-and-reapply-them-on-resume.adr.md)); executor identity is a per-call value, never graph state.

- GIVEN a run paused after a step ran on `antigravity` WHEN resumed with `--set code.executor=claude` THEN the next attempt uses `claude`, and so does every later resume

### DUR-B8 Run alias

WHEN a start gives `--alias <name>` THE engine SHALL keep it in `runs/aliases.json` under the state root, of 1 to 40 letters, digits, `.`, `_` or `-`, unique among live threads, and accept it in place of the thread id in `status`, `resume` and `wait`; a `--label` is free text, scrubbed, of at most 80 characters.

- GIVEN a live thread holding `auth-fix` WHEN another start asks for it THEN it is refused with exit 2 naming the holder
- GIVEN that thread finished WHEN a new start takes `auth-fix` and `status auth-fix` runs THEN it shows the newer thread

## Acceptance criteria

- DUR-AC1 (DUR-B9): Every thread state's resume rule is tested, including refusals that write nothing
- DUR-AC2 (DUR-B3): A multi-process test with 16 writers loses no write
- DUR-AC3 (DUR-B4, DUR-B5): Status and wait leave the state root unchanged, by a test with file hashes
- DUR-AC4 (DUR-B6): Fixture checkpoints from each earlier release resume in tests, and the oldest is never regenerated
- DUR-AC5 (DUR-B1, DUR-B10): A fresh start on an existing thread and a second process on a held lock both exit 2 before any spend
- DUR-AC6 (DUR-B2): A killed attempt reruns under the same number without charging the budget
- DUR-AC7 (DUR-B11): A status row of a fixture thread holds every field of DUR-B11 that applies to it
- DUR-AC8 (DUR-B7): A setting changed at a resume applies to the next attempt and to every later resume
- DUR-AC9 (DUR-B8): An alias held by a live thread is refused to a second start and freed when the thread finishes
