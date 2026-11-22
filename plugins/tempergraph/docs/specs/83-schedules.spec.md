# Schedules

## Purpose

A schedule starts a registered workflow, or a saved orchestration, once or on a recurrence, given in an exact format (ISO 8601, an RFC 5545 rule, cron) or, optionally, in words ("tomorrow at 9", "every weekday at 8:00", "every month on the last day at 17:00"). Both paths are deterministic and model-free; the words are a convenience on top of the exact formats, never a requirement ([ADR-0096](../adr/0096-exact-formats-first-and-an-optional-word-grammar-echoed-back.adr.md)). This spec owns the `schedule` verbs, the exact formats, the word grammar, how either becomes one canonical form that is echoed back before anything is saved, time zones and daylight saving ([ADR-0097](../adr/0097-schedules-keep-an-iana-zone-and-rfc-5545-daylight-saving-rules.adr.md)), the schedule entry and its fire log, and the policies for missed fires, overlapping runs, failures and spend ([ADR-0098](../adr/0098-missed-slots-catch-up-latest-and-a-live-run-skips-the-next.adr.md)). What fires a schedule is the tick, an OS-agnostic, model-free engine routine that reads the schedules, decides what is due and starts each due run through the engine's own `run` verb; the engine's portable loop calls it, and an OS scheduler or a pipeline may too ([TCK](84-schedule-ticks-and-unattended-fires.spec.md), [ADR-0095](../adr/0095-a-model-free-tick-behind-os-agnostic-triggers.adr.md)). The tick calls no model and answers no gate (OVR-B20). A scheduled run is an ordinary run, preflighted, capped, logged and costed, every pause staying with a person; a schedule adds who started it (caller kind `scheduler`, [PRV](85-caller-provenance.spec.md)), which slot it served, and the rules that keep it from piling up paused runs or spend ([ADR-0099](../adr/0099-a-scheduled-fire-is-an-attested-caller-with-a-capped-unattended-spend.adr.md)). Operators, the schedule skill and pipelines depend on it; design notes and assumptions are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### SCH-B13 Concepts

WHEN schedules are kept THE engine SHALL keep each as one entry file plus its fire log under `~/.tempergraph/schedules/<schedule_id>/` (home store, [LOS-B10](33-local-observability-store.spec.md)), per user and per machine, at most 64 (`too_many_schedules`); give it a `schedule_id` `<name>-<4 hex>`, the name a slug from `--name` or the workflow name, unique on the machine, the verbs accepting the name alone when unique; give it a target `workflow` (a run), `orchestration` (an `orchestrate start` of a saved `*.orch.json`) or `program` (reserved: `add --program` refused `program_target_reserved` until a package can declare programs, [WFM](02-workflow-model.spec.md)); compute from its When slots, each a UTC instant plus its local wall time; handle each slot by at most one fire (started, skipped, missed or refused); and count as live a fire's run whose thread is `running` or `paused`, or an orchestration in any state but an ended one.

- GIVEN `schedule add --program …` WHEN run THEN it exits 2 `program_target_reserved`

### SCH-B14 Schedule entry

WHEN an entry is written, owner-only (0600) and atomically, with values that are constants, checked numbers, names or scrubbed strings THE engine SHALL write `schema_version` 1; `schedule_id`, `name` and a `description` of at most 200 characters; `state` (`active`, `paused`, `done` after a `once` fired or a `recur` passed its end, or `removed`); `target` (`{kind, workflow, repo, request, inputs}` or `{kind, orchestration_file, repo, args}`, `repo` the absolute main checkout whose state root the run uses, [WSP](13-workspace-and-concurrency.spec.md)); `when` (`{input, phrase, kind, at | rule, zone, starts, ends, count}`, `phrase` what `--when` gave or null, `at` an ISO 8601 local date-time, `rule` a RECUR string of the stored subset, `zone` an IANA name); `options` (any settings key on the `flag` layer with `via: schedule`, [RST-B22](80-run-settings-and-overrides.spec.md), plus `profiles`); the required `run_cost_cap_usd`; an optional `budget` `{period: day|week|month, cap_usd}` over the calendar period in the schedule's zone; `catch_up` and `catch_up_window_s`; `overlap`; `max_live` (1 to 4, default 1); `pause_after_failures` (1 to 10, default 3); `executors_checked` (`{executor, credential_kind, checked_at}` from the creation preflight, [TCK](84-schedule-ticks-and-unattended-fires.spec.md)); `created` and `edited` as `{at, caller, from}`; `token_digest`, the SHA-256 of the fire token; and the derived `next_slot` and `last_fire`, readers trusting the fire log over them; the request reaching a run only through a hand-off ticket ([SEC-B5](14-security.spec.md)).

