# Schedule ticks and unattended fires

## Purpose

A schedule ([SCH](83-schedules.spec.md)) must fire when nobody is at a terminal or in a conversation. This spec owns what makes it fire: the tick, one OS-agnostic, deterministic, model-free routine that decides what is due and starts it; the triggers that call the tick, of which the engine's own portable loop is the default and OS schedulers, pipelines and any other scheduler are optional adapters; the fire token that marks a scheduled run as the scheduler's; the credentials a run needs when nobody is present to sign in; what a fire leaves in the records; and the `tempergraph:schedule` skill ([ADR-0095](../adr/0095-a-model-free-tick-behind-os-agnostic-triggers.adr.md)). All scheduling logic (slots, zones, catch-up, overlap, budgets, idempotence) lives in the tick and reads only the engine's files, so it behaves the same on macOS, Linux and Windows and under any trigger; a trigger only decides when the tick is called. The tick is a sibling of the orchestration supervisor ([ORC](45-orchestration.spec.md)): both start work only through the engine's own verbs and answer no gate (OVR-B20). Operators, the schedule skill, pipelines and caller provenance ([PRV](85-caller-provenance.spec.md)) depend on it; design notes and assumptions are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### TCK-B1 The default trigger is portable

WHEN the person runs `schedule loop --detach` on a machine with no trigger THE engine SHALL start one loop, a second call reporting it and exiting 0, write no OS entry, and show `loop`, its pid and `last_tick_at` in `schedule trigger status`; and `schedule trigger install --os` run twice SHALL leave exactly one autostart entry that names the shim and `schedule loop` only.

- GIVEN macOS, Linux or Windows with no trigger WHEN `schedule loop --detach` runs twice THEN one loop runs and no OS entry exists

### TCK-B2 One tick at a time

WHEN a tick starts while another tick holds the lock THE tick SHALL exit 0 within one second without reading any schedule.

- GIVEN a tick holding `tick.lock` WHEN a second tick starts THEN it exits 0 at once and reads no schedule

### TCK-B3 Missed while asleep

WHEN a machine wakes after sleeping through a slot THE loop SHALL end its sleep and tick at once on every OS and under every trigger, and the tick SHALL start a slot still inside its catch-up window, the run's `run_started` showing the slot and the later start time.

- GIVEN a laptop asleep from 08:50 to 09:40 with a schedule due at 09:00 WHEN it wakes THEN the 09:00 slot starts at about 09:40 and `run_started` shows `slot` 09:00

### TCK-B4 A pause reaches a person

WHEN a scheduled run pauses with nobody at the machine THE engine SHALL exit the run 3, fire the `paused` lifecycle hook with the facts file ([HOK](17-engine-cli.spec.md)), list the pause in `attention` with its schedule and the resume command, show it in the monitor, and let nothing answer it but a person.

- GIVEN a scheduled run that pauses at 08:20 WHEN it exits 3 THEN `attention` lists the pause with `schedule digest` and the resume command

### TCK-B5 Credential missing at a fire

WHEN a slot comes due and a credential the run needs is gone from the profile THE tick SHALL refuse the fire in the preflight with reason `credential`, record `refused` in the fire log, start no session, and list `schedule_refused` once in `attention` with the executor named.

- GIVEN a schedule created with an API key in the profile WHEN the key is removed and the next slot comes due THEN the fire is `refused` with reason `credential` and no session starts

### TCK-B6 Judge credential

WHEN a `claude` schedule whose judges launch with `--bare` is added or edited and the profile holds only `CLAUDE_CODE_OAUTH_TOKEN` THE engine SHALL refuse it with exit 2 `judge_credential`, naming an API key, an `apiKeyHelper` or cloud credentials as the fix.

- GIVEN a profile with only `CLAUDE_CODE_OAUTH_TOKEN` and `--bare` judges WHEN the schedule is added THEN it exits 2 `judge_credential`

### TCK-B7 Stale trigger

