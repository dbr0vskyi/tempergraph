# Engine install and update

## Purpose

`tempergraph update` moves a machine from one engine release to another: the CLI on `PATH`, the managed Python environment and its optional executor packages, the home folder's layout, and every registered workflow, which is reinstalled into the new environment so it keeps working. `tempergraph install` is the same machinery on a machine with no engine yet. Both are deterministic code that calls no model. Neither stops, waits for or rewrites a run: a running process keeps the engine it started on, and paused threads and each repository's store are owned by [MIG](state-and-run-migration.spec.md). Claude Code updates the `tempergraph` plugin ([research `updating-a-tool-with-long-lived-runs`](../research/updating-a-tool-with-long-lived-runs.rsrch.md) U1); the plugin carries a staged copy of the engine of the same version, and only this verb installs it. The new release is installed beside the current one and made current by one atomic switch ([ADR `side-by-side-engine-environments-switched-atomically`](../adr/side-by-side-engine-environments-switched-atomically.adr.md)), so a failed install changes nothing, a rollback is a switch back, and Windows file locks on a running engine's libraries never meet the installer; registered workflows are reinstalled and pinned, never lost ([ADR `registered-workflows-are-reinstalled-and-pinned-never-lost`](../adr/registered-workflows-are-reinstalled-and-pinned-never-lost.adr.md)). Operators, the install and update skills and CI images depend on it; design and build notes are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### UPD-B10 What moves, and who moves it

WHEN a machine changes release THE engine SHALL leave the plugin, its skills, hooks and staged engine and the workflow plugins in Claude Code's plugin cache to Claude Code; move with this verb the engine environments under `~/.tempergraph/engines/<engine_version>-<digest12>/`, their optional executor packages (the `agent-sdk` and `messages-api` extras from `release.json` `extras`), the shim and Windows wrapper in `~/.tempergraph/bin/` when their content changes, the home layout ([LOS-B10](local-observability-store.spec.md)) by [MIG](state-and-run-migration.spec.md), and the registry entries and Python dependencies of registered workflows; and never move a repository's state root (moved by MIG at the new engine's first write), a paused or unfinished thread (moved at its next resume) or workflow content (its owner's, helped by [WUP](workflow-upgrade.spec.md)).

- GIVEN an update WHEN it ends THEN no state root under a repository has changed

### UPD-B11 Engine environments and the switch

WHEN an environment is installed or made current THE engine SHALL write `.complete` last in its folder, never make current a folder without it, keep in the folder the `release.json` it was built from, replace `engines/current.json` (`schema_version`, `engine_version`, `digest`, `path`, `switched_at`, `extras`, `reads_store_layouts`, `resumes_checkpoint_formats`) by write-then-rename after moving the old value to `previous.json`, and reuse a release already installed and complete rather than rebuild it.

- GIVEN `current.json` naming a folder without `.complete` WHEN the shim runs THEN it uses `previous.json` and warns, and `update` repairs it

### UPD-B12 The shim

WHEN the CLI is invoked through `~/.tempergraph/bin/tempergraph` (a POSIX `sh` script on macOS and Linux) THE shim SHALL read `current.json`, or the engine an internal dispatch names ([MIG](state-and-run-migration.spec.md)), and exec that environment's interpreter with `-m tempergraph`, find the interpreter by `TEMPERGRAPH_PYTHON` (for CI) then the managed environment, never a bare `python` or an alias stub, and exit 127 when no complete environment is found.

- GIVEN no complete environment WHEN the shim runs THEN it exits 127

### UPD-B13 Kept and pruned engines

WHEN `update --prune-engines` runs THE engine SHALL remove only environments that are none of `current`, `previous`, an engine a thread or a workflow is pinned to, and an engine a live process's lock names, naming each one kept.

- GIVEN a lock naming engine 1.4.0 WHEN pruned THEN 1.4.0 is kept and named

### UPD-B14 The update verb

