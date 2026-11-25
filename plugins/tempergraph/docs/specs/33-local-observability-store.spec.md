# Local observability store

## Purpose

Everything a repository's runs leave on the machine lives in one folder, the state root `<main checkout>/.tempergraph/` ([WSP](13-workspace-and-concurrency.spec.md)), in a fixed layout: checkpoints, run logs, the full log of every agent session on every executor, the engine's own code log, deterministic check output, hook output, batch files, the ledger and scratch. A per-user home folder, `~/.tempergraph/`, holds what spans repositories on one machine. This spec owns both layouts, the manifest that versions them, the engine's code log, retention and the `logs` and `store` verbs. One known layout means the monitor, the troubleshooter skill and a person with a shell all find a session's full log by its `session_key`, whichever executor ran it ([ADR-0024](../adr/0024-one-local-store-layout-with-a-manifest.adr.md)). Writing any of it is best effort (OVR-B4) and nothing here is published (OVR-B11). Retention is never automatic: a person decides what history to drop. Every observer, the troubleshooter and the self-improvement loop depend on this layout; release 1 deviations are kept in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### LOS-B7 State root top level

WHEN a state root (layout version 1) is created THE engine SHALL lay out `manifest.json` (layout version, the engine version that created it, `created_at`), `.gitignore` holding `*`, `config/` (operator config: hooks, observers, sinks, price overrides, `observe.*` settings and `settings.json`, [RST](80-run-settings-and-overrides.spec.md)), `checkpoints/<workflow>.sqlite` and `locks/<workflow>/<task_id>.lock` ([DUR](09-durability-and-resume.spec.md)), `runs/<workflow>/<task_id>/`, `batches/<batch_id>/` (batch file and batch event file, [WSP](13-workspace-and-concurrency.spec.md)), `ledger.jsonl` and `filing-outbox.jsonl` (issue payloads a code host refused, [SIL](16-self-improvement.spec.md)), `backups/layout-<N>-<ts>/` ([MIG](62-state-and-run-migration.spec.md)), `upgrades/<upgrade_id>/` ([WUP](63-workflow-upgrade.spec.md)), `authoring/<session_id>/` (local only, [AUT](89-workflow-authoring.spec.md)), `engine/<YYYY-MM-DD>-<pid>.jsonl` (the code log) and `scratch/` (owner-only, removed per session, [WSP-B5](13-workspace-and-concurrency.spec.md)), all created owner-only (0700 for folders, 0600 for files on POSIX).

- GIVEN a new state root on POSIX WHEN its files are listed THEN folders are 0700 and files 0600

### LOS-B8 Run folder

