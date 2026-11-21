---
task: r2-t1
complexity: complex
specs: [plugins/tempergraph/docs/specs/79-measured-switches.spec.md, plugins/tempergraph/docs/specs/77-map-unit.spec.md, plugins/tempergraph/docs/specs/94-complexity-routing.spec.md]
---

# Plan: switches, maps and complexity (R2-T1)

## 0. Hand-off

- Triage note: `plugins/tempergraph/docs/tasks/r2-t1.triage.md`
- Specs read: SWM (79), MAP (77), CXR (94), CMP (03), RST (80), BUD (08), OBS (15)
- Why this design: a switch's pick stays in the gate node, so shadow mode, the operator's arm and re-arming are all changes to one pure function and its record. Arm overrides are applied where a session request is built, below the four operator layers, so the settings resolution stays one table. Re-arming is a trip back with one extra static edge per listed unit.

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | A shadow switch records what the predicate would pick and takes the default arm | SWM-B1, SWM-AC-2 |
| R2 | AC 1 | A unit under an arm in force takes the arm's model, limits and effort, below the operator layers, and its records name the layer | SWM-B2, SWM-AC-3 |
| R3 | AC 1 | A listed unit that spends its budget or times out under arm `from` sends the run to the entry of arm `to`, once | SWM-B3 |
| R4 | AC 1 | An operator's `<switch>.arm` setting picks the arm in either mode | CMP-B7, RST §2.2 |
| R5 | AC 2 | A sequential map runs its body once per item of a list a unit produced | MAP-AC-1 to MAP-AC-4 |
| R6 | AC 3 | A complexity switch builds its predicate from measures and a rules file, fails safe and re-arms one way | CXR-AC-1 to CXR-AC-5 |

## 2. Phases

### Phase 1: Measured switches

Goal: SWM-AC-1 to SWM-AC-3, with `effort_ladder` and `escalation` accepted in `arm_overrides` and applied in R2-T2.
Weight: light

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 1.1 | test | `plugins/tempergraph/engine/tests/test_measured_switches.py` | SWM-AC-1 | SWM-B1 to B3, each row of the SWM-B3 table, CMP-B7 and every §4 validation row |
| 1.2 | code | `plugins/tempergraph/engine/src/tempergraph/contracts.py` | | `SwitchSpec.mode`, `arm_overrides`, `rearm`; `RearmSpec` |
| 1.3 | code | `plugins/tempergraph/engine/src/tempergraph/api.py` | | `Switch` takes the new fields; `Rearm` builder |
| 1.4 | code | `plugins/tempergraph/engine/src/tempergraph/model/validate.py` | | The four validation rows of SWM §4 |
| 1.5 | code | `plugins/tempergraph/engine/src/tempergraph/model/flow.py` | | A static edge from each re-armed unit's gate to the entry of arm `to` |
| 1.6 | code | `plugins/tempergraph/engine/src/tempergraph/run/gate.py` | | Shadow pick, signals, operator arm, re-arm as a trip back |
| 1.7 | code | `plugins/tempergraph/engine/src/tempergraph/run/nodes.py` | | Arm overrides on the session request; the `route` record's new fields |
| 1.8 | code | `plugins/tempergraph/engine/src/tempergraph/settings.py` | | The `arm` key on a switch unit; operator-set keys marked for the arm layer |

### Phase 2: Sequential map and item keys

Goal: MAP-AC-1 to MAP-AC-4 for the sequential form; item keys validated; the concurrent mode stays `not_in_release`.
Weight: heavy (refactor)

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 2.1 | test | `plugins/tempergraph/engine/tests/test_map.py` | MAP-AC-1, MAP-AC-2, MAP-AC-3, MAP-AC-4 | MAP-B1 to B6 for the sequential form, every §2.3 row that the form can reach, VAL-B4 |
| 2.2 | code | `plugins/tempergraph/engine/src/tempergraph/contracts.py` | | `MapSpec`, `MapItem`, `ExtractContext`, `UnitSpec.map` |
| 2.3 | code | `plugins/tempergraph/engine/src/tempergraph/api.py` | | The `Map` builder |
| 2.4 | code | `plugins/tempergraph/engine/src/tempergraph/run/mapping.py` | | Reading the list, the item in hand, advancing |
| 2.5 | code | `plugins/tempergraph/engine/src/tempergraph/run/nodes.py` | | Fan-out, item sessions, item keys and records |
| 2.6 | code | `plugins/tempergraph/engine/src/tempergraph/run/gate.py` | | Next item, list fault stop, item on the pause |
| 2.7 | code | `plugins/tempergraph/engine/src/tempergraph/model/validate.py` | | MAP §2.3 rows and limits |
| 2.8 | code | `plugins/tempergraph/engine/src/tempergraph/settings.py` | | A map's step takes the step-side settings |

### Phase 3: Complexity switches

Goal: CXR-AC-1 to CXR-AC-5: stock measures, the rules file and its repository override, zones, the arm contract at validation, one-way re-arm, exploration, `report --switch`.
Weight: heavy (many-tests)

## 3. Verification

- `cd plugins/tempergraph/engine && python -m pytest`
- `cd plugins/tempergraph/engine && ruff check src tests`

| Criterion | Test | Command |
|---|---|---|
| AC 1 | `plugins/tempergraph/engine/tests/test_measured_switches.py` | `cd plugins/tempergraph/engine && python -m pytest` |
| AC 2 | `plugins/tempergraph/engine/tests/test_map.py` | `cd plugins/tempergraph/engine && python -m pytest` |

## 4. Docs to update

- `plugins/tempergraph/docs/specs/80-run-settings-and-overrides.spec.md`: the `arm` key and the `arm:` layer are built, no longer refused
- `plugins/tempergraph/docs/specs/79-measured-switches.spec.md`: acceptance criteria ticked; the reading of a step timeout recorded
