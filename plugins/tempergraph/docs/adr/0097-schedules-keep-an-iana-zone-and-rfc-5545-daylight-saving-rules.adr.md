# ADR-0097 Schedules keep an IANA zone; calendar rules follow wall time, intervals follow elapsed time, by RFC 5545

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

"Every day at 9" means 09:00 on the person's clock in winter and in summer. "Every 2 hours" means every 7,200 seconds. Twice a year local times skip an hour or repeat one. A laptop moves between zones. The rules must be the ones a standard library computes, so the engine, the monitor and a test agree ([R-095](../research/R-095-scheduling-runs-prior-art-and-gaps.rsrch.md) F24, F25, F27).

## Decision

We will store one **IANA zone** per schedule (the machine's zone at creation unless `--tz` says otherwise, named as assumed in the echo) and compute slots in it, then store them as UTC. Calendar recurrences follow **wall time**; interval recurrences follow **elapsed time**. A local time in a gap takes the offset from before the gap (02:30 becomes 03:30); a time that occurs twice fires once, at its first occurrence, as RFC 5545 and `zoneinfo` define. Abbreviations such as `CET` are refused. A machine zone change moves no schedule; `list` marks the difference. Spec: [SCH §2.4](../specs/83-schedules.spec.md).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Stored IANA zone, RFC 5545 rules (chosen) | Standard; matches people's clocks; testable against `dateutil.rrule` | A travelling person's schedules stay in the old zone until edited |
| Always UTC | Simple; no gaps or overlaps | "At 9" moves by an hour twice a year |
| Follow the machine's current zone | Follows a travelling laptop | A trip silently moves every schedule; a team machine's zone change moves everyone's |
| Fixed UTC offset | Simple | Same as UTC for daylight saving |

## Decision rationale

| Criterion | IANA zone | UTC | Machine zone | Offset |
|---|---|---|---|---|
| "At 9" stays at 9 all year | yes | no | yes | no |
| A zone change never moves a schedule silently | yes | yes | no | yes |
| Standard rules for gaps and overlaps | yes | n/a | yes | n/a |

## Consequences

- Positive: the echo shows exactly when each slot fires, in local and UTC time, across changes.
- Negative: the zone database must be current. Mitigation: `tzdata` pinned in the engine environment and refreshed by `update`; `next_slot` is recomputed at every read.
- Risk: pipeline cron is UTC only. Mitigation: export refuses a rule with a moving offset unless the owner pins today's ([TCK §2.5](../specs/84-schedule-ticks-and-unattended-fires.spec.md)).
