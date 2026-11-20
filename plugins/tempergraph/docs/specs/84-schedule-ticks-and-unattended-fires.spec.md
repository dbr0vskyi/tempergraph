---
title: Schedule ticks and unattended fires
type: component
status: review
prefix: TCK
adrs: [0095, 0099, 0085, 0035]
---

# Schedule ticks and unattended fires

## 1. Overview

A schedule ([SCH](83-schedules.spec.md)) must fire when nobody is at a terminal or in a conversation. This spec owns what makes it fire: the **tick**, one OS-agnostic, deterministic, model-free routine that decides what is due and starts it; the **triggers** that call the tick, of which the engine's own portable **loop** is the default and OS schedulers, pipelines and any other scheduler are optional adapters; the fire token that marks a scheduled run as the scheduler's; the credentials a run needs when nobody is present to sign in; what a fire leaves in the records; and the `tempergraph:schedule` skill ([ADR-0095](../adr/0095-a-model-free-tick-behind-os-agnostic-triggers.adr.md)).

All scheduling logic (slots, zones, catch-up, overlap, budgets, idempotence) lives in the tick and reads only the engine's files, so it behaves the same on macOS, Linux and Windows and under any trigger. A trigger only decides when the tick is called; it carries no rule. The tick is a sibling of the orchestration supervisor ([ORC](45-orchestration.spec.md)): both start work only through the engine's own verbs and answer no gate (contract C18). A schedule whose target is an orchestration fires `orchestrate start`, which starts that orchestration's own supervisor.

## 2. Contract

### 2.1 Triggers

The tick (§2.2) is the one contract every trigger calls: `tempergraph schedule tick`. It is idempotent and lock-guarded, so it is safe at any frequency, from several triggers at once, and after any gap; a trigger that calls it late only makes slots late, and the catch-up rule decides what then fires ([SCH §2.5.1](83-schedules.spec.md)).

| Trigger | What calls the tick | OS-specific | Survives a reboot | Timing |
|---|---|---|---|---|
| `loop` (default) | `schedule loop [--detach]`: a portable engine process in the engine's interpreter. It runs the tick, then sleeps until the earlier of the next slot of any schedule and 60 s, and repeats. It holds nothing in memory between ticks; one per user (lock `schedules/loop.lock`); `schedule loop --stop` ends it | No | Only if something starts it again: a person, the plugin hook below, or an `os` adapter | Seconds after the slot |
| `host` (optional) | The plugin's Claude Code `SessionStart` hook starts `schedule loop --detach` when `schedule.loop_autostart` is on and none is running ([SHL §2.2](19-plugin-shell.spec.md)) | No | Yes, from the first session after it | As `loop` |
| `os` (optional) | `schedule trigger install --os` writes one per-user autostart entry that starts the loop at login and restarts it if it exits: a LaunchAgent on macOS, a systemd user unit on Linux, a Task Scheduler task on Windows; where none exists, a crontab line that runs `schedule tick` every 5 minutes | Only the entry it writes | Yes | As `loop`, or the cron interval |
| `external` (optional) | Any scheduler the owner already runs calls `schedule tick`: cron, a CI schedule, a Kubernetes CronJob, a cloud routine, a desktop task that runs a shell command | Belongs to that scheduler | As that scheduler | That scheduler's interval |