WHEN `tempergraph update [--check] [--dry-run] [--json] [--with agent-sdk|messages-api]... [--rollback [--restore-backups]] [--prune-engines]` runs THE engine SHALL take as source the staged engine of the plugin copy that invoked it, no option naming a path; plan from both `release.json` files ([VER](version-metadata.spec.md)) and the content digest one of `up_to_date`, `install`, `reinstall` (same version, other digest) or `refused_downgrade` (exit 2 naming the newer shim to run first), listing live processes and pinned threads across the indexed state roots ([CST-B8](central-run-stats.spec.md)), each registered workflow's compatibility and the state roots whose layout will move; install the new environment with the current extras plus those of `--with` and every registered workflow's dependencies, with constants-only argv and a long timeout, removing the folder and exiting 1 on failure; self-check it by running the constant self-check module in the new environment (engine version and workflow interface level, executor imports, the CLI import) and loading and validating every registered workflow, no probe and no model, an engine failure exiting 1; migrate the home layout with its backup, exiting 1 and restoring the backup on failure; switch, refresh the shim if its content differs, reconcile the registry inside the new environment and pin each workflow that worked on the old engine and fails on the new one, a registry failure reported while the switch stands; and report.

- GIVEN a package install that fails half-way WHEN the verb exits 1 THEN `current.json` names the old engine

### UPD-B1 A failed install changes nothing

WHEN an update's package install fails half-way THE engine SHALL exit 1 with `current.json` naming the old engine and the half folder gone, so the next `run` uses the old engine.

- GIVEN a failure injected at each step WHEN the verb exits THEN `current.json` and the old environment are byte-for-byte unchanged

### UPD-B3 Same version, other content

WHEN `update` runs on an installed 1.5.0 whose digest differs from the plugin's staged 1.5.0 THE engine SHALL plan `reinstall`, install into a folder with the new digest and switch ([LIF-B1](lifecycle-and-evals.spec.md)).

- GIVEN equal versions and different digests WHEN updated THEN the plan is `reinstall`

### UPD-B6 Check is read-only

WHEN `update --check` runs THE engine SHALL run the source and plan steps only, change no file under the home folder, a state root or the plugin data folder, and start no model or package installer (OVR-B15); `--dry-run` prints the plan with every write it would make, and `--json` one object per line ([LIF-B8](lifecycle-and-evals.spec.md)).

- GIVEN any machine WHEN `update --check` runs THEN a hash of the home, state roots and plugin data is unchanged

### UPD-B15 Report

WHEN `update` reports THE engine SHALL print `engine` (up to date, will install, will reinstall, installed, or refused downgrade with the likely cause, an older shim first on `PATH`, and the fix), `extras` (each optional package, version range and state, one line even when there is none), `live` (each live process, its thread and engine, "keeps engine X until it exits"), `threads` (per state root the threads that move at their next resume and those pinned to an older engine with the reason), `store` (state roots whose layout moves at the first run, and whether a backup is taken), `workflow` (per registered workflow: version, source `plugin` or `local`, dependencies reinstalled, loads and validates on the new engine, compatibility state, a pin with its reason, and the remedy `tempergraph upgrade <workflow>` for a local source or a plugin update for a marketplace one), `plugin` (whether the invoking plugin copy matches the installed engine, and `/reload-plugins` when the session runs an older copy) and `summary` (one line answering "am I on the latest, and must I do anything?"), each with a fixed JSON key set.

- GIVEN `update --json` WHEN read THEN every line kind has its fixed key set

### UPD-B2 A live run keeps its engine

WHEN `update` installs 1.5.0 while a run is in progress on 1.4.0 THE engine SHALL let the run's process continue on 1.4.0 to its exit, keep the 1.4.0 folder while the lock names it, report it, and start any new `run` after the switch on 1.5.0.

