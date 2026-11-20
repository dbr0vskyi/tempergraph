---
title: Engine update
type: component
status: review
prefix: UPD
adrs: [0055, 0056, 0057, 0015]
---

# Engine update

## 1. Overview


The `tempergraph` Claude Code plugin and the engine update by different mechanisms. Claude Code updates the plugin ([R-055](../research/R-055-updating-a-tool-with-long-lived-runs.rsrch.md) U1); the plugin carries a staged copy of the engine of the same version, and only this verb installs it. §2.5 says how the plugin's skills learn that the two differ.

The new release is installed **beside** the current one and made current by one atomic switch ([ADR-0055](../adr/0055-side-by-side-engine-environments-switched-atomically.adr.md)), so a failed install changes nothing, a rollback is a switch back, and Windows file locks on a running engine's libraries never meet the installer.

## 2. Contract

### 2.1 What moves, and who moves it

| Part | Where | Moved by |
|---|---|---|
| `tempergraph` plugin (skills, hooks, staged engine) | Claude Code's plugin cache, one folder per version | Claude Code (`claude plugin update`, auto-update, `/plugin`) |
| Workflow plugins | Same cache | Claude Code; their manifest entries by this verb (§2.3 step 6) |
| CLI shim and Windows wrapper | `~/.tempergraph/bin/` | Installer skill once; this verb when the shim's content changes |
| Engine environments | `~/.tempergraph/engines/<engine_version>-<digest12>/` | This verb |
| Optional executor packages (`agent-sdk`, `messages-api` extras) | Inside each engine environment | This verb, from `release.json` `extras` |
| Home folder layout (`~/.tempergraph/`) | [LOS §2.2](33-local-observability-store.spec.md) | This verb, by [MIG §2.2](62-state-and-run-migration.spec.md) |
| State roots of repositories | `<checkout>/.tempergraph/` | [MIG](62-state-and-run-migration.spec.md), at first write by the new engine; never by this verb |
| Paused and unfinished threads | Checkpoints | [MIG §2.4](62-state-and-run-migration.spec.md), at their next resume |
| Workflow content | The workflow's source | Its owner, helped by [WUP](63-workflow-upgrade.spec.md); never by this verb |

### 2.2 Engine environments

```text
~/.tempergraph/
  bin/tempergraph, bin/tempergraph.cmd   shim: reads engines/current.json, execs that environment's interpreter
  engines/
    current.json                        {schema_version, engine_version, digest, path, switched_at}
    previous.json                       the one before, same shape
    <engine_version>-<digest12>/        one virtual environment per installed release
      .complete                         written last by the install; an environment without it is never made current
```

| Rule | Value |
|---|---|
| Switch | `current.json` is replaced by write-then-rename; the old value moves to `previous.json` first |
| Shim | Content-independent of the release: it reads `current.json`, or the engine an internal dispatch names ([MIG §2.4](62-state-and-run-migration.spec.md)); exits 127 when no complete environment is found |
| Kept | `current`, `previous`, every engine a thread is pinned to ([MIG §2.4](62-state-and-run-migration.spec.md)) and every engine a live process runs on (its lock file names it, [MIG §2.3](62-state-and-run-migration.spec.md)) |
| Removed | Only by `update --prune-engines`, and only environments that are none of the kept ones |

### 2.3 Verb

```text
tempergraph update [--check] [--dry-run] [--json]
                   [--with agent-sdk|messages-api]...
                   [--rollback [--restore-backups]] [--prune-engines]
```

| Step | Does | On failure |
|---|---|---|
| 2 Plan | Reads both `release.json` files ([VER §2.2](61-version-metadata.spec.md)) and the content digest; decides `up_to_date`, `install`, `reinstall` (same version, other digest) or `refused_downgrade`; lists live processes and pinned threads across the state roots in the machine index ([CST §2.1](34-central-run-stats.spec.md)); lists each registered workflow's compatibility under the new release ([VER §2.7](61-version-metadata.spec.md)); lists state roots whose layout the new release will migrate | Exit 2 on a downgrade, naming the newer shim to run first |
| 3 Install | Creates the new environment folder, installs the engine and the extras the current environment has plus those asked by `--with`, with constants-only argv and a long timeout; writes `.complete` | Exit 1; the folder is removed; `current.json` untouched |
| 4 Self-check | Runs the new environment's `tempergraph --version --json` and an import check of every executor module; no probe, no model | Exit 1 as step 3 |
| 5 Home migration | Moves the home layout forward by [MIG §2.2](62-state-and-run-migration.spec.md), with its backup | Exit 1; the switch does not happen |
| 6 Switch and reconcile | Writes `current.json`; refreshes the shim if its content differs; reconciles the manifest (repoint stale entries, register installed workflow packages, never delete one, [LIF](18-lifecycle-and-evals.spec.md)) | A manifest failure is reported; the switch stands |
| 7 Report | §2.4 | — |

`--check` runs steps 1 and 2 only and is read-only (contract C13); `--dry-run` prints the plan with every write it would make; `--json` prints one object per line ([LIF](18-lifecycle-and-evals.spec.md)).

### 2.4 Report

| Line kind | Says |
|---|---|
| `engine` | One sentence: up to date, will install, will reinstall (same version, other content), installed, refused downgrade with the likely cause (an older shim found first on `PATH`) and the fix |
| `extras` | Each optional package, its version range and state |
| `live` | Each live process, its thread and engine: "keeps engine X until it exits" |
| `threads` | Counts per state root of threads that will move at their next resume and threads pinned to an older engine, with the reason ([MIG §2.4](62-state-and-run-migration.spec.md)) |
| `store` | State roots whose layout moves at the first run, and whether a backup will be taken |
| `workflow` | Per registered workflow: version, source, compatibility state, and `tempergraph upgrade <workflow>` when not `current` |
| `plugin` | Whether the plugin copy that ran the verb matches the installed engine, and `/reload-plugins` when the session still runs an older plugin copy |
| `summary` | Answers "am I on the latest, and must I do anything?" in one line |

