---
task: r2-t4
complexity: complex
specs: [plugins/tempergraph/docs/specs/eval-suites.spec.md, plugins/tempergraph/docs/specs/lifecycle-and-evals.spec.md]
---

# Plan: evals (R2-T4)

## 0. Hand-off

- Triage note: `plugins/tempergraph/docs/tasks/r2-t4.triage.md`
- Specs read: EVS (51), LIF (18), JCL (50), FBK (41), PRP (40), PKG (88), SHL (19), WUP (63)
- Why this design: a suite reuses what a run already does. A check case is a check fixture, a step trial is the one step run as its own workflow in a fresh repository, a workflow trial is the dry-run child run a version trial already uses. Grading is one pure function in the order code, accepted judge, person, so every rate can leave out what no grader decided. Results are rows of one file under the state root, with ids, statuses and digests only.

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | Check, step and workflow suites run and record results; figures follow EVS-B17, EVS-B18 | EVS-B8, EVS-B13, EVS-B14, EVS-B17, EVS-B18, EVS-B2, B3, B6 |
| R2 | AC 1 | A trial is graded by code, then an accepted judge, then a person; a `needs_person` trial counts in no rate | EVS-B16, EVS-B4, EVS-AC4 |
| R3 | AC 1 | No live suite starts under the test marker; a record holds no text; report and grade make no model call | EVS-AC3, AC-5, AC-6 |
| R4 | AC 1 | A check without both kinds of fixture warns; a stamp needs green model-free suites | EVS-B1, EVS-B7 |
| R5 | AC 2 | A judge miss becomes a local case candidate | LIF-B7 to LIF-B16 harvest, LIF-AC5 |
| R6 | AC 3 | Judges are replayed on kept cases and compared with the recorded score | LIF-B7 to LIF-B16 replay |
| R7 | AC 4 | A skill drives the eval verbs and never grades or labels | SHL-B5, SHL-B12, SHL-B13 |

## 2. Phases

### Phase 1: Suites and grading

Goal: EVS-AC1, AC-3 to AC-6: the three suite kinds, the grader order, figures, the cap, `evals run|report|grade`, the stamp rule.
Weight: heavy (many-tests)

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 1.1 | test | `plugins/tempergraph/engine/tests/test_eval_suites.py` | EVS-AC1, AC-3 to AC-6 | Figures, grader order, each suite kind, cap, grade, stale, graduation, the CLI |
| 1.2 | code | `plugins/tempergraph/engine/src/tempergraph/improve/suites.py` | | Cases, trials, grading, results, figures, report |
| 1.3 | code | `plugins/tempergraph/engine/src/tempergraph/package/selftest.py` | | Per-fixture check runs |
| 1.4 | code | `plugins/tempergraph/engine/src/tempergraph/cli/improve.py` | | `evals run`, `evals report`, `evals grade` |
| 1.5 | code | `plugins/tempergraph/engine/src/tempergraph/package/rules.py` | | `check_without_fail_case` |
| 1.6 | test | `plugins/tempergraph/engine/tests/test_stamp.py` | EVS-B7 | A failing check case refuses the stamp |
| 1.7 | code | `plugins/tempergraph/engine/src/tempergraph/package/stamp.py` | | V6 runs the model-free suites |

### Phase 2: Harvest and replay

Goal: LIF-AC5 and the replay batch.
Weight: medium

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 2.1 | test | `plugins/tempergraph/engine/tests/test_eval_harvest_replay.py` | LIF-AC5 | Candidates, no request text, replay agreement, the cap, the CLI |
| 2.2 | code | `plugins/tempergraph/engine/src/tempergraph/improve/harvest.py` | | Harvest and replay |
| 2.3 | code | `plugins/tempergraph/engine/src/tempergraph/cli/improve.py` | | `evals harvest`, `evals replay` |

### Phase 3: Eval skill

Goal: the eval skill of SHL.
Weight: light

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 3.1 | test | `plugins/tempergraph/engine/tests/test_shell_skills.py` | SHL-AC1 | The structure test finds the new skill |
| 3.2 | doc | `plugins/tempergraph/skills/evals/SKILL.md` | | The skill |

## 3. Verification

- `cd plugins/tempergraph/engine && python -m pytest`
- `cd plugins/tempergraph/engine && ruff check src tests`

## 4. Doc changes

- `plugins/tempergraph/docs/specs/eval-suites.spec.md`: as-built notes and ticked criteria
- `plugins/tempergraph/docs/specs/lifecycle-and-evals.spec.md`: harvest and replay as built
- `plugins/tempergraph/docs/specs/engine-cli.spec.md`: the eval verbs' options
- `plugins/tempergraph/docs/specs/workflow-package.spec.md`: `evals/steps/`
- `plugins/tempergraph/docs/specs/plugin-shell.spec.md`: the evals skill
