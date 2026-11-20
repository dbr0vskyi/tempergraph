---
title: Local observability store
type: component
status: ready-for-implementation
prefix: LOS
adrs: [0009, 0014, 0024]
---

# Local observability store

## 1. Overview

Everything a repository's runs leave on the machine lives in one folder, the state root `<main checkout>/.tempergraph/` ([WSP](13-workspace-and-concurrency.spec.md)), in a fixed layout: checkpoints, run logs, the full log of every agent session on every executor, the engine's own code log, deterministic check output, hook output, batch files, the ledger and scratch. A per-user home folder, `~/.tempergraph/`, holds what spans repositories on one machine. This spec owns both layouts, the manifest that versions them, the engine's code log, retention and the `logs` and `store` verbs. Writing any of it is best effort (contract C2) and nothing here is published (contract C9).

## 2. Contract

### 2.1 State root layout (layout version 1)

```text
.tempergraph/
  manifest.json                     layout version, engine version that created it, created_at
  .gitignore                        "*" so the folder never enters a commit, whatever the repository's own ignore file says
  config/                           operator config: hooks, observers, sinks, price overrides, observe.* settings, settings.json [RST §2.4]
  checkpoints/<workflow>.sqlite     [DUR]
  locks/<workflow>/<task_id>.lock   [DUR]
  runs/<workflow>/<task_id>/
    run.jsonl                       run log [OBS], with the envelope of [EVT §2.1]
    evidence/                       request, outputs, feedback; local only [SEC §2.3]
    findings.json                   [SIL]
    engine.json                     engines and workflow versions each process ran on; a pin [MIG §2.1]
    control/stop.json               only while a stop is pending [RCT]
    exit.json                       the last segment's exit code and reason word, rewritten at each segment's end [DUR-B5]
    lineage.json                    reruns made from this thread [RRN §2.4]
    sessions/<session_key>/
      meta.json                     executor, cli_version, session_id, transcript locator, pgid, started_at, ended_at
      raw.jsonl                     every line the executor's stream produced, with receive time; the session's full log
      activity.jsonl                normalized events [EVT §2.3]
      live.json                     live progress file [OBS §2.3]; removed at session end
      stderr.log                    the child's standard error
      tools.jsonl                   messages-api only: each tool the engine's tool host ran, exit code, duration [THS]
      output/                       messages-api only: clipped command output per tool call, local
    checks/<unit>[.<item>].<attempt>/
      result.json                   CheckResult and duration
      stdout.log, stderr.log        the check command's output
    hooks/<event>-<seq>.log         a lifecycle hook's output and exit code
  batches/<batch_id>/               batch file and batch event file [WSP §2.2]
  ledger.jsonl                      [SIL]
  backups/layout-<N>-<ts>/          files a breaking layout step moved or rewrote [MIG §2.2]
  upgrades/<upgrade_id>/            plan, baseline and report of a workflow upgrade [WUP §2.2]
  authoring/<session_id>/          authoring.json, draft outcome.json and blueprint.json, saved sources; local only [AUT §2.1]
  engine/<YYYY-MM-DD>-<pid>.jsonl   engine code log (§2.3)
  scratch/                          executor scratch, owner-only, removed per session [WSP-B5]
```

The folder and everything under it is created owner-only (0700 for folders, 0600 for files on POSIX).

### 2.2 Home layout (`TEMPERGRAPH_HOME`, default `~/.tempergraph/`)

```text
~/.tempergraph/
  manifest.json
  bin/                              the CLI shim and Windows wrapper [UPD §2.2]
  engines/                          one environment per installed release, current.json, previous.json [UPD §2.2]
  registry.json                     registered workflows, their dependencies and pins [UPD §2.8]
  machine.json                      machine_id (random UUID made once), label (operator-set, default the host name), created_at
  index.json                        known state roots: path, repository name, first_seen, last_run_at [CST §2.1]
  stats/<YYYY-MM>.jsonl             per-user stats rows [OBS §2.4], one per thread exit
  config/                           user-level sinks and defaults; a state root's config overrides it
  outbox/                           rows waiting for a sink [CST §2.3]
  supervision/<host>/<session>.jsonl  supervision journal of one host session [SCO §2.2]
  schedules/<schedule_id>/          entry.json (owner-only) and fires.jsonl of one schedule [SCH §2.2]
  schedules/tick.json, tick.lock    the tick's heartbeat and lock [TCK §2.2]
  schedules/runs.jsonl              every scheduled run on this machine, whatever folder it was set up in [TCK §2.7]
  fleet/<sink>/                     merged copy of every machine's rows from that sink [CST §2.3]
    machines/<machine_id>/          same shape as the sink's machine folder, this machine's included
    rollup/<YYYY-MM>.json           totals by machine, user, repo, workflow, executor, model; rebuilt by each sync
    synced.json                     last sync time and row counts per machine
```

Both folders carry the same name, `.tempergraph`, and the same `manifest.json` shape with `kind: state_root` or `kind: home`, so one reader and one person's habit serve both: the per-repository folder holds everything about that repository's runs, the home folder holds what spans repositories and machines.

### 2.3 Engine code log

The engine's own Python logging, as JSON lines, one file per process per day:

| Field | Meaning |
|---|---|
| `ts`, `level`, `logger`, `pid` | |
| `thread_id`, `seq` | The thread and the last run-log `seq` when the line was written, when inside a run |
| `msg` | Scrubbed message; exception lines carry the type and a scrubbed traceback |

Default level `INFO`; `--log-level` or `TEMPERGRAPH_LOG_LEVEL` changes it. Worker processes ([ADR-0019](../adr/0019-in-process-executors-run-in-a-worker-process.adr.md)) write to the same folder under their own pid and tag `worker: sdk|api`. Read-only verbs log only to standard error, never to this folder (contract C13).

