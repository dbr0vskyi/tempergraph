---
title: Measured switches
type: component
status: review
prefix: SWM
adrs: [0079]
---

# Measured switches

## 1. Overview

A switch picks one arm by a pure predicate ([CMP §2.2](03-compiler-and-flow.spec.md)). temperspec's code-mode router (one session for a small plan, one per phase for a large one) needs three more things before such a switch can be trusted: a **shadow mode** that records what the predicate would pick and routes nothing, **arm overrides** that give the units of an arm their own limits and models (the single-session arm needs a longer code timeout), and **re-arming** that moves a run to the safer arm when the cheaper one spends its budget ([R-075](../research/R-075-temperspec-needs-against-the-engine.rsrch.md) T46, [ADR-0079](../adr/0079-switches-are-measured-before-they-route.adr.md)). The same three serve any switch whose choice is a cost bet. A switch whose predicate the engine builds from declared complexity measures and a rules file, with a failsafe arm, one-way re-arming and an arm contract, is a complexity switch ([CXR](94-complexity-routing.spec.md)).

## 2. Contract

### 2.1 Switch fields

| Field (on a `switch` unit) | Kind | Meaning |
|---|---|---|
| `predicate` | callable ref | Pure: `(state) -> arm` or `(state) -> (arm, signals)`; `signals` is a map of at most 10 names to numbers or strings ≤ 60 chars |
| `default` | arm name | Taken on a predicate fault, and always in shadow mode |
| `mode` | `route` \| `shadow`, default `route` | §2.2 |
| `arm_overrides` | map arm → map unit → `{model, timeout_s, idle_s, effort, effort_ladder, escalation}` | §2.3; the last two from release 2 ([LAD](92-effort-ladder-and-model-escalation.spec.md)) |
| `rearm` | list of `{from, to, units, on}` | §2.4; `on` ⊆ {`budget_spent`, `timeout`} |

### 2.2 Shadow mode

The predicate runs as usual, and its pick and signals are recorded; the default arm is taken. The `route` record ([OBS §2.1](15-observability-and-cost.spec.md)) gains `shadow`, `would_choose`, `signals` and `chosen_by` (`predicate`, `default`, `operator`, `rearm`). An operator's `--arm` still wins in either mode. A report groups finished runs of one workflow version by `would_choose` against the arm taken, with first-pass yield, cost and time per group, so a person can see what routing would have changed before setting `mode: route`.

### 2.3 Arm overrides

While an arm is the switch's chosen arm (sticky per visit or per run, as declared), each unit it names takes the override values in place of its own declared `model`, `timeout_s`, `idle_s` and `effort`. Operator layers still win over them. Every record shows the value and its source layer `arm:<switch>.<arm>`. A unit may be named by several arms; it is overridden only by the arm in force.

### 2.4 Re-arming

When a unit listed in a `rearm` entry, while arm `from` is in force, ends with a spent retry budget or a step timeout listed in `on`, the engine does not apply the gate's `on_budget_spent` policy. It sends the run back to the entry of arm `to` as a trip back ([BUD-B4](08-budgets-and-failures.spec.md)): units from that entry on are cleared in state, files in the workspace stay, and the switch's arm becomes `to` with `chosen_by: rearm`. The trip counts on the loop budget of (unit, `to`'s entry). When `to` also spends its budget, the gate's own policy applies.

## 3. Behaviours

**SWM-B1 Shadow first.** Given a switch `code_mode` with arms `per_phase` (default) and `single`, a predicate that picks `single` for plans of at most three phases and 30 rows and returns `{phases: 2, rows: 18}`, and `mode: shadow`, when a two-phase plan reaches it, then `per_phase` runs and the `route` record holds `shadow: true, would_choose: single, chosen_by: default` and both signals.

**SWM-B2 Arm override.** Given `arm_overrides: {single: {code: {timeout_s: 5400}}}` and code's own `timeout_s: 1800`, when `single` is taken, then the code step gets 5,400 s with source `arm:code_mode.single`; when `per_phase` is taken, it gets 1,800 s; an operator's per-step timeout of 7,200 s for `code` beats both.

**SWM-B3 Re-arm.** Given `rearm: [{from: single, to: per_phase, units: [code], on: [budget_spent, timeout]}]`, when the single-session code step spends its retry budget, then the run goes back to the `phase` map with arm `per_phase`, the map and `code` run as a new visit on the same branch, and the `route` record says `chosen_by: rearm`.

| Arm in force | Code ends | Effect |
|---|---|---|
| single | budget spent | re-arm to per_phase |
| single | step timeout | re-arm to per_phase |
| single, already re-armed once | budget spent | gate's `on_budget_spent` |
| per_phase | budget spent | gate's `on_budget_spent` |

## 4. Error conditions

| Condition | Result |
|---|---|
| `arm_overrides` names an arm the switch does not have, or a unit no arm path reaches | Validation error |
| An override value outside the unit's own allowed range (a non-positive timeout, an alias no binding resolves) | Validation error, as for the unit's own field |
| A `rearm.to` whose entry does not precede the listed unit on the `from` path | Validation error |
| `signals` larger than allowed | Clipped and counted on the record |
| Shadow predicate raises | Recorded as a fault with the exception type; the default arm runs, as in route mode |

## 5. Design notes

- Overrides belong to the arm because the reason for them (a longer limit for a whole-plan session) belongs to the arm, not to the unit; they are workflow data below every operator layer.
- Re-arming is a trip back, not a new edge kind, so budgets, clearing and records stay the ones every other trip back uses.

## 6. Acceptance criteria

- [ ] SWM-AC-1 SWM-B1 to SWM-B3 and every row of the SWM-B3 table hold offline with scripted executors.
- [ ] SWM-AC-2 In shadow mode the arm taken is the default (or the operator's) in every fixture, whatever the predicate returns.
- [ ] SWM-AC-3 Every limit and alias record of a unit under an arm override names the layer `arm:<switch>.<arm>`.

## Open questions

| Question | Owner |
|---|---|
| Should the shadow report suggest switching to `route` mode when one arm is better by a stated margin, or only show the figures? This spec shows figures only. | Owner |

## References

[CMP §2.2](03-compiler-and-flow.spec.md) · [CXR](94-complexity-routing.spec.md) · [BUD](08-budgets-and-failures.spec.md) · [OBS](15-observability-and-cost.spec.md) · [MAP](77-map-unit.spec.md) · [ADR-0079](../adr/0079-switches-are-measured-before-they-route.adr.md)
