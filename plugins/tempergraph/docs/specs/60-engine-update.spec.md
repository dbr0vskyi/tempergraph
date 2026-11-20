---
title: Engine install and update
type: component
status: ready-for-implementation
prefix: UPD
adrs: [0055, 0056, 0057, 0060, 0015]
---

# Engine install and update

## 1. Overview


The `tempergraph` Claude Code plugin and the engine update by different mechanisms. Claude Code updates the plugin ([R-055](../research/R-055-updating-a-tool-with-long-lived-runs.rsrch.md) U1); the plugin carries a staged copy of the engine of the same version, and only this verb installs it. §2.5 says how the plugin's skills learn that the two differ.

The new release is installed **beside** the current one and made current by one atomic switch ([ADR-0055](../adr/0055-side-by-side-engine-environments-switched-atomically.adr.md)), so a failed install changes nothing, a rollback is a switch back, and Windows file locks on a running engine's libraries never meet the installer.

## 2. Contract

### 2.1 What moves, and who moves it

| Part | Where | Moved by |
|---|---|---|
| `tempergraph` plugin (skills, hooks, staged engine) | Claude Code's plugin cache, one folder per version | Claude Code (`claude plugin update`, auto-update, `/plugin`) |
| Workflow plugins | Same cache | Claude Code; their registry entries and Python dependencies by this verb (§2.8) |
| Local workflow sources (a person's own repositories) | Their checkouts | Their owner; their registry entries and Python dependencies by this verb (§2.8); their content by [WUP](63-workflow-upgrade.spec.md) |
| Workflow registry | `~/.tempergraph/registry.json` (§2.8) | `install`, `update`, `workflows register\|unregister`; outside every engine environment, so no update can lose it |
| CLI shim and Windows wrapper | `~/.tempergraph/bin/` | `install` once (§2.7); this verb when the shim's content changes |
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
| Kept | `current`, `previous`, every engine a thread ([MIG §2.4](62-state-and-run-migration.spec.md)) or a workflow (§2.8) is pinned to, and every engine a live process runs on (its lock file names it, [MIG §2.3](62-state-and-run-migration.spec.md)) |
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
| 3 Install | Creates the new environment folder, installs the engine, the extras the current environment has plus those asked by `--with`, and the Python dependencies of every registered workflow (§2.8), with constants-only argv and a long timeout; writes `.complete` | Exit 1; the folder is removed; `current.json` untouched |
| 4 Self-check | Runs the new environment's `tempergraph --version --json`, an import check of every executor module, and a load and `validate` of every registered workflow under the new engine; no probe, no model | Engine failure: exit 1 as step 3. A workflow that fails is pinned at step 6 (§2.8), not a failure of the update |
| 5 Home migration | Moves the home layout forward by [MIG §2.2](62-state-and-run-migration.spec.md), with its backup | Exit 1; the switch does not happen |
| 6 Switch and reconcile | Writes `current.json`; refreshes the shim if its content differs; reconciles the registry (§2.8: repoint stale entries, register newly installed workflow plugins, never delete one) and pins each workflow that worked on the old engine and fails on the new one | A registry failure is reported; the switch stands |
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
| `workflow` | Per registered workflow: version, source (`plugin` or `local`), dependencies reinstalled, loads and validates on the new engine, compatibility state, a pin to the previous engine with its reason, and the remedy: `tempergraph upgrade <workflow>` for a local source, a plugin update for a marketplace one |
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

### 2.7 First install


```text
<plugin>/bin/tempergraph install [--check] [--json] [--with agent-sdk|messages-api]...
                                 [--add-to-path] [--repair]
```

| Step | Does |
|---|---|
| 1 Python | Ordered lookup: `TEMPERGRAPH_PYTHON`, an activated environment, the Windows launcher, the 3.11+ names; never a bare `python` or an alias stub. None found: exit 2 with how to install one |
| 2 Home | Creates `~/.tempergraph/` in the layout of [LOS §2.2](33-local-observability-store.spec.md), owner-only, with `manifest.json` and `machine.json` |
| 3 Engine | Update steps 3 and 4 into the first environment folder, then writes `current.json` (no `previous.json`) |
| 4 Shim | Writes `~/.tempergraph/bin/tempergraph` and the Windows wrapper. Prints the `PATH` block for the detected shell. With `--add-to-path`, appends it to the detected shell file after a marker check, so a second run adds nothing. |
| 5 Registry | Creates `registry.json`, merges a legacy manifest if one exists, and registers every installed workflow plugin it finds in Claude Code's plugin cache (§2.8) |
| 6 Report | The engine, the extras, the shim and the `PATH` state, the registered workflows, each executor found on this machine (`executors`, no probe), and the next steps: open a new terminal, and run `tempergraph executors --probe` and the project bootstrap per repository ([SHL](19-plugin-shell.spec.md)) |

| Case | Result |
|---|---|
| An engine is already current | Nothing installed; the report says so and names `update`; exit 0 |
| `--repair` | Rewrites the shim and `current.json` from the newest complete environment, and rebuilds missing home files; installs nothing |
| `--check` | Steps 1 and 2 are only looked up and the plan is printed; read-only |
| CI | Not used: the image installs the engine package and sets `TEMPERGRAPH_PYTHON` ([§2.5](#25-plugin-and-engine-in-step)) |

Once the shim is on `PATH`, `tempergraph install` and `tempergraph update` run the same code through the shim.

**Release 1.** macOS and Linux only, so the shim is a POSIX `sh` script that execs `<environment>/bin/python -m tempergraph`, and no Windows wrapper is written. The launcher puts the staged engine (`<plugin>/engine/src`) on the import path and runs `tempergraph.install.bootstrap`, which imports only the standard library and the stdlib-only engine modules (a test pins this). The self-check of step 4 runs the constant module `tempergraph.install.selfcheck` in the new environment: it reports the engine version and the workflow interface level, imports the shipped executors through the registry, and imports the CLI. Step 5 reconciles inside the new environment (`tempergraph.install.reconcile`), because loading a workflow needs the engine's libraries. No earlier release wrote a legacy manifest, so nothing is merged. `update` belongs to release 2 ([ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md)): the launcher refuses it with exit 2. The `PATH` block goes to `~/.zshrc`, `~/.bashrc`, fish's `config.fish`, or `~/.profile` for any other shell, between `# >>> tempergraph >>>` markers. Reconcile takes each plugin's newest version folder that holds a `tempergraph.json` and has no `.orphaned_at` marker. A cached plugin whose workflow name is already registered from a local path is reported as `name-taken` and not registered.

### 2.8 Workflow registry and reinstall


| `registry.json` entry field | Meaning |
|---|---|
| `name` | The workflow's name; unique |
| `kind` | `plugin` (installed from a marketplace), `local` (a source checkout the person registered) or `builtin` |
| `plugin` | `<plugin>@<marketplace>`, for `plugin` |
| `path` | The package folder. For `plugin` it is recomputed from Claude Code's cache at each reconcile, because that folder changes with every version ([R-055](../research/R-055-updating-a-tool-with-long-lived-runs.rsrch.md) U4) |
| `version`, `workflow_version` | Last seen ([VER §2.4](61-version-metadata.spec.md)) |
| `requirements_digest`, `installed_into[]` | The Python dependencies the package declares, and the environments they are installed in |
| `engine_pin` | null, or `{engine, reason, since}` |
| `state` | `ok`, `pinned`, `not_loaded` (with a reason code), `missing` |
| `registered_at`, `last_checked_at` | |

| Rule | Value |
|---|---|
| Dependencies | Read from the package's declared Python requirements. Each line is checked against the requirement grammar and the dependency gate ([SEC](14-security.spec.md)). They are written to an engine-owned requirements file in the environment and installed from that file, so no package text reaches the installer's argv. A conflict with the engine or with another workflow gives that workflow `not_loaded: dependency_conflict` and touches no other workflow. |
| On every update | Step 3 installs every entry's dependencies into the new environment. Step 4 loads and validates each entry under the new engine. Step 6 reconciles. |
| Pin on breakage | A workflow that loaded and validated on the old engine but fails on the new one is pinned to the old engine. Its runs, resumes and checks are dispatched there, as [MIG §2.4](62-state-and-run-migration.spec.md) dispatches a pinned thread, so it **keeps working**. The catalog, `run --check` and the report show the pin, the failing finding and the remedy. A pinned engine is kept (§2.2). |
| Pin cleared | Automatically, at the first reconcile, reinstall or plugin update after which the workflow loads and validates on the current engine |
| Never lost | No verb but `workflows unregister` removes an entry. A `missing` path (a local checkout moved, or a plugin uninstalled) keeps its entry and its threads, and is reported. |

```text
tempergraph workflows list [--json]                 # the registry, with state and pins (the catalog of `list` adds routing data)
tempergraph workflows register <path> [--check]     # a local source: the folder must hold a workflow package that loads and validates
tempergraph workflows unregister <name>             # removes the entry only, never files; refused while a thread of it is live
tempergraph workflows reinstall [<name>|--all]      # dependencies into the current environment, then load and validate; clears a pin that no longer applies
```

`register` resolves the path, refuses one under Claude Code's plugin cache (that is a `plugin` entry, found by reconcile), and runs validation before it writes the entry. Refusals exit 2 and write nothing: `not-a-package` (no `tempergraph.json`), `plugin-cache-path`, `not-valid` (with the findings), `name-taken` (the name, or its private import name [PKG §2.3](88-workflow-package.spec.md), is registered from another path). Registering the same path again refreshes the entry. `unregister` checks the run locks of the current repository's state root; the home keeps no index of repositories, so a live thread elsewhere is not seen.

**Release 1.** No managed engine environment exists before plan T8.2, so `reinstall` checks each declared requirement against the dependency gate and records `requirements_digest`, but installs nothing: an entry that declares requirements shows `dependencies: pending`.

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

**UPD-B7 Registered workflows survive an update.** Given three registered workflows, one from a marketplace, one local source with a Python dependency, and one whose validation the new release tightens, when `update` installs 2.0.0, then all three entries remain. The first two are reinstalled into the new environment and run on 2.0.0. The third is pinned to 1.6.2 with the failing finding, its runs dispatch to 1.6.2, and the report offers `tempergraph upgrade <name>` for its local source.

| Workflow on the new engine | Worked on the old | Result |
|---|---|---|
| loads and validates | — | `ok`, runs on the new engine |
| fails | yes | `pinned` to the old engine; keeps working |
| fails | no | `not_loaded`, as before; nothing pinned |
| dependency conflict | yes | `pinned`, reason `dependency_conflict` |

**UPD-B8 Pin clears itself.** Given a workflow pinned to 1.6.2, when the person merges its upgrade and the next reconcile finds it validates on 2.0.0, then the pin is removed and its next run starts on 2.0.0.

**UPD-B9 First install from the plugin.** Given a machine with the plugin and no `~/.tempergraph/`, when `<plugin>/bin/tempergraph install --add-to-path` runs, then the home folder, the first environment, `current.json`, the shim, the `PATH` block (once) and the registry with every installed workflow plugin exist, and a second run changes nothing.

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
| A workflow's dependencies fail to install in the new environment | That workflow pinned (UPD-B7); the update goes on |
| `registry.json` unreadable | Restored from the last copy the engine keeps beside it; never rebuilt empty over the old file |

## 5. Design notes

- The verb updates no workflow and no repository's store: a machine may hold many repositories, and some are not checked out at update time. Each store moves when the new engine first writes to it ([MIG](62-state-and-run-migration.spec.md)).
- A later Python-package channel (pip, uv tool) would replace steps 1 and 3 only; the switch, the report and MIG stay ([R-057](../research/R-057-engine-update-and-workflow-upgrade-gaps.rsrch.md) open question).

## 6. Acceptance criteria

- [ ] UPD-AC-1 A failure injected at each step of §2.3 leaves `current.json` and the old environment byte-for-byte unchanged.
- [ ] UPD-AC-2 A run started before an update finishes on its engine and records it; a run started after uses the new one (two-process test).
- [ ] UPD-AC-3 `update --check` leaves the home folder, every state root and the plugin data folder unchanged (hash test) and starts no package installer.
- [ ] UPD-AC-4 Every line kind of §2.4 has a JSON form with a fixed key set, tested against a schema.
- [ ] UPD-AC-5 Every row of UPD-B2's table is a test.
- [ ] UPD-AC-6 `--prune-engines` never removes an engine named by a lock, a thread or workflow pin, `current.json` or `previous.json`.
- [ ] UPD-AC-7 Every row of UPD-B7's table is a test; no update, install, reinstall or reconcile removes a registry entry (property test over fault injection).
- [ ] UPD-AC-8 `install` run twice gives the same files byte for byte, and the shell file holds the `PATH` block once.

## Open questions

| Question | Owner | Release 1 default |
|---|---|---|
| How many unpinned old engines should `update` keep before it suggests `--prune-engines`? The design keeps two and reports the size of the rest. | Owner | Two |

## References

