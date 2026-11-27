# Schedule timing formats

## Purpose

The exact formats a schedule's timing is given in, `--at`, `--rrule`, `--every` and `--cron` with `--tz`, `--starts`, `--until` and `--count`, how each becomes the stored rule of [SCH-B18](schedules.spec.md) with no model and no question, and which values are refused. Split from [SCH](schedules.spec.md) to keep it under the spec budget; the behaviours keep their SCH ids. The word grammar, the canonical form, the echo, zones and every `schedule` verb stay in SCH. The parser of `schedule parse`, `add` and `edit` depends on it; design notes and assumptions are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md) F50.

## Depends on

- `overview.spec.md`: read-only verbs call no model (OVR-B15)

## Behaviours

### SCH-B15 Exact formats

WHEN timing is given by `--at`, `--rrule`, `--every` or `--cron`, with `--tz` (IANA), `--starts`, `--until` and `--count`, THE engine SHALL parse it with no model (OVR-B15) and never interpret it, so it never produces a `needs`.

- GIVEN `--at 2026-12-01T08:00`, `--every PT2H` or `--cron "0 8 * * 1-5"` with `--yes` from a script WHEN added THEN none exits 3

### SCH-B34 What each exact format means

WHEN an exact format is parsed THE engine SHALL read `--at` as an ISO 8601 local time, or one with an offset or `Z`, giving a `once`; `--rrule` as an RFC 5545 RECUR of the stored subset with `--starts` as DTSTART; `--every` as an ISO 8601 duration of at least `PT15M` from `--starts`, default now, giving an interval; and `--cron` as five fields read in the schedule's zone (SCH-B29); the last three each giving a `recur`.

- GIVEN `--every PT2H` with no `--starts` WHEN parsed THEN the rule recurs every two hours from now
- GIVEN `--at 2026-12-01T08:00Z` WHEN parsed THEN the schedule is a `once` at that instant

### SCH-B35 Exact-format refusals

WHEN an exact format cannot be stored THE engine SHALL refuse it with its reason: `when_malformed` naming the format for a malformed value, `rule_unsupported` for a recurrence the stored rule cannot hold (SCH-B30, SCH-B31), `interval_too_short` for slots under 15 minutes apart (SCH-B32), `when_in_past` for a time in the past, `when_too_far` for no slot within 400 days, and `zone_unknown` for an unknown zone or a gap the rule cannot leave.

- GIVEN `--at 2020-01-01T08:00` WHEN added THEN it exits 2 `when_in_past` and writes nothing
- GIVEN `--tz Mars/Olympus` WHEN parsed THEN it exits 2 `zone_unknown`

### SCH-B19 Exact formats never ask

WHEN a schedule is added with an exact format and `--yes` from a script with no terminal THE engine SHALL save it with exit 0 and give the same echo as its word-grammar twin.

- GIVEN `schedule add digest "daily digest" --rrule "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=0" --tz Europe/Warsaw --run-cost-cap 3 --yes` WHEN it runs THEN it is saved with exit 0 and the echo equals that of `every weekday at 8:00`

### SCH-B29 Cron maps onto the stored rule

WHEN `--cron` gives five fields (minute, hour, day of month, month, day of week) THE engine SHALL store, with no `INTERVAL`, the one rule that fires at the local times the fields name in the schedule's zone: `FREQ=HOURLY` when the hour is `*`, otherwise `FREQ=DAILY`, `FREQ=WEEKLY` when only the day of week is restricted, or `FREQ=MONTHLY` when only the day of month is restricted, with `BYDAY` or `BYMONTHDAY` for that restriction, `BYHOUR` unless the hour is `*`, and `BYMINUTE`.

- GIVEN `schedule parse --cron "0 8 * * 1-5" --tz Europe/Warsaw` WHEN run THEN the echo's rule is `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=0`, the rule of `every weekday at 8:00`
- GIVEN `--cron "0 9 1,15 * *"` WHEN parsed THEN the rule is `FREQ=MONTHLY;BYMONTHDAY=1,15;BYHOUR=9;BYMINUTE=0`
- GIVEN `--cron "30 * * * mon-fri"` WHEN parsed THEN the rule is `FREQ=HOURLY;BYDAY=MO,TU,WE,TH,FR;BYMINUTE=30`

### SCH-B36 Cron field forms

WHEN a `--cron` field is read THE engine SHALL take it as the ascending list of the values it names, from a `*`, a number, a range `a-b`, a step `*/n` or `a-b/n`, or a comma-separated list of these, with month and weekday names (`jan` to `dec`, `mon` to `sun`, any case) and `7` as Sunday, a field that names every value counting as `*`.

