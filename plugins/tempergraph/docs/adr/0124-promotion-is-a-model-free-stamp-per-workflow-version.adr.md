# ADR-0124 Promotion is a model-free stamp per workflow version; release 2 promotes to `local-stable` and pipelines come later

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — (specifies [ADR-0041](0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md)) |

## Context

ADR-0041 decided measured stages and a `promote-check` verb, but no spec existed. Ladders, escalation and complexity switches add paths an unattended run must not take unmeasured. On 2026-11-20 the owner moved CI pipelines to a later release, with run state carried on a branch in the meantime ([ADR-0126](0126-a-run-carries-a-scrubbed-thread-state-on-its-own-branch-and-deletes-it-when-done.adr.md)).

## Decision

We will specify `promote-check` as [PRO](../specs/95-promotion-check.spec.md): every run carries a stage derived from its caller, the workflow's mode and a `promotion.json` stamp for its exact version; criteria (ADR-0041's, SUP-B17's, and new ones for escalation coverage, ladder use, switch arms and unattended credentials) are read model-free from the run store; `--stamp` writes only when all are met; any version change voids the stamp. **Release 2** builds the stage model and `--to local-stable`. The `pipeline` stage, `--to pipeline`, the regressed watch and pipeline runs are designed now and built with pipelines in a later release, refused meanwhile with `not_in_release`.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Pipelines in release 2 on `claude` | One release sooner | The owner moved pipelines later |
| **Stage model and `local-stable` now, pipeline later (chosen)** | Ladders and switches already read the stage; nothing unattended ships before its release | `pipeline` rows of LAD and CXR wait |
| No promotion spec until pipelines | Less now | Stable mode has no measured entry |

## Decision rationale

| Criterion | Pipelines now | Chosen | Nothing now |
|---|---|---|---|
| Follows the owner's 2026-11-20 call | no | yes | yes |
| `local-stable` entry measured | yes | yes | no |
| Every unattended path measured before use | yes | yes | n/a |

## Consequences

- Positive: "ready for stable mode" is a checkable claim in release 2; the pipeline criteria are already written.
- Negative: an `auto` escalation at stage `pipeline` cannot exist before the pipeline release.

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| P1 | When pipelines arrive, a pipeline run's state travels by CAR's state branch or a hosted store. | PRO-B11 |
| P2 | Thresholds are defaults without data, revisited after 20 runs of one workflow. | PRO-B9 |

## Revisit when

Pipelines are scheduled for a release.
