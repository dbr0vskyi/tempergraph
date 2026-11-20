---
title: Schedules
type: component
status: review
prefix: SCH
adrs: [0095, 0096, 0097, 0098, 0099]
---

# Schedules

## 1. Overview

A **schedule** starts a registered workflow, or a saved orchestration, once or on a recurrence, given in an **exact format** (ISO 8601, an RFC 5545 rule, cron) or, optionally, in **words** ("tomorrow at 9", "every weekday at 8:00", "every month on the last day at 17:00"). Both paths are deterministic and model-free; the words are a convenience on top of the exact formats, never a requirement. This spec owns the `schedule` verbs, the exact formats, the word grammar, how either becomes one canonical form that is echoed back before anything is saved, time zones and daylight saving, the schedule entry and its fire log, and the policies for missed fires, overlapping runs, failures and spend.

What fires a schedule is the **tick**: an OS-agnostic, model-free engine routine that reads the schedules, decides what is due and starts each due run through the engine's own `run` verb. The engine's portable loop calls it on every OS the engine runs on; an OS scheduler, a pipeline or any other scheduler may call it too, as optional adapters ([TCK](84-schedule-ticks-and-unattended-fires.spec.md), [ADR-0095](../adr/0095-a-model-free-tick-behind-os-agnostic-triggers.adr.md)). The tick, like the orchestration supervisor, calls no model and answers no gate (contract C18).

A scheduled run is an ordinary run: it is preflighted, capped, logged and costed like any other, it pauses for a person like any other, and every pause stays with a person ([ADR-0099](../adr/0099-a-scheduled-fire-is-an-attested-caller-with-a-capped-unattended-spend.adr.md)). What a schedule adds is who started it (caller kind `scheduler`, [PRV](85-caller-provenance.spec.md)), which slot it served, and the rules that keep a recurring schedule from piling up paused runs or spend.

## 2. Contract

### 2.1 Concepts

| Concept | Definition |
|---|---|
| Schedule | One entry file plus its fire log, under `~/.tempergraph/schedules/<schedule_id>/` (home store, [LOS §2.2](33-local-observability-store.spec.md)). Per user and per machine. |
| `schedule_id` | `<name>-<4 hex>`; the name is a slug given with `--name` or made from the workflow name. Unique on the machine; `schedule` verbs accept the name alone when it is unique. |
| Target | What a fire starts: `workflow` (a run), `orchestration` (an `orchestrate start` of a saved `*.orch.json`), or `program` (a declared program of a workflow package, reserved, §5). |
| When | The canonical timing: a `once` instant, or a `recur` rule, each in a named zone (§2.3, §2.4). |
| Slot | One due time the When produces, as a UTC instant plus its local wall time. |
| Fire | The tick's handling of one slot: started, skipped, missed or refused. One slot has at most one fire. |
| Live run | A fire's run or orchestration whose thread state is `running` or `paused` (or, for an orchestration, any state but an ended one). |
| Tick | One `schedule tick` call (§2.7, [TCK §2.2](84-schedule-ticks-and-unattended-fires.spec.md)). |

### 2.2 Schedule entry (schema version 1)

JSON, owner-only (mode 0600), written atomically. Values are constants, checked numbers or names, or scrubbed strings; the request reaches a run only through a hand-off ticket ([SEC §2.1](14-security.spec.md)).

