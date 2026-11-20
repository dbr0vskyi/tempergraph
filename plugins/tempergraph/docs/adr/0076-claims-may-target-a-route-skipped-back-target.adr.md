# ADR-0076 Upstream claims and attributions may target a listed back target that a route skipped

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

A step may end with `UPSTREAM <unit>: <defect>`, and a judge may attribute a blocker to an earlier artifact, sending the run back. Both are offered only when the target is a listed back target **that has run** ([PRM-B11](../specs/04-prompt-rendering.spec.md)). temperspec skips discovery when triage finds no gap. If the plan then meets a spec defect, the plan step can only end blocked, and a code blocker that is really a spec fault stays unattributed, so the code step retries until its budget is spent; a person then sends the run back to discovery by hand ([R-075](../research/R-075-temperspec-needs-against-the-engine.rsrch.md) T17). The skip was the cheap bet; when it loses, the engine makes the loss larger.

## Decision

We will treat a listed back target that a route or switch **skipped on the path to this unit** as an allowed target, exactly like one that ran: the step is offered the upstream line for it, a judge's `defect_in` may name the artifact kinds it would have produced, and a trip back to it starts its first visit with the claim or the attribution as its reason. The loop budget of the pair counts as for any trip. A target that was never on the path (another switch arm) stays refused.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Allow route-skipped listed targets (chosen) | The run reaches the step that closes the defect without a person; no new edge kind | A model can claim a skipped step is needed; bounded by the loop budget and by the judge's confirmation of a claim |
| Keep "ran" only | Simplest | Spent budgets and person time on the case the skip was meant to avoid |
| Make the person's back the only way | Person decides | Retries until the budget is spent, then a pause |
| Never skip; run discovery as a no-op | Target always ran | Pays a session on every run to save the rare one |

## Decision rationale

| Criterion | Allow skipped | Ran only | Person only | Never skip |
|---|---|---|---|---|
| Retries spent on an unattributable blocker | none | up to the budget | up to the budget | none |
| Extra cost on runs that need no trip | none | none | none | one session each |
| Bounded | loop budget | n/a | human cap | n/a |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| K1 | A skipped unit's artifacts are absent, so a step that names them already sees the missing marker; a claim against it is the natural signal. | [VAL-B3](../specs/76-step-values-and-template-keys.spec.md) |
| K2 | The judge confirms an upstream claim as today ([HUM §2.1](../specs/07-gate-and-human.spec.md)); an unconfirmed claim still escalates. | PRM, JDG |

## Consequences

- Positive: temperspec's "spec defect after a skipped discovery" ends in a trip back, not a spent budget.
- Negative: the rule "offered only when that unit is a listed target that has run" in PRM and JDG becomes "has run or was skipped by a route on this path".
- Risk: a step claims upstream to dodge work. Mitigation: the claim is shown to the judge, confirmed or escalated; each pair has a loop budget of one by default; the audit counts claims per pair.

## Revisit when

History shows more than one in ten trips back to a skipped target ending with that target finding nothing to do.
