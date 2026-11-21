---
task: r2-t3
complexity: complex
specs: [plugins/tempergraph/docs/specs/93-judge-model-by-risk.spec.md]
---

# Plan: judge model by risk (R2-T3)

## 0. Hand-off

- Triage note: `plugins/tempergraph/docs/tasks/r2-t3.triage.md`
- Specs read: JRK (93), JDG (05), JCL (50), LAD (92), LIF (18), CHK (75), RST (80), EVT (30)
- Why this design: the judge node already holds everything the rule may read (git facts, check facts, the request, settings, the stage, the producer's alias), so the level is resolved there, just before the judge's session, and written on the judgement and as a `judge_risk` record. The rule runs under the same one-second guard as a complexity measure. A level is a binding of its own: `current_binding` takes a level, scores carry it, and trust for a ladder reads the state of the level that graded the attempt.

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | The rule's level sets the judge's model and effort for the attempt; a fault, an unknown name or a slow rule takes the last level | JRK-B1, JRK-B2, JRK §2.3 |
| R2 | AC 1 | After an escalated attempt the judge is at or above the producer's tier; shadow mode records and runs level 0; an operator pin wins and records `would_choose` | JRK-B3, JRK-B4, JRK §2.3, JRK-AC-2 |
| R3 | AC 1 | The rule's context holds no step text, artifact content or value | JRK §2.2, JRK-AC-3 |
| R4 | AC 1 | Levels are validated; `risk` is refused where bindings are fixed | JRK §4 |
| R5 | AC 2 | Scores, states and `evals bar` are per level; stable mode needs every level accepted in `route` mode | JRK §2.4, JRK-B5, JRK-AC-4 |
| R6 | AC 3 | `report --risk` shows attempts, verdict rates and cost per gate and level | JRK §2.5 |

## 2. Phases

### Phase 1: Rule, levels and resolution

Goal: JRK-AC-1 to AC-3: `RiskContext`, stock rules, levels, fault and floor, shadow mode, the `judge_risk` record, `report --risk`.
Weight: heavy (many-tests)

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 1.1 | test | `plugins/tempergraph/engine/tests/test_judge_risk.py` | JRK-AC-1, JRK-AC-2, JRK-AC-3 | JRK-B1 to B4, the §2.3 order, §4 validation rows, the report |
| 1.2 | code | `plugins/tempergraph/engine/src/tempergraph/contracts.py` | | `RiskSpec`, `RiskLevel`, `RiskContext`, `JudgeSpec.risk` |
| 1.3 | code | `plugins/tempergraph/engine/src/tempergraph/api.py` | | `Risk`, `Level`, `Judge(risk=)` |
| 1.4 | code | `plugins/tempergraph/engine/src/tempergraph/run/risk.py` | | The rule under its guard, the resolution order, stock rules |
| 1.5 | code | `plugins/tempergraph/engine/src/tempergraph/run/nodes.py` | | The level's alias and effort on the judge's request; the record |
| 1.6 | code | `plugins/tempergraph/engine/src/tempergraph/model/validate.py` | | `risk-invalid` |
| 1.7 | code | `plugins/tempergraph/engine/src/tempergraph/observe/risk_report.py` | | `report --risk` |

### Phase 2: Calibration per level

Goal: JRK-AC-4 and JRK-B5: a binding, a score and a state per level; stable mode refused while a routed level is not accepted.
Weight: medium

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 2.1 | test | `plugins/tempergraph/engine/tests/test_judge_risk_calibration.py` | JRK-AC-4, JRK-AC-1 (B5) | A state per level, staleness of one level, the JRK-B5 table |
| 2.2 | code | `plugins/tempergraph/engine/src/tempergraph/improve/calibration.py` | | Bindings, scores and states per level |
| 2.4 | code | `plugins/tempergraph/engine/src/tempergraph/package/readiness.py` | | Every routed level accepted for stable mode |
| 2.3 | code | `plugins/tempergraph/engine/src/tempergraph/cli/improve.py` | | `evals score --level`, `evals bar` rows per level |

## 3. Verification

- `cd plugins/tempergraph/engine && python -m pytest`
- `cd plugins/tempergraph/engine && ruff check src tests`

## 4. Doc changes

- `plugins/tempergraph/docs/specs/93-judge-model-by-risk.spec.md`: as-built notes and ticked criteria
- `plugins/tempergraph/docs/specs/17-engine-cli.spec.md`: `evals score --level`
- `plugins/tempergraph/docs/specs/30-run-events.spec.md`: the fields of `judge_risk`