- GIVEN a running thread WHEN updated THEN the same process keeps the engine it started on
- GIVEN a paused, unfinished or stopped thread WHEN next resumed THEN it runs on the current engine unless pinned ([MIG](state-and-run-migration.spec.md))
- GIVEN a new run WHEN started THEN it runs on the current engine
- GIVEN a running orchestration supervisor WHEN updated THEN it and the child runs it starts keep the supervisor's engine ([MIG-B6](state-and-run-migration.spec.md))

### UPD-B16 Plugin and engine in step

WHEN a session starts or the run driver prepares a run THE plugin SHALL keep its `plugin.json` version equal to the staged engine's `engine_version` ([VER](version-metadata.spec.md)), run `update --check --json` from the run driver's preflight and from a session-start hook that keeps the last plugin version it checked in `${CLAUDE_PLUGIN_DATA}` so it checks once per plugin version ([research `updating-a-tool-with-long-lived-runs`](../research/updating-a-tool-with-long-lived-runs.rsrch.md) U5), tell the person what will change and offer the update on `install` or `reinstall` without running it unasked, and decide from what the engine answers when the engine is newer than the plugin; CI skips the plugin, builds the environment in the image, sets `TEMPERGRAPH_PYTHON` and reads drift from `update --check --json`.

- GIVEN a person who declines the update WHEN the run goes ahead THEN it runs on the installed engine

### UPD-B4 Plugin updated, engine not

WHEN the next session's run driver prepares a run after Claude Code updated the plugin to 1.6.0 while the engine is 1.5.0 THE skill SHALL see `install` from `update --check --json`, show the engine and workflow lines and ask before updating, the run going ahead on 1.5.0 if the person declines.

- GIVEN plugin 1.6.0 and engine 1.5.0 WHEN a run is prepared THEN the skill asks before updating

### UPD-B17 Rollback

WHEN `update --rollback` runs THE engine SHALL swap `current.json` and `previous.json` after checking every indexed state root and the home folder, refusing with exit 2 and listing each root whose layout the previous engine cannot read (`store_layout`, [VER](version-metadata.spec.md)) unless `--restore-backups` is given, which restores each such root's pre-migration backup when no run has written to it since ([MIG](state-and-run-migration.spec.md)); threads resumed on the newer engine keep their checkpoints, and a checkpoint format the previous engine cannot resume pins them to the newer one, which is then kept.

- GIVEN a root written by a run since its migration WHEN rolled back with `--restore-backups` THEN that root is refused

### UPD-B5 Rollback across a layout change

WHEN `update --rollback` runs to 1.5.0, which reads layout 1 only, after 1.6.0 moved a state root from layout 1 to 2 THE engine SHALL refuse it naming that root, and with `--restore-backups` and no run since the move restore the root's backup and switch.

- GIVEN no run since the move and `--restore-backups` WHEN rolled back THEN the backup is restored and the switch made

### UPD-B18 First-install launcher

WHEN a machine has the plugin and no engine THE plugin's launcher `${CLAUDE_PLUGIN_ROOT}/bin/tempergraph` SHALL put the staged engine (`<plugin>/engine/src`) on the import path and run its bootstrap code, which imports only the standard library and stdlib-only engine modules and loads none of the engine's compiled libraries, with the first real Python 3.11+ it finds, accept only `install` and `update`, and refuse every other verb with exit 127 and the line to run.

- GIVEN `<plugin>/bin/tempergraph run` WHEN invoked THEN it exits 127 with the line to run

### UPD-B19 First install

WHEN `<plugin>/bin/tempergraph install [--check] [--json] [--with agent-sdk|messages-api]... [--add-to-path] [--repair]` runs THE engine SHALL find Python by `TEMPERGRAPH_PYTHON`, an activated environment, the Windows launcher, then the 3.11+ names, never a bare `python` or an alias stub, exiting 2 before any write with how to install one when none matches `release.json` `python`; create `~/.tempergraph/` owner-only with `manifest.json` and `machine.json`; run the update's install and self-check into the first environment and write `current.json` with no `previous.json`; write the shim, print the `PATH` block for the detected shell and with `--add-to-path` append it once between `# >>> tempergraph >>>` markers to `~/.zshrc`, `~/.bashrc`, fish's `config.fish` or `~/.profile`; create `registry.json` and reconcile the installed workflow plugins; and report the engine, extras, shim and `PATH` state, registered workflows, each executor found (no probe) and the next steps (a new terminal, `tempergraph executors --probe` and the project bootstrap per repository, [SHL](plugin-shell.spec.md)); when an engine is already current install nothing and name `update` with exit 0; with `--repair` rewrite the shim and `current.json` from the newest complete environment and rebuild missing home files, installing nothing; and with `--check` only look up and print the plan, read-only.