| Field | Kind | Meaning |
|---|---|---|
| `schema_version` | int | `1` |
| `schedule_id`, `name`, `description` | id, slug, text ≤ 200 | |
| `state` | `active` \| `paused` \| `done` \| `removed` | `done` after a `once` fired or a `recur` passed its end |
| `target` | `{kind, workflow, repo, request, inputs}` or `{kind, orchestration_file, repo, args}` | `repo` is the absolute path of the main checkout whose state root the run uses ([WSP](13-workspace-and-concurrency.spec.md)); `request` and `inputs` may use the fire keys of §2.6 |
| `when` | `{input, phrase, kind: once\|recur, at \| rule, zone, starts, ends, count}` | `input` names the option used (§2.3); `phrase` is what the person typed with `--when`, else null; `at` an ISO 8601 local date-time; `rule` an RFC 5545 RECUR string from the subset of §2.3.3; `zone` an IANA name |
| `options` | map `SettingKey` → value, plus `profiles` | Any key of the settings catalog, applied on the `flag` layer with `via: schedule` ([RST §2.3](80-run-settings-and-overrides.spec.md)); no widening key (§2.5.5) |
| `run_cost_cap_usd` | float > 0 | Required (§2.5.4); written as `run.run_cost_cap_usd` on every fire |
| `budget` | `{period: day\|week\|month, cap_usd}`, optional | Cap on the summed cost of this schedule's fires in a calendar period of the schedule's zone |
| `catch_up`, `catch_up_window_s` | `latest` (default) \| `none` \| `all`; window in seconds | §2.5.1 |
| `overlap` | `skip` (default) \| `queue` \| `parallel` | §2.5.2 |
| `max_live` | int 1–4, default 1 | Live runs allowed at once under `parallel` |
| `pause_after_failures` | int 1–10, default 3 | §2.5.3 |
| `executors_checked` | list of `{executor, credential_kind, checked_at}` | From the creation preflight ([TCK §2.4](84-schedule-ticks-and-unattended-fires.spec.md)) |
| `created`, `edited` | `{at, caller, from}` | Who added or last edited it ([PRV §2.5](85-caller-provenance.spec.md)); `from` is the folder and repository the verb ran in |
| `token_digest` | hex | SHA-256 of the schedule's fire token ([TCK §2.3](84-schedule-ticks-and-unattended-fires.spec.md)) |
| `next_slot`, `last_fire` | UTC instant, fire summary | Derived; readers trust the fire log over them |

### 2.3 When: exact formats and words

Timing is given in exactly one of two ways, both parsed by the engine with no model (contract C13) ([ADR-0096](../adr/0096-exact-formats-first-and-an-optional-word-grammar-echoed-back.adr.md)):

| Option | Format | Example | Becomes |
|---|---|---|---|
| `--at` | ISO 8601 local date-time, or with an offset or `Z` | `2026-12-01T08:00`, `2026-12-01T08:00+01:00` | `once` |
| `--rrule` | RFC 5545 RECUR of the subset in §2.3.4, with `--starts` (DTSTART) | `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=0` | `recur` |
| `--every` | ISO 8601 duration, ≥ `PT15M`, from `--starts` (default now) | `PT2H`, `P1D`, `P1W` | `recur` (interval) |
| `--cron` | Five-field cron, read in the schedule's zone | `0 8 * * 1-5` | `recur` |
| `--tz`, `--starts`, `--until`, `--count` | IANA zone; ISO 8601 date-times; integer | `Europe/Warsaw` | zone and bounds |
| `--when` | A phrase of the word grammar (§2.3.2, §2.3.3) | `every weekday at 8:00` | either |

The **exact formats are the deterministic path**: they are never interpreted, so they never produce a `needs`; the only refusals are a malformed value, a time in the past, a gap the rule cannot leave, or an unknown zone. Scripts, pipelines, workflow packages and the skill use them; a person may too. The word grammar is an optional layer for people: English, case-insensitive, extra spaces and a trailing period ignored; a phrase that matches no rule is refused with the nearest rules shown, and a phrase with more than one reading is a `needs` (§2.3.5). Every path ends in the same canonical form and the same echo (§2.3.4).

#### 2.3.2 Parts of the word grammar