### 2.5 Plugin and engine in step

| Rule | Value |
|---|---|
| Version parity | The plugin's `plugin.json` version equals the staged engine's `engine_version` ([VER §2.1](61-version-metadata.spec.md)) |
| Session check | The run driver's preflight, and a session-start hook of the plugin, run `update --check --json`; on `install` or `reinstall` the skill tells the person what will change and offers the update; it never runs it unasked |
| Last seen | The hook keeps the last plugin version it checked in `${CLAUDE_PLUGIN_DATA}`, which survives plugin updates ([R-055](../research/R-055-updating-a-tool-with-long-lived-runs.rsrch.md) U5), so it runs the check once per plugin version, not every session |
| CI | Skips the plugin; the image builds the environment and sets `TEMPERGRAPH_PYTHON`; `update --check --json` reports drift |

### 2.6 Rollback

`update --rollback` swaps `current.json` and `previous.json`. Before it does, it checks every indexed state root and the home folder: a root whose layout the previous engine cannot read ([VER §2.2](61-version-metadata.spec.md) `store_layout`) is listed, and the rollback is refused with exit 2 unless `--restore-backups` is given, which restores each such root's pre-migration backup when no run has written to it since ([MIG §2.2](62-state-and-run-migration.spec.md)). Threads resumed on the newer engine since the switch keep their checkpoints; a checkpoint format the previous engine cannot resume pins them to the newer one, which is then kept.

## 3. Behaviours

**UPD-B1 A failed install changes nothing.** Given an update whose package install fails half-way, when the verb exits 1, then `current.json` names the old engine, the half folder is gone, and the next `run` uses the old engine.

**UPD-B2 A live run keeps its engine.** Given a run in progress on 1.4.0, when `update` installs 1.5.0, then the run's process continues on 1.4.0 to its exit, the 1.4.0 folder is kept while the lock names it, and the report says so; a new `run` started after the switch uses 1.5.0.

| Thread at update | Next process | Engine |
|---|---|---|
| running | the same process | the one it started on |
| paused, unfinished, stopped | the next resume | the current one, unless pinned ([MIG §2.4](62-state-and-run-migration.spec.md)) |
| none (new run) | `run` | the current one |
| orchestration supervisor, running | the same process and the child runs it starts | the supervisor's ([MIG-B6](62-state-and-run-migration.spec.md)) |

**UPD-B3 Same version, other content.** Given an installed 1.5.0 whose digest differs from the plugin's staged 1.5.0, when `update` runs, then it plans `reinstall`, installs into a folder with the new digest and switches ([LIF-B1](18-lifecycle-and-evals.spec.md)).

**UPD-B4 Plugin updated, engine not.** Given Claude Code updated the plugin to 1.6.0 while the engine is 1.5.0, when the next session's run driver prepares a run, then `update --check --json` reports `install`, the skill shows the engine line and the workflow lines and asks before updating; the run may go ahead on 1.5.0 if the person declines.

**UPD-B5 Rollback across a layout change.** Given 1.6.0 moved a state root from layout 1 to 2 and the person rolls back to 1.5.0, which reads layout 1 only, when `update --rollback` runs, then it is refused naming that root; with `--restore-backups` and no run since the move, the root's backup is restored and the switch is made.

**UPD-B6 Check is read-only.** Given any machine, when `update --check` runs, then no file under the home folder, a state root or the plugin data folder changes, and no model or package installer is started.

## 4. Error conditions

| Condition | Result |
|---|---|
| No Python matching `release.json` `python` | Exit 2 before any write; says how to install one |
| Downgrade | Exit 2; names the newer copy and the `PATH` cause |
| Package install or self-check fails | Exit 1; nothing switched |
| Home layout migration fails | Exit 1; backup restored; nothing switched |
| `current.json` names a folder without `.complete` | The shim uses `previous.json` and warns; `update` repairs |
| Manifest reconcile fails | Reported; exit 0 with a warning line, since the engine is installed |
| `--prune-engines` while a process holds a lock naming an engine | That engine kept and named |

## 5. Design notes

- The verb updates no workflow and no repository's store: a machine may hold many repositories, and some are not checked out at update time. Each store moves when the new engine first writes to it ([MIG](62-state-and-run-migration.spec.md)).
- A later Python-package channel (pip, uv tool) would replace steps 1 and 3 only; the switch, the report and MIG stay ([R-057](../research/R-057-engine-update-and-workflow-upgrade-gaps.rsrch.md) open question).

## 6. Acceptance criteria

- [ ] UPD-AC-1 A failure injected at each step of §2.3 leaves `current.json` and the old environment byte-for-byte unchanged.
- [ ] UPD-AC-2 A run started before an update finishes on its engine and records it; a run started after uses the new one (two-process test).
- [ ] UPD-AC-3 `update --check` leaves the home folder, every state root and the plugin data folder unchanged (hash test) and starts no package installer.
- [ ] UPD-AC-4 Every line kind of §2.4 has a JSON form with a fixed key set, tested against a schema.
- [ ] UPD-AC-5 Every row of UPD-B2's table is a test.
- [ ] UPD-AC-6 `--prune-engines` never removes an engine named by a lock, a pin, `current.json` or `previous.json`.

## Open questions

| Question | Owner |
|---|---|
| How many unpinned old engines should `update` keep before it suggests `--prune-engines`? The design keeps two and reports the size of the rest. | Owner |

## References

