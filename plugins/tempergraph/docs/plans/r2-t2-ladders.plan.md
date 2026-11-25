---
task: r2-t2
complexity: complex
specs: [plugins/tempergraph/docs/specs/effort-ladder-and-model-escalation.spec.md]
---

# Plan: ladders (R2-T2)

## 0. Hand-off

- Triage note: `plugins/tempergraph/docs/tasks/r2-t2.triage.md`
- Specs read: LAD (92), BUD (08), CON (01), RST (80), HUM (07), JCL (50), CXR (94), VER (61)
- Why this design: the gate stays a pure function of state, so the judge node records whether its judgement is trusted (binding state, stage, placeholder) and the gate classifies the failed attempt into climbing evidence or a held cause. The rung of a visit lives in the unit's counters next to the retries it never adds to; the step node only reads it. One module, `run/ladder.py`, holds the classification and the escalation conditions so each has a table-driven test.

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | A retry moves one effort rung up only on `judge_blocker` or `check_fail` evidence; every other cause holds the rung | LAD-B1 to B3, LAD-B10, LAD-B11 |
| R2 | AC 1 | A person's retry, a re-open, a trip back and a rewind start the visit at rung 0; an operator pin switches the ladder off | LAD-B8, LAD-B11 |
| R3 | AC 1 | No judge session ever runs with a ladder effort or an escalated alias | LAD-AC4 |
| R4 | AC 2 | One escalated attempt runs only when E1 to E9 hold; `offer` pauses with `resume --escalate` | LAD-B4 to B7, LAD-B12, LAD-B13 |
| R5 | AC 2 | Reports show rung-0 and climbed attempts apart | LAD-AC5, LAD-B16, LAD-B17 |
| R6 | AC 3 | A release 1 `model` list is refused and rewritten by rule | LAD-B14, LAD-B18 |

## 2. Phases

### Phase 1: Effort ladder

Goal: LAD-AC1, LAD-AC2, LAD-AC4: `xhigh`, `CheckFinding.kind`, climbing evidence, every held cause, resets, preflight of each rung, the `ladder` record and `ladder_decision`.
Weight: heavy (many-tests)

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 1.1 | test | `plugins/tempergraph/engine/tests/test_ladder.py` | LAD-AC1, LAD-AC2, LAD-AC4 | LAD-B1 to B3, B8, every §2.3 row, §2.6 validation and preflight rows |
| 1.2 | code | `plugins/tempergraph/engine/src/tempergraph/contracts.py` | | `xhigh`, `CheckFinding.kind`, `StepSpec.effort_ladder`, `EscalationSpec`, effort capabilities |
| 1.3 | code | `plugins/tempergraph/engine/src/tempergraph/api.py` | | `Step(effort, effort_ladder, escalation)`, `Escalation` |
| 1.4 | code | `plugins/tempergraph/engine/src/tempergraph/run/ladder.py` | | Evidence, held causes, the next rung |
| 1.5 | code | `plugins/tempergraph/engine/src/tempergraph/run/gate.py` | | The rung in the counters; resets; the decision on the route write |
| 1.6 | code | `plugins/tempergraph/engine/src/tempergraph/run/nodes.py` | | The attempt's effort and `ladder` record; judge trust on the judgement; `ladder_decision` |
| 1.7 | code | `plugins/tempergraph/engine/src/tempergraph/model/validate.py` | | LAD-B14 validation rows |
| 1.8 | code | `plugins/tempergraph/engine/src/tempergraph/executors/preflight.py` | | A rung the executor cannot apply; an uncertain rung warned |
| 1.9 | code | `plugins/tempergraph/engine/src/tempergraph/settings.py` | | `xhigh`; `effort_ladder` and `escalation` refused at operator layers |

### Phase 2: Escalation

Goal: LAD-AC3, LAD-AC5: E1 to E9, stages, the offer pause and `resume --escalate`, the escalation record, rung-0 figures in `report`.
Weight: heavy (many-tests)

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 2.1 | test | `plugins/tempergraph/engine/tests/test_escalation.py` | LAD-AC3, LAD-AC5 | LAD-B4 to B7, one fixture per condition failing alone, §4 rows, the report's split |
| 2.2 | code | `plugins/tempergraph/engine/src/tempergraph/run/ladder.py` | | E1 to E9 and the escalation record |
| 2.3 | code | `plugins/tempergraph/engine/src/tempergraph/run/gate.py` | | The escalated attempt, the offer pause, the end of an escalation |
| 2.4 | code | `plugins/tempergraph/engine/src/tempergraph/run/nodes.py` | | The escalated alias and effort on the session request |
| 2.5 | code | `plugins/tempergraph/engine/src/tempergraph/cli/main.py` | | `resume --escalate` with the relay rule |
| 2.6 | code | `plugins/tempergraph/engine/src/tempergraph/observe/report.py` | | Rung-0 and climbed attempts apart |

### Phase 3: Model list retirement

Goal: LAD-AC6: `model-ladder-retired`, the changelog entry and the `model_list_to_escalation` transform; the loop alias setting (I2-24).
Weight: light

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 3.1 | test | `plugins/tempergraph/engine/tests/test_ladder_retirement.py` | LAD-AC6 | Each row of the §2.8 table; the refusal |
| 3.2 | code | `plugins/tempergraph/engine/src/tempergraph/model/validate.py` | | `model-ladder-retired` |
| 3.3 | code | `plugins/tempergraph/engine/src/tempergraph/run/nodes.py` | | The retry-count list is gone |
| 3.4 | code | `plugins/tempergraph/engine/src/tempergraph/model/retire.py` | | The transform by rule |
| 3.5 | code | `plugins/tempergraph/engine/src/tempergraph/settings.py` | | One alias per `model`; the loop's alias as a setting |

## 3. Verification

- `cd plugins/tempergraph/engine && python -m pytest`
- `cd plugins/tempergraph/engine && ruff check src tests`

| Criterion | Test | Command |
|---|---|---|
| AC 1 | `plugins/tempergraph/engine/tests/test_ladder.py` | `cd plugins/tempergraph/engine && python -m pytest` |
| AC 2 | `plugins/tempergraph/engine/tests/test_escalation.py` | `cd plugins/tempergraph/engine && python -m pytest` |
| AC 3 | `plugins/tempergraph/engine/tests/test_ladder_retirement.py` | `cd plugins/tempergraph/engine && python -m pytest` |
| AC 4 | pending: probe P-LAD-1 in `plugins/tempergraph/docs/plans/live-checks.plan.md` | on the owner's machine |

## 4. Docs to update

- `plugins/tempergraph/docs/specs/effort-ladder-and-model-escalation.spec.md`: acceptance criteria ticked, as-built notes
- `plugins/tempergraph/docs/specs/budgets-and-failures.spec.md`: BUD-B7 replaced
- `plugins/tempergraph/docs/specs/contracts.spec.md`: `xhigh`, `CheckFinding.kind`