### 2.4 Verbs

| Verb | Does | Writes | Spends |
|---|---|---|---|
| `logs <selector> [--session <key>] [--kind run\|raw\|activity\|stderr\|check\|hook\|engine] [--follow] [--json]` | Prints one log of a run; with no `--kind`, lists the run's files with sizes | no | no |
| `store usage [--json]` | Size per thread, per kind and in total; threads past the retention rule | no | no |
| `store prune [--older-than <days>] [--keep-failed] [--dry-run]` | Removes session logs, check output and hook logs of finished threads | yes | no |
| `store export <selector> <path.tar.gz>` | Packs one run's folder for a person to share by hand, after a scrub pass over every text file | the archive only | no |

### 2.5 Retention

Nothing is removed automatically. The rule `store usage` checks and `store prune` applies by default:

| Item | Kept for |
|---|---|
| `raw.jsonl`, `activity.jsonl`, `stderr.log`, `output/`, `checks/*/*.log`, `hooks/` | 30 days after the thread finished; a thread that ended stopped or failed is kept until `--keep-failed` is dropped |
| Supervision journals | 90 days after the session ended; closed figures stay in the ledger |
| Evidence | 90 days after the thread finished, operator-configurable ([IMD-R10](43-improvement-data.spec.md)); its records stay readable |
| `run.jsonl`, `meta.json`, `result.json`, findings | Until the thread is pruned whole by the operator, and at least 400 days ([IMD-R10](43-improvement-data.spec.md)) |
| Checkpoints, ledger, stats, `fleet/` | Never pruned by `store`; `fleet/` is a copy and can be deleted and rebuilt by `stats sync` |
| `engine/` | 14 days |

`status` adds one warning line when the state root passes 2 GB (operator config `observe.warn_size_gb`).

### 2.6 Capture level

The default is full local capture ([ADR-0029](../adr/0029-own-observability-first-export-deferred.adr.md)): every item of §2.1 is written for every session on every executor, including `raw.jsonl`, the activity journal with tool input summaries and resource samples, check and hook output and the engine code log at `INFO`. An operator may lower it per item in config (`observe.raw = off`, `observe.tool_inputs = off`, `observe.check_output = off`); lowering is recorded once per run in the run log, so a reader knows what is missing and why.

## 3. Behaviours

**LOS-B1 One folder per session.** Given a unit whose step was retried once and whose judge re-asked once, when the run ends, then `sessions/` holds five folders, `code.1.step`, `code.1.judge`, `code.2.retry`, `code.2.judge` and `code.2.judge_reask.1` for the re-ask, each with `meta.json` and `raw.jsonl`.

**LOS-B2 Full session log on every executor.** Given one session on each of the four executors, when each ends, then its `raw.jsonl` holds every stream line (stream-json lines for `claude` and `antigravity`, the worker's typed message records for `agent-sdk` and `messages-api`), each with its receive time, and `stats` can reproduce the session's usage from it.

**LOS-B3 Check output kept.** Given a check that runs the test suite and fails, when the gate routes, then `checks/code.1/stdout.log` holds the suite's output (capped at 16 MB, the head and tail kept), and the `check` record points at it.

**LOS-B4 Ignored by git.** Given a repository whose own ignore file lacks the state root, when a run starts, then `git status` still shows nothing under `.tempergraph/`, because the folder carries its own `.gitignore`.

**LOS-B5 Prune keeps the record.** Given a thread finished 40 days ago, when `store prune` runs, then its session logs and check output are gone, its run log, metadata, findings and checkpoint remain, and `status --detail` still builds with `transcript` paths marked `pruned`.

**LOS-B6 Index is best effort.** Given a read-only home folder, when a run starts, then the run starts, `index.json` is not updated, and one engine-log warning is written.

## 4. Error conditions

| Condition | Result |
|---|---|
| `manifest.json` names a newer layout | Read-only verbs work by tolerant read; a run refuses with exit 2 naming the needed engine version |
| `manifest.json` missing in an existing state root | Written as layout 1 at the next run; old flat files are read where they are |
| Disk full while writing a session log | That log stops, one record of the failure; the session goes on ([OBS-B3](15-observability-and-cost.spec.md)) |
| `store prune` on a running thread | Refused for that thread, others pruned |

## 5. Design notes

- One known layout means the monitor, the troubleshooter skill and a person with a shell all find a session's full log by its `session_key`, without knowing which executor ran it ([ADR-0024](../adr/0024-one-local-store-layout-with-a-manifest.adr.md)).
- `raw.jsonl` is the engine's own copy; an executor's native transcript, when there is one, is only linked ([EVT §2.4](30-run-events.spec.md)). This matters because the judge sessions run with isolation flags that may turn the native store off.
- Command output is the bulkiest data; it gets the shortest life and its own cap.
- Retention is never automatic, as worktree cleanup is not ([WSP](13-workspace-and-concurrency.spec.md)): a person decides what history to drop.

## 6. Acceptance criteria

- [ ] LOS-AC-1 A fixture run on each executor produces exactly the layout of §2.1 (tree comparison), with owner-only modes on POSIX.
- [ ] LOS-AC-2 `logs`, `store usage` and `store prune --dry-run` leave the state root unchanged (hash test).
- [ ] LOS-AC-3 `store export` of a canary run contains no canary string.
- [ ] LOS-AC-4 A failure injected into every write of this spec leaves the run's exit code unchanged.

## Open questions

| Question | Owner | Release 1 default |
|---|---|---|
| Should the state root move out of the main checkout for repositories on network drives? | Owner | The state root stays `<main checkout>/.tempergraph/` per [WSP](13-workspace-and-concurrency.spec.md); a state root outside git is release 2 (plan X2-24) |

## References