- GIVEN `install --add-to-path` run twice WHEN the shell file is read THEN it holds the block once and the files are byte for byte the same

### UPD-B9 First install from the plugin

WHEN `<plugin>/bin/tempergraph install --add-to-path` runs on a machine with the plugin and no `~/.tempergraph/` THE engine SHALL create the home folder, the first environment, `current.json`, the shim, the `PATH` block once and the registry with every installed workflow plugin, a second run changing nothing.

- GIVEN a second run WHEN it ends THEN nothing has changed

### UPD-B20 Workflow registry

WHEN the registry `~/.tempergraph/registry.json` is written THE engine SHALL keep it outside every engine environment, one entry per workflow with `name` (unique), `kind` (`plugin`, `local` or `builtin`), `plugin` (`<plugin>@<marketplace>`), `path` (for `plugin` recomputed from Claude Code's cache at each reconcile, [research `updating-a-tool-with-long-lived-runs`](../research/updating-a-tool-with-long-lived-runs.rsrch.md) U4), `version` and `workflow_version` last seen ([VER](version-metadata.spec.md)), `requirements_digest`, `installed_into[]`, `engine_pin` (null or `{engine, reason, since}`), `state` (`ok`, `pinned`, `not_loaded` with a reason code, `missing`), `registered_at` and `last_checked_at`; keep a copy beside it and restore from it when the file is unreadable, never rebuilding it empty; and remove an entry only by `workflows unregister`, a `missing` path keeping its entry and its threads and being reported.

- GIVEN an unreadable registry WHEN read THEN it is restored from the kept copy

### UPD-B21 Reconcile

WHEN the registry is reconciled ([LIF-B9](lifecycle-and-evals.spec.md)) THE engine SHALL take each cached plugin's newest version folder that holds a `tempergraph.json` and has no `.orphaned_at` marker, repoint stale entries, register newly installed workflow plugins, report a cached plugin whose workflow name is already registered from a local path as `name-taken` without registering it, and delete no entry.

- GIVEN a cached plugin whose name is registered locally WHEN reconciled THEN it is reported `name-taken`

### UPD-B22 Workflow dependencies

WHEN a workflow's Python dependencies are installed THE engine SHALL check each declared requirement line against the requirement grammar and the dependency gate ([SEC](security.spec.md)), write them to an engine-owned requirements file in the environment and install from that file so no package text reaches the installer's argv, give a workflow whose dependencies conflict with the engine or another workflow `not_loaded: dependency_conflict` touching no other workflow, and pin a workflow whose dependencies fail to install in the new environment while the update goes on.

- GIVEN two workflows with conflicting requirements WHEN installed THEN only the later one is `not_loaded: dependency_conflict`

### UPD-B23 Pin on breakage and its clearing

WHEN a workflow that loaded and validated on the old engine fails on the new one THE engine SHALL pin it to the old engine, dispatch its runs, resumes and checks there as MIG dispatches a pinned thread so it keeps working, keep the pinned engine, show the pin, the failing finding and the remedy in the catalog, `run --check` and the report, and clear the pin at the first reconcile, reinstall or plugin update after which it loads and validates on the current engine.

- GIVEN a pinned workflow WHEN `run --check` runs THEN it shows the pin and the failing finding

### UPD-B7 Registered workflows survive an update

WHEN `update` installs 2.0.0 with three registered workflows, one from a marketplace, one local source with a Python dependency, and one whose validation the new release tightens THE engine SHALL keep all three entries, reinstall the first two into the new environment to run on 2.0.0, and pin the third to 1.6.2 with the failing finding, dispatching its runs there and offering `tempergraph upgrade <name>` for its local source.

- GIVEN a workflow that loads and validates on the new engine WHEN updated THEN it is `ok`
- GIVEN a workflow that fails on the new engine and worked on the old WHEN updated THEN it is `pinned` and keeps working
- GIVEN a workflow that fails on both WHEN updated THEN it stays `not_loaded` and nothing is pinned
- GIVEN a dependency conflict for a workflow that worked on the old WHEN updated THEN it is `pinned` with reason `dependency_conflict`

### UPD-B8 Pin clears itself

WHEN the next reconcile finds a workflow pinned to 1.6.2 validating on 2.0.0 after its upgrade was merged THE engine SHALL remove the pin and start its next run on 2.0.0.

- GIVEN the upgrade merged WHEN reconciled THEN the pin is gone

### UPD-B24 Workflows verbs

WHEN `tempergraph workflows list [--json]`, `workflows register <path> [--check]`, `workflows unregister <name>` or `workflows reinstall [<name>|--all]` runs THE engine SHALL print the registry with state and pins; resolve the path, run validation and write an entry, refreshing it for a path registered again and refusing with exit 2 writing nothing `not-a-package` (no `tempergraph.json`), `plugin-cache-path` (a path under Claude Code's plugin cache), `not-valid` (with the findings) or `name-taken` (the name, or its private import name, [PKG](workflow-package.spec.md), registered from another path); remove the entry only, never files, refused while a thread of it is live under the current repository's state root; or install dependencies into the current environment then load and validate, clearing a pin that no longer applies.

- GIVEN a path under the plugin cache WHEN registered THEN it exits 2 `plugin-cache-path` and writes nothing

## Acceptance criteria

- UPD-AC1 (UPD-B1, UPD-B11, UPD-B14): A failure injected at each update step leaves `current.json` and the old environment byte-for-byte unchanged
- UPD-AC2 (UPD-B2): A run started before an update finishes on its engine and records it; a run started after uses the new one, by a two-process test
- UPD-AC3 (UPD-B6): `update --check` leaves the home folder, every state root and the plugin data folder unchanged, by a hash test, and starts no package installer
- UPD-AC4 (UPD-B15): Every report line kind has a JSON form with a fixed key set, tested against a schema
- UPD-AC5 (UPD-B2): Every scenario of UPD-B2 is a test
- UPD-AC6 (UPD-B13): `--prune-engines` never removes an engine named by a lock, a thread or workflow pin, `current.json` or `previous.json`
- UPD-AC7 (UPD-B7, UPD-B20, UPD-B21, UPD-B23): Every scenario of UPD-B7 is a test; no update, install, reinstall or reconcile removes a registry entry, by a property test over fault injection
- UPD-AC8 (UPD-B19, UPD-B9): `install` run twice gives the same files byte for byte, and the shell file holds the `PATH` block once
- UPD-AC9 (UPD-B3, UPD-B4, UPD-B5, UPD-B8, UPD-B10, UPD-B12, UPD-B16, UPD-B17, UPD-B18, UPD-B22, UPD-B24): Fixtures cover a reinstall, the session check, a refused and a restoring rollback, a cleared pin, the shim's exit 127, the launcher's refusals, a dependency conflict and each registry refusal

## Open questions

- How many unpinned old engines should `update` keep before it suggests `--prune-engines`? Until answered: two, with the size of the rest reported. Owner: owner.
- Not built yet: `workflows reinstall` checks each requirement against the dependency gate and records `requirements_digest` but installs nothing, so an entry that declares requirements shows `dependencies: pending`; a Windows wrapper is not written; AC2 and AC5 need two installed engines, and AC7 is tested on a fixed set of faults. Owner: engine owner.
