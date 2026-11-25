# Measured switches

## Purpose

A switch picks one arm by a pure predicate ([CMP-B10](compiler-and-flow.spec.md)). A switch whose choice is a cost bet, such as a router that runs a small plan in one session and a large one per phase, needs three more things before it can be trusted: a shadow mode that records what the predicate would pick and routes nothing, arm overrides that give the units of an arm their own limits and models, and re-arming that moves a run to the safer arm when the cheaper one spends its budget ([ADR `switches-are-measured-before-they-route`](../adr/switches-are-measured-before-they-route.adr.md)). A switch whose predicate the engine builds from declared complexity measures and a rules file, with a failsafe arm, one-way re-arming and an arm contract, is a complexity switch ([CXR](complexity-routing.spec.md)). Workflow authors and the run reports depend on it; design and build notes are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### SWM-B4 Switch fields

WHEN a `switch` unit is declared THE engine SHALL read `predicate` (pure: `(state) -> arm` or `(state) -> (arm, signals)`, `signals` a map of at most 10 names to numbers or strings of at most 60 characters, larger signals clipped and counted on the record), `default` (the arm taken on a predicate fault, recorded with the exception type, and always in shadow mode), `mode` (`route` or `shadow`, default `route`), `arm_overrides` (arm to unit to `{model, timeout_s, idle_s, effort, effort_ladder, escalation}`, the last two applied by [LAD](effort-ladder-and-model-escalation.spec.md)) and `rearm` (a list of `{from, to, units, on}`, `on` within `budget_spent` and `timeout`), and SHALL refuse at validation `arm_overrides` naming an arm the switch lacks or a unit no arm path reaches, an override value outside the unit's own allowed range (a non-positive timeout, an alias no binding resolves), and a `rearm.to` whose entry does not precede the listed unit on the `from` path.

- GIVEN `arm_overrides` naming an arm the switch lacks WHEN validated THEN it is refused

### SWM-B5 Shadow mode

WHEN a switch runs with `mode: shadow` THE engine SHALL run the predicate, record its pick and signals and take the default arm, an operator's `--arm` winning in either mode, and add `shadow`, `would_choose`, `signals` and `chosen_by` (`predicate`, `default`, `operator` or `rearm`) to the `route` record ([OBS](observability-and-cost.spec.md)); and `report --switch` ([CXR](complexity-routing.spec.md)) SHALL group finished runs of one workflow version by `would_choose` against the arm taken, with first-pass yield, cost and time per group.

- GIVEN a shadow predicate that raises WHEN the switch runs THEN the fault is recorded with the exception type and the default arm runs

### SWM-B1 Shadow first

WHEN a shadow switch's predicate picks a non-default arm THE engine SHALL run the default arm and record the pick.

- GIVEN arms `per_phase` (default) and `single`, a predicate picking `single` for at most three phases and 30 rows that returns `{phases: 2, rows: 18}`, and `mode: shadow` WHEN a two-phase plan reaches it THEN `per_phase` runs and the record holds `shadow: true, would_choose: single, chosen_by: default` and both signals

### SWM-B6 Arm overrides

WHEN an arm is the switch's chosen arm (sticky per visit or per run, as declared) THE engine SHALL give each unit it names the override values in place of its own `model`, `timeout_s`, `idle_s` and `effort`, operator layers still winning, overriding a unit named by several arms only by the arm in force, and record every value with its source layer `arm:<switch>.<arm>`, an attempt under an override carrying `sources: {<key>: arm:<switch>.<arm>}` on its `attempt_start` and `agent_run` records.

- GIVEN an override WHEN the attempt is recorded THEN `attempt_start` names the layer `arm:<switch>.<arm>`

### SWM-B2 Arm override

WHEN an arm with an override is taken THE engine SHALL use the override, and SHALL use the unit's own value under another arm.

- GIVEN `arm_overrides: {single: {code: {timeout_s: 5400}}}` and code's own `timeout_s: 1800` WHEN `single` is taken THEN code gets 5,400 s from `arm:code_mode.single`
- GIVEN the same WHEN `per_phase` is taken THEN code gets 1,800 s
- GIVEN an operator's per-step timeout of 7,200 s for `code` WHEN either arm is taken THEN code gets 7,200 s

### SWM-B7 Re-arming

WHEN a unit listed in a `rearm` entry, while arm `from` is in force, ends with a spent retry budget or a step timeout listed in `on` THE engine SHALL skip the gate's `on_budget_spent` policy and send the run back to the entry of arm `to` as a trip back ([BUD-B4](budgets-and-failures.spec.md)), clearing units from that entry on in state and keeping the workspace's files, set the arm to `to` with `chosen_by: rearm`, count the trip on the loop budget of the unit and `to`'s entry, re-arm on a listed timeout at once without first spending the retry budget, re-arm a switch at most once per run and never let the predicate make a re-armed pick again; and when `to` also spends its budget the gate's own policy SHALL apply.

- GIVEN a re-arm WHEN the trip back runs THEN the workspace's files are kept and the loop budget of the unit and `to`'s entry is charged once

### SWM-B3 Re-arm

WHEN the cheaper arm's listed unit spends its budget THE engine SHALL re-arm to the safer arm, and apply the gate's own policy once re-armed or under the safer arm.

- GIVEN `rearm: [{from: single, to: per_phase, units: [code], on: [budget_spent, timeout]}]` WHEN single's code step spends its budget THEN the run goes back to the `phase` map with `per_phase`, the map and `code` run as a new visit on the same branch, and the record says `chosen_by: rearm`
- GIVEN `single` in force WHEN code times out THEN it re-arms to `per_phase`
- GIVEN `single` already re-armed once WHEN code spends its budget THEN the gate's `on_budget_spent` applies
- GIVEN `per_phase` in force WHEN code spends its budget THEN the gate's `on_budget_spent` applies

## Acceptance criteria

- SWM-AC1 (SWM-B1, SWM-B2, SWM-B3, SWM-B7, SWM-B4): SWM-B1 to SWM-B3 and every scenario of SWM-B3 hold offline with scripted executors
- SWM-AC2 (SWM-B5): In shadow mode the arm taken is the default (or the operator's) in every fixture, whatever the predicate returns
- SWM-AC3 (SWM-B6): Every limit and alias record of a unit under an arm override names the layer `arm:<switch>.<arm>`

## Open questions

- Should the shadow report suggest switching to `route` mode when one arm is better by a stated margin, or only show the figures? Until answered: figures only. Owner: owner.
