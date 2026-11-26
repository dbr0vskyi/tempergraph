# Durability and resume

## Purpose

A run is a durable thread in a per-workflow SQLite checkpoint under the state root ([ADR `sqlite-checkpointer`](../adr/sqlite-checkpointer.adr.md); Postgres stays a seam for many hosts or about 50 concurrent runs). Resume is defined for every thread state, and the engine reads that state before it spends anything. Status and wait are read-only, model-free observers. Operators, skills, CI and the `tempergraph-monitor` plugin depend on the thread states, the resume rules and the status document; its per-thread detail form is [RDD](run-detail-document.spec.md). State is JSON merged by reducers under a stable thread id, and a fresh run never merges into a thread.

## Behaviours

### DUR-B1 Fresh run never merges

WHEN a fresh start names a thread in any state but `none` THE engine SHALL refuse it with exit 2 before the preflight, a worktree, the run log or any model call, naming the resume command and a new thread id form.

- GIVEN a `paused` thread WHEN `run` names its request again THEN it exits 2 and the message names `resume` and the new id form

### DUR-B9 Resume by thread state

WHEN `resume` names a thread THE engine SHALL read its state first and act by it: `none` (no checkpoint values) and `running` (lock held) are refused with exit 2; `paused` (a pending node with an interrupt) delivers the decision to that gate, and `rewind:<unit>` closes the pause and goes back ([RRN-B16](reruns-and-feedback.spec.md)); `unfinished` (pending nodes, no interrupt) continues with a fresh attempt allowance, feedback going to the pending unit and `rewind:<unit>` the only decision accepted ([RRN-B19](reruns-and-feedback.spec.md)); `stopped` (nothing pending, ended at a gate) re-opens with `retry`, `back` or `rewind` through the human node's own update and refuses other decisions; and `finished` is refused, `rerun` starting a new linked thread instead ([RRN-B17, RRN-B18](reruns-and-feedback.spec.md)).

- GIVEN a `stopped` thread WHEN `resume --decision proceed` runs THEN it exits 2 and nothing is written
- GIVEN an `unfinished` thread WHEN it is resumed with feedback THEN the pending unit gets the feedback
- GIVEN a thread whose lock is held WHEN it is classified THEN it reads `running` whatever its checkpoint holds

### DUR-B14 A refused re-open names the stop

WHEN `resume` refuses a thread in state `stopped` because it carries no decision or one other than `retry`, `back` or `rewind` THE engine SHALL name in the refusal the unit the thread stopped at and the reason of its stop, the word its `run_exit` record carries.

- GIVEN a thread a person stopped at unit `a` WHEN `resume` runs with no decision THEN it exits 2 and its message names `a` and the reason `person`
- GIVEN a thread stopped at unit `a` with its retry budget spent and `on_budget_spent` set to `stop` WHEN `resume --decision proceed` runs THEN it exits 2 and its message names `a` and the reason `budget`
- GIVEN the same thread WHEN `resume --decision retry` runs THEN it is not refused

### DUR-B2 Cut-off attempt

WHEN a run resumes after an attempt whose start record no step record closed THE engine SHALL turn the start into an interrupted record with one notice (output and cost not recorded, workspace changes unaccounted for) and run the step again under the same attempt number without charging the budget.

- GIVEN a process killed during attempt 2 WHEN the run resumes THEN attempt 2 runs again and the retry budget is unchanged

### DUR-B12 Resume after a usage limit

WHEN `resume` names a thread paused for a usage limit ([HUM-B14](gate-and-human.spec.md)) and carries no decision THE engine SHALL rerun only the session the usage limit ended, in its unit, under the attempt number that session had and with every counter as it was before that session ran.

- GIVEN a step with a retry budget of 3 whose first session the usage limit ended WHEN `resume` runs with no decision THEN the session that runs is attempt 1 of the same unit and no retry has been spent
- GIVEN a judge session that the usage limit ended after its step passed WHEN `resume` runs with no decision THEN the judge runs and the step does not
- GIVEN a thread paused for a usage limit whose reset instant has not passed WHEN `resume` runs and the session it reruns ends not ok with `usage_limit` true THEN the resume is not refused and the thread pauses for a usage limit with every counter as it was