- GIVEN an entry WHEN its mode is read THEN it is 0600

### SCH-B15 Exact formats

WHEN timing is given by `--at` (ISO 8601 local, or with an offset or `Z`; `once`), `--rrule` (RFC 5545 RECUR of the stored subset with `--starts` as DTSTART; `recur`), `--every` (an ISO 8601 duration of at least `PT15M` from `--starts`, default now; an interval `recur`), `--cron` (five fields read in the schedule's zone; `recur`), with `--tz` (IANA), `--starts`, `--until` and `--count` THE engine SHALL parse it with no model (OVR-B15) and never interpret it, so it never produces a `needs`, refusing only a malformed value (`when_malformed` naming the format), a time in the past (`when_in_past`), no slot within 400 days (`when_too_far`), a gap the rule cannot leave or an unknown zone (`zone_unknown`).

- GIVEN `--at 2026-12-01T08:00`, `--every PT2H` or `--cron "0 8 * * 1-5"` with `--yes` from a script WHEN added THEN none exits 3

### SCH-B19 Exact formats never ask

WHEN a schedule is added with an exact format and `--yes` from a script with no terminal THE engine SHALL save it with exit 0 and give the same echo as its word-grammar twin.

- GIVEN `schedule add digest "daily digest" --rrule "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=0" --tz Europe/Warsaw --run-cost-cap 3 --yes` WHEN it runs THEN it is saved with exit 0 and the echo equals that of `every weekday at 8:00`

### SCH-B16 Word grammar parts

WHEN `--when` gives a phrase (English, case-insensitive, extra spaces and a trailing period ignored) THE engine SHALL read times (`9am`, `9:30pm`, `09:00`, `21:30`, `noon`, `midnight`, `HH:MM` being 24-hour); days (`today`, `tomorrow`, `monday` to `sunday` and `mon` to `sun`, `next <weekday>`, `this <weekday>`); dates (ISO `2026-12-01`; `dec 1`, `1 dec`, `december 1st` with an optional year, numeric dates other than ISO refused `date_ambiguous` naming the ISO forms); offsets (`in <n> minutes|hours|days|weeks`, `in an hour`, `in half an hour`); instants (ISO 8601 with an offset or `Z`); zones (`--tz <IANA name>` or a trailing ` in <IANA name>`, `UTC` accepted, abbreviations such as `EST` or `CET` refused since they name no rules); and bounds (`from <date>`, `until <date>`, `for <n> times`), refusing a phrase that matches no rule with `when_unparsed` and the nearest phrases.

- GIVEN `every day at 9 CET` WHEN parsed THEN it is refused `zone_unknown`

### SCH-B17 Phrases

WHEN a phrase is read THE engine SHALL give `once` for `in 2 hours` (now plus 2 h, as local time in the zone), `tomorrow at 9am`, `at 18:00` (today if in the future, else a `needs`: tomorrow or refuse), `next monday at 10:00` (next week's Monday, never this week's) and `on dec 1 at 08:00` or `2026-12-01 08:00` (a past month-day without a year meaning next year); and `recur` for `every day at 9am` and `daily at 09:00` (`FREQ=DAILY;BYHOUR=9;BYMINUTE=0`), `every weekday at 8:00` (`FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=0`), `every monday` and `every monday and thursday at 7pm` (`FREQ=WEEKLY;BYDAY=…`), `every 2 weeks on friday at 16:00` (`INTERVAL=2`), `every month on the 1st at 9am` (`BYMONTHDAY=1`), `every month on the last day at 17:00` (`BYMONTHDAY=-1`), `every first monday of the month at 9am` (`BYDAY=1MO`, `last friday` giving `-1FR`), `every 2 hours`, `every 30 minutes` and `hourly` (interval rules from `starts`), `every 2 hours between 9am and 5pm on weekdays` (`FREQ=HOURLY;INTERVAL=2;BYHOUR=9,11,13,15,17;BYDAY=MO,…,FR`) and any of these with `from`, `until` or `for 5 times` (`starts`, `UNTIL`, `COUNT`), refusing an interval under 15 minutes `interval_too_short`.

- GIVEN `every 5 minutes` WHEN parsed THEN it exits 2 `interval_too_short`
- GIVEN `next tuesday at 10:00` on a Monday WHEN parsed THEN it is the Tuesday 8 days later, echoed with its date

### SCH-B18 Canonical form and echo

WHEN any When is parsed THE engine SHALL store only the canonical form, `once` as `{at, zone}` and `recur` as an RFC 5545 RECUR limited to `FREQ` (`MINUTELY` only with `INTERVAL` of at least 15, `HOURLY`, `DAILY`, `WEEKLY`, `MONTHLY`), `INTERVAL`, `BYDAY` (with ordinals for `MONTHLY`), `BYMONTHDAY` (1 to 31, −1), `BYHOUR`, `BYMINUTE`, `COUNT` and `UNTIL`, plus `starts` and `zone`, so every reader computes the same slots with a standard library; and echo it as the canonical form, a sentence rendered from it (never from the phrase), the zone with its current UTC offset, the next three slots (or the one slot) in local and UTC time and each assumption made, as the output of `schedule parse` and the confirmation of `add` and `edit`.

- GIVEN `every weekday at 8:00` in `Europe/Warsaw` WHEN echoed THEN it reads "At 08:00, Monday to Friday." with the RRULE, the next three slots in local and UTC time, and "assumed: zone from this machine"

### SCH-B2 Ambiguity in words is asked, not guessed

WHEN a phrase has more than one reading THE engine SHALL exit 3 with the readings as choices, in the status shape of `run --check` ([CLI-B1](17-engine-cli.spec.md)), for a bare hour 1 to 12 with no `am`, `pm` or `:MM` (`09:00` or `21:00`), a recurrence with no time (`09:00` offered, never applied silently), `at <time>` with no day after that time today (tomorrow, or refuse) and `every month on the 29th`, `30th` or `31st` (skip short months, or the last day); use the machine's zone when none is given, named in the echo as assumed; show a daylight-saving gap or overlap on a listed slot in the echo; take the phrase again with the reading explicit or `--choose <n>`; and never save a phrase with an open `needs`.

- GIVEN `every day at 9` WHEN parsed THEN it exits 3 offering `09:00` or `21:00`
- GIVEN `every monday` WHEN parsed THEN it exits 3 offering `09:00`
- GIVEN `03/04 at 10:00` WHEN parsed THEN it exits 2 `date_ambiguous` naming `2027-03-04` or `2027-04-03`
- GIVEN `every month on the 31st at 9am` WHEN parsed THEN it exits 3 offering to skip short months or use the last day

### SCH-B1 Echo before save

WHEN `schedule add` runs with a phrase THE engine SHALL print the echo and ask for a yes in a terminal, and with no terminal and no `--yes` exit 3 with the echo as the `needs` and save nothing.

- GIVEN `schedule add triage "open bugs" --when "every weekday at 8:00"` in `Europe/Warsaw` WHEN run with no terminal and no `--yes` THEN it exits 3 with the echo and saves nothing

### SCH-B20 Time zones and daylight saving

WHEN slots are computed THE engine SHALL compute them in the schedule's one IANA zone and store them as UTC, a machine zone change moving no schedule and `list` marking a zone that differs from the machine's; fire calendar rules at wall-clock time on both sides of a change and interval rules every elapsed UTC period, their local times shifting across a change; take a local time inside a gap with the offset from before the gap (02:30 on a spring-forward day becoming 03:30, RFC 5545 §3.3.5) and a local time inside an overlap once at the first occurrence (`fold=0`); and take zone data from the engine's interpreter (`zoneinfo` with `tzdata` pinned in the engine environment), `schedule list` recomputing `next_slot` from current zone data at every call.

- GIVEN a machine zone change WHEN `schedule list` runs THEN no schedule moves and the differing zone is marked

### SCH-B3 Daylight saving

WHEN a daily slot falls in a daylight-saving change THE engine SHALL apply the gap and overlap rules and name both slots in `schedule show`.

- GIVEN `every day at 02:30` in `Europe/Warsaw` WHEN the slots around 2027-03-28 and 2027-10-31 are computed THEN 2027-03-28's is 03:30 local (01:30 UTC) and 2027-10-31's fires once at the first 02:30 (00:30 UTC)

### SCH-B21 Missed slots

WHEN a tick finds slots passed since the last fire with no tick between a slot and `slot + catch_up_window_s` ([TCK-B3](84-schedule-ticks-and-unattended-fires.spec.md)) THE engine SHALL under `catch_up: latest` (default) fire only the most recent passed slot within the window and record the older ones `missed`; under `none` record every passed slot `missed` and wait for the next; under `all` fire each passed slot within the window in order, at most 3 per tick, under the overlap policy; default the window to the recurrence's period capped at 24 hours, and to 24 hours for a `once`; and raise for a missed `once` an attention item `schedule_missed` answered by `schedule fire <id>`.

- GIVEN a missed `once` WHEN the tick runs THEN a `schedule_missed` item names `schedule fire <id>`

### SCH-B6 Missed slots after the machine was off

WHEN the machine was off across several daily slots THE engine SHALL fire the latest slot within the window and record the rest `missed`.

- GIVEN `every day at 9am` with `catch_up: latest` and a machine off from Friday evening to Monday 10:00 WHEN the first tick runs at 10:05 THEN Saturday's and Sunday's slots are `missed` and Monday's fires
- GIVEN the machine back on Sunday 10:00 WHEN the first tick runs THEN Sunday's slot fires and Saturday's is `missed`

### SCH-B22 Overlap

WHEN a slot comes due while the schedule has a live run THE engine SHALL under `overlap: skip` (default) record it `skipped` with reason `overlap` and start nothing; under `queue` hold it as one pending fire, a later slot replacing it, started by the first tick after the live run ends; and under `parallel` start it while live runs are under `max_live`, else skip, `parallel` refused at `add` with `parallel_needs_worktree` unless `run.workspace` resolves to `worktree`; a paused run counting as live, and after 3 slots skipped behind the same paused run, the pause's attention item being marked `blocking_schedule` with the count.

- GIVEN `overlap: parallel` and `run.workspace` resolving to `in_place` WHEN added THEN it exits 2 `parallel_needs_worktree`

### SCH-B5 Overlap skips behind a pause

WHEN slots come due while the schedule's last run waits at a pause THE engine SHALL skip them and mark the pause as blocking.

- GIVEN a daily schedule with `overlap: skip` whose Monday run paused WHEN Tuesday's, Wednesday's and Thursday's slots come due THEN each is `skipped` with `overlap`, no run starts, and the pause's attention item carries `blocking_schedule: 3`

### SCH-B23 Failures

WHEN a fire's run ends with exit 4 or 5, or its start is refused with exit 2 THE engine SHALL count a failure, exit 0 resetting the count, and after `pause_after_failures` in a row set the schedule `paused` with reason `failures`, raise an attention item `schedule_paused` with the last failure's thread and cause, and fire the hook event `schedule_paused` ([HOK](24-lifecycle-hooks.spec.md)), never retrying a slot itself and leaving an infra failure to the run's own policy.

- GIVEN a failure then a fire ending with exit 0 WHEN counted THEN the count is reset

### SCH-B9 Failures pause the schedule

WHEN three fires in a row fail under `pause_after_failures: 3` THE engine SHALL pause the schedule, and `schedule resume` SHALL restart it and reset the count.

- GIVEN three fires ending with exit 5 WHEN the third ends THEN the schedule is `paused` with `failures`, `schedule_paused` fires and `attention` lists it with the last thread and cause

### SCH-B24 Spend

WHEN a schedule spends THE engine SHALL require `run_cost_cap_usd` at `add` (`cost_cap_required`), a workflow-declared cap satisfying it and the flag only lowering it; with `budget`, before each fire sum the estimated cost of this schedule's fires in the current period from the stats rows ([OBS](15-observability-and-cost.spec.md)) and, if the sum plus the run cap would exceed `cap_usd`, record the slot `skipped` with reason `budget` and raise an attention item `schedule_budget` once per period; and count a fire whose cost is `incomplete` at its run cap, so an unmeasured run never makes the budget look unspent (C1).

- GIVEN a fire whose cost is `incomplete` WHEN the period is summed THEN it counts at its run cap

### SCH-B8 Spend is capped

WHEN the next fire would pass the period budget THE engine SHALL skip it until the next period.

- GIVEN `--budget month:20 --run-cost-cap 4` and fires costing 6.10, 5.80 and 4.30 this month WHEN the next slot comes due THEN 16.20 + 4 > 20, the slot is `skipped` with `budget` and one `schedule_budget` item is raised
- GIVEN no `--run-cost-cap` and no workflow cap WHEN added THEN it exits 2 `cost_cap_required`
- GIVEN `--run-cost-cap 50` and a workflow cap of 10 WHEN added THEN the cap stays 10 and the echo says so

### SCH-B25 Settings, inputs and grants

WHEN a schedule's `options` and `profiles` are given THE engine SHALL validate them at `add` and `edit` by `run --check` with the run's own function ([RST-B32](80-run-settings-and-overrides.spec.md)), exiting 3 or 2 with its questions and saving nothing on `needs` or `error`, re-resolve them at each fire, record them with `via: schedule`, refuse a key that widens tools, commands or judge views with `widening_in_schedule` (a grant is a person's decision for one run, [ADR-0080](../adr/0080-a-person-may-grant-a-step-tools-for-a-run.adr.md)) while a workflow's own profile still widens, and resolve `run.workspace` as for any run, so under `auto` a workflow that writes files gets its own worktree ([WTR-B18](82-worktree-mode.spec.md)) and a fire never writes into the checkout a person works in.

- GIVEN a schedule whose options a settings file changed after `add` WHEN it fires THEN the options are re-resolved

### SCH-B10 A grant cannot be scheduled

WHEN a schedule carries a grant THE engine SHALL refuse it and save nothing, while the same grant given by a person to one paused scheduled run on `resume` is accepted ([RST-B28](80-run-settings-and-overrides.spec.md)).

- GIVEN `schedule add triage … --grant triage=mcp:tracker/get_issue` WHEN checked THEN it exits 2 `widening_in_schedule`

### SCH-B26 Fire identity and keys

WHEN a slot fires THE engine SHALL name the fire `<schedule_id>@<slot as yyyymmddThhmmZ>`, or `@manual-<yyyymmddThhmmssZ>` for `schedule fire`; the thread `<workflow>/s-<schedule_id>-<slot as yyyymmddThhmm>`, so a second start of the slot is refused by [DUR-B1](09-durability-and-resume.spec.md); an orchestration `<name>-s<yyyymmddThhmm>-<4 hex>`; render the fire keys `{fire.slot}` (local ISO date-time), `{fire.date}` (local ISO date), `{fire.previous_slot}` (the last slot that started a run, or empty) and `{fire.schedule}` in `request`, `inputs` and orchestration `args` by the template grammar ([CON-B8](01-contracts.spec.md)); set no `--alias`; and label the run `schedule <name> <fire.date>` unless set.

- GIVEN `schedule fire digest` WHEN run THEN its fire id ends `@manual-<yyyymmddThhmmssZ>`

### SCH-B11 Fire keys

WHEN a request names a fire key THE engine SHALL render it for the slot.

- GIVEN `request: "daily digest for {fire.date}"` and the slot 2026-11-23 08:00 WHEN it fires THEN the request is `daily digest for 2026-11-23` and the label `schedule digest 2026-11-23`

### SCH-B7 A slot never runs twice

WHEN two ticks find the same due slot at once THE engine SHALL start it exactly once, the tick lock serializing them ([TCK-B2](84-schedule-ticks-and-unattended-fires.spec.md)) and the slot's thread id making any second start a refusal.

- GIVEN the loop and an external cron ticking at the same moment WHEN both find a due slot THEN exactly one starts it

### SCH-B27 Verbs

WHEN a `schedule` verb runs THE engine SHALL offer `schedule parse <when> [--count n] [--json]` (the echo, `needs` or refusal); `schedule add <workflow> <request…> <when> [--name n] [--choose n] [run options] [--run-cost-cap usd] [--budget <period>:<usd>] [--catch-up …] [--overlap …] [--max-live n] [--pause-after-failures n] [--check] [--yes]` (parse, preflight with `run --check` and the credential check of [TCK](84-schedule-ticks-and-unattended-fires.spec.md), print the echo, save on `--yes` or an interactive yes, `--check` saving nothing) and `schedule add --orchestration <file> [--arg k=v…] <when>` (validated with `orchestrate validate`); `schedule list [--all] [--json]` (every schedule from any folder: name, target, sentence, zone, state, next slot, last fire, live runs, failures, period spend); `schedule show <id> [--json]` (entry, echo, next ten slots, last 20 fires); `schedule history <id> [--since <date>] [--json]`; `schedule edit <id> [<when>] [options] [--yes]` (re-parsed, re-checked and echoed like `add`, the target workflow, repo and kind fixed, `target_fixed`); `schedule pause <id> [--reason text]` and `schedule resume <id> [--catch-up]` (slots passed while paused `missed` unless `--catch-up`); `schedule skip <id> [--next | --until <date>]` (recorded `skipped` with reason `person`); `schedule fire <id> [--yes]` (one fire now through the tick's path, no catch-up); `schedule remove <id> [--yes]` (`state: removed`, history kept until `store prune`, live runs going on); `schedule tick` and `schedule loop [--detach|--stop]`; and `schedule trigger install|status|remove` and `schedule export <id> --for <system>` ([TCK](84-schedule-ticks-and-unattended-fires.spec.md)); `parse`, `list`, `show` and `history` writing nothing and starting no process, `tick` and `fire` the only ones that spend, the mutating verbs `add`, `edit`, `pause`, `resume`, `skip`, `fire` and `remove` classifying their caller into the fire log ([PRV](85-caller-provenance.spec.md)), exits 0, 2 refused and 3 `needs` ([CON-B12](01-contracts.spec.md)), an unregistered workflow or a `repo` without a state root exiting 2 at `add` and `refused` at a fire, and `schedule` a reserved verb word ([CLI-B2](17-engine-cli.spec.md)).

- GIVEN `schedule edit` changing the workflow WHEN run THEN it exits 2 `target_fixed`

### SCH-B12 Edit keeps history

WHEN a schedule is edited THE engine SHALL show the echo, record an `edited` event with the old and new canonical forms and the caller, leave past fires unchanged and recompute `next_slot` from now.

- GIVEN an active schedule with 12 fires WHEN `schedule edit digest --when "every weekday at 7:30" --yes` runs THEN the `edited` event holds both forms and the caller and past fires are unchanged

### SCH-B28 Fire log

WHEN a schedule's events happen THE engine SHALL append JSON lines to its fire log, each with `seq`, `at` (UTC), `kind`, `slot`, `fire_id` and metadata only, never request, input or feedback text, of kinds `created`, `edited` (changed fields), `paused` (`person` or `failures`), `resumed`, `due`, `started` (thread or orchestration id), `skipped` (`overlap`, `budget`, `person` or `paused`), `queued`, `missed`, `refused` (the exit 2 reason, `credential` included), `ended` (exit, outcome, `cost` with `reported`, `estimated` and `incomplete`) and `removed`, each person-made event with its `caller` block; record a failed fire-log write on standard error and go on with the fire (C2); and add every fire as a row of the machine-wide scheduled-run ledger read by `schedule runs` ([TCK](84-schedule-ticks-and-unattended-fires.spec.md)), a scheduled run's status document, `run_started` and stats row carrying `origin: schedule` and the schedule fields.

- GIVEN a scheduled run WHEN `report --by schedule` runs THEN its totals match the fire log's `ended` costs

## Acceptance criteria

- SCH-AC1 (SCH-B15, SCH-B16, SCH-B17, SCH-B18, SCH-B2): Every exact format, phrase and ambiguity case has a fixture giving its canonical form, echo sentence and next three slots for a fixed "now" and zone; the echo sentence is generated from the canonical form only (re-parse of its rule equals the stored rule)
- SCH-AC2 (SCH-B20, SCH-B3): For 5,000 random rules of the stored subset in 20 zones, the engine's slots over two years equal `dateutil.rrule` with `zoneinfo`, including every gap and overlap of those years
- SCH-AC3 (SCH-B19, SCH-B15): No input given through `--at`, `--rrule`, `--every` or `--cron` exits 3 in a corpus of 1,000 valid values, and each equals the canonical form of its word-grammar twin where one exists
- SCH-AC4 (SCH-B27, SCH-B13): `parse`, `list`, `show` and `history` leave the home store unchanged (hash test) and start no process
- SCH-AC5 (SCH-B21, SCH-B22, SCH-B23, SCH-B24, SCH-B5, SCH-B6, SCH-B7, SCH-B8, SCH-B9, SCH-B11, SCH-B26): With scripted runs and a fake clock, SCH-B5 to SCH-B9 give the stated fire-log events, and no slot ever has two `started` events across 1,000 runs of two concurrent ticks
- SCH-AC6 (SCH-B1, SCH-B10, SCH-B12, SCH-B25): Every refusal exits with its code and writes nothing
- SCH-AC7 (SCH-B28): A scheduled run's status document, `run_started` and stats row carry `origin: schedule` and the schedule fields, and `report --by schedule` totals match the fire log's `ended` costs
- SCH-AC8 (SCH-B14, SCH-B28): No fire log line carries request, input or feedback text; the request lives only in the owner-only entry and reaches the run through a ticket

## Open questions

- Should a team be able to commit schedules in the repository (for example a `tempergraph/schedules/` folder that each member's tick reads), with caps limited to lowering? Until answered: per-user, per-machine schedules. Owner: owner.
- Should a delegation policy later let a scheduled run's verification pauses be answered by an agent with engine-checked evidence? Until answered: every pause waits for a person ([HUM](07-gate-and-human.spec.md), [ADR-0039](../adr/0039-pauses-stay-with-the-person-failures-follow-node-policy.adr.md)). Owner: owner.
- Not built yet: schedules are release 3 work (third-release plan R3-T5), first the slice of `once` and calendar `recur` for workflow targets, `catch_up: latest|none`, `overlap: skip`, both caps, every verb but `export` and the portable loop with the `host` adapter, then the rest. Owner: engine owner.
