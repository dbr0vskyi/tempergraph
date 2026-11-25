---
task: r2-t6
complexity: complex
specs: [plugins/tempergraph/docs/specs/engine-update.spec.md, plugins/tempergraph/docs/specs/state-and-run-migration.spec.md, plugins/tempergraph/docs/specs/version-metadata.spec.md, plugins/tempergraph/docs/specs/workflow-upgrade.spec.md, plugins/tempergraph/docs/specs/upgrade-workflow.spec.md, plugins/tempergraph/docs/specs/lifecycle-skills.spec.md]
---

# Plan: update, migrations and workflow upgrade (R2-T6)

## 0. Hand-off

- Triage note: `plugins/tempergraph/docs/tasks/r2-t6.triage.md`
- Specs read: UPD (`engine-update`), VER (`version-metadata`), MIG (`state-and-run-migration`), WUP (`workflow-upgrade`), UWF (`upgrade-workflow`), LSK (`lifecycle-skills`), SEC (`security`) §2.2, LOS (`local-observability-store`), DUR (`durability-and-resume`), CAR (`run-state-on-a-branch`)
- Why this design: an update never changes an installed engine. It builds the new one beside it and moves a pointer, so a failure at any step leaves the old engine in use, a rollback is the pointer moved back, and a live run keeps the folder it was loaded from. What a thread needs at its next resume is decided by a pure function over three documents (the thread's engine file, this engine's release record and the kept engines' release records), so every row of MIG's tables is a test without a second engine installed. The environment builder and the pinned engine's launch are parameters, so tests replace them and no test creates an environment.

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | `update` plans, installs beside, checks, migrates the home, switches, reconciles; a failure before the switch changes nothing | UPD-B14, UPD-B6, UPD-B1, UPD-AC1 |
| R2 | AC 1 | `--check` and `--dry-run` write nothing; each report line kind has a fixed key set | UPD-B15, UPD-AC3, AC-4 |
| R3 | AC 1 | `--rollback` swaps the pointers and is refused across a layout the previous engine cannot read, unless backups restore | UPD-B17, UPD-B5 |
| R4 | AC 1 | `--prune-engines` keeps every engine a lock, a pin or a pointer names | UPD-AC6 |
| R5 | AC 1 | No update removes a registry entry; a workflow that stops loading is pinned to the engine it worked on | UPD-B20 to UPD-B24, UPD-B7, B8 |
| R6 | AC 2 | A thread records each process's engine and workflow version; `run_started` carries `engine_version`, `shape_digest`, `moved_from` | MIG-B8 |
| R7 | AC 2 | At a resume: dispatch a pinned thread, move one whose format this engine resumes, pin on a format break, refuse when no kept engine resumes it | MIG-B12, MIG-B13, MIG-B14, MIG-B1, B2, MIG-AC1 |
| R8 | AC 2 | One checkpoint database per format | MIG-B12, MIG-B13, MIG-B14, MIG-AC5 |
| R9 | AC 2 | A changed workflow resumes with one notice when the four tests pass, and is refused with the breaks when one fails | MIG-B15, MIG-B3, B4, MIG-AC2 |
| R10 | AC 2 | Layout steps run at the first write under a lock, back up before a breaking step, restore on a fault, wait for older live runs; reading never migrates | MIG-B9, MIG-B10, MIG-B5, MIG-B5, MIG-AC3, AC-4 |
| R11 | AC 3 | Each transform is a pure, idempotent function over the package files | VER-B13, VER-AC3 |
| R12 | AC 4 | `upgrade` applies transforms on a branch, one commit per entry, verifies and finishes | WUP-B14, WUP-B7, WUP-B20, WUP-B21 |
| R13 | AC 5 | The upgrade workflow is built in, found by its flag, started by `upgrade` only | UWF-B6, UWF-B5, UWF-B7, UWF-B12, UWF-B13 |

## 2. Phases

### Phase 1: Update and rollback

Goal: UPD's release 2 part.
Weight: heavy (many-tests)

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 1.1 | test | `plugins/tempergraph/engine/tests/test_update.py` | UPD-AC1, AC-3, AC-4, AC-6, UPD-B1 to B8 | The plan's decisions, a fault at each step, the report's line kinds, registered workflows, rollback, prune |
| 1.2 | code | `plugins/tempergraph/engine/src/tempergraph/install/update.py` | | The verb: plan, steps, report, rollback, prune |
| 1.3 | code | `plugins/tempergraph/engine/src/tempergraph/install/environment.py` | | Install beside, the pointers with what the engine reads, the environment's release record |
| 1.4 | code | `plugins/tempergraph/engine/src/tempergraph/package/registry.py` | | Dependencies reinstalled per workflow, pins set and cleared |
| 1.5 | code | `plugins/tempergraph/engine/src/tempergraph/install/reconcile.py` | | The reconcile run inside the new environment |
| 1.6 | code | `plugins/tempergraph/engine/src/tempergraph/store/migrate.py` | | Layout steps, lock, backup, restore |

### Phase 2: Migrations

Goal: MIG-AC1 to AC-5.
Weight: heavy (many-tests)

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 2.1 | test | `plugins/tempergraph/engine/tests/test_migration.py` | MIG-AC1 to AC-5, MIG-B1 to B5 | The decision table, move, pin and hand-over, the four tests of a changed workflow, layout steps with a fault and a live older run, reading against an older layout |
| 2.2 | code | `plugins/tempergraph/engine/src/tempergraph/durability/engine_file.py` | | The thread's engine file, the decision, the tests of a changed workflow |
| 2.3 | code | `plugins/tempergraph/engine/src/tempergraph/run/runner.py` | | The record at each process, `moved_from`, `workflow_changed`, the refusals |
| 2.4 | code | `plugins/tempergraph/engine/src/tempergraph/cli/main.py` | | The hand-over to a pinned engine, `resume --unpin` |
| 2.5 | code | `plugins/tempergraph/engine/src/tempergraph/store/layout.py` | | The database name per format; migration at the first write |

### Phase 3: Changelog and transforms

Goal: VER-AC3.
Weight: normal

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 3.1 | test | `plugins/tempergraph/engine/tests/test_transforms.py` | VER-AC3 | A before and after fixture package per transform, run twice |
| 3.2 | code | `plugins/tempergraph/engine/src/tempergraph/package/transforms.py` | | The transforms of VER-B13 |
| 3.3 | code | `plugins/tempergraph/engine/src/tempergraph/data/changelog/` | | The release 2 entry that retires a model list |

### Phase 4: Upgrade, the upgrade workflow and the skills

Goal: WUP phases 4 to 7, UWF, the skills of LSK.
Weight: heavy (many-tests)

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 4.1 | test | `plugins/tempergraph/engine/tests/test_upgrade.py` | WUP-AC2, AC-3, AC-5, AC-6, WUP-B2, B7, B9 | A fixture package per transform upgraded with no session, a failing fixture per check, the scope guard, the report's shares |
| 4.2 | code | `plugins/tempergraph/engine/src/tempergraph/package/upgrade.py` | | Locate, baseline, plan, transform, verify, finish, the record |
| 4.3 | code | `plugins/tempergraph/engine/src/tempergraph/cli/upgrade.py` | | The verb's options and exits |
| 4.4 | test | `plugins/tempergraph/engine/tests/test_upgrade_workflow.py` | UWF-AC1 to AC-4 | The built-in workflow validates, is found by its flag, refuses a direct start, gates each item |
| 4.5 | code | `plugins/tempergraph/engine/src/tempergraph/builtin/upgrade.py` | | The built-in upgrade workflow |
| 4.6 | docs | `plugins/tempergraph/skills/` | | The update and upgrade skills |

## 3. Verification

- `cd plugins/tempergraph/engine && python -m pytest`
- `cd plugins/tempergraph/engine && ruff check src tests`