### DUR-B3 Concurrency

WHEN many processes write to one workflow's checkpoint THE engine SHALL lose no write, waiting up to 60 s for the lock and retrying the creation of an empty store for 30 s.

- GIVEN sixteen processes writing to one checkpoint WHEN they commit THEN every write is present
- GIVEN a busy wait of 60 s that runs out WHEN the run fails THEN it resumes from its last committed checkpoint

### DUR-B10 One process per thread

WHEN a process asks for a thread's lock held by another process THE engine SHALL exit 2.

- GIVEN a running thread WHEN a second `resume` names it THEN it exits 2

### DUR-B4 Observer creates nothing

WHEN `status` or `wait` runs THE engine SHALL open the checkpoint read-only, probe the lock without creating it and for an instant only, and write no file, except what `status` hands to the loop for a lost runner ([SIL-B29](runs-without-a-final-exit.spec.md)): with no write-ahead log beside the store the store opens `immutable`, and with one `mode=ro`.

- GIVEN a live run WHEN `status` runs THEN the state root's file hashes are unchanged

### DUR-B11 Status document

WHEN `status` prints a thread THE engine SHALL write one row, under schema version 1, with `thread_id`, `workflow`, `state`, `alive` (from the lock probe), `attempt_in_flight` (unit, item, attempt number, executor, start time), `pending_gates` (unit, item, pause kind, resume command), `finalizer` (the `outcome`, `reason` and `manual_steps` of the `finalize` event, present only for a finalizer that returned manual steps or ended with outcome `error`, [FIN-B8](finalizer-contract.spec.md)), `carry` for a carried thread (`on`, `pushed`, `pulled`, `unpushed` or `delete_failed`, [CAR](run-state-on-a-branch.spec.md)), `engine` and `engine_pin` (`{engine, reason, since}`, [MIG-B8, MIG-B12, MIG-B13, MIG-B14](state-and-run-migration.spec.md)), `last_verdict`, `cost` (`reported`, `estimated`, `incomplete`), `executors` with CLI versions, `log_path` (local only), `alias`, `label`, `origin` (`cli`, `skill`, `batch`, `orchestration`, `self_improvement`, `upgrade`, `hook`, `ci`, `schedule` or `rerun`), `rerun_of`, `reruns` (with `same_branch: true` on a `--same-branch` one) and `superseded_by` ([RRN-B17, RRN-B18](reruns-and-feedback.spec.md)), `settings_digest`, `overridden_keys` and `settings_stale` (true when the settings files now resolve differently from the snapshot, null while one cannot be read, [RST-B27](run-settings-and-overrides.spec.md)), `parent` ([ORC](orchestration.spec.md)), `schedule` (`schedule_id`, `fire_id`, `slot`, and `declared: true` for a pipeline export, [TCK-B23, TCK-B24](schedule-ticks-and-unattended-fires.spec.md)) and `resume_count`.

- GIVEN a thread started by a schedule WHEN `status` prints it THEN `origin` is `schedule` and `schedule` holds its ids and slot
- GIVEN a status reader of an earlier version WHEN it reads a row with a field it does not know THEN it ignores the field ([CON-B1](contracts.spec.md))
- GIVEN one thread whose checkpoint cannot be read WHEN `status` runs THEN only its row is marked unreadable

### DUR-B13 A usage-limit pause on the status row

WHEN `status` prints a thread paused for a usage limit ([HUM-B14](gate-and-human.spec.md)) THE engine SHALL add `usage_limit_resets_at` to its row: the latest reset instant among the thread's pending pauses for a usage limit, null when none of them carries one.

