# A gate with no judge may send the run back with its findings

## Context

A workflow may hold a model-free unit whose failure carries findings that an earlier unit can fix: a script unit whose check reads what the script reported. The engine has no line back from such a unit, so its failure repeats under the retries and then waits for a person. A workflow that needs the line back cannot be built until the engine offers one as a general capability.

## Current state

- The engine gives a run three lines back: a judge's `defect_in` that names an allowed back target ([JDG-B13](../specs/judge-and-verdict.spec.md)), a step's upstream claim that a judge confirms ([JDG-B9](../specs/judge-and-verdict.spec.md)) and a person's `back:<unit>` ([HUM-B12](../specs/gate-and-human.spec.md)).
- A check FAIL of a gate with no judge derives RETRY with the findings as blockers, and an environmental FAIL escalates at once (`plugins/tempergraph/engine/src/tempergraph/run/nodes.py`, the check branch of the judge node, [BUD-B11](../specs/budgets-and-failures.spec.md)). A RETRY runs the unit again, which for a deterministic script unit repeats the failure, and when the retries are spent the run pauses for a person ([SCR-B7](../specs/script-units-and-hybrid-steps.spec.md)).
- A BACK is applied only for a target in the gate's `back_targets` and within its `loop_budget`; the reason of the visit is the blockers' problems joined (`plugins/tempergraph/engine/src/tempergraph/run/gate.py`, the BACK branch of `decide`), which drops a finding's criterion, place and fix.
- A hybrid step's `after` script that fails fails the attempt, and the step retries under its own retry budget; the reason of that retry names the failed script and holds none of its findings ([SCR-B2](../specs/script-units-and-hybrid-steps.spec.md), `plugins/tempergraph/engine/src/tempergraph/run/nodes.py`, the failed-attempt branch of the judge node).
- A map's gate takes no back target ([MAP-B11](../specs/map-unit.spec.md)).

## Forces

- C1 (constraint): the capability is stated and tested without naming a workflow. Source: decision record `the-engine-names-no-workflow`
- C2 (constraint): a map's gate takes no back target. Source: [MAP-B11](../specs/map-unit.spec.md)
- C3 (constraint): a failure of the environment is never sent back; it pauses at once. Source: [BUD-B11](../specs/budgets-and-failures.spec.md)
- F1: a model-free gate stays model-free: no model session to decide what the check has already decided
- F2: the trips back have a budget of their own, not one shared with the other failures of the earlier step
- F3: the earlier step is given the findings (criterion, place, message and fix) as the reason of its visit
- F4: a person is not paused for a failure that the earlier step can fix
- F5: the unit runs after the earlier step has passed its own gate
- F6: few new paths through the gate, and few declarations for validation to refuse

## Options considered

### A. A gate policy for a gate with no judge (chosen)

How it works: `on_fail` takes the value `back` on a gate with no judge and one back target. A check FAIL with findings derives BACK to that target, counted against the gate's loop budget, and the visit's reason is one numbered line for each finding.
For: the line back exists where the findings are, with no model session (F1, F3, F4); the loop budget and `on_budget_spent` already bound it and say what a spent budget does (F2); the compiler already draws a BACK edge for each listed back target; `on_fail` already holds the other two policies for a failed unit (`stop`, `fallback`), so a workflow author finds it where they look; the unit stays a unit of its own after the earlier step's gate (F5). Against: one more path through the gate, and three declarations that validation has to refuse (F6).

### B. A script as the `after` script of the earlier step

How it works: nothing is built. The workflow declares the script as the `after` script of the step that can fix its findings.
For: no engine change (F6). Against: the script then runs before that step's own gate and not after it (F5); its failure retries the step under the step's retry budget, shared with every other failure of the step and not bounded by a budget of its own (F2); and the retry's reason holds no finding (F3).

### C. A judge on the gate with mechanical criteria

How it works: the model-free unit's gate gets a judge whose criteria are mechanical, and the judge's `defect_in` names the earlier unit.
For: a judge's `defect_in` already sends a run back (F6). Against: a model session on every pass of a model-free gate, for a verdict that the check has already decided (F1).

### D. A pause for a person on every failure

How it works: nothing is built. The unit's failure retries and then pauses, and the person fixes the findings or sends the run back by hand.
For: nothing to build (F6). Against: the person is the cost the unit exists to remove, and the findings are fixable by the step the run would go back to (F4).

## Decision

We will let a gate with no judge declare `on_fail: back`, option A, which sends the run back to the gate's one back target when its check fails with findings, gives the target those findings as the reason of its visit, and counts the trip against the gate's loop budget, as [HUM-B15](../specs/gate-and-human.spec.md) to [HUM-B18](../specs/gate-and-human.spec.md) say.

## Decision rationale

Option A is the only one that meets F1 to F5 together. C1 is met: the policy is a field of any gate with no judge, stated in [HUM-B15](../specs/gate-and-human.spec.md) to [HUM-B18](../specs/gate-and-human.spec.md) and proved by an engine fixture. C2 is met: validation refuses the policy on a map's gate. C3 is met: a check FAIL marked environmental escalates before the policy is read. F1 is met, no session is added. F2 is met by the gate's own loop budget. F3 is met by the numbered lines of [HUM-B16](../specs/gate-and-human.spec.md). F4 is met for the first failure; the pause comes only when the budget is spent. F5 is met, the unit keeps its place after the earlier step's gate. F6 is given up in part: the gate gains one path and validation three refusals, which is less than a second mechanism beside `back_targets` and `loop_budget` would cost.

## Consequences

A workflow can put a model-free unit after a step and let a failure go back to that step once, with the findings in its brief. A gate that has a judge keeps `defect_in` as its only line back. A failure of the environment never goes back: it pauses at once ([BUD-B11](../specs/budgets-and-failures.spec.md)). The blueprint reads `on_fail` as a string, so a declared `back` compares as any other value.

## Risks

- A deterministic failure that the earlier step cannot fix costs one more visit of that step before the run pauses. Limited by: the gate's loop budget, default 1 ([HUM-B17](../specs/gate-and-human.spec.md)). Noticed by: the pause of kind `budget` that lists the findings left, and the trip back in the run's records.

## Assumptions

- A1: one back target is enough for a gate with no judge, so no workflow needs the target chosen from several by the findings. Check: read the gates that declare `on_fail: back` in the workflow packages. If wrong: such a workflow needs a judge on the gate, or one gate for each target, until the policy takes a rule for choosing.

## Revisit when

A workflow needs the target chosen by the findings from several, or a gate with a judge needs a line back driven by its check.