WHEN `schedule list`, `status` or `attention` runs with active schedules and a `last_tick_at` older than three intervals THE engine SHALL show `trigger_stale` with the age and the `schedule trigger status` command, read-only verbs still writing nothing.

- GIVEN active schedules and a heartbeat 20 minutes old under a 5-minute interval WHEN `status` runs THEN it shows `trigger_stale` and the store is unchanged

### TCK-B8 Engine update between ticks

WHEN an `update` switches engines ([UPD](60-engine-update.spec.md)) THE loop SHALL finish its tick and re-execute itself through the shim, so the next tick runs on the new engine with the same schedules, and an `os` entry SHALL be rewritten only if the shim path changed.

- GIVEN a running loop WHEN `update` switches engines THEN the next tick reports the new engine version in `tick.json`

### TCK-B9 Orchestration target

WHEN a schedule whose target is an orchestration fires THE tick SHALL run `orchestrate start` with the schedule's args, record the orchestration id as the fire's, settle the fire on later ticks from `orchestrate status`, and count a live orchestration as a live fire for `overlap`.

- GIVEN a schedule targeting `release-train.orch.json` WHEN its slot fires THEN the fire records the orchestration id and a live orchestration makes the next slot `skipped` with `overlap`

### TCK-B10 Agent-made schedule

WHEN an agent session runs `schedule add … --yes` THE engine SHALL refuse it `schedule_not_by_person` without `--relayed`, and with `--relayed` and a person turn within the window save it with `created.caller` of kind `agent`, `decided_by: person`, `relay: turn_only`.

- GIVEN a Claude Code session with a person turn 2 minutes earlier WHEN it runs `schedule add … --yes --relayed` THEN the schedule is saved with `decided_by: person`

### TCK-B11 Export refuses a moving offset

WHEN `schedule export` is asked for a calendar rule in a zone with daylight saving THE engine SHALL exit 2 `export_needs_utc`, and with `--pin-offset` print the cron line for today's offset with a comment stating the local time it runs at in the other season.

- GIVEN `every weekday at 8:00` in `Europe/Warsaw` WHEN `schedule export digest --for github-actions --pin-offset` runs THEN it prints `0 7 * * 1-5` and a comment that the job runs at 09:00 local in summer

### TCK-B12 Several triggers

WHEN a slot comes due and more than one trigger calls `schedule tick` THE engine SHALL start the slot once, a later tick finding it handled and exiting 0 without waiting.

- GIVEN the loop running and an `external` cron also calling `schedule tick` every 5 minutes WHEN a slot comes due THEN it has one `started` event

### TCK-B13 One record of every scheduled run

WHEN the person runs `schedule runs` from any directory THE engine SHALL list every fire on the machine with its schedule, target repository, `created_from`, outcome and cost, including fires of removed schedules, and mark rows whose state root is gone `records_gone`.

- GIVEN schedules made from `~/work/api`, `~/work/web` and the home folder, one since removed and the `web` state root deleted WHEN `schedule runs --since 2026-11-01` runs THEN every fire of all three appears and the `web` rows are marked `records_gone`

### TCK-B14 Triggers

WHEN something must call the tick THE engine SHALL make `tempergraph schedule tick` the one contract every trigger calls, idempotent and lock-guarded so it is safe at any frequency, from several triggers and after any gap, and offer four triggers: `loop` (default; `schedule loop [--detach]`, a portable engine process in the engine's interpreter that runs the tick, sleeps until the earlier of the next slot of any schedule and 60 s, and repeats, holding nothing in memory between ticks, one per user by lock `schedules/loop.lock`, ended by `schedule loop --stop`); `host` (the plugin's `SessionStart` hook runs `schedule loop --if-autostart`, which starts `schedule loop --detach` when `schedule.loop_autostart` is on and none is running, [SHL](19-plugin-shell.spec.md)); `os` (`schedule trigger install --os` writes one per-user autostart entry that starts the loop at login and restarts it if it exits: a LaunchAgent on macOS, a systemd user unit on Linux, a Task Scheduler task on Windows, and where none exists a crontab line that runs `schedule tick` every 5 minutes; exit 2 `no_os_scheduler` when no per-user scheduler is usable, `loop` and `external` still working); and `external` (any scheduler the owner runs, such as cron, a CI schedule, a Kubernetes CronJob or a cloud routine, calls `schedule tick`); a late call only makes slots late, the catch-up rule deciding what fires ([SCH-B21](83-schedules.spec.md)).