| Part | Accepted forms |
|---|---|
| Time | `9am`, `9:30pm`, `09:00`, `21:30`, `noon`, `midnight`; `HH:MM` is 24-hour; a bare hour `9` or `at 9` is ambiguous unless 0 or 13–23 (§2.3.4) |
| Day | `today`, `tomorrow`, `monday` … `sunday` (also `mon` … `sun`), `next <weekday>`, `this <weekday>` |
| Date | ISO `2026-12-01`; `dec 1`, `1 dec`, `december 1st`, with an optional year; numeric `01/12` and `12/01` are refused as ambiguous unless ISO |
| Offset | `in <n> minutes\|hours\|days\|weeks`, `in an hour`, `in half an hour` |
| Instant | ISO 8601 with an offset or `Z`, e.g. `2026-12-01T08:00+01:00` |
| Zone | `--tz <IANA name>` or a trailing ` in <IANA name>`; `UTC` accepted; abbreviations such as `EST` or `CET` are refused (they name no rules) |
| Bounds | `from <date>`, `until <date>`, `for <n> times` |

#### 2.3.3 Phrases (optional words)

| Kind | Phrase | Canonical form |
|---|---|---|
| once | `in 2 hours` | `at` = now + 2 h, as local time in the zone |
| once | `tomorrow at 9am` | `at` = tomorrow 09:00 |
| once | `at 18:00` | today 18:00 if in the future, else a `needs`: tomorrow 18:00 or refuse |
| once | `next monday at 10:00` | the Monday of next week (never this week's) |
| once | `on dec 1 at 08:00`, `2026-12-01 08:00` | that date; a past month-day without a year means next year |
| recur | `every day at 9am`, `daily at 09:00` | `FREQ=DAILY;BYHOUR=9;BYMINUTE=0` |
| recur | `every weekday at 8:00` | `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=0` |
| recur | `every monday`, `every monday and thursday at 7pm` | `FREQ=WEEKLY;BYDAY=MO`, time from the default (§2.3.5) when none is given |
| recur | `every 2 weeks on friday at 16:00` | `FREQ=WEEKLY;INTERVAL=2;BYDAY=FR;…` |
| recur | `every month on the 1st at 9am` | `FREQ=MONTHLY;BYMONTHDAY=1;…` |
| recur | `every month on the last day at 17:00` | `FREQ=MONTHLY;BYMONTHDAY=-1;…` |
| recur | `every first monday of the month at 9am` | `FREQ=MONTHLY;BYDAY=1MO;…`; `last friday` gives `-1FR` |
| recur | `every 2 hours`, `every 30 minutes`, `hourly` | interval rule, elapsed time from `starts` (§2.4) |
| recur | `every 2 hours between 9am and 5pm on weekdays` | `FREQ=HOURLY;INTERVAL=2;BYHOUR=9,11,13,15,17;BYDAY=MO,…,FR` |
| recur | any of the above with `from …`, `until …` or `for 5 times` | `starts`, `UNTIL`, `COUNT` |

Limits: intervals ≥ 15 minutes (`interval_too_short`); a slot within 400 days; 64 schedules per machine.

#### 2.3.4 Canonical form and echo

`once`: `{at: "2026-11-21T09:00", zone: "Europe/Warsaw"}`. `recur`: an RFC 5545 RECUR string limited to `FREQ` (`MINUTELY` only with `INTERVAL` ≥ 15, `HOURLY`, `DAILY`, `WEEKLY`, `MONTHLY`), `INTERVAL`, `BYDAY` (with ordinals for `MONTHLY`), `BYMONTHDAY` (1–31, −1), `BYHOUR`, `BYMINUTE`, `COUNT`, `UNTIL`, plus `starts` (DTSTART) and `zone`. Nothing else is stored, so every reader computes the same slots with a standard library.

The **echo** of any When, exact or in words, is: the canonical form, a sentence the engine renders from it (never from the phrase), the zone with its current UTC offset, the next three slots (or the one slot) in local and UTC time, and each assumption made (§2.3.5). It is the output of `schedule parse` and the confirmation of `add` and `edit`.

```text
"every weekday at 8:00" in Europe/Warsaw (UTC+01:00 now)
  → At 08:00, Monday to Friday.  RRULE FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=0
  next: Fri 2026-11-20 08:00 (07:00 UTC) · Mon 2026-11-23 08:00 · Tue 2026-11-24 08:00
  assumed: zone from this machine
```

#### 2.3.5 Ambiguity and defaults (words only)

| Input | Rule |
|---|---|
| A bare hour 1–12 with no `am`, `pm` or `:MM` | `needs`: `09:00` or `21:00`; `HH:MM` is never ambiguous |
| A recurrence with no time | `needs` with `09:00` offered (the assumed default); the default is never applied silently |
| `at <time>` with no day, time passed today | `needs`: tomorrow, or refuse |
| Numeric dates other than ISO | refused `date_ambiguous`, naming the ISO form |
| `every month on the 29th`, `30th`, `31st` | `needs`: skip short months, or use the last day |
| No `--tz` and no ` in <zone>` | the machine's zone, named in the echo as assumed |
| A local time inside a daylight-saving gap or overlap on a listed slot | shown in the echo with the rule of §2.4 |

A `needs` exits 3 with the readings as choices, the same status shape as `run --check` ([CLI-B1](17-engine-cli.spec.md)); the caller re-sends the phrase with the reading made explicit, or passes `--choose <n>`. `add` never saves a phrase with an open `needs`.

### 2.4 Time zones and daylight saving

| Rule | Behaviour |
|---|---|
| Zone | Every schedule stores one IANA zone; slots are computed in it, then stored as UTC. A machine zone change moves no schedule; `list` marks a zone that differs from the machine's |
| Calendar rules | Wall-clock: `every day at 9am` fires at 09:00 local on both sides of a change |
| Interval rules | Elapsed time: `every 2 hours` fires every 7,200 s of UTC, so its local times shift by an hour across a change |
| Gap (a local time that does not exist) | The slot is taken with the offset from before the gap: 02:30 on a spring-forward day becomes 03:30 (RFC 5545 §3.3.5) |
| Overlap (a local time that occurs twice) | The slot fires once, at the first occurrence (`fold=0`) |
| Zone data | From the engine's interpreter (`zoneinfo` with the `tzdata` package pinned in the engine environment); `schedule list` recomputes `next_slot` from current zone data at every call |

### 2.5 Policies

#### 2.5.1 Missed slots

A slot is **missed** when no tick ran between it and `slot + catch_up_window_s`, for example because the machine was off or asleep ([TCK-B3](84-schedule-ticks-and-unattended-fires.spec.md)).

| `catch_up` | When a tick finds slots passed since the last fire |
|---|---|
| `latest` (default) | Fire only the most recent passed slot, if it is within the window; the older ones are recorded `missed` |
| `none` | Record every passed slot `missed`; wait for the next one |
| `all` | Fire each passed slot within the window in order, at most 3 per tick, subject to the overlap policy |

`catch_up_window_s` defaults to the recurrence's period capped at 24 hours (so an hourly schedule waits up to 1 hour, a weekly one up to 24 hours) and to 24 hours for a `once`. A `once` whose slot is missed is an attention item `schedule_missed` with `schedule fire <id>` as its answer, since nobody would otherwise learn it did not run.

#### 2.5.2 Overlap

| `overlap` | A slot comes due while the schedule has a live run |
|---|---|
| `skip` (default) | Recorded `skipped` with reason `overlap`; nothing starts |
| `queue` | Held as one pending fire (a later slot replaces it); started by the first tick after the live run ends |
| `parallel` | Started while live runs < `max_live`; else as `skip`. Refused at `add` unless `run.workspace` resolves to `worktree` |

A **paused** run is live: a recurring schedule whose last run waits for a person does not start another one. After 3 slots skipped behind the same paused run, the pause's attention item is marked `blocking_schedule` with the count.

#### 2.5.3 Failures

A fire whose run ends with exit 4 or 5, or whose start is refused (exit 2), counts as a failure; exit 0 resets the count. After `pause_after_failures` failures in a row the schedule becomes `paused` with reason `failures`, an attention item `schedule_paused` lists the last failure's thread and cause, and the hook event `schedule_paused` fires ([CLI §2.2](17-engine-cli.spec.md)). The schedule never retries a slot on its own; an infra failure is left to the run's own policy.

#### 2.5.4 Spend

| Limit | Rule |
|---|---|
| Per run | `run_cost_cap_usd` is required at `add`: a schedule is unattended spend. A workflow-declared `run_cost_cap_usd` satisfies it; the flag value may only lower it |
| Per period | With `budget`, before each fire the tick sums the estimated cost of this schedule's fires in the current period from the stats rows ([OBS §2.4](15-observability-and-cost.spec.md)); if the sum plus the run cap would exceed `cap_usd`, the slot is `skipped` with reason `budget` and an attention item `schedule_budget` is raised once per period |
| Unmeasured | A fire whose cost is `incomplete` counts at its run cap, so an unmeasured run never makes the budget look unspent (C1) |

#### 2.5.5 Settings, inputs and grants

A schedule's `options` and `profiles` are validated at `add` and `edit` by `run --check` with the same function as a run's ([RST §4](80-run-settings-and-overrides.spec.md)), then re-resolved at each fire, since the file layers may have changed. They are recorded with `via: schedule`. A key that widens tools, commands or judge views is refused at `add` (`widening_in_schedule`), as in a settings file: a grant is a person's decision for one run, and a fire is nobody's decision ([ADR-0080](../adr/0080-a-person-may-grant-a-step-tools-for-a-run.adr.md)). A workflow's own profile still widens. A scheduled run resolves `run.workspace` like any run; under the default `auto`, a workflow that writes files gets its own worktree ([WTR §2.2](82-worktree-mode.spec.md)), so a fire never writes into the checkout a person is working in; worktree settings ride along like any other key.

### 2.6 Fire identity and keys

| Item | Value |
|---|---|
| `fire_id` | `<schedule_id>@<slot as yyyymmddThhmmZ>`, or `@manual-<yyyymmddThhmmssZ>` for `schedule fire` |
| Thread id | `<workflow>/s-<schedule_id>-<slot as yyyymmddThhmm>`; a second start of the same slot finds the thread and is refused by DUR-B1, so a slot can never run twice |
| Orchestration id | `<name>-s<yyyymmddThhmm>-<4 hex>` from the fire id |
| Fire keys | `{fire.slot}` (local ISO date-time), `{fire.date}` (local ISO date), `{fire.previous_slot}` (the last slot that started a run, or empty), `{fire.schedule}` (the name); usable in `request`, `inputs` and orchestration `args`, rendered by the template grammar of [CON §2.2](01-contracts.spec.md) |
| Alias and label | No `--alias` (aliases are unique among live threads); label `schedule <name> <fire.date>` unless set |

### 2.7 Verbs

| Verb | Does | Writes | Spends |
|---|---|---|---|
| `schedule parse <when> [--count n] [--json]` | The echo of §2.3.4, or the `needs` or refusal; `<when>` is one of the options of §2.3 | no | no |
| `schedule add <workflow> <request…> <when> [--name n] [--choose n] [run options] [--run-cost-cap usd] [--budget <period>:<usd>] [--catch-up …] [--overlap …] [--max-live n] [--pause-after-failures n] [--check] [--yes]` | Parse, preflight with `run --check` and the credential check ([TCK §2.4](84-schedule-ticks-and-unattended-fires.spec.md)), print the echo, and save on `--yes` or an interactive yes; `--check` saves nothing | entry, fire log | no |
| `schedule add --orchestration <file> [--arg k=v…] <when>` | The same for a saved orchestration; validated with `orchestrate validate` | entry, fire log | no |
| `schedule list [--all] [--json]` | Every schedule on the machine, from any folder: name, target, sentence, zone, state, next slot, last fire, live runs, failures, period spend | no | no |
| `schedule show <id> [--json]` | Entry, echo, next ten slots, last 20 fires | no | no |
| `schedule history <id> [--since <date>] [--json]` | The fire log | no | no |
| `schedule edit <id> [<when>] [options as for add] [--yes]` | Change timing, options or policies; re-parsed, re-checked and echoed like `add`; the target workflow and repo cannot change (remove and add instead) | entry, fire log | no |
| `schedule pause <id> [--reason text]`, `schedule resume <id> [--catch-up]` | Stop or restart firing; slots passed while paused are `missed` unless `--catch-up` | entry, fire log | no |
| `schedule skip <id> [--next \| --until <date>]` | Skip slots, recorded `skipped` (reason `person`) | entry, fire log | no |
| `schedule fire <id> [--yes]` | One fire now, off-cycle, through the tick's path (no catch-up) | as a tick | yes |
| `schedule remove <id> [--yes]` | `state: removed`; history kept until `store prune`; live runs go on | entry, fire log | no |
| `schedule tick`, `schedule loop [--detach\|--stop]` | One tick, called by any trigger; the portable loop that ticks until stopped ([TCK §2.1](84-schedule-ticks-and-unattended-fires.spec.md)) | fire log, runs | yes |
| `schedule trigger install\|status\|remove`, `schedule export <id> --for <system>` | Optional trigger adapters and pipeline export ([TCK §2.1](84-schedule-ticks-and-unattended-fires.spec.md), [TCK §2.5](84-schedule-ticks-and-unattended-fires.spec.md)) | per TCK | no |

`add`, `edit`, `pause`, `resume`, `skip`, `fire` and `remove` are mutating verbs: each classifies its caller and records the `caller` block in the fire log ([PRV](85-caller-provenance.spec.md)). Exits per [CON §2.9](01-contracts.spec.md): 0, 2 refused, 3 `needs`. `schedule` is a reserved verb word ([CLI-B2](17-engine-cli.spec.md)).

### 2.8 Fire log

The fire log is append-only JSON lines in the schedule's folder, one per event, each with `seq`, `at` (UTC), `kind`, `slot`, `fire_id` and metadata only:

`created`, `edited` (changed fields), `paused` (reason `person`, `failures`), `resumed`, `due`, `started` (thread or orchestration id), `skipped` (reason `overlap`, `budget`, `person`, `paused`), `queued`, `missed`, `refused` (exit 2 reason, `credential` included), `ended` (exit, outcome, `cost` with `reported`, `estimated`, `incomplete`), `removed`. Each person-made event carries its `caller` block.

Every fire is also a row of the machine-wide scheduled-run ledger, readable from any folder with `schedule runs`; that and what a run leaves elsewhere are [TCK §2.7](84-schedule-ticks-and-unattended-fires.spec.md).

## 3. Behaviours

**SCH-B1 Echo before save.** Given `schedule add triage "open bugs" --when "every weekday at 8:00"` on a machine in `Europe/Warsaw`, when it runs in a terminal, then it prints the echo of §2.3.3 with the zone marked assumed and asks for a yes; with no terminal and no `--yes` it exits 3 with the echo as the `needs` and saves nothing.

**SCH-B1a Exact formats never ask.** Given `schedule add digest "daily digest" --rrule "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=0" --tz Europe/Warsaw --run-cost-cap 3 --yes` from a script with no terminal, when it runs, then it is saved with exit 0 and the same echo as the phrase `every weekday at 8:00`; `--at 2026-12-01T08:00`, `--every PT2H` and `--cron "0 8 * * 1-5"` likewise never exit 3.

**SCH-B2 Ambiguity in words is asked, not guessed.**

| Phrase | Result |
|---|---|
| `every day at 9` | exit 3: `09:00` or `21:00` |
| `every monday` | exit 3: no time given, `09:00` offered |
| `03/04 at 10:00` | exit 2 `date_ambiguous`, naming `2027-03-04` or `2027-04-03` |
| `every month on the 31st at 9am` | exit 3: skip short months, or last day |
| `every 5 minutes` | exit 2 `interval_too_short` |
| `next tuesday at 10:00` on a Monday | the Tuesday 8 days later, echoed with its date |

**SCH-B3 Daylight saving.** Given `every day at 02:30` in `Europe/Warsaw`, when the slots around 2027-03-28 (spring forward) and 2027-10-31 (fall back) are computed, then 2027-03-28's slot is 03:30 local (01:30 UTC), 2027-10-31's fires once at the first 02:30 (00:30 UTC), and the echo of `schedule show` names both.

**SCH-B5 Overlap skips behind a pause.** Given a daily schedule with `overlap: skip` whose Monday run paused at a gate, when the Tuesday, Wednesday and Thursday slots come due with the pause unanswered, then each is `skipped` with reason `overlap`, no run starts, and after Thursday the pause's attention item carries `blocking_schedule: 3`.

**SCH-B6 Missed slots after the machine was off.** Given `every day at 9am` with `catch_up: latest` and a machine off from Friday evening to Monday 10:00, when the first tick runs on Monday at 10:05, then Saturday's and Sunday's slots are `missed` (older than the 24-hour window) and Monday's 09:00 slot fires at that tick; given the machine back on Sunday 10:00 instead, Sunday's slot fires at that tick and Saturday's is `missed`.

**SCH-B7 A slot never runs twice.** Given two ticks that run at the same moment (the loop and an external cron), when both find the same due slot, then exactly one starts it: the tick lock serializes them ([TCK-B2](84-schedule-ticks-and-unattended-fires.spec.md)), and the slot's thread id makes any second start a DUR-B1 refusal.

**SCH-B8 Spend is capped.** Given `schedule add … --budget month:20 --run-cost-cap 4` and fires that cost 6.10, 5.80 and 4.30 this month, when the next slot comes due, then 16.20 + 4 > 20 so the slot is `skipped` with reason `budget`, one `schedule_budget` attention item is raised, and slots resume next month.

| Case | Result at `add` |
|---|---|
| No `--run-cost-cap` and the workflow declares none | exit 2 `cost_cap_required` |
| `--run-cost-cap 50` and the workflow declares 10 | the run cap stays 10 (a flag may only lower it here) and the echo says so |

**SCH-B9 Failures pause the schedule.** Given `pause_after_failures: 3`, when three fires in a row end with exit 5, then the schedule is `paused` with reason `failures`, the hook event `schedule_paused` fires, and `attention` lists it with the last thread and its cause; `schedule resume` restarts it and resets the count.

**SCH-B10 A grant cannot be scheduled.** Given `schedule add triage … --grant triage=mcp:tracker/get_issue`, when it is checked, then it exits 2 `widening_in_schedule` and saves nothing; the same grant given to one paused scheduled run by a person on `resume` is accepted ([RST §2.8](80-run-settings-and-overrides.spec.md)).

**SCH-B11 Fire keys.** Given `request: "daily digest for {fire.date}"` and the slot 2026-11-23 08:00, when it fires, then the run's request is `daily digest for 2026-11-23` and its label `schedule digest 2026-11-23`.

**SCH-B12 Edit keeps history.** Given an active schedule with 12 fires, when `schedule edit digest --when "every weekday at 7:30" --yes` runs, then the echo is shown, an `edited` event holds the old and new canonical forms and the caller, past fires are unchanged, and `next_slot` is recomputed from now.

## 4. Error conditions

| Condition | Result |
|---|---|
| Phrase matches no rule | Exit 2 `when_unparsed`, with the closest phrases of §2.3.3; a malformed exact value exits 2 `when_malformed` naming the format |
| `once` in the past, or no slot within 400 days | Exit 2 `when_in_past`, `when_too_far` |
| Unknown zone or abbreviation | Exit 2 `zone_unknown` |
| Workflow not registered, `repo` without a state root | Exit 2 at `add`; `refused` at a fire |
| `run --check` says `needs` or `error` at `add` | Exit 3 or 2 with its questions; nothing saved |
| No run cost cap | Exit 2 `cost_cap_required` |
| A widening key in `options` | Exit 2 `widening_in_schedule` |
| `--overlap parallel` without a worktree workspace | Exit 2 `parallel_needs_worktree` |
| Over 64 schedules | Exit 2 `too_many_schedules` |
| `edit` changing workflow, repo or target kind | Exit 2 `target_fixed` |
| Fire log write fails | Recorded on stderr; the fire goes on (C2) |

## 5. Design notes

- **One mechanism.** A person at a terminal, the schedule skill and a pipeline export produce the same entry; only the tick fires it ([ADR-0095](../adr/0095-a-model-free-tick-behind-os-agnostic-triggers.adr.md)).
- **A grammar, not a guesser**: a wrong reading on a recurrence repeats every period ([ADR-0096](../adr/0096-exact-formats-first-and-an-optional-word-grammar-echoed-back.adr.md)). Zones and daylight saving: [ADR-0097](../adr/0097-schedules-keep-an-iana-zone-and-rfc-5545-daylight-saving-rules.adr.md). Missed and overlapping slots: [ADR-0098](../adr/0098-missed-slots-catch-up-latest-and-a-live-run-skips-the-next.adr.md). Unattended spend and pauses: [ADR-0099](../adr/0099-a-scheduled-fire-is-an-attested-caller-with-a-capped-unattended-spend.adr.md).
- **Release slice.** Scheduling rests on unattended credentials, cost caps, `attention` and caller provenance, so it is recommended for the release after the first: `once` and calendar `recur` for workflow targets, `catch_up: latest|none`, `overlap: skip`, both caps, every verb but `export`, and the portable loop with the `host` adapter. Later: the `os` adapter, orchestration and program targets, `catch_up: all`, `overlap: queue|parallel`, `cron` input, pipeline export.
- **Assumptions** (owner unavailable): per-user, per-machine schedules; 15-minute minimum interval; 09:00 offered as the default time; English only; 64 schedules per machine; 3 failures before a pause; a catch-up window of one period capped at 24 hours.

## 6. Acceptance criteria

- [ ] SCH-AC-1 Every row of §2.3 and §2.3.3 and of SCH-B2 has a fixture giving its canonical form, echo sentence and next three slots for a fixed "now" and zone; the echo sentence is generated from the canonical form only (test: re-parse of the sentence's rule equals the stored rule).
- [ ] SCH-AC-2 For 5,000 random rules of the §2.3.4 subset in 20 zones, the engine's slots over two years equal `dateutil.rrule` with `zoneinfo`, including every gap and overlap of those years.
- [ ] SCH-AC-1a No input given through `--at`, `--rrule`, `--every` or `--cron` exits 3 in a corpus of 1,000 valid values, and each equals the canonical form of its word-grammar twin where one exists.
- [ ] SCH-AC-3 `parse`, `list`, `show` and `history` leave the home store unchanged (hash test) and start no process.
- [ ] SCH-AC-4 With scripted runs and a fake clock, SCH-B5 to SCH-B9 give the stated fire-log events, and no slot ever has two `started` events across 1,000 runs of two concurrent ticks.
- [ ] SCH-AC-5 Every refusal in §4 exits with its code and writes nothing.
- [ ] SCH-AC-6 A scheduled run's status document, `run_started` record and stats row carry `origin: schedule` and the schedule fields, and `report --by schedule` totals match the fire log's `ended` costs.
- [ ] SCH-AC-7 No fire log line carries request, input or feedback text; the request lives only in the owner-only entry and reaches the run through a ticket.

## Open questions

| Question | Owner |
|---|---|
| Should a team be able to commit schedules in the repository (for example a `tempergraph/schedules/` folder that each member's tick reads), with caps limited to lowering? Per-user, per-machine schedules are assumed. | Owner |
| Is scheduling in the first release? The recommended slice is above. | Owner |

## References

