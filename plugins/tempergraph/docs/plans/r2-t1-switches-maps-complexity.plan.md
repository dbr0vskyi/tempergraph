---
task: r2-t1
complexity: complex
specs: [plugins/tempergraph/docs/specs/measured-switches.spec.md, plugins/tempergraph/docs/specs/map-unit.spec.md, plugins/tempergraph/docs/specs/complexity-routing.spec.md]
---

# Plan: switches, maps and complexity (R2-T1)

## 0. Hand-off

- Triage note: `plugins/tempergraph/docs/tasks/r2-t1.triage.md`
- Specs read: SWM (`measured-switches`), MAP (`map-unit`), CXR (`complexity-routing`), CMP (`compiler-and-flow`), RST (`run-settings-and-overrides`), BUD (`budgets-and-failures`), OBS (`observability-and-cost`)
- Why this design: a switch's pick stays in the gate node, so shadow mode, the operator's arm and re-arming are all changes to one pure function and its record. Arm overrides are applied where a session request is built, below the four operator layers, so the settings resolution stays one table. Re-arming is a trip back with one extra static edge per listed unit.

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | A shadow switch records what the predicate would pick and takes the default arm | SWM-B1, SWM-AC2 |
| R2 | AC 1 | A unit under an arm in force takes the arm's model, limits and effort, below the operator layers, and its records name the layer | SWM-B2, SWM-AC3 |
| R3 | AC 1 | A listed unit that spends its budget or times out under arm `from` sends the run to the entry of arm `to`, once | SWM-B3 |
| R4 | AC 1 | An operator's `<switch>.arm` setting picks the arm in either mode | CMP-B7, RST-B18, RST-B19, RST-B20, RST-B21 |
| R5 | AC 2 | A sequential map runs its body once per item of a list a unit produced | MAP-AC1 to MAP-AC4 |
| R6 | AC 3 | A complexity switch builds its predicate from measures and a rules file, fails safe and re-arms one way | CXR-AC1 to CXR-AC5 |

## 2. Phases

### Phase 1: Measured switches

Goal: SWM-AC1 to SWM-AC3, with `effort_ladder` and `escalation` accepted in `arm_overrides` and applied in R2-T2.
Weight: light

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 1.1 | test | `plugins/tempergraph/engine/tests/test_measured_switches.py` | SWM-AC1 | SWM-B1 to B3, each row of the SWM-B3 table, CMP-B7 and every §4 validation row |
| 1.2 | code | `plugins/tempergraph/engine/src/tempergraph/contracts.py` | | `SwitchSpec.mode`, `arm_overrides`, `rearm`; `RearmSpec` |
| 1.3 | code | `plugins/tempergraph/engine/src/tempergraph/api.py` | | `Switch` takes the new fields; `Rearm` builder |
| 1.4 | code | `plugins/tempergraph/engine/src/tempergraph/model/validate.py` | | The four validation rows of SWM-B4, SWM-B5 |
| 1.5 | code | `plugins/tempergraph/engine/src/tempergraph/model/flow.py` | | A static edge from each re-armed unit's gate to the entry of arm `to` |
| 1.6 | code | `plugins/tempergraph/engine/src/tempergraph/run/gate.py` | | Shadow pick, signals, operator arm, re-arm as a trip back |
| 1.7 | code | `plugins/tempergraph/engine/src/tempergraph/run/nodes.py` | | Arm overrides on the session request; the `route` record's new fields |
| 1.8 | code | `plugins/tempergraph/engine/src/tempergraph/settings.py` | | The `arm` key on a switch unit; operator-set keys marked for the arm layer |

### Phase 2: Sequential map and item keys

