# ADR-0124 Promotion is a model-free stamp per workflow version, and release 2 pipelines run on `claude`

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — (specifies [ADR-0041](0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md); amends its assumption C1 for release 2) |

## Context

ADR-0041 decided measured stages and a `promote-check` verb but no spec existed; release 2 holds promotion "on `claude`" while ADR-0041 assumed the `agent-sdk` executor in CI, which waits for release 3 ([ADR-0091](0091-first-release-ships-the-claude-executor-only.adr.md)). Ladders, escalation and complexity switches add paths a pipeline must not take unmeasured.

## Decision

We will specify `promote-check` as [PRO](../specs/95-promotion-check.spec.md): every run carries a stage derived from its caller, the workflow's mode and a `promotion.json` stamp for its exact version; twelve criteria (ADR-0041's, SUP §2.7's, and new ones for escalation coverage, ladder use, switch arms and unattended credentials) are read model-free from the run store; `--stamp` writes only when all are met; any version change voids the stamp; a regressed watch reports and never demotes. In release 2 the pipeline runs the `claude` executor with an API key, an `apiKeyHelper` or cloud credentials.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Wait for `agent-sdk` (release 3) | Matches ADR-0041 C1 | No pipeline in release 2, though the owner scoped it |
| **`claude` with unattended credentials (chosen)** | Uses the one shipped executor and TCK's credential rules | `--bare` judges need an API key, not the OAuth token |
| Pipeline without a stamp | Less to build | Unmeasured paths in unattended runs |

## Decision rationale

| Criterion | Wait | Chosen | No stamp |
|---|---|---|---|
| Pipeline in release 2 | no | yes | yes |
| Every unattended path measured | yes | yes | no |
| One executor through release 2 | yes | yes | yes |

## Consequences

- Positive: "ready for the pipeline" is a checkable claim with a number on every row.
- Negative: an API key is needed for unattended judges.
- Risk: the run state between pipeline jobs. Mitigation: release 2 needs a runner with a persistent state root, stated as PRO's open question.

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| P1 | A pipeline in release 2 is a CI job or a scheduler fire on a machine whose state root persists between jobs. | PRO §2.6 |
| P2 | Thresholds are defaults without data, revisited after 20 runs of one workflow. | PRO §2.3 |

## Revisit when

The `agent-sdk` executor ships, or a hosted run store exists.
