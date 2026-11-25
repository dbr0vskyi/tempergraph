# Missed slots catch up the latest one; a live or paused run skips the next slot; a slot runs at most once

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

A laptop sleeps or is off when a slot passes. A scheduled run may still be running, or paused waiting for a person, when the next slot comes. Two ticks may race. Each OS scheduler has its own catch-up rule and none knows the engine's runs ([research `scheduling-runs-prior-art-and-gaps`](../research/scheduling-runs-prior-art-and-gaps.rsrch.md) F12 to F16). A slot that fires only when no attempt is live never starts a run twice. A paused run holds a branch or worktree; starting another every day piles them up (F23).

## Decision

We will decide missed and overlapping slots in the engine, the same on every platform ([SCH-B21 to SCH-B25](../specs/schedules.spec.md)):

- **Catch-up `latest`** by default: after a gap, fire only the most recent passed slot within a window (one period, at most 24 hours); record the older ones `missed`. `none` and `all` (at most 3 per tick) are options. A missed `once` becomes an attention item.
- **Overlap `skip`** by default: a slot that comes due while the schedule has a live run is `skipped`; a **paused run counts as live**. `queue` and `parallel` (worktree only, `max_live` ≤ 4) are options. After three skips behind one pause, the pause is marked as blocking the schedule.
- **Slot identity**: the thread id carries the slot, so a second start of the same slot is refused by the engine's fresh-run rule (DUR-B1); the tick lock serializes ticks.
- **Failures pause the schedule** after three in a row; the schedule never retries a slot itself.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Latest catch-up, skip on live, slot identity (chosen) | One fire after a gap; no pile-up of paused runs; no double start | A person away for a week misses a week of slots |
| Catch up every missed slot | Nothing lost | A week off starts seven runs at once, with seven caps of spend |
| Follow each OS scheduler's own rule | No engine logic | Three behaviours; none sees live or paused runs |
| Start regardless of live runs | Simple | Paused runs and branches pile up; spend multiplies while nobody answers |

## Decision rationale

| Criterion | Chosen | All | OS rule | Regardless |
|---|---|---|---|---|
| Bounded burst after a gap | yes | no | partly | no |
| No pile-up behind a pause | yes | no | no | no |
| Same on every platform | yes | yes | no | yes |
| A slot never runs twice | yes | yes | no | no |

## Consequences

- Positive: an unattended schedule can at most leave one run waiting for a person; the person sees why later slots did not run.
- Negative: a daily report misses the days a person sat on a pause. Mitigation: `queue` for workflows where every period counts; `{fire.previous_slot}` lets the next run cover the gap.
- Risk: a long-lived paused run blocks a schedule for weeks. Mitigation: the `blocking_schedule` mark in `attention` and the audit's unbounded-wait rule ([ARC](../specs/audit-rule-catalog.spec.md)).

## Assumptions

- Three failures in a row is the default pause point.
