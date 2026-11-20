# ADR-0121 Ladders climb only on trusted, substantive evidence: effort first, one model step last

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | The retry-count model ladder of [BUD-B7](../specs/08-budgets-and-failures.spec.md) (release 1), from release 2 |

## Context

Release 1 builds a model ladder: attempt n of a visit uses the n-th alias, whatever made attempt n−1 fail ([R-120](../research/R-120-effort-ladders-and-one-step-model-escalation.rsrch.md) F3). On 2026-11-20 the owner put ladders into release 2 with one hard condition: "ladders should be bulletproof, I don't want to increase model or efforts on any failure." Most failure causes are not fixed by a stronger session, and a judge's RETRY is only a signal when the judge is known not to fail good work ([R-121](../research/R-121-judge-model-by-risk-and-evidence-for-escalation.rsrch.md) F3, F4).

## Decision

We will replace the retry-count model ladder with an **effort ladder** and a **one-step model escalation**, both declared per step and both gated by evidence ([LAD](../specs/92-effort-ladder-and-model-escalation.spec.md)):

- The effort rises one rung only after a failed attempt that ended normally and carries **climbing evidence**: a parsed judge blocker on substance from an `accepted` judge binding, or a substantive check failure the engine verified. Every other cause holds the rung.
- The model rises at most one tier, for at most one attempt per visit, only when nine conditions hold, among them the same trusted blocker on two consecutive top-rung attempts, a judge calibrated at the higher tier, cost headroom, and no decomposition re-arm left to try. A failed escalated attempt goes straight to a person or a stop.
- In `local-dev` an escalation is offered to a person, never taken; `auto` needs a measured escalation record in `local-stable` and promotion coverage in `pipeline`.
- Release 1 `model` lists are retired by an upgrade transform.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Keep the retry-count model ladder | Built; simple | Climbs on timeouts, caps and false judge alarms, the owner's "any failure" |
| Effort ladder on any counted retry (R-120's first reading) | Simple; vendor-backed pattern | Still climbs on untrusted RETRYs and output-contract failures |
| **Evidence-gated effort ladder plus a guarded one-step escalation (chosen)** | Climbs only where a stronger session is the likely fix; every climb is explained in the record | More rules to test; fewer climbs mean some fixable failures go to a person |
| No ladder at all | Nothing to get wrong | Gives up the measured "re-run failures at higher effort" saving |

## Decision rationale

| Criterion | Retry-count | Effort on any retry | Chosen | None |
|---|---|---|---|---|
| No climb on timeouts, caps, infra, tool access | no | partly | yes | yes |
| No climb on an untrusted judge | no | no | yes | yes |
| Uses the vendor's effort-first evidence | no | yes | yes | no |
| Every climb has a recorded reason | no | partly | yes | n/a |

## Consequences

- Positive: a climb means something; reports can separate first-try yield from rescued yield.
- Negative: until judges are `accepted`, ladders rarely climb, by design.
- Risk: a release 1 workflow's ladder changes behaviour after the update. Mitigation: the changelog transform rewrites it, and an owner item covers what no rule can.

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| L1 | "Bulletproof" means no climb without evidence, not no climb at all. | LAD §2.2 |
| L2 | Two repeated blockers and ≥ 5 escalations with a lower bound ≥ 0.5 are defaults without data. | LAD §2.4, §2.5 |
| L3 | `xhigh` is applied by the CLI on the shipped aliases; until probe P-LAD-1 it is `uncertain` and warned. | LAD §2.6 |

## Revisit when

Twenty escalations are recorded, or the first live probe of `xhigh` and `max` is in.
