# ADR-0109 Author backwards from the good outcome, from any of three entry paths, preferring verifications the person already has

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Authoring commonly starts from a process the person runs. The owner names three starts: an existing solution, references or sources, or a conversation from scratch, and asks authoring to focus on the good outcome and on finding or creating verifiable outcomes, intermediate ones included. Backward design fixes evidence before activities ([R-105](../research/R-105-workflow-packages-authoring-and-good-outcomes.rsrch.md) B1); deterministic assertions are preferred where they express the requirement (B4).

## Decision

We will run one interview after intake, whatever the entry path: final outcome first, then intermediate outcomes found by asking what must be true before each deliverable, then a verification for every criterion in a fixed search order (an existing verification from the inventory, a created deterministic check, a split, a judge, a person, then `none` with a reason), then the steps' work. The entry paths differ only in where the first drafts come from; the chat path uses graded drafts. Model-free verbs inventory sources and check drafts; the skill leads. Details: [AUT](../specs/89-workflow-authoring.spec.md).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Outcome first, backwards, fixed search order (chosen) | Steps exist because an outcome needs them; existing verifications are reused; gaps are explicit | The person answers outcome questions before seeing steps |
| Process first: the process, then steps, then criteria per step | Familiar to people with a runbook | Criteria fitted to steps; no run-level bar; nothing for the chat path |
| Generate the workflow from a description, then ask for criteria | Fast first draft | Criteria rationalize what was generated |

## Decision rationale

| Criterion | Backwards | Process first | Generate first |
|---|---|---|---|
| Works for all three entry paths | yes | solution only | yes |
| Reuses the person's verifications | by rule | by chance | by chance |
| Unverifiable criteria surfaced | yes | partly | no |

## Consequences

- Positive: a non-expert's workflow starts with a bar they stated and the tests they already trust.
- Negative: a longer first phase for people who think in steps. Mitigation: the solution path drafts the outcome from the steps' outputs.
- Risk: the inventory misses a verification. Mitigation: the skill asks "what does a reviewer check first" for every final criterion.

## Assumptions

- The person's own Claude Code session hosts the skill; the verbs are host-neutral.
