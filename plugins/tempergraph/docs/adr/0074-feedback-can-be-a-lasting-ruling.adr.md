# ADR-0074 A person's feedback can be a lasting ruling that later steps and their judges are shown

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Feedback today reaches the retried step and its judge once ([HUM-B12](../specs/07-gate-and-human.spec.md)). temperspec treats a person's feedback as a ruling copied into the next artifact and shown to the judge, but nothing verifies that an earlier ruling reaches every later judge, so a run can spend attempts and human retries on a gap a person has already ruled on. Feedback is also refused on `proceed` and on an unfinished thread ([R-070](../research/R-070-config-overrides-and-reruns-gaps.rsrch.md) F18, F19).

## Decision

We will accept feedback on every resume that a person decides, and on `rerun`, and let a person mark it as a **ruling** with `--ruling`. A ruling is engine state: it is rendered to every attempt of the units it applies to (by default the unit it was given at and every later unit), shown to each of their judges as direction that wins over a reference with one engine blocker that the output follows it, kept across retries, trips back, rewinds and reruns, and ended only by a person's revocation ([RRN §2.2](../specs/81-reruns-and-feedback.spec.md)). One-time feedback keeps today's behaviour.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Opt-in rulings in state (chosen) | Reaches every later judge by construction; bounded and revocable | Prompts grow with each ruling; limits needed |
| Every feedback lasts | Simple | A one-off hint ("rename the flag") would bind every later unit |
| Rely on the step to copy the ruling into its artifact (temperspec today) | No engine change | Not verified to reach later judges; depends on a model's copy |

## Decision rationale

| Criterion | Rulings | All lasting | Step copies |
|---|---|---|---|
| Later judges see it | yes | yes | not verified |
| One-off hints stay one-off | yes | no | yes |
| Bounded prompt growth | yes (10, 16 000 chars) | no | yes |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | A ruling the work cannot satisfy is a conflict for a person, so a `no_change` blocker against it escalates rather than retries. | RRN §2.2 |

## Consequences

- Positive: a person's decision is not re-litigated by the next attempt or the next judge.
- Negative: PRM and JDG each gain one section.
- Risk: a stale ruling misleads later units. Mitigation: the run detail lists active rulings with their age, and revocation is one flag.