Goal: MAP-AC1 to MAP-AC4 for the sequential form; item keys validated; the concurrent mode stays `not_in_release`.
Weight: heavy (refactor)

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 2.1 | test | `plugins/tempergraph/engine/tests/test_map.py` | MAP-AC1, MAP-AC2, MAP-AC3, MAP-AC4 | MAP-B1 to B6 for the sequential form, every §2.3 row that the form can reach, VAL-B4 |
| 2.2 | code | `plugins/tempergraph/engine/src/tempergraph/contracts.py` | | `MapSpec`, `MapItem`, `ExtractContext`, `UnitSpec.map` |
| 2.3 | code | `plugins/tempergraph/engine/src/tempergraph/api.py` | | The `Map` builder |
| 2.4 | code | `plugins/tempergraph/engine/src/tempergraph/run/mapping.py` | | Reading the list, the item in hand, advancing |
| 2.5 | code | `plugins/tempergraph/engine/src/tempergraph/run/nodes.py` | | Fan-out, item sessions, item keys and records |
| 2.6 | code | `plugins/tempergraph/engine/src/tempergraph/run/gate.py` | | Next item, list fault stop, item on the pause |
| 2.7 | code | `plugins/tempergraph/engine/src/tempergraph/model/validate.py` | | MAP-B11 rows and limits |
| 2.8 | code | `plugins/tempergraph/engine/src/tempergraph/settings.py` | | A map's step takes the step-side settings |

### Phase 3: Complexity switches

Goal: CXR-AC1 to CXR-AC5: stock measures, the rules file and its repository override, zones, the arm contract at validation, one-way re-arm, exploration, `report --switch`.
Weight: heavy (many-tests)

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 3.1 | test | `plugins/tempergraph/engine/tests/test_complexity.py` | CXR-AC1, CXR-AC2, CXR-AC3, CXR-AC4, CXR-AC5 | CXR-B1 to B6, every §2.3 fault, every §4 row, the report's cells |
| 3.2 | code | `plugins/tempergraph/engine/src/tempergraph/contracts.py` | | `MeasureSpec`, `ComplexitySpec`, `MeasureContext`, the optional predicate |
| 3.3 | code | `plugins/tempergraph/engine/src/tempergraph/api.py` | | `ComplexitySwitch`, `Measure`, `stock` |
| 3.4 | code | `plugins/tempergraph/engine/src/tempergraph/run/complexity.py` | | Measures, the rules file and its override, zones, exploration |
| 3.5 | code | `plugins/tempergraph/engine/src/tempergraph/run/nodes.py` | | The switch's step node evaluates once; the route record's fields |
| 3.6 | code | `plugins/tempergraph/engine/src/tempergraph/run/gate.py` | | The pick reads the evaluation; a spent budget re-arms only on evidence |
| 3.7 | code | `plugins/tempergraph/engine/src/tempergraph/model/validate.py` | | CXR-B7, CXR-B4, CXR-B10 and the arm contract |
| 3.8 | code | `plugins/tempergraph/engine/src/tempergraph/observe/switch_report.py` | | Per arm and zone, re-armed runs apart, cells under 5 runs |
| 3.9 | code | `plugins/tempergraph/engine/src/tempergraph/cli/observe_cli.py` | | `report --switch` |

## 3. Verification

- `cd plugins/tempergraph/engine && python -m pytest`
- `cd plugins/tempergraph/engine && ruff check src tests`

| Criterion | Test | Command |
|---|---|---|
| AC 1 | `plugins/tempergraph/engine/tests/test_measured_switches.py` | `cd plugins/tempergraph/engine && python -m pytest` |
| AC 2 | `plugins/tempergraph/engine/tests/test_map.py` | `cd plugins/tempergraph/engine && python -m pytest` |
| AC 3 | `plugins/tempergraph/engine/tests/test_complexity.py` | `cd plugins/tempergraph/engine && python -m pytest` |

## 4. Docs to update

- `plugins/tempergraph/docs/specs/run-settings-and-overrides.spec.md`: the `arm` key and the `arm:` layer are built, no longer refused
- `plugins/tempergraph/docs/specs/measured-switches.spec.md`: acceptance criteria ticked; the reading of a step timeout recorded