- GIVEN a machine with no per-user scheduler WHEN `schedule trigger install --os` runs THEN it exits 2 `no_os_scheduler` and `schedule loop --detach` still works

### TCK-B15 Adapters and trigger status

WHEN a trigger is installed, checked or a schedule is added THE engine SHALL write adapter entries and hooks that run only the shim's absolute path with `schedule loop` or `schedule tick`, with no shell, no person-typed value and no environment value of their own ([SEC](14-security.spec.md)); make `install` idempotent and rewrite an entry whose shim path changed after `update` or that points at a missing shim, which `trigger status` reports `broken`; list in `schedule trigger status` every trigger seen (loop, hook, entries, external ticks from the heartbeat) with the last error; make `remove` delete what `install` wrote; and at `schedule add`, when no trigger is alive (no loop lock, no `os` entry, no heartbeat within three intervals), save the schedule with a warning that offers `schedule loop --detach` and names the optional adapters once.

- GIVEN an `os` entry whose shim was deleted WHEN `schedule trigger status` runs THEN the entry is `broken`, and `install` rewrites it

### TCK-B16 The tick

WHEN `schedule tick` runs THE tick SHALL take `~/.tempergraph/schedules/tick.lock` without waiting and exit 0 if held; write the heartbeat `schedules/tick.json` with `last_tick_at`, engine version, trigger kind, interval and per executor the credential kinds its environment resolves (presence only); settle every `started` fire with no `ended` event from its thread's or orchestration's status, appending `ended` with exit, outcome and cost and updating the failure count ([SCH-B23](83-schedules.spec.md)); find each `active` schedule's slots passed since its last handled slot, in order of next slot, as UTC instants from the canonical When ([SCH-B20](83-schedules.spec.md)), applying `catch_up` and the window and recording `missed` ones; decide each slot by the schedule still `active`, overlap against live fires ([SCH-B22](83-schedules.spec.md)), the period budget ([SCH-B24](83-schedules.spec.md)) and the preflight `run --check` (or `orchestrate validate`) with the schedule's options and the credential check of TCK-B19, a refusal being a `refused` event and a failure with no spend; append `started` with the thread id, then launch `run` (or `orchestrate start`) detached in its own process group with the fire token, `--schedule <fire_id>` and a hand-off ticket carrying the rendered request and inputs ([SEC-B5](14-security.spec.md)), never waiting for the run; start at most 4 runs and spend at most 20 s per tick, leaving the rest oldest slot first for the next tick with `deferred` in the heartbeat; refuse a schedule whose repository was moved or deleted as `refused` (`repo_missing`); and release the lock and exit 0, an unhandled error being logged in the engine code log ([LOS](33-local-observability-store.spec.md)) and the heartbeat, an unwritable home store making the tick exit non-zero without starting anything.

- GIVEN six due slots WHEN one tick runs THEN four start, two wait for the next tick and the heartbeat records `deferred`

### TCK-B17 Fire token and caller

