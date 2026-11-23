# ADR-0059 An upgrade is done when model-free checks pass against the workflow's own pre-upgrade baseline; only then is it stamped

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner's upgrade command needs a definition of "verified", and suggested validate and audit. A stamp that means every deterministic check of the changelog passes does not mean that behaviour is identical. Public practice validates every model edit in a fixed order and found pre-existing test failures blocking validation ([R-056](../research/R-056-automated-and-model-assisted-migrations.rsrch.md) M4, M8). A model-assisted upgrade can also add findings or weaken a gate while clearing the changelog's checks ([R-057](../research/R-057-engine-update-and-workflow-upgrade-gaps.rsrch.md) X10).

## Decision

We will take a baseline of the unchanged workflow under the running engine (validation, audit definition and host, model-free regression suites, shape, parse) and accept an upgrade only when, in order ([WUP-B19](../specs/63-workflow-upgrade.spec.md)): it loads; validation has no error and no new warning; every applied entry's proof is clear; the audit has no new finding at warning or above; change classification shows no weakening the owner did not answer and no model edit of a protected path; the regression suites that passed still pass and failing ones fail no more; the diagram is regenerated; and, when asked, a paired trial does not regress. The stamp is written only then.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Model-free checks against the own baseline (chosen) | Pre-existing problems do not block; new ones do; free and repeatable; reuses validate, audit, PRP classes and EVS | Does not prove behaviour unchanged |
| The changelog's checks only | Simple | A model edit that adds findings or weakens a gate is stamped |
| Absolute checks (zero findings, all suites green) | Strict | Blocks every upgrade of a workflow that had findings before |
| A paired trial always | Measures behaviour | Spends on every upgrade, even transform-only ones; needs a case set |

## Decision rationale

| Criterion | Own baseline | Changelog only | Absolute | Trial always |
|---|---|---|---|---|
| Catches new findings and weakening | yes | no | yes | partly |
| Not blocked by old findings | yes | yes | no | yes |
| Free | yes | yes | yes | no |
| Measures behaviour | opt-in | no | no | yes |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | "Verified through validate and audit" includes the model-free suites and the change classification, since both exist and cost nothing. | WUP-B19 |
| A2 | Audit findings are matched by rule id and location; a moved finding counts as new. | WUP-B19 V4 |

## Consequences

- Positive: a stamp now means "no worse by every model-free measure, and the changelog is cleared".
- Negative: an upgrade can fail on a finding the change merely moved; the person then fixes or ignores it with a reason ([AUD](../specs/55-workflow-audit.spec.md)).
- Risk: behaviour shifts that no check sees. Mitigation: `--trial`, stale rubric scores and judge acceptance shown in the report, and the post-release watch of the improvement loop ([PRP-B9](../specs/40-improvement-proposals.spec.md)).

## Revisit when

Audit locations prove too unstable to match, or the owner wants the trial by default for `stable` workflows.
