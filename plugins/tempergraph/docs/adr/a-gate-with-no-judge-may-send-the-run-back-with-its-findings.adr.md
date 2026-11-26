# A gate with no judge may send the run back with its findings

## Context

A workflow may hold a model-free unit whose failure carries findings that an earlier unit can fix: a script unit whose check reads what the script reported. The engine gives a run three lines back today: a judge's `defect_in` that names an allowed back target ([JDG-B13](../specs/judge-and-verdict.spec.md)), a step's upstream claim that a judge confirms ([JDG-B9](../specs/judge-and-verdict.spec.md)) and a person's `back:<unit>` ([HUM-B12](../specs/gate-and-human.spec.md)).

What the engine does for a gate with no judge, read in the code:

- A check FAIL derives RETRY with the findings as blockers, and an environmental FAIL escalates at once (`plugins/tempergraph/engine/src/tempergraph/run/nodes.py`, the check branch of the judge node, [BUD-B11](../specs/budgets-and-failures.spec.md)). A RETRY runs the unit again; for a deterministic script unit that repeats the failure, and when the retries are spent the run pauses for a person.
- A BACK is applied only for a target in the gate's `back_targets` and within its `loop_budget`; the reason of the visit is the blockers' problems joined (`plugins/tempergraph/engine/src/tempergraph/run/gate.py`, the BACK branch of `decide`), which drops a finding's criterion, place and fix.
- A hybrid step's `after` script that fails fails the attempt, and the step retries under its own retry budget; the reason of that retry names the failed script and holds none of its findings ([SCR-B2](../specs/script-units-and-hybrid-steps.spec.md), `plugins/tempergraph/engine/src/tempergraph/run/nodes.py`, the failed-attempt branch of the judge node).
- A map's gate takes no back target ([MAP-B11](../specs/map-unit.spec.md)).

## Decision

We will let a gate with no judge declare `on_fail: back`, which sends the run back to the gate's one back target when its check fails with findings, gives the target those findings as the reason of its visit, and counts the trip against the gate's loop budget, as [HUM-B15](../specs/gate-and-human.spec.md) to [HUM-B18](../specs/gate-and-human.spec.md) say.

## Options considered

### A. A gate policy for a gate with no judge (chosen)

For: the line back exists where the findings are, with no model session; the loop budget and `on_budget_spent` already bound it and say what a spent budget does; the compiler already draws a BACK edge for each listed back target; `on_fail` already holds the other two policies for a failed unit (`stop`, `fallback`), so a workflow author finds it where they look. Against: one more path through the gate, and three declarations that validation has to refuse.

### B. A script as the `after` script of the earlier step

For: no engine change. Against: the script then runs before that step's own gate and not after it; its failure retries the step under the step's retry budget, shared with every other failure of the step and not bounded by a budget of its own; and the retry's reason holds no finding.

### C. A judge on the gate with mechanical criteria

For: a judge's `defect_in` already sends a run back. Against: a model session on every pass of a model-free gate, for a verdict that the check has already decided.

### D. A pause for a person on every failure

For: nothing to build. Against: the person is the cost the unit exists to remove, and the findings are fixable by the step the run would go back to.

## Consequences

A workflow can put a model-free unit after a step and let a failure go back to that step once, with the findings in its brief. A gate that has a judge keeps `defect_in` as its only line back. A deterministic failure that the earlier step cannot fix goes back once, then pauses, so the loop budget bounds the cost. A failure of the environment never goes back: it pauses at once ([BUD-B11](../specs/budgets-and-failures.spec.md)). The blueprint reads `on_fail` as a string, so a declared `back` compares as any other value.

## Revisit when

A workflow needs the target chosen by the findings from several, or a gate with a judge needs a line back driven by its check.
