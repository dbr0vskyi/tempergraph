# ADR-0079 Switches can be measured in shadow, carry per-arm overrides, and re-arm on a spent budget

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

temperspec measured per-phase code at 111 to 149% of one session on small plans, and found a whole-plan session risky on large ones. Its planned code-mode router needs "a generic conditional route in the engine with per-arm session options", a shadow mode that logs the signals and the would-be choice and routes nothing, and escalation from the single-session arm to per-phase; its triage and release skips are to become the same kind of named, recorded route ([R-075](../research/R-075-temperspec-needs-against-the-engine.rsrch.md) T46). The engine's switch has arms, a default, an operator pick and a `route` record, but none of those three.

## Decision

We will add to the switch a `mode` (`route` or `shadow`), `arm_overrides` (per arm, per unit: model, timeout, idle limit, effort) and `rearm` entries (from one arm to another when a listed unit spends its budget or times out, applied as a trip back), with the predicate's signals and the would-be arm on the `route` record ([SWM](../specs/79-measured-switches.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Shadow, arm overrides and re-arm on the switch (chosen) | A router is measured before it moves money; arm-specific limits live where their reason is; fallback to the safe arm without a person | Three more fields on one unit kind |
| A workflow-specific router step | No engine work | A model or bespoke code in the path; not recorded like a route |
| Operator `--arm` only | Exists | The choice stays manual; nothing measures it |
| Separate workflows per mode | Simple | Two copies of the same workflow that drift |

## Decision rationale

| Criterion | Measured switch | Router step | `--arm` only | Two workflows |
|---|---|---|---|---|
| Measured before it routes | yes | no | no | no |
| Per-arm limits | yes | ad hoc | no | yes |
| Recovers from a lost bet without a person | yes (re-arm) | ad hoc | no | no |
| One definition | yes | yes | yes | no |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| K1 | The run settings design places workflow-declared arm overrides below every operator layer. | SWM-B6; the settings design (specs 80 to 84) |
| K2 | One re-arm per visit is enough; a second loss falls to the gate's own policy. | SWM-B7 |

## Consequences

- Positive: temperspec's router ships in shadow, then routes when its report supports it, with the single arm's longer timeout and a fallback to per-phase.
- Negative: the `route` record and the cost report gain fields.
- Risk: re-arming hides a bad predicate by always recovering. Mitigation: re-arms are recorded with `chosen_by: rearm` and the shadow report counts them against the arm the predicate picked.

## Revisit when

A second workflow needs a re-arm trigger other than a spent budget or a timeout.
