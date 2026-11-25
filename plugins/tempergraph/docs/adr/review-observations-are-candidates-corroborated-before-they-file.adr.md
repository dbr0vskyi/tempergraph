# Review observations are candidates, corroborated before they file

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The best public method found the decisive step of a multi-agent failure 14.2% of the time ([research `reading-session-logs-for-self-improvement`](../research/reading-session-logs-for-self-improvement.rsrch.md) P3). So an issue is evidence, not an order; a verdict is a candidate until people confirm it; and flagging is not selecting (B10). Uncalibrated outcome verdicts already stay local (SIL-B7). Steps and their graders change apart ([ADR `steps-and-their-graders-change-apart`](steps-and-their-graders-change-apart.adr.md)), and every change to a workflow is decided by a trial or a person ([ADR `improvement-closes-through-measured-proposals`](improvement-closes-through-measured-proposals.adr.md)).

## Decision

We will rank what the loop knows in three tiers of trust: run records, then the model-free digest, then review observations ([SRV-B20, SRV-B22](../specs/session-review.spec.md)). A review observation is kept only if its citations pass the engine's check, and it files nothing on its own: it is shown in a local report, weights the cluster of a model-free finding it corroborates on the same unit and run (adding its category word, never its note, to that finding's issue), and is context for the proposer and for lessons drafts. A step session's observation may propose producer classes only, a judge session's grader classes only. Release 1 builds the local report and never files from reviews; corroborated filing comes with stable-mode plans.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **Candidates, corroborated before they file (chosen)** | No issue rests on a model's reading alone; the author still sees every observation | A real problem only a model can see (a prompt misread) files only through a proposal or a person |
| File observations like causes | More issues, sooner | Mostly noise, as a model's attribution is wrong more often than right (P3, B10); text-based classification (B6) |
| File once the reviewer is calibrated on a gold set | Principled | No gold set exists; deferred as an open question in SRV |
| Keep observations out of proposals | Simplest | Wastes the signal GEPA-style proposers use (P2) |

## Decision rationale

| Criterion | Chosen | File like causes | Calibrated filing |
|---|---|---|---|
| Issues resting on model text alone | none | many | after a score |
| Signal reaches the author | yes, locally | yes | yes |
| Available in release 1 | yes | yes | no |

## Consequences

- Positive: the trust order is visible on every finding (`review_weight`, `review:<category>`), so a reader can tell a counted fact from a model's reading.
- Positive: the producer and grader split holds for remedies drafted from transcripts.
- Negative: model-only categories (`prompt_misread`, `judge_shallow`) reach issues only via a proposal or a person.

## Assumptions

| Id | Assumption | Where it binds |
|---|---|---|
| A1 | A model-free finding on the same unit and run is a fair corroboration for a review category, even when the two describe the problem differently | SRV-B22, SRV-B7 |
| A2 | The author of a dev-mode workflow reads the local report; nothing has to be filed for the signal to be used | SRV-B23 |

## Revisit when

A gold set of reviewed sessions exists and the reviewer can be scored like a judge ([JCL](../specs/judge-calibration.spec.md)).
