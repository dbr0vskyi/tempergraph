---
title: Data sources
type: component
status: review
prefix: MDS
adrs: [0002, 0005]
---

# Data sources

## 1. Overview

What the monitor reads, from where, how often, and the rule that it never writes: contract M1. The monitor reads engine files directly where they are append-only or replaced atomically (cheap to stat, safe to read mid-run), and calls read-only engine verbs where the engine must combine the checkpoint, the lock and the log (the status and detail documents). All reads run on the mod's own timers, never inside a drawing, so a slow read never holds Claude Code's interface.

## 2. Contract

### 2.1 Sources

| Source | How | When | Engine owner |
|---|---|---|---|
| State roots to watch | The session's own repository (git common directory of the session's working directory, found by `git rev-parse --git-common-dir` with constant argv), plus every root in `~/.tempergraph/index.json` when `scope = machine` | At start, and when the index file's mtime changes | [CST §2.1](../../../tempergraph/docs/specs/34-central-run-stats.spec.md) |
| Run rows | `tempergraph status --json` per watched root (the verb is run in that root) | Every 5 s while any row is alive or the pane is open; every 30 s otherwise; at once when a watched run log grew | [DUR §2.2](../../../tempergraph/docs/specs/09-durability-and-resume.spec.md) |
| Change signal | `$.fs.stat` of each live thread's `run.jsonl` | Every 1 s | [LOS §2.1](../../../tempergraph/docs/specs/33-local-observability-store.spec.md) |
| Run-log tail | `$.fs.read` with `{offset, length}` from the last offset read | When the change signal moved | [EVT §2.1](../../../tempergraph/docs/specs/30-run-events.spec.md) |
| Detail document | `tempergraph status --detail <thread> --json` (with `--unit` when the document says it was cut) | When the person opens a run, then when its run log grew, at most every 2 s | [RDD](../../../tempergraph/docs/specs/31-run-detail-document.spec.md) |
| Live session | `$.fs.read` of `live.json`; tail of `activity.jsonl` | Every 1 s while a session view is open | [EVT §2.3](../../../tempergraph/docs/specs/30-run-events.spec.md) |
| Processes | `ps -A -o pid=,pgid=,ppid=,etime=,comm=` (constant argv, POSIX), filtered to the session's `pgid` | Every 2 s while a session view's Processes tab is open | [RDD §2.2](../../../tempergraph/docs/specs/31-run-detail-document.spec.md) |
| Log tails | `$.fs.read` of the last 64 KB of `raw.jsonl`, `stderr.log`, a check's `stdout.log` | On request in a session or check view | [LOS](../../../tempergraph/docs/specs/33-local-observability-store.spec.md) |
| Orchestrations | `tempergraph orchestrate list --json`, then `orchestrate status <id> --json` | Every 5 s while one is live or open | [ORC §2.7](../../../tempergraph/docs/specs/45-orchestration.spec.md) |
| Projection | `tempergraph stats --projection --by workflow --json` | Every 10 min, and when a run of a new workflow appears | [CST §2.5](../../../tempergraph/docs/specs/34-central-run-stats.spec.md) |
| Fleet | `tempergraph stats --live --json`, which reads the home folder's fleet copy (`~/.tempergraph/fleet/`); the mod stats `synced.json` to know when it changed | Every 60 s while the fleet tab is open or `alerts.fleet = on` | [CST §2.5](../../../tempergraph/docs/specs/34-central-run-stats.spec.md) |

Every verb is run by `$.process.run` with list argv built from constants and values the engine itself printed (thread ids, session keys, sink names from config), never from text a person typed into the pane ([MAC](05-actions-and-safety.spec.md)). A call has a 20 s timeout; at most two verb calls run at once.

### 2.2 Cache and freshness

| Rule | Detail |
|---|---|
| One copy per document | The last good copy of each document is kept in session state with its read time; a failed read keeps it and marks it `stale since` |
| Partial lines | A tail read drops a last line without a newline and re-reads it next time |
| Rotation | A file whose size shrank, or whose inode changed, is read again from 0 |
| Schema | A document with a newer major schema is not drawn; its row says so (contract C12 of the engine) |
| Bounds | At most 4 MiB per read; tails keep the last 2 000 activity lines and 500 run-log records per thread in memory |