- GIVEN `--cron "*/15 9-17 * * *"` WHEN parsed THEN the rule is `FREQ=DAILY;BYHOUR=9,10,11,12,13,14,15,16,17;BYMINUTE=0,15,30,45`
- GIVEN `--cron "0 9 * * 7"` WHEN parsed THEN the rule is `FREQ=WEEKLY;BYDAY=SU;BYHOUR=9;BYMINUTE=0`

### SCH-B30 Cron the stored rule cannot hold is refused

WHEN `--cron` is not five fields of the forms SCH-B29 accepts, restricts the month, or restricts both the day of month and the day of week THE engine SHALL exit 2 and save nothing, with `when_malformed` naming `cron` for a value outside those forms (a macro such as `@daily`, a seconds or year field, `?`, `L`, `W` or `#`, a number out of range, a range written backwards) and `rule_unsupported` naming the field for a month restriction or for both day fields restricted.

- GIVEN `--cron "0 9 * 6 *"` WHEN added THEN it exits 2 `rule_unsupported` naming the month field
- GIVEN `--cron "0 9 1 * 1"` WHEN added THEN it exits 2 `rule_unsupported` naming the day of month and the day of week
- GIVEN `--cron "@daily"` or `--cron "0 9 * *"` WHEN added THEN it exits 2 `when_malformed` naming `cron`
- GIVEN `--cron "0 9 1-31 1-12 0-7"` WHEN added THEN it is accepted as the rule of `daily at 09:00`

### SCH-B31 A recurrence outside the stored subset is refused

WHEN `--rrule` carries a part or value that the stored subset of SCH-B18 leaves out THE engine SHALL exit 2 `rule_unsupported` naming the part and save nothing, the parts left out being a `FREQ` other than `MINUTELY`, `HOURLY`, `DAILY`, `WEEKLY` or `MONTHLY`, `BYMONTH`, `BYSETPOS`, `BYWEEKNO`, `BYYEARDAY`, `BYSECOND`, `WKST`, a `BYDAY` ordinal outside `MONTHLY`, a `BYMONTHDAY` other than 1 to 31 or −1, and a `DTSTART`, `RDATE` or `EXDATE` line.

- GIVEN `--rrule "FREQ=YEARLY;BYMONTH=6;BYMONTHDAY=1"` WHEN added THEN it exits 2 `rule_unsupported` naming `FREQ=YEARLY`
- GIVEN `--rrule "FREQ=MONTHLY;BYDAY=MO;BYSETPOS=1"` WHEN added THEN it exits 2 `rule_unsupported` naming `BYSETPOS`
- GIVEN `--rrule "FREQ=WEEKLY;BYDAY=1MO"` WHEN added THEN it exits 2 `rule_unsupported` naming the ordinal on `BYDAY`
- GIVEN `--rrule "FREQ=MONTHLY;BYDAY=1MO;BYHOUR=9;BYMINUTE=0"` WHEN added THEN it is accepted

### SCH-B32 Slots under fifteen minutes apart are refused

WHEN an exact format gives consecutive slots less than 15 minutes apart on the local clock (`--every` under `PT15M`, or an `--rrule` or `--cron` whose times fall closer) THE engine SHALL exit 2 `interval_too_short` naming the shortest gap and save nothing.

- GIVEN `--every PT10M` WHEN added THEN it exits 2 `interval_too_short`
- GIVEN `--cron "*/10 * * * *"` or `--rrule "FREQ=DAILY;BYHOUR=9;BYMINUTE=0,10"` WHEN added THEN it exits 2 `interval_too_short`
- GIVEN `--rrule "FREQ=MINUTELY;INTERVAL=10"` WHEN added THEN it exits 2 `interval_too_short`
- GIVEN `--every PT15M` WHEN added THEN it is accepted

## Acceptance criteria

- SCH-AC3 (SCH-B19, SCH-B15, SCH-B34): No input given through `--at`, `--rrule`, `--every` or `--cron` exits 3 in a corpus of 1,000 valid values, and each equals the canonical form of its word-grammar twin where one exists
- SCH-AC9 (SCH-B29, SCH-B36): For a corpus of `--cron` values using every accepted form (lists, ranges, steps, month and weekday names, `7` for Sunday), the stored rule is the one SCH-B29 states, and its slots over two years in three zones equal those of a minute-by-minute match of the five fields against the local clock
- SCH-AC10 (SCH-B30, SCH-B31, SCH-B35): Every `--cron` value outside the accepted forms exits 2 `when_malformed`, every `--cron` value that restricts the month or both day fields and every `--rrule` value outside the stored subset exits 2 `rule_unsupported`, and none of them writes anything
- SCH-AC11 (SCH-B32, SCH-B15, SCH-B35): `--every PT14M`, an `--rrule` or `--cron` with slots 14 minutes apart and `--rrule "FREQ=MINUTELY;INTERVAL=10"` exit 2 `interval_too_short` and write nothing, and the same inputs at 15 minutes are accepted

## Open questions

- None. Owner: engine owner.
