# A scheduled fire is an attested `scheduler` caller; unattended spend needs a cap; pauses stay with a person

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Caller provenance ([PRV](../specs/caller-provenance.spec.md)) has kinds person, agent, orchestrator, pipeline, engine and unknown, and files "a cron job" under pipeline. A run the engine's own tick starts would then look like any cron job, hiding the schedule and the person who made it; filing it under `engine` would hide the schedule too ([research `scheduling-runs-prior-art-and-gaps`](../research/scheduling-runs-prior-art-and-gaps.rsrch.md) F8). A scheduled run spends with nobody watching, and the run cost cap is optional (F22). The design keeps every pause with a person and reserves an unattended mode (F9).

## Decision

We will:

1. Add caller kind **`scheduler`**, confidence `attested` by a per-schedule fire token whose digest the entry keeps (signal S1 of PRV, extended), with a `schedule` block naming the schedule, fire, slot and the creator's kind and decider. A pipeline export stays `pipeline` with a declared schedule tie.
2. Let only a **person decider** create, edit, resume or fire a schedule (a person at a terminal, or an agent relay with a recent person turn); lowering verbs (pause, skip, remove) are open to any known caller.
3. Require a **run cost cap** on every schedule and offer a **period budget**; an unmeasured fire counts at its cap.
4. Refuse **widening grants** in a schedule, as in settings files.
5. Keep **every pause with a person**: a scheduled run that pauses waits, is listed in `attention`, fires the `paused` hook, and skips the schedule's next slots under `overlap: skip`.
6. Count a fire as **no supervision touch**; the person's setup counts once per schedule.
7. Record **every scheduled run on the machine in one ledger** in the home store, whatever folder the schedule was made in, kept when the schedule, the repository or its state root goes away ([TCK-B23, TCK-B24](../specs/schedule-ticks-and-unattended-fires.spec.md)), so unattended work can always be checked later.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| New attested `scheduler` kind (chosen) | Reports tell scheduled runs and their creators apart; supervision stays honest | One more kind for every reader |
| Reuse `pipeline` | No new kind | Hides the schedule; a person's schedule looks like CI |
| Reuse `engine` | No new kind | `engine` means the engine on its own account; a schedule is a person's standing instruction |
| Let scheduled runs answer verification pauses | More autonomy | Needs the delegation policy that does not exist; breaks C6 |

## Decision rationale

| Criterion | `scheduler` | `pipeline` | `engine` |
|---|---|---|---|
| The schedule is visible in every record | yes | no | no |
| The person behind it is recorded | yes | no | no |
| Cannot be declared by a caller | yes | no | yes |

## Consequences

- Positive: `report --by schedule`, supervision levels and promotion criteria see scheduled runs as what they are: designed once, run unattended, answered by a person when needed.
- Negative: readers of the `caller` block gain a kind. Mitigation: tolerant readers (C12); `scheduler` sorts with `orchestrator` as an attested machine caller.
- Risk: a token leak lets a same-user process pose as the scheduler. Mitigation: provenance is accounting, not a security boundary (PRV); the entry is owner-only.

## Revisit when

A delegation policy exists, so a scheduled run's verification pauses could be answered on engine-checked evidence.
