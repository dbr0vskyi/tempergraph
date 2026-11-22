# ADR-0089 Supervision by every decider is a promotion criterion and an improvement signal

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — (replaces one criterion row of [ADR-0041](0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md)) |

## Context

The owner's lifecycle is to improve a workflow locally until it needs less human-in-the-loop, then move it to the pipeline ([ADR-0041](0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md)). ADR-0041 counts "person interventions per run" and the audit's `interventions-per-run` counts the same ([R-085](../research/R-085-callers-supervision-and-babysitting-cost.rsrch.md) D6). When an agent babysits, person interventions are near zero and the workflow looks ready; in the pipeline no agent babysits, and the same pauses stop the job. Public measurement also found that fewer approvals do not mean less supervision (R-085 P2).

## Decision

We will measure supervision on every decider ([SUP](../specs/86-supervision-metrics.spec.md)): each touch is classed `designed` (approvals, asks, event values), `rescue` (escalations and budget pauses) or `steer` (rewinds, reruns, grants, overrides, stops, rulings, breakpoints), with its caller and decider; each run gets a supervision level on the five-role scale (observer, approver, consultant, collaborator, operator) and who acted. For promotion, ADR-0041's "person interventions per run" row is replaced by the rows of [SUP-B17](../specs/86-supervision-metrics.spec.md): undesigned touches by anyone, the unattended rate, the agent's own rescue share, the supervision cost share, and two data-quality rows; missing data is `unmeasured`, which is not met. In the improvement loop each agent's own rescue is a finding (`agent_decided:<pause cause>`) clustered across runs, so a pause an agent keeps waving through becomes a workflow issue whose remedy is a check. Evals may assert a level ceiling per scenario.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Every decider, classed touches, levels, promotion rows (chosen) | An agent-babysat workflow is not promoted; approvals stay legitimate; the loop learns from agent answers | More figures; thresholds without data |
| Keep person-only counts | No change | Misses exactly the owner's case |
| One autonomy score (weighted sum) | One number | Weights are arbitrary; hides which touch to fix |
| Supervision cost only | Money is clear | A cheap agent rescue still fails in the pipeline |

## Decision rationale

| Criterion | Chosen | Person only | Score | Cost only |
|---|---|---|---|---|
| Catches agent babysitting | yes | no | yes | partly |
| Names what to fix | yes (class, pause cause) | partly | no | no |
| Keeps approvals out of the debt | yes | yes | depends | yes |
| Model-free and from records | yes | yes | yes | yes |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| E1 | In the pipeline stage nobody babysits a run; a pause reaches a person through `attention` ([ADR-0040](0040-take-script-steps-attention-and-composition-from-archon.adr.md)). | SUP-B17 |
| E2 | The thresholds are defaults chosen without data, revisited after the first 20 runs of one workflow version. | SUP-B17 |
| E3 | `promote-check` gets its own spec later; until then ADR-0041 and SUP-B17 together define its criteria. | SUP-B17 |

## Consequences

- Positive: "needs less human-in-the-loop" becomes "needs fewer undesigned touches by anyone, at a known supervision cost", which is what the pipeline needs.
- Negative: workflows that rely on an agent's judgement at pauses cannot be promoted until a delegation policy exists.
- Risk: authors turn rescues into approvals to pass. Mitigation: an approval answered by an agent is shown as `designed_by: agent`, and the audit's `approval-on-most-gates` rule still fires.

## Revisit when

A delegation policy exists, or the first workflow reaches 20 runs of one version.