WHEN a schedule is added and its fires start THE engine SHALL make a random fire token at `add`, store its SHA-256 as the entry's `token_digest`, pass the token to the run in `TEMPERGRAPH_SCHEDULE_TOKEN` with `--schedule <fire_id>` on argv, and have the run's caller classification ([PRV](85-caller-provenance.spec.md)) check the digest against the entry the fire id names and record caller kind `scheduler`, confidence `attested`, host `schedule`, with a `schedule` block `{schedule_id, fire_id, slot, created_by}` (`created_by` the entry's `created.caller` kind and decider); refuse a missing or wrong token with exit 2 `schedule_token_invalid` and `--schedule` given by hand without a token with exit 2 `schedule_reserved`, before anything is written; keep the token off argv, out of every record and out of every step session's environment ([EXI](10-executor-interface.spec.md)), as for the supervisor's token ([ORC-B17](45-orchestration.spec.md)); and classify an orchestration target's `orchestrate start` as `scheduler`, its children staying `orchestrator` with both `parent` and the orchestration's `schedule` in their status.

- GIVEN a fire with a token whose digest does not match the entry WHEN the run starts THEN it exits 2 `schedule_token_invalid` and writes nothing

### TCK-B18 Unattended credential kinds

WHEN a fire needs credentials THE engine SHALL take them from the operator's credentials profile under `~/.tempergraph/config/` (the profile the executors already read, [ECC](11-executor-claude-code.spec.md), [EAG](12-executor-antigravity.spec.md)), never from a value in the trigger entry, a fire running in the trigger's environment with no shell profile, agent host or keychain prompt anyone can answer; and know the kinds `api_key` (an API key in the profile such as `ANTHROPIC_API_KEY` or `GEMINI_API_KEY`, or an `apiKeyHelper` command), `cloud` (Bedrock, Vertex or Foundry credentials resolvable without a person), `oauth_token` (a long-lived token made for scripts, such as Claude Code's `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`, [R-095](../research/R-095-scheduling-runs-prior-art-and-gaps.rsrch.md) F18) and `interactive_login` (a person's sign-in cached by the product), each executor declaring the kinds it can use unattended as a capability (OVR-B17).

- GIVEN a trigger entry WHEN it is read THEN it holds no credential value

### TCK-B19 Credential check per executor

WHEN a schedule is added or edited, and again at each fire in the tick's environment THE engine SHALL resolve each executor and judge binding of the run and accept for `claude` the kinds `api_key`, `cloud` and `oauth_token`, and `interactive_login` with warning `credential_may_expire`, a judge launched with `--bare` needing `api_key` or `cloud` (else `judge_credential`); for `agent-sdk` ([EAS](21-executor-agent-sdk.spec.md)) and `messages-api` ([EMA](20-executor-messages-api.spec.md)) `api_key` and `cloud`; for `antigravity` `api_key` (`GEMINI_API_KEY`), `interactive_login` refused `credential_unattended` until P-SCH-3 confirms it; refuse another kind with exit 2 `credential_unattended` at `add` and `refused` at a fire; save a binding with no credential at all at `add` or `edit` with warning `credential_none`; treat a missing credential at a fire as TCK-B5, counting as a failure; and never make a model call (C13), testing presence, form and, where the product offers one, a model-free account call.

- GIVEN an `antigravity` schedule with only a cached sign-in WHEN it is added THEN it exits 2 `credential_unattended`

### TCK-B20 Pipeline export

WHEN `schedule export <id> --for github-actions|gitlab-ci|crontab` runs THE engine SHALL print a snippet the owner commits to the pipeline's configuration and keep nothing for it, with the rule as five-field cron in UTC (TCK-B11 for a rule with a moving offset); the command `tempergraph run <workflow> …` with the schedule's options, `--run-cost-cap`, `--label` and `--caller pipeline`, the request read from a file in the repository, never inline; the system's own concurrency group so a new job waits for or skips a running one, matching `overlap` where the system can; caller `pipeline`, host `ci:<system>` ([PRV-B7](85-caller-provenance.spec.md)), `origin: ci` and `schedule: {schedule_id, declared: true}`, the tie being the pipeline's word, not attested; pipeline secrets of kind `api_key` or `cloud` only; and a run that pauses exiting 3 as any pipeline run, resuming elsewhere being deferred hosted-pipeline work.

- GIVEN a UTC schedule WHEN it is exported for `gitlab-ci` THEN the snippet's command carries `--caller pipeline` and reads the request from a repository file

### TCK-B21 The schedule skill

WHEN the `tempergraph:schedule` skill runs THE skill SHALL drive the verbs and hold no state, every schedule remaining possible with the CLI and exact formats alone: find the workflow, request and inputs from the person's words as the run driver does (`list`, `run --check`); translate the words into an exact format (`--at`, `--rrule`, `--every`, `--cron`, `--tz`) or pass a phrase of the word grammar unchanged with `--when`, the engine computing the slots; show `schedule parse`'s echo verbatim and ask about each `needs` reading in the person's terms; state the run cost cap and, for a recurrence, propose a period budget from `stats --projection` ([CST](34-central-run-stats.spec.md)); ask for one yes on the echo, caps and policies and save with `schedule add … --yes --relayed`; offer `schedule loop --detach` when `schedule trigger status` shows no live trigger, naming the adapters once; and never fire a run from Claude Code's own scheduled tasks or `/loop` ([R-095](../research/R-095-scheduling-runs-prior-art-and-gaps.rsrch.md) F10, F11), a desktop task that calls the skill making a schedule the tick fires.

- GIVEN the person asks for a run "every weekday at 8" WHEN the skill saves it THEN it called `schedule parse` and `schedule add … --yes --relayed`, and no Claude Code scheduled task exists

### TCK-B22 Who may create a schedule

WHEN `schedule add`, `edit`, `resume` or `fire` runs THE engine SHALL require `decided_by: person` ([PRV](85-caller-provenance.spec.md)), a person at a terminal or an agent with `--relayed` and a person turn in its host session within 10 minutes before the call (`turn_only` suffices), and refuse it otherwise with exit 2 `schedule_not_by_person`; and accept `pause`, `skip` and `remove`, which only lower spend, from any caller but `unknown`, recorded with their caller.

- GIVEN an agent with no person turn in 30 minutes WHEN it runs `schedule pause digest` THEN it is accepted and recorded with caller kind `agent`

### TCK-B23 Scheduled-run ledger

WHEN a fire is handled by the tick or by `schedule fire` THE engine SHALL append one row to `~/.tempergraph/schedules/runs.jsonl` in the home store ([LOS-B10](33-local-observability-store.spec.md)), whatever folder or repository the schedule was made in, with `fire_id`, `schedule_id`, `name`, `slot`, `fired_at` ([SCH-B28](83-schedules.spec.md)); `target` (workflow or orchestration file name, the target repository's path and folder name); `created_from` (where `schedule add` ran); `outcome` (`started`, `skipped` with reason, `missed`, `refused` with reason), updated by an `ended` row with exit, run outcome and cost (`reported`, `estimated`, `incomplete`); `thread_id`, `orchestration_id` and `state_root`; and `trigger`; holding metadata only, keeping rows when their schedule, state root or repository is gone, shortened only by `store prune --schedules --older-than <days>` (default kept); and make `schedule runs [--schedule <id>] [--repo <path>] [--workflow <w>] [--since <date>] [--outcome …] [--json]` read it read-only from any directory (C13), `--detail` adding each run's live status through its state root when it exists.

- GIVEN a removed schedule WHEN `store prune` runs without `--schedules` THEN its ledger rows remain

### TCK-B24 What a scheduled run adds elsewhere

WHEN a scheduled run is recorded THE engine SHALL write `origin: schedule` and `schedule: {schedule_id, fire_id, slot}` beside `parent` in the status document ([DUR](09-durability-and-resume.spec.md)); `origin`, `schedule` and the `caller` block of kind `scheduler` in `run_started` ([EVT](30-run-events.spec.md)); `origin` and `schedule_id` in the stats row and `run` sink row, as an HMAC in rows that leave the machine as for `repo_id` ([CST](34-central-run-stats.spec.md), [OBS](15-observability-and-cost.spec.md)); fires, outcomes, cost, skipped and missed counts per schedule in `report --by schedule`; in `attention` the pauses of scheduled runs with their schedule and the items `schedule_missed`, `schedule_paused`, `schedule_budget` and `schedule_refused` ([ADR-0040](../adr/0040-take-script-steps-attention-and-composition-from-archon.adr.md)); and for supervision no touch for a fire, the person's `add` and `edit` counted once per schedule as `designed` setup ([SUP](86-supervision-metrics.spec.md)), and supervision cost of the start `measured_zero` ([SCO](87-supervision-cost.spec.md)).

- GIVEN a scheduled run WHEN its stats row is sent to a sink THEN it carries `origin: schedule` and an HMAC of the `schedule_id`

## Acceptance criteria

- TCK-AC1 (TCK-B1, TCK-B14, TCK-B15): The same tick test suite (fake clock, scripted runs) passes unchanged on macOS, Linux and Windows under the `loop` and under direct `schedule tick` calls; each `os` entry `install` writes holds only the shim path and `schedule loop` or `schedule tick` (golden files), and `remove` leaves no trace
- TCK-AC2 (TCK-B2, TCK-B3, TCK-B7, TCK-B8, TCK-B9, TCK-B12, TCK-B16): With a fake clock, a tick that is killed at each of its steps and run again never starts a slot twice and records every slot as exactly one of started, skipped, missed or refused
- TCK-AC3 (TCK-B16, TCK-B21): The tick starts no model session and no process other than the engine's `run` or `orchestrate start` (process audit)
- TCK-AC4 (TCK-B4, TCK-B17, TCK-B24): A scheduled run's `run_started.caller` is `scheduler` (`attested`) with the schedule block; the token appears in no record, argv or step environment (scan test)
- TCK-AC5 (TCK-B13, TCK-B23): Every slot the tick handles yields exactly one ledger row (plus one `ended` row for a started fire), and removing a schedule, pruning a state root or `store prune` without `--schedules` deletes no ledger row
- TCK-AC6 (TCK-B5, TCK-B6, TCK-B18, TCK-B19, TCK-B20): Each accepted and refused credential kind per executor has a fixture: accepted kinds pass, others are refused at `add` and at a fire with the stated reason and no spend
- TCK-AC7 (TCK-B10, TCK-B11, TCK-B21, TCK-B22): The skill's eval cases ([LIF](18-lifecycle-and-evals.spec.md)) cover a clear phrase, each `needs` case of [SCH-B2](83-schedules.spec.md), the same schedule given in an exact format, a missing cost cap and an agent call without a person turn
- TCK-AC8 (TCK-B3, TCK-B14, TCK-B19): Probes P-SCH-1 (a systemd user unit started by the `os` adapter runs while the user is logged out, with and without lingering), P-SCH-2 (a loop started by a LaunchAgent reads a Claude Code `/login` sign-in from the Keychain while the screen is locked and after a restart before login), P-SCH-3 (Antigravity's cached sign-in works from a session home started by the loop or an `os` adapter, with P-AG-1) and P-SCH-4 (a loop's sleep on Windows, macOS and Linux ends within one loop interval after the machine wakes) are recorded before the controls they gate are marked `LIVE-PROVEN`

## Open questions

- Should the engine offer to enable lingering on Linux, or only name it? Until answered: it names it. Owner: owner, after P-SCH-1.
- May scheduled runs use the operator's Claude subscription through `setup-token`? Until answered: allowed as the products document it; the Agent SDK question of [R-005](../research/R-005-claude-agent-sdk-executor.rsrch.md) is separate. Owner: owner.
- Not built yet: orchestration targets (TCK-B9 and the `orchestrate` parts of TCK-B16 and TCK-B17) wait for orchestration, release 4 ([ADR-0132](../adr/0132-release-three-is-workflows-that-compose-run-in-parallel-and-grade-in-the-pipeline.adr.md)). Everything else of this spec is built (third-release plan R3-T5.2): the tick, the portable loop with the `host` and `os` adapters, the fire token, the credential check, the ledger, pipeline export and the skill; probes P-SCH-1 to P-SCH-4 have not run, so no control they gate is `LIVE-PROVEN` (TCK-AC8). Owner: engine owner.