### 2.3 Read-only rule (contract M1)

| Never | Instead |
|---|---|
| Write, create, lock or delete anything under a state root, `~/.tempergraph/` or a sink folder | Read |
| Open a checkpoint database | `status` verb |
| Call a verb that writes (`run`, `resume`, `stop`, `batch`, `store prune`, `hooks add`, `update`) | Fill the prompt ([MAC](05-actions-and-safety.spec.md)) |
| Parse an executor's raw stream for meaning | Normalized activity journal; raw lines are shown as text only |

The mod's own memory across sessions (pinned runs, last alerted `seq` per thread, settings) is in Claude Code's plugin store (`$.store`), never in an engine folder.

## 3. Behaviours

**MDS-B1 Cheap when idle.** Given no live run and the pane closed, when an hour passes, then the mod has made at most 120 verb calls (one per root every 30 s) and no file read other than stats of known run logs.

**MDS-B2 Fast when something happens.** Given a live run whose judge writes its `judgement` record, when the next 1 s stat sees the run log grow, then the record is read from the old offset, the band and any open view are redrawn, and a detail refresh is asked for if the run is open; the person sees the verdict within about 3 s of its write.

**MDS-B3 Engine gone.** Given a run whose process was killed, when the status verb reports the lock free and no `run_exit`, then the run row shows `orphaned` from the detail document's health, with the resume command, and polling for it drops to the idle rate.

**MDS-B4 Machine scope.** Given `scope = machine` and an index with four roots, one of them deleted, when the run list is built, then three roots are polled, the fourth shows `missing`, and the index file is not touched.

**MDS-B5 Read-only proof.** Given a test that hashes a state root before and after a monitor session that opens every view, when the session ends, then the hashes differ only in files the engine run wrote.

## 4. Error conditions

| Condition | Result |
|---|---|
| A verb exits 127 | Engine marked not installed; polling stops until the session restarts or the person runs the installer |
| A verb exits non-zero otherwise | The row keeps its last copy, marked stale with the exit code; retried at the idle rate |
| `ps` missing or not POSIX | The Processes tab says "not available on this system" |
| A file read refused by Claude Code (outside an allowed root) | The view says which path and why; nothing else changes |

## 5. Design notes

- Stat first, read second: the same rule `wait` follows in the engine; it keeps a monitor with ten live runs cheap ([MADR-0002](../adr/0002-poll-files-and-read-only-verbs.adr.md)).
- Status and detail come from verbs because only the engine can probe the lock without creating it and open the checkpoint read-only.
- `scope` (`repo` default, or `machine`) is a mod setting; the fleet needs a sink the engine is configured with ([MADR-0005](../adr/0005-three-scopes-repo-machine-fleet.adr.md)).

## 6. Acceptance criteria

- [ ] MDS-AC-1 MDS-B5 passes in a test session against a scripted-executor run.
- [ ] MDS-AC-2 A source-scan test lists every `$.process.run` call and its argv; none holds a verb that writes.
- [ ] MDS-AC-3 A run log grown by a partial line, then completed, yields each record once.
- [ ] MDS-AC-4 The idle and live poll counts of MDS-B1 hold under a replaced clock.

## Open questions

| Question | Owner |
|---|---|
| Can `$.fs` read paths outside the session's working directory (other roots, `~/.tempergraph/`) without a prompt on every surface? Probe P-MOD-2 ([R-001](../research/R-001-claude-code-mods.rsrch.md)). If not, those reads go through `tempergraph logs` and `events`. | Monitor implementer |

## References

[EVT](../../../tempergraph/docs/specs/30-run-events.spec.md) · [RDD](../../../tempergraph/docs/specs/31-run-detail-document.spec.md) · [LOS](../../../tempergraph/docs/specs/33-local-observability-store.spec.md) · [CST](../../../tempergraph/docs/specs/34-central-run-stats.spec.md) · [R-001](../research/R-001-claude-code-mods.rsrch.md)