- **The default needs no OS integration.** `schedule add` checks that some trigger is alive (a loop's lock, an `os` entry, or a tick heartbeat within three intervals) and, when none is, offers `schedule loop --detach` and names the optional adapters once.
- **Adapters hold constants only.** An `os` entry or a hook runs the shim's absolute path with `schedule loop` or `schedule tick` and nothing else: no shell, no person-typed value, no environment value of its own ([SEC §2.1](14-security.spec.md)). `install` is idempotent and rewrites an entry whose shim path changed after `update` ([UPD](60-engine-update.spec.md)); `schedule trigger status` lists every trigger seen (loop, hook, entries, external ticks from the heartbeat); `remove` deletes what `install` wrote.
- **Sleep and power-off are the trigger's limit, not the tick's.** While the machine sleeps or is off, nothing calls the tick; on wake the loop's sleep ends late or the restarted loop ticks at once, and the catch-up rule applies. Whether an `os` entry runs while the user is logged out is per platform (P-SCH-1, P-SCH-4) and only matters for that adapter.

### 2.2 The tick

| Step | Rule |
|---|---|
| 1 Lock | Take `~/.tempergraph/schedules/tick.lock` without waiting; if held, exit 0 at once. One tick runs at a time per user |
| 2 Heartbeat | Write `schedules/tick.json`: `last_tick_at`, engine version, trigger kind, interval, and per executor the credential kinds the tick's environment resolves (§2.4, presence only) |
| 3 Settle ended fires | For every `started` fire with no `ended` event, read its thread's status (or orchestration status); when ended, append `ended` with exit, outcome and cost, and update the failure count ([SCH §2.5.3](83-schedules.spec.md)) |
| 4 Find due slots | For each `active` schedule in order of next slot: the slots passed since its last handled slot, as UTC instants from the canonical When ([SCH §2.3.4](83-schedules.spec.md)); apply `catch_up` and the window; record `missed` ones |
| 5 Decide each slot | In order: schedule still `active`; overlap against live fires ([SCH §2.5.2](83-schedules.spec.md)); period budget ([SCH §2.5.4](83-schedules.spec.md)); then the preflight: `run --check` (or `orchestrate validate`) with the schedule's options, which includes the credential check of §2.4; a refusal is a `refused` event and a failure, with no spend |
| 6 Start | Append `started` with the thread id, then launch the engine's `run` (or `orchestrate start`) detached, in its own process group, with the fire token (§2.3), `--schedule <fire_id>` and a hand-off ticket carrying the rendered request and inputs ([SEC §2.1](14-security.spec.md)); the tick never waits for the run |
| 7 Bound | At most 4 starts per tick and 20 s of wall time; what is left waits for the next tick, oldest slot first |
| 8 Release | Release the lock and exit 0. An unhandled error is logged in the engine code log ([LOS §2.3](33-local-observability-store.spec.md)), the heartbeat records it, and the next tick starts over |

The tick reads each schedule's repository through its state root, so a schedule in a repository that was moved or deleted is `refused` (`repo_missing`) at its next slot and, after the failure count, paused.

### 2.3 The fire token and the caller

Each schedule has a random **fire token** made at `add`; its SHA-256 is the entry's `token_digest`. The tick passes the token to the run it starts in `TEMPERGRAPH_SCHEDULE_TOKEN`, with `--schedule <fire_id>` on argv. The run's caller classification ([PRV §2.3](85-caller-provenance.spec.md)) checks the digest against the entry the fire id names and records caller kind `scheduler`, confidence `attested`, host `schedule`, with a `schedule` block `{schedule_id, fire_id, slot, created_by}` where `created_by` is the entry's `created.caller` kind and decider. A token that does not match is refused (`schedule_token_invalid`) before anything is written. The token is never on argv, in a record or in a step session's environment ([EXI §2.3](10-executor-interface.spec.md)), as for the supervisor's token ([ORC-B17](45-orchestration.spec.md)).

For an orchestration target, the tick's `orchestrate start` is classified `scheduler`; the supervisor's children are `orchestrator` as always, and their status shows both `parent` and the orchestration's `schedule`.

### 2.4 Unattended credentials

A fire runs in the trigger's environment, not in the person's shell: no shell profile, no agent host, no keychain prompt anyone can answer. Credentials for scheduled runs come from the operator's credentials profile under `~/.tempergraph/config/` (the profile the executors already read, [ECC](11-executor-claude-code.spec.md), [EAG](12-executor-antigravity.spec.md)), never from a value in the trigger entry. Each executor declares the credential kinds it can use unattended, a capability like any other (C15).

| Credential kind | Meaning |
|---|---|
| `api_key` | An API key in the profile (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`) or an `apiKeyHelper` command |
| `cloud` | Bedrock, Vertex or Foundry credentials resolvable without a person |
| `oauth_token` | A long-lived token made for scripts, such as Claude Code's `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` (one year, model requests only, [R-095](../research/R-095-scheduling-runs-prior-art-and-gaps.rsrch.md) F18) |
| `interactive_login` | A person's sign-in cached by the product (Claude Code `/login`, Antigravity's login) |

| Executor | Accepted unattended | Notes |
|---|---|---|
| `claude` | `api_key`, `cloud`, `oauth_token`; `interactive_login` with warning `credential_may_expire` | A judge launched with `--bare` does not read `CLAUDE_CODE_OAUTH_TOKEN` (F18), so a schedule whose judges run `--bare` on this executor needs `api_key` or `cloud` for them, or is refused `judge_credential`; a cached `/login` may expire or be unreadable from a background job (P-SCH-2) |
| `agent-sdk` | `api_key`, `cloud` | As [EAS §4](21-executor-agent-sdk.spec.md) |
| `messages-api` | `api_key`, `cloud` | As [EMA §2.7](20-executor-messages-api.spec.md) |
| `antigravity` | `api_key` (`GEMINI_API_KEY`) | `interactive_login` refused `credential_unattended` until P-SCH-3 confirms it |

At `add` and `edit`, the check resolves each executor and judge binding of the run and compares the kinds the profile provides with the table; at each fire the preflight does it again in the tick's environment. A missing credential at a fire is `refused` with reason `credential`, spends nothing, raises an attention item `schedule_refused` once until the next successful fire, and counts as a failure. A check never makes a model call (C13): it tests presence, form and, where the product offers one, a model-free account call.

### 2.5 Pipelines

A pipeline has its own clock and no tick. `schedule export <id> --for github-actions|gitlab-ci|crontab` prints a snippet the owner commits to the pipeline's configuration; the engine keeps nothing for it.

| Item | Rule |
|---|---|
| Timing | The rule as five-field cron in UTC. A calendar rule in a zone with daylight saving cannot be one UTC cron line; export refuses it (`export_needs_utc`) unless `--pin-offset` accepts today's offset, which the snippet states in a comment |
| Command | `tempergraph run <workflow> …` with the schedule's options, `--run-cost-cap`, `--label`, and `--caller pipeline`; the request comes from a file in the repository, never inline |
| Overlap | The snippet sets the system's own concurrency group so a new job waits for or skips a running one, matching `overlap` where the system can |
| Caller | `pipeline`, host `ci:<system>` ([PRV-B7](85-caller-provenance.spec.md)), `origin: ci`, and `schedule: {schedule_id, declared: true}`: the tie to the schedule is the pipeline's word, not attested |
| Credentials | Pipeline secrets; `api_key` or `cloud` only |

### 2.6 The schedule skill

`tempergraph:schedule` ships in the engine plugin ([SHL](19-plugin-shell.spec.md)). It is optional: every schedule can be made with the CLI and exact formats alone, with no model anywhere. The skill drives the verbs and holds no state of its own.

| # | Step | Verbs |
|---|---|---|
| 1 | Find the workflow, request and inputs from the person's words, as the run driver does | `list`, `run --check` |
| 2 | Translate the person's words into an exact format (`--at`, `--rrule`, `--every`, `--cron`, `--tz`), or pass their phrase unchanged with `--when` when it is in the word grammar; the engine, not the skill, computes the slots | — |
| 3 | Show the engine's echo verbatim; ask about each `needs` reading in the person's terms | `schedule parse` |
| 4 | State the run cost cap and, for a recurrence, propose a period budget from `stats --projection` ([CST §2.5](34-central-run-stats.spec.md)) | `stats` |
| 5 | Ask for one yes on the echo, the caps and the policies, then save | `schedule add … --yes --relayed` |
| 6 | Offer `schedule loop --detach` when `status` shows no live trigger, and name the optional adapters once | `schedule trigger status`, `schedule loop` |

The skill never fires a run from Claude Code's own scheduled tasks or `/loop`: they live as long as a session or the desktop app, catch up only the latest slot, and cost a model turn per fire ([R-095](../research/R-095-scheduling-runs-prior-art-and-gaps.rsrch.md) F10, F11). A person may still ask a desktop task to call the skill; the schedule it makes is fired by the tick.

**Who may create a schedule.** `add`, `edit`, `resume` and `fire` authorize unattended spend, so they need `decided_by: person` ([PRV §2.4](85-caller-provenance.spec.md)): a person at a terminal, or an agent with `--relayed` and a person turn in its host session within 10 minutes before the call (`turn_only` suffices; there is no pause word to name). Otherwise they are refused `schedule_not_by_person`. `pause`, `skip` and `remove` only lower spend and are accepted from any caller but `unknown`, recorded with their caller.

### 2.7 What a fire leaves in the records

**The scheduled-run ledger.** Every scheduled run on the machine is recorded in one place, whatever folder or repository its schedule was made in: `~/.tempergraph/schedules/runs.jsonl` in the home store ([LOS §2.2](33-local-observability-store.spec.md)), append-only, one row per fire, written by the tick and by `schedule fire` beside the schedule's own fire log.

| Field | Meaning |
|---|---|
| `fire_id`, `schedule_id`, `name`, `slot`, `fired_at` | The fire and its schedule ([SCH §2.6](83-schedules.spec.md)) |
| `target` | Workflow name or orchestration file name; the target repository's path and folder name |
| `created_from` | The folder and repository `schedule add` ran in |
| `outcome` | `started`, `skipped` (with reason), `missed`, `refused` (with reason); updated by an `ended` row with exit, run outcome and cost (`reported`, `estimated`, `incomplete`) |
| `thread_id`, `orchestration_id`, `state_root` | Where the run's own records live |
| `trigger` | `loop`, `host`, `os` or `external` |

The ledger holds metadata only, like the fire log. It outlives the things it points at: a removed schedule, a pruned or deleted state root and a moved repository leave their rows, and `schedule runs` shows such a row as `records_gone` rather than dropping it. Only `store prune --schedules --older-than <days>` shortens it (default: kept). `schedule runs [--schedule <id>] [--repo <path>] [--workflow <w>] [--since <date>] [--outcome …] [--json]` reads it from any directory, read-only (C13); `--detail` adds each run's live status through its state root when that still exists. The stats rows ([OBS §2.4](15-observability-and-cost.spec.md)) carry `schedule_id`, so a sink gives the same view across machines ([CST](34-central-run-stats.spec.md)).

**Elsewhere.**

| Where | What a scheduled run adds |
|---|---|
| Status document | `origin: schedule`; `schedule: {schedule_id, fire_id, slot}` beside `parent` ([DUR §2.2](09-durability-and-resume.spec.md)) |
| `run_started` | `origin`, `schedule`, and the `caller` block of kind `scheduler` ([EVT §2.2](30-run-events.spec.md), [PRV §2.1](85-caller-provenance.spec.md)) |
| Stats row and `run` sink row | `origin`, `schedule_id` (an HMAC in rows that leave the machine, as `repo_id`, [CST §2.4](34-central-run-stats.spec.md)) |
| `report` | `--by schedule`: fires, outcomes, cost, skipped and missed counts per schedule |
| `attention` | Pauses of scheduled runs with their schedule; and the schedule items `schedule_missed`, `schedule_paused`, `schedule_budget`, `schedule_refused` ([ADR-0040](../adr/0040-take-script-steps-attention-and-composition-from-archon.adr.md)) |
| Supervision | The fire is not a touch; the person's `add` and `edit` are counted once per schedule as `designed` setup, never per run ([SUP §2.2](86-supervision-metrics.spec.md)); supervision cost of the start is `measured_zero` ([SCO §2.3](87-supervision-cost.spec.md)) |

### 2.8 Probes

| Probe | Fact | Rests on it | State |
|---|---|---|---|
| P-SCH-1 | A systemd user unit started by the `os` adapter runs while the user is logged out, with and without lingering, on a stock distribution | The `os` adapter on Linux | not run |
| P-SCH-2 | A loop started by a LaunchAgent can read a Claude Code `/login` sign-in from the Keychain while the screen is locked, and after a restart before login | `interactive_login` warning on macOS | not run |
| P-SCH-3 | Antigravity's cached sign-in works from a session home started by the loop or an `os` adapter (with P-AG-1) | `interactive_login` for `antigravity` | not run |
| P-SCH-4 | A loop's sleep on Windows, macOS and Linux ends within one loop interval after the machine wakes (monotonic against wall clock) | `loop` timing after sleep | not run |

## 3. Behaviours

**TCK-B1 The default trigger is portable.** Given a machine on macOS, Linux or Windows with no trigger, when the person runs `schedule loop --detach` twice, then one loop runs (the second call reports it and exits 0), it writes no OS entry, and `schedule trigger status` shows `loop`, its pid and `last_tick_at`; `schedule trigger install --os` run twice leaves exactly one autostart entry that names the shim and `schedule loop` only.

**TCK-B2 One tick at a time.** Given a tick holding the lock, when a second tick starts, then it exits 0 within one second without reading any schedule.

**TCK-B3 Missed while asleep.** Given a laptop asleep from 08:50 to 09:40 with a schedule due at 09:00, when it wakes, then the loop's sleep ends and it ticks at once (on every OS, whatever the trigger), the tick finds the 09:00 slot inside its window and starts it, and the run's `run_started` shows `slot` 09:00 and a start time of about 09:40.

**TCK-B4 A pause reaches a person.** Given a scheduled run that pauses at 08:20 with nobody at the machine, when the run exits 3, then the `paused` lifecycle hook fires with the facts file ([CLI §2.2](17-engine-cli.spec.md)), `attention` lists the pause with `schedule digest` and the resume command, the monitor shows it, and nothing answers it but a person.

**TCK-B5 Credential missing at a fire.** Given a schedule created with an API key in the profile, when the key is removed and the next slot comes due, then the preflight refuses with reason `credential`, the fire log records `refused`, no session starts, and `attention` lists `schedule_refused` once with the executor named.

**TCK-B6 Judge credential.** Given a `claude` schedule whose profile holds only `CLAUDE_CODE_OAUTH_TOKEN` and whose judges launch with `--bare`, when it is added, then it is refused with `judge_credential`, naming an API key, an `apiKeyHelper` or cloud credentials as the fix.

**TCK-B7 Stale trigger.** Given active schedules and a `last_tick_at` older than three intervals, when `schedule list`, `status` or `attention` runs, then each shows `trigger_stale` with the age and the `schedule trigger status` command; read-only verbs still write nothing.

**TCK-B7a Several triggers.** Given the loop running and an `external` cron also calling `schedule tick` every 5 minutes, when a slot comes due, then it starts once: the second tick waits on nothing, finds the slot handled and exits 0.

**TCK-B7b One record of every scheduled run.** Given schedules made from `~/work/api`, `~/work/web` and the home folder, one of them since removed and the `web` state root deleted, when the person runs `schedule runs --since 2026-11-01` from any directory, then every fire of all three appears with its schedule, target repository, `created_from`, outcome and cost, the `web` rows marked `records_gone`.

**TCK-B8 Engine update between ticks.** Given an `update` that switches engines ([UPD](60-engine-update.spec.md)), when the next tick runs, then a running loop finishes its tick and re-executes itself through the shim, so the next tick runs on the new engine with the same schedules; an `os` entry is rewritten only if the shim path changed.

**TCK-B9 Orchestration target.** Given a schedule whose target is `release-train.orch.json`, when its slot fires, then the tick runs `orchestrate start` with the schedule's args, records the orchestration id as the fire's, and on later ticks settles the fire from `orchestrate status`; a live orchestration is a live fire for `overlap`.

**TCK-B10 Agent-made schedule.** Given a Claude Code session that runs `schedule add … --yes` with no `--relayed`, when it is checked, then it is refused `schedule_not_by_person`; with `--relayed` and a person turn 2 minutes earlier, it is saved with `created.caller` of kind `agent`, `decided_by: person`, `relay: turn_only`.

**TCK-B11 Export refuses a moving offset.** Given `every weekday at 8:00` in `Europe/Warsaw`, when `schedule export digest --for github-actions` runs, then it exits 2 `export_needs_utc`; with `--pin-offset` it prints `0 7 * * 1-5` and a comment that the job runs at 09:00 local in summer.

## 4. Error conditions

| Condition | Result |
|---|---|
| `trigger install --os` on a machine with no usable per-user scheduler | Exit 2 `no_os_scheduler`; the `loop` and `external` triggers still work |
| No live trigger when a schedule is added | Saved; a warning names `schedule loop --detach` |
| The trigger entry exists but points at a missing shim | `trigger status` reports `broken`; `install` rewrites it |
| Fire token missing or wrong | Exit 2 `schedule_token_invalid`, nothing written |
| `--schedule` given by hand without a token | Exit 2 `schedule_reserved` |
| Credential kind not accepted for an executor | Exit 2 `credential_unattended` at `add`; `refused` at a fire |
| Judge binding without a usable credential | Exit 2 `judge_credential` |
| A schedule verb that authorizes spend without a person decider | Exit 2 `schedule_not_by_person` |
| Tick exceeds 20 s | Remaining slots wait for the next tick; the heartbeat records `deferred` |
| Home store unwritable | The tick exits non-zero without starting anything; `trigger status` shows the last error |

## 5. Design notes

- **OS-agnostic core, optional adapters.** Every rule is in the tick and reads files only; the portable loop calls it the same way on every OS. OS schedulers differ in catch-up, sleep and logout behaviour ([R-095](../research/R-095-scheduling-runs-prior-art-and-gaps.rsrch.md) F12 to F16), so they are used, when the owner wants, only to start the loop at login; they never decide a slot ([ADR-0095](../adr/0095-a-model-free-tick-behind-os-agnostic-triggers.adr.md)).
- **Supervisor and tick stay apart.** The supervisor lives as long as its orchestration; the tick lives for seconds. Merging them would make every orchestration a resident process or every tick a supervisor.
- **Credentials are a capability.** A fire that would stall on a sign-in nobody can answer is refused before spend, like any undeclared capability (C15). The Claude Code CLI's `/login` is allowed with a warning because it often works on a desktop that stays signed in; the token made for scripts is the recommended path.
- **Deadlines.** The tick is the scheduler that [FLX §2.3](74-flow-extensions.spec.md) assumed the owner would bring: a later slice may let it apply overdue deadlines with `resume --apply-deadline`, recorded with caller `scheduler`. Not in the first slice.
- **Assumptions** (owner unavailable): a 60 s loop ceiling is enough to settle ended fires promptly; a 5-minute cron interval for the crontab fallback; four starts and 20 s per tick bound a burst after a long sleep; the 10-minute window for a relayed person turn matches the time a person takes to read an echo and say yes.

## 6. Acceptance criteria

- [ ] TCK-AC-1 The same tick test suite (fake clock, scripted runs) passes unchanged on macOS, Linux and Windows under the `loop` and under direct `schedule tick` calls; each `os` entry `install` writes holds only the shim path and `schedule loop` or `schedule tick` (golden files), and `remove` leaves no trace.
- [ ] TCK-AC-2 With a fake clock, a tick that is killed at each step of §2.2 and run again never starts a slot twice and records every slot as exactly one of started, skipped, missed or refused.
- [ ] TCK-AC-3 The tick starts no model session and no process other than the engine's `run` or `orchestrate start` (process audit).
- [ ] TCK-AC-4 A scheduled run's `run_started.caller` is `scheduler` (`attested`) with the schedule block; the token appears in no record, argv or step environment (scan test).
- [ ] TCK-AC-4a Every slot the tick handles yields exactly one ledger row (plus one `ended` row for a started fire), and removing a schedule, pruning a state root or `store prune` without `--schedules` deletes no ledger row.
- [ ] TCK-AC-5 Each row of the credential tables has a fixture: accepted kinds pass, others are refused at `add` and at a fire with the stated reason and no spend.
- [ ] TCK-AC-6 The skill's eval cases ([LIF §5](18-lifecycle-and-evals.spec.md)) cover a clear phrase, each `needs` row of [SCH §2.3.5](83-schedules.spec.md), the same schedule given in an exact format, a missing cost cap and an agent call without a person turn.

## Open questions

| Question | Owner |
|---|---|
| Should the engine offer to enable lingering on Linux, or only name it? Naming it is assumed. | Owner, after P-SCH-1 |
| May scheduled runs use the operator's Claude subscription through `setup-token`? The design allows it as the products document it; the Agent SDK question of [R-005](../research/R-005-claude-agent-sdk-executor.rsrch.md) is separate. | Owner |

## References

[SCH](83-schedules.spec.md) · [R-095](../research/R-095-scheduling-runs-prior-art-and-gaps.rsrch.md) · [ORC](45-orchestration.spec.md) · [PRV](85-caller-provenance.spec.md) · [SEC](14-security.spec.md) · [EXI](10-executor-interface.spec.md) · [UPD](60-engine-update.spec.md) · [SHL](19-plugin-shell.spec.md)