WHEN a thread runs THE engine SHALL keep in `runs/<workflow>/<task_id>/` the run log `run.jsonl` ([OBS](15-observability-and-cost.spec.md), with the envelope of [EVT-B8](30-run-events.spec.md)); `evidence/` (request, outputs, feedback, `review/<session_key>.json` from the session reviewer and `prompts/<session_key>.txt`, a step's scrubbed prompt for the review; local only, [SEC-B9](14-security.spec.md), [SRV](44-session-review.spec.md)); `findings.json`; `loop.jsonl` (the loop child's records for the thread); `engine.json` (engines and workflow versions each process ran on, [MIG](62-state-and-run-migration.spec.md)); `control/stop.json` only while a stop is pending ([RCT](32-run-control.spec.md)); `exit.json` (the last segment's exit code and reason word, [DUR-B5](09-durability-and-resume.spec.md)); `lineage.json` ([RRN](81-reruns-and-feedback.spec.md)); `sessions/<session_key>/`; `checks/<unit>/<attempt>/<n>.out` (the n-th command a check ran, standard output and error together); `hooks/<event>-<seq>.<hook>.log` with `<event>-<seq>.facts.json` and `results.jsonl` beside it; and `answers/<unit>.json` ([ASK](73-ask-unit.spec.md)).

- GIVEN a check that ran two commands WHEN its folder is read THEN it holds `1.out` and `2.out`

### LOS-B9 Session folder

WHEN a session opens THE engine SHALL keep in `sessions/<session_key>/` `meta.json` (executor, `cli_version`, `session_id`, transcript locator, `pgid`, `started_at`, written at open and completed with `ended_at` at close), `raw.jsonl` (every line the executor's stream produced, the session's full log), `activity.jsonl` ([EVT-B17](30-run-events.spec.md)), `digest.json` (the model-free session digest, [SRV](44-session-review.spec.md)), `live.json` (removed at session end), `stderr.log`, and for `messages-api` only `tools.jsonl` (each tool the tool host ran, exit code, duration, [THS](22-tool-host.spec.md)) and `output/` (clipped command output per tool call).

- GIVEN a closed session WHEN its `meta.json` is read THEN it holds `ended_at`

### LOS-B1 One folder per session

WHEN a session of a unit ends THE engine SHALL have written it a folder of its own, `<unit>.<attempt>.<kind>` with the kind `step`, `retry`, `judge` or `judge_reask.<n>`, holding `meta.json` and `raw.jsonl`.

- GIVEN a unit `a` whose step was retried once and whose judge re-asked once WHEN the run ends THEN `sessions/` holds `a.1.step`, `a.1.judge`, `a.2.retry`, `a.2.judge` and `a.2.judge_reask.1`

### LOS-B2 Full session log on every executor

WHEN a session on any of the four executors ends THE engine SHALL have its `raw.jsonl` hold every stream line (stream-json lines for `claude` and `antigravity`, the worker's typed message records for `agent-sdk` and `messages-api`) verbatim, receive times being in the activity journal's `t`, so `stats` can reproduce the session's usage from it.

- GIVEN a finished `claude` session WHEN its `raw.jsonl` is parsed as stream-json THEN every line parses and the usage matches

### LOS-B3 Check output kept

WHEN a check that runs the test suite fails THE engine SHALL keep the suite's output in the check's command output file (capped at 16 MB, head and tail kept), its result in the `check` record and the checkpoint, and the `check` record pointing at it.

- GIVEN a failing test suite WHEN the gate routes THEN its output is in `checks/code/1/1.out` and the `check` record points at it

### LOS-B4 Ignored by git

WHEN a run starts in a repository whose own ignore file lacks the state root THE engine SHALL leave `git status` showing nothing under `.tempergraph/`, because the folder carries its own `.gitignore`; that file is not the root ignore rule of [SHL-B8](19-plugin-shell.spec.md).

- GIVEN a repository with no ignore rule for the state root WHEN a run starts THEN `git status` shows nothing under `.tempergraph/`

### LOS-B10 Home layout

WHEN the home folder (`TEMPERGRAPH_HOME`, default `~/.tempergraph/`) is used THE engine SHALL lay out `manifest.json`; `bin/` (the CLI shim and Windows wrapper) and `engines/` (one environment per installed release, `current.json`, `previous.json`, [UPD](60-engine-update.spec.md)); `registry.json` (registered workflows, dependencies and pins); `machine.json` (`machine_id`, a random UUID made once, `label`, default the host name, `created_at`); `index.json` (known state roots with path, repository name, `first_seen`, `last_run_at`, [CST](34-central-run-stats.spec.md)); `stats/<YYYY-MM>.jsonl` (one row per thread exit, [OBS](15-observability-and-cost.spec.md)); `config/` (user-level `sinks.json` and `settings.json`, a state root's config overriding it); `outbox/<sink>.jsonl` and `.state.json`; `improve/tickets/` ([SIL](16-self-improvement.spec.md)); `supervision/<host>/<session>.jsonl` ([SCO](87-supervision-cost.spec.md)); `schedules/<schedule_id>/` (owner-only `entry.json` and `fires.jsonl`, [SCH](83-schedules.spec.md)), `schedules/tick.json`, `tick.lock` and `schedules/runs.jsonl` ([TCK](84-schedule-ticks-and-unattended-fires.spec.md)); and `fleet/<sink>/` with `machines/<machine_id>/`, `rollup/<YYYY-MM>.json` and `synced.json` ([CST](34-central-run-stats.spec.md)).

- GIVEN a first run on a machine WHEN `machine.json` is read twice later THEN `machine_id` is the same

### LOS-B11 One manifest shape

WHEN either folder's `manifest.json` is written THE engine SHALL use the same shape with `kind: state_root` or `kind: home`, so one reader serves both.

- GIVEN both folders WHEN their manifests are read THEN they differ only in `kind` and values

### LOS-B12 Manifest versions

WHEN a `manifest.json` names a newer layout, or an existing state root has none THE engine SHALL serve read-only verbs by tolerant read and refuse a run with exit 2 naming the needed engine version, or write it as layout 1 at the next run and read old flat files where they are.

- GIVEN a manifest naming layout 2 WHEN a run starts THEN it exits 2 naming the needed engine version

### LOS-B6 Index is best effort

WHEN a run starts with a read-only home folder THE engine SHALL start the run, leave `index.json` unchanged and write one engine-log warning.

- GIVEN a read-only home WHEN a run starts THEN it starts and one warning is logged

### LOS-B13 Engine code log

WHEN the engine logs THE engine SHALL write JSON lines, one file per process per day, with `ts`, `level`, `logger`, `pid`, `thread_id` and `seq` (the thread and its last run-log `seq`, inside a run) and a scrubbed `msg` (exception lines carrying the type and a scrubbed traceback), at `INFO` unless `--log-level` or `TEMPERGRAPH_LOG_LEVEL` changes it, worker processes writing under their own pid tagged `worker: sdk` or `worker: api` ([ADR-0019](../adr/0019-in-process-executors-run-in-a-worker-process.adr.md)), and read-only verbs logging only to standard error (OVR-B15).

- GIVEN `status` run with `--log-level DEBUG` WHEN it ends THEN nothing was written under `engine/`

### LOS-B14 The logs verb

WHEN `logs <selector> [--session <key>] [--kind run|raw|activity|stderr|check|hook|engine] [--follow] [--json]` runs THE engine SHALL print one log of the run, writing and spending nothing: with no `--kind` list the run's files with kinds and sizes; `raw`, `activity` and `stderr` need `--session <session_key>`, `check` takes `--session <unit>[.<attempt>]`, `engine` prints the thread's code-log lines, and `--follow` takes one file and ends when the thread's lock is free.

- GIVEN `logs auth-fix --kind raw` without `--session` WHEN run THEN it exits 2

### LOS-B15 The store verbs

WHEN `store usage`, `store prune` or `store export` runs THE engine SHALL for `store usage [--json]` print the size per thread, per kind and in total, the threads past the retention rule, and one warning line past 2 GB, writing nothing; for `store prune [--older-than <days>] [--keep-failed|--no-keep-failed] [--dry-run] [--json]` apply the retention rule, never touch a paused or running thread while pruning the others, and print without removing for `--dry-run`; and for `store export <selector> <path.tar.gz>` pack one run's folder after a scrub pass over every text file, leaving binary files out, refusing a path inside the state root.

- GIVEN `store prune` while one thread runs WHEN it runs THEN that thread is untouched and the others are pruned

### LOS-B16 Retention rule

WHEN `store usage` checks or `store prune` applies the retention rule THE engine SHALL keep `raw.jsonl`, `activity.jsonl`, `stderr.log`, `output/`, check output and `hooks/` for 30 days after the thread finished (a stopped or failed thread kept unless `--no-keep-failed`), supervision journals for 90 days after the session ended, evidence for 90 days after the thread finished (operator-configurable, [IMD-B14](43-improvement-data.spec.md)), `run.jsonl`, `meta.json`, findings and `digest.json` until the operator prunes the thread whole and at least 400 days, `engine/` for 14 days, and never prune checkpoints, the ledger, stats or `fleet/` (a copy `stats sync` rebuilds); nothing is removed automatically.

- GIVEN a failed thread finished 40 days ago WHEN `store prune` runs THEN its session logs stay

### LOS-B5 Prune keeps the record

WHEN `store prune` runs over a thread finished 40 days ago THE engine SHALL remove its session logs and check output, keep its run log, metadata, findings and checkpoint, and let `status --detail` still build with `transcript` paths marked `pruned`.

- GIVEN a thread finished 40 days ago WHEN pruned THEN `status --detail` builds with paths marked `pruned`

### LOS-B17 Capture level

WHEN a session runs THE engine SHALL capture every item of the layout on every executor by default ([ADR-0029](../adr/0029-own-observability-first-export-deferred.adr.md)), and let the operator lower it per item in the `observe` map of `settings.json` (`observe.raw = off` removing the session's `raw.jsonl` at session end, `observe.tool_inputs = off`, `observe.check_output = off` removing a check's output files after the check), the project file winning per key ([RST](80-run-settings-and-overrides.spec.md)), recording the lowering once per run as `capture_lowered` on `run_started`.

- GIVEN `observe.raw = off` WHEN a session ends THEN its `raw.jsonl` is gone and `run_started` lists `raw` in `capture_lowered`

### LOS-B18 Write failures stay local

WHEN the disk fills while a session log is written THE engine SHALL stop that log, write one record of the failure, and let the session go on ([OBS-B3](15-observability-and-cost.spec.md)).

- GIVEN a full disk during a session WHEN `raw.jsonl` fails THEN the session goes on and one failure record is written

## Acceptance criteria

- LOS-AC1 (LOS-B7, LOS-B8, LOS-B9, LOS-B10, LOS-B11, LOS-B1, LOS-B2): A fixture run on each executor produces exactly the stated layout, by tree comparison, with owner-only modes on POSIX
- LOS-AC2 (LOS-B14, LOS-B15, LOS-B13): `logs`, `store usage` and `store prune --dry-run` leave the state root unchanged, by a hash test
- LOS-AC3 (LOS-B15): `store export` of a canary run contains no canary string
- LOS-AC4 (LOS-B18, LOS-B6): A failure injected into every write of this spec leaves the run's exit code unchanged
- LOS-AC5 (LOS-B3, LOS-B4, LOS-B5, LOS-B12, LOS-B16, LOS-B17): Fixtures of a failing check, a repository without an ignore rule, a 40-day-old thread, a newer manifest and each lowered capture item give the stated results

## Open questions

- Should the state root move out of the main checkout for repositories on network drives? Until answered: it stays `<main checkout>/.tempergraph/` per [WSP](13-workspace-and-concurrency.spec.md); a state root outside git is release 2. Owner: owner.