- GIVEN two pending gates of a parallel block, both paused for a usage limit, one with an earlier and one with a later reset instant WHEN `status --json` runs THEN its row holds the later instant as `usage_limit_resets_at`
- GIVEN a thread paused for a usage limit whose executor reported no reset instant WHEN `status --json` runs THEN its row holds `usage_limit_resets_at` null
- GIVEN a thread that was paused for a usage limit and is running after a `resume` WHEN `status --json` runs THEN its row holds no `usage_limit_resets_at`

### DUR-B15 An unfinished thread's row says how to continue it

WHEN `status` prints a thread in state `unfinished` THE engine SHALL add to its row `resume`, the exact command that continues the thread with no decision.

- GIVEN a thread stopped by request WHEN `status --json` runs THEN its row shows the state `unfinished`, the exit reason `stopped_by_request` and a `resume` command that names the workflow and the thread and carries no `--decision`
- GIVEN a thread paused at a gate WHEN `status --json` runs THEN its row holds no `resume`, and each of its `pending_gates` carries its own resume command

### DUR-B5 Wait

WHEN `wait` names a thread THE engine SHALL exit when the run pauses, completes, fails or records a new gate verdict, or when the timeout passes, with the run's own exit code when it is recorded in the run folder's `exit.json` ([LOS-B7, LOS-B8, LOS-B9](local-observability-store.spec.md)), else 3 paused, 0 finished, 4 stopped or unfinished, 0 with the row for a new verdict on a running thread, and 5 with state `running` at the timeout, rebuilding a row only when a file's size or time moved.

- GIVEN a run that pauses WHEN `wait` is waiting on it THEN `wait` exits 3
- GIVEN `wait --timeout 5` on a running thread with no change WHEN 5 s pass THEN it exits 5 with state `running`

### DUR-B6 Old checkpoints resume

WHEN the current engine resumes a checkpoint written by an earlier release THE engine SHALL answer it correctly for each of paused, stopped, unfinished, fork, map and wait.

- GIVEN binary fixture checkpoints from each earlier release WHEN they are resumed THEN each continues as its state says

### DUR-B7 Settings change across resume

WHEN a resume carries `--set` or a named option THE engine SHALL apply it to the next attempt and store it in the thread's settings snapshot, reapplied on later resumes ([RST-B26](run-settings-and-overrides.spec.md), [ADR `threads-snapshot-settings-and-reapply-them-on-resume`](../adr/threads-snapshot-settings-and-reapply-them-on-resume.adr.md)); executor identity is a per-call value, never graph state.

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
- DUR-AC7 (DUR-B11): A status row of a fixture thread holds every field of DUR-B11 that applies to it: `finalizer` equal to the `finalize` event's `outcome`, `reason` and `manual_steps` for a finalizer that returned manual steps, with `outcome` `error` and no steps for one that raised, and absent for one that published or skipped without steps
- DUR-AC8 (DUR-B7): A setting changed at a resume applies to the next attempt and to every later resume
- DUR-AC9 (DUR-B8): An alias held by a live thread is refused to a second start and freed when the thread finishes
- DUR-AC10 (DUR-B12): A fixture thread paused by a step session that the usage limit ended and resumed with no decision runs that session under the same attempt number with every counter equal to its value before the session, and a fixture thread paused by a judge session that the usage limit ended and resumed with no decision starts the judge and not the step
- DUR-AC11 (DUR-B13): The `status` row of a fixture thread paused for a usage limit holds `usage_limit_resets_at` equal to the reset its stand-in executor reported (the latest of them when several gates of a parallel block are paused for it), null when it reported none, and the row of that thread while it runs after a `resume` holds no such key
- DUR-AC12 (DUR-B14): A fixture thread a person stopped and a fixture thread stopped with its budget spent are each refused on `resume` with exit 2 and a message naming the unit and the reason `person` or `budget`, writing nothing, and a `retry` resume of each is accepted
- DUR-AC13 (DUR-B15): The `status --json` row of a fixture thread stopped by request holds a `resume` command that a plain `resume` accepts, and the rows of a fixture paused thread and a fixture running thread hold none
