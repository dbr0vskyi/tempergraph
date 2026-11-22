---
task: r2-t5
complexity: complex
specs: [plugins/tempergraph/docs/specs/95-promotion-check.spec.md, plugins/tempergraph/docs/specs/96-run-state-on-a-branch.spec.md]
---

# Plan: promotion and carried state (R2-T5)

## 0. Hand-off

- Triage note: `plugins/tempergraph/docs/tasks/r2-t5.triage.md`
- Specs read: PRO (95), SUP (86) §2.4 and §2.7, CAR (96), VER (61), LOS (33), DUR (09), WTR (82), SEC (14)
- Why this design: the check adds no measurement of its own. Each row calls the function a report already uses (the first-pass yield and escapes of `report`, the aggregate of `report --supervision`, the judge states of `evals bar`, the suites of `evals report`), so two verbs can never show two numbers. The bars are one data file. A stamp names the workflow version with its content digest, so reading it against the current digest is all that voiding needs. Carried state is written with git plumbing into an orphan branch, so no checkout and no work branch is touched.

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | The window is the last finished runs of the current workflow version, without trial, eval, scenario and dry runs | PRO-B8 |
| R2 | AC 1 | Each criterion gives a number, a bar and a verdict; missing data is `unmeasured`, never met | PRO-B9, SUP-B17, PRO-B2, PRO-AC3 |
| R3 | AC 1 | The verb is read-only without `--stamp`; the stamp is written only when every row is met, by a person, into a source package | PRO-B10, PRO-B6, PRO-B9, PRO-AC2 |
| R4 | AC 1 | A change inside the content digest voids the stamp | PRO-AC4, PRO-B4 |
| R5 | AC 1 | `--to pipeline`, an unregistered executor and a pipeline caller's stamp are refused with `not_in_release` | PRO-AC6 |
| R6 | AC 2 | The stage is on `settings_resolved` and the ledger row | PRO-B7, PRO-B4 |
| R7 | AC 3 | A paused carried run is pushed to its state branch and resumed from a second state root | CAR-B6, CAR-B8, CAR-B3, CAR-B1 |
| R8 | AC 3 | Only the carried subset travels, scrubbed | CAR-B7, CAR-B2, CAR-B2, CAR-AC2 |
| R9 | AC 3 | The branch is deleted at the finish; the lease allows one driver | CAR-B8, CAR-B3, CAR-B9, CAR-B4, CAR-B3, CAR-B4 |
| R10 | AC 3 | A pull checks the manifest, formats, workflow version and work branch first | CAR-B10, CAR-AC4 |

## 2. Phases

### Phase 1: Stages and the promotion check

Goal: PRO-AC1 to AC-4 and AC-6 for `local-stable`.
Weight: heavy (many-tests)

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 1.1 | test | `plugins/tempergraph/engine/tests/test_promotion.py` | PRO-AC1 to AC-4, AC-6 | One fixture per failing criterion, the window, the verb, the stamp, voiding, the stage records |
| 1.2 | code | `plugins/tempergraph/engine/src/tempergraph/improve/promotion.py` | | Stage of a run, window, criteria, stamp |
| 1.3 | code | `plugins/tempergraph/engine/src/tempergraph/data/promotion.json` | | The bars of both stages |
| 1.4 | code | `plugins/tempergraph/engine/src/tempergraph/cli/improve.py` | | The `promote-check` verb |
| 1.5 | code | `plugins/tempergraph/engine/src/tempergraph/run/runner.py` | | `stage`, `unpromoted_pipeline` and `content_version` on the run's records |
| 1.6 | code | `plugins/tempergraph/engine/src/tempergraph/package/loader.py` | | The workflow version with its digest, kept per loaded package |

### Phase 2: Carried state

Goal: CAR-AC1 to AC-4.
Weight: heavy (many-tests)

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 2.1 | test | `plugins/tempergraph/engine/tests/test_carry.py` | CAR-AC1 to AC-4 | Two state roots and a bare remote: push, pull, resume, lease, deletion, the refusals |
| 2.2 | code | `plugins/tempergraph/engine/src/tempergraph/durability/carry.py` | | The carried subset, the state branch, push, pull, lease, drop |
| 2.3 | code | `plugins/tempergraph/engine/src/tempergraph/cli/main.py` | | `--carry` and the `carry` verbs |
| 2.4 | code | `plugins/tempergraph/engine/src/tempergraph/run/runner.py` | | Push at a pause or an unfinished exit, deletion at the finish |

## 3. Verification

- `cd plugins/tempergraph/engine && python -m pytest`
- `cd plugins/tempergraph/engine && ruff check src tests`

## 4. Out of scope

The `pipeline` stage, the regressed watch and pauses in a pipeline (PRO-B5, PRO-B11, PRO-AC5) arrive with pipelines in a later release.
