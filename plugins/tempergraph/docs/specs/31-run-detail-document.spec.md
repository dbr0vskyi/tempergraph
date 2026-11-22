# Run detail document

## Purpose

One versioned JSON document that describes a single thread in full: the declared plan, every visit and attempt of every unit, each attempt's step session, check, judge and gate, the sessions with their transcript and activity locations, the pause in front of a person, cost, and derived health. It is what a monitor draws when a person "enters" a run. It is built on demand by `status --detail <selector> --json` from the diagram model, the run log and the checkpoint opened read-only; it is never stored, calls no model and creates nothing (OVR-B15), so it never disagrees with the run log ([ADR-0022](../adr/0022-observers-read-files-not-sockets.adr.md)). The one-row-per-thread status document stays owned by [DUR](09-durability-and-resume.spec.md); this spec owns its detail form. The newer unit kinds add no section: scripts are attempts with no session, council members and chairs are sessions of the step with their round, contest slots are items, and an ask's questions are the pause's payload. The monitor and anyone drilling into a run depend on it; `health` fields are hints for a person, and nothing in the engine acts on them.

## Behaviours

### RDD-B7 Document blocks

WHEN the detail document (schema version 1) is built THE engine SHALL write `schema_version`, `generated_at`, `run` (every field of the thread's status row plus `segment`, `last_seq`, local `run_dir` and `plan_digest`), `plan`, `units[]`, `pause`, `budgets` (each counter's used and limit, and the run cost cap with what is left of it), `health`, `supervision` (touches in time order with class, action, caller kind, decider, relay and wait seconds, the supervising host sessions seen so far, the level so far, and supervision cost so far with its completeness, [SUP](86-supervision-metrics.spec.md), [SCO](87-supervision-cost.spec.md)), `loop` (the thread's newest `loop_summary` record, [SIL-B22](16-self-improvement.spec.md), `null` until a loop child has ended) and `events_tail` (the last 20 run-log records of kinds `unit_entered`, `check`, `gate`, `route`, `pause`, `human`, `budget` and `stop_requested`, one line each).

- GIVEN any thread WHEN its detail is built THEN every block is present, empty where nothing happened
- GIVEN a thread whose loop child has ended WHEN its detail is built THEN `loop` holds the counts of findings recorded and filed and at most three observations as category, unit and confidence, and no note text

### RDD-B8 Plan block

WHEN `plan` is built THE engine SHALL list the units in graph order, then the finalizer, each with `name`, `kind` (`step`, `map`, `fork`, `join`, `switch`, `human`, `sub_workflow`, `finalizer`), `gated`, declared executor and judge executor, alias, `edges` of `{target, on}` (the unit a verdict or arm takes, `human` for a pause, `end` for a stop) and `items` for map and fork, and when the diagram model's digest differs from the run's `plan_digest`, build it from the run's own records with `plan_stale = true`.

- GIVEN a diagram model whose digest differs from the run's WHEN the detail is built THEN `plan_stale` is true

### RDD-B1 Plan before any run

WHEN the detail is built for a thread that has reached unit 2 of 5 THE engine SHALL list all five units in `plan` in graph order with units 3 to 5 `not_reached`.

- GIVEN a thread at unit 2 of 5 WHEN the detail is built THEN units 3 to 5 are `not_reached`

### RDD-B9 Units, visits and attempts

WHEN `units[]` is built THE engine SHALL give each unit `state` (`not_reached`, `running`, `passed`, `failed`, `paused`, `skipped`), `visits[]`, `cost` (`reported`, `estimated`, `figure` as the run line counts it, `completeness`), `duration_s` and `share` of the run's cost figure; each visit `visit`, `entered_from` (the words of [EVT-B12](30-run-events.spec.md), a bare unit name in the run log reading as `back:<unit>`) and `attempts[]`; and each attempt `attempt`, `item`, `started_at`, `ended_at`, `step` (session), `check` (result, duration, `output_path`, clipped evidence), `judge` (session and verdict inputs: per criterion `{n, id, status}`, `met`, `total`, `blockers` with clipped evidence and fix from the local evidence file, `confidence` and source), `gate` (verdict, route target, guard status), `repeat_cause` on an attempt its gate sent round again (`blocker:<id>`, `check:FAIL` or `retry`) and `scripts` for a script unit or a hybrid step.

- GIVEN a run log naming `entered_from = plan` WHEN read THEN the visit reads `back:plan`

### RDD-B10 Records placed by their envelope

WHEN a run-log record is placed THE engine SHALL open the attempt an `attempt_start` record's `session_key` names and put a unit's `check`, `judgement` or `gate` record in that unit's open attempt, showing evidence and fix lines for the last judged attempt of each unit (kept in the checkpoint) and blocker ids only for earlier attempts until the evidence folder holds one judgement per attempt ([LOS](33-local-observability-store.spec.md)).

- GIVEN a unit judged twice WHEN the detail is built THEN the second attempt shows evidence and the first blocker ids only

### RDD-B2 Retry history

WHEN the detail is built for a unit whose first attempt was sent back by its judge and whose second passed THE engine SHALL show one visit with two attempts, the first with gate `RETRY`, its blockers and `repeat_cause = blocker:<id>`, the second with gate `PROCEED`.

- GIVEN attempt 1 with check PASS, judge 4/6, blockers c3 and c5 and gate RETRY, and attempt 2 with PASS, 6/6 and PROCEED WHEN the detail is built THEN both attempts show those values in one visit

### RDD-B3 Trip back

WHEN the detail is built after a gate routed `back:plan` from `code` THE engine SHALL give `plan` a second visit with `entered_from = back:code`, and end `code`'s first visit with gate `BACK` and route target `plan`.

- GIVEN a route `back:plan` from `code` WHEN the detail is built THEN `plan` has a second visit entered from `back:code`

### RDD-B11 Sessions

WHEN a step or judge session is shown THE engine SHALL give it `session_key`, `kind`, executor, alias, model, `session_id`, `transcript`, `activity_path`, `live_path`, `usage`, `tool_calls` count, `outcome` (`ok`, `timed_out`, `stalled`, `partial`, `infra_cause`, `error_kind`) and, when live, the live block.

- GIVEN a finished session WHEN shown THEN it has no live block

### RDD-B12 Live block

WHEN the detail is built with live data THE engine SHALL read from the live progress file and the activity journal ([EVT-B19](30-run-events.spec.md)) `open_tool` (name, capability, `input_summary`, elapsed seconds), `recent[]` (the last 10 finished calls with name, `input_summary`, `ok`, `duration_s`), `last_text` (scrubbed, clipped), `tokens_so_far` and `turns_so_far` (null until reported), `pgid` (POSIX), and `last_event_age_s`, using the previous complete read when the live file is mid-replace and never a partial JSON.

- GIVEN a live file being replaced WHEN read THEN the previous complete read is used

### RDD-B4 Live session

WHEN the detail is built with live data for a running judge whose open tool has been `Grep` for 12 s THE engine SHALL set `live.open_tool = {name: Grep, capability: search, elapsed: 12}` with up to ten earlier calls in `recent`.

- GIVEN `Grep` open for 12 s WHEN the detail is built THEN `open_tool` shows it with elapsed 12

### RDD-B13 Pause block

WHEN the thread is paused THE engine SHALL give `pause` the unit, kind, `question`, artifact keys with local paths (null for a value), decision words, exact resume commands, `waiting_since` and `waiting_s`.

- GIVEN a paused thread WHEN the detail is built THEN `pause` holds the exact resume commands

### RDD-B14 Health

WHEN `health` is built THE engine SHALL set `alive` from the lock probe ([DUR](09-durability-and-resume.spec.md)), `silent_s` since the segment's newest run-log record or activity line, `suspect_stall` when alive and the open session's `last_event_age_s` is at least 80 % of its idle limit, `orphaned` when not alive with state `running` in the checkpoint's last view and no `run_exit` for the segment, `waiting_for_person_s` since the open `pause` record, `burn_usd_per_h` as the segment's estimated cost over its wall time, and `cap_eta_min` until the run cost cap at that burn (null without a cap).

- GIVEN a live session silent for 85 % of its idle limit WHEN health is built THEN `suspect_stall` is true

### RDD-B5 Orphan

WHEN the detail is built for a thread whose process was killed without a `run_exit` THE engine SHALL set `health.orphaned` true, leave `pause` absent, and let the status document's resume command apply ([DUR-B2](09-durability-and-resume.spec.md)).

- GIVEN a killed process with no `run_exit` WHEN the detail is built THEN `orphaned` is true

### RDD-B15 Text, paths and size

WHEN text is put in the document THE engine SHALL scrub it and clip it to 200 characters (evidence and fix lines to 400, from the local evidence file and only in this local document, [SEC-B9](14-security.spec.md)), keep paths local, and cut a document over 1 MB by dropping `events_tail`, then the attempt detail of passed units, saying so in `truncated`; `--unit <name>` returns one unit in full and `--no-live` builds it without live blocks.

- GIVEN a document over 1 MB WHEN built THEN `events_tail` is dropped first and `truncated` says so

### RDD-B16 Errors

WHEN the run log is unreadable or missing, or the thread is unknown THE engine SHALL return `units` empty with `truncated = run_log_unreadable` and exit 0 with the status fields filled, or exit 2 for an unknown thread.

- GIVEN an unknown thread WHEN the detail is asked THEN it exits 2

### RDD-B6 Read-only

WHEN the detail of a live run is built 100 times THE engine SHALL leave the state root's file hashes and sizes as the run itself wrote them, with no wait on the reader in the run's timing records.

- GIVEN a live run WHEN the detail is built 100 times THEN the state root is as the run wrote it

## Acceptance criteria

- RDD-AC1 (RDD-B1, RDD-B2, RDD-B3, RDD-B7, RDD-B8, RDD-B9, RDD-B10, RDD-B11, RDD-B13): A fixture run with a retry, a trip back, a map of three items and a pause reproduces a hand-written expected document
- RDD-AC2 (RDD-B6): Building the detail leaves the state root unchanged, by a hash test, and takes under 300 ms for a 5 000-record run log on the reference machine
- RDD-AC3 (RDD-B15): Every text field is scrubbed, by a canary test, and within its clip length
- RDD-AC4 (RDD-B15): The 1 MB cut drops blocks in the stated order and says so
- RDD-AC5 (RDD-B4, RDD-B5, RDD-B12, RDD-B14, RDD-B16): Fixtures of a live session, a killed process, a live file mid-replace, an unreadable run log and an unknown thread give the stated blocks and exit codes
- RDD-AC6 (RDD-B7): The detail of a fixture thread whose loop child has ended holds `loop` with the counts and at most three observations and no note text, and `loop` is `null` for a thread with no loop child
