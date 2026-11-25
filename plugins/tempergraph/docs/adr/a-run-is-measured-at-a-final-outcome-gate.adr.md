# A run is measured at a mandatory final outcome gate; unverified criteria are shown, never passed

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

A run whose every step passed can still miss the request; the outcome lens of self-improvement graded "did the result meet the request" against nothing declared ([SIL-B10](../specs/self-improvement.spec.md)). research `design-gap-review` recommended a mandatory outcome gate. The owner asks for verifiable outcomes and, by the thread's brief, for unverifiable ones to be flagged rather than hidden.

## Decision

We will compile a reserved `outcome` unit before the finalizer on every workflow: a built-in deliverables check, the workflow's outcome check, a fresh judge over the judge-verified final criteria, and a sign-off for person-verified ones. A failure goes back to the earliest unit whose criteria serve the failed criterion. Every run writes an outcome record whose verdict separates `met` from `met_with_open`, and every report lists the unverified criteria. The outcome lens reads this record. Details: [OUT-B15, OUT-B16, OUT-B17, OUT-B18, OUT-B19](../specs/run-outcome.spec.md).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Mandatory outcome gate (chosen) | One bar; a defect the step gates missed is caught in the run; the loop's outcome grade costs no second judge | One judge session per run |
| Optional outcome gate | Cheaper for trivial workflows | The workflows without it are exactly the ones nobody measured |
| Outcome graded only by the loop after the run | No run cost | A miss is found after the finalizer published it |

## Decision rationale

| Criterion | Mandatory | Optional | Loop only |
|---|---|---|---|
| Caught before the finalizer | yes | sometimes | no |
| One bar for gates and loop | yes | sometimes | no |
| Cost per run | one judge | 0 or one | one judge, later |

## Consequences

- Positive: the outcome met rate, escape rate and unverified share exist for every workflow and feed promotion.
- Negative: `outcome` is a reserved unit name.
- Risk: a weak outcome judge passes misses. Mitigation: its calibration and corrected rates as for any judge ([JCL](../specs/judge-calibration.spec.md), [EVS-B15](../specs/eval-suites.spec.md)); `stable` may sample it.

## Assumptions

- The cost of one judge per run is acceptable in `dev`; cost data will set the `stable` default.
