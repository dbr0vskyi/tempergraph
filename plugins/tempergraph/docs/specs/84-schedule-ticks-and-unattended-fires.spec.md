---
title: Schedule ticks and unattended fires
type: component
status: review
prefix: TCK
adrs: [0095, 0099, 0085, 0035]
---

# Schedule ticks and unattended fires

## 1. Overview

A schedule ([SCH](83-schedules.spec.md)) must fire when no terminal, no conversation and no engine process is open. This spec owns what makes it fire: one **per-user OS trigger** per machine that runs `tempergraph schedule tick` every few minutes, the tick's algorithm, the fire token that marks a scheduled run as the scheduler's, the credentials a run needs when nobody is present to sign in, what a pipeline does instead of a tick, and the `tempergraph:schedule` skill that turns a person's words into a confirmed schedule ([ADR-0095](../adr/0095-one-per-user-os-trigger-runs-a-model-free-tick.adr.md)).

The tick holds no state in memory and stays running for seconds, not hours. It is a sibling of the orchestration supervisor ([ORC](45-orchestration.spec.md)): both are model-free engine processes that start work only through the engine's own verbs and answer no gate (contract C18). They do not depend on each other: a schedule whose target is an orchestration fires `orchestrate start`, which starts that orchestration's own supervisor, and the tick goes back to sleep.

## 2. Contract

### 2.1 The OS trigger

`schedule trigger install [--every 1m|2m|5m|10m|15m]` writes one entry in the platform's per-user scheduler; `add` offers it when none is installed; `status` reports it; `remove` deletes it. The entry runs the shim's absolute path with the constant arguments `schedule tick` and nothing else: no shell, no person-typed value, no environment value of its own ([SEC §2.1](14-security.spec.md)). Default interval 5 minutes, so a slot fires within one interval after its time.

| Platform | Entry | Runs after sleep | Runs while logged out | Notes |
|---|---|---|---|---|
| macOS | LaunchAgent `~/Library/LaunchAgents/dev.tempergraph.tick.plist`, `StartCalendarInterval` at every interval minute, `RunAtLoad` true, `ProcessType` Background | Yes: a due calendar job runs on wake ([R-095](../research/R-095-scheduling-runs-prior-art-and-gaps.rsrch.md) F14) | No: a LaunchAgent runs in the user's session | Keychain access while locked is P-SCH-2 |
| Linux (systemd) | User units `tempergraph-tick.service` and `.timer`, `OnCalendar=*:0/5`, `Persistent=true`, `AccuracySec=30s` | Yes: one activation for elapses missed while asleep or off (F12) | Only if the user manager runs: P-SCH-1 | `schedule trigger status` names `loginctl enable-linger` as the owner's choice, never runs it |
| Linux (no user systemd) | One line in the user's crontab, marked with a comment the engine owns | No catch-up; the engine's own rule covers it at the next tick | As cron allows | Fallback only |
| Windows | Task Scheduler task `tempergraph\tick` for the current user, repeated every interval indefinitely, `StartWhenAvailable`, "run only when user is logged on", no elevation | Yes, after the scheduler's queue delay (F15) | No | |

The OS's own catch-up only makes a tick run soon after a wake; which slots fire is always the engine's rule ([SCH §2.5.1](83-schedules.spec.md)). `install` is idempotent and rewrites an entry whose shim path changed after `update` ([UPD](60-engine-update.spec.md)); `update` re-checks the entry. The trigger writer is a sanctioned launch site with constants only.

### 2.2 The tick

| Step | Rule |
|---|---|
| 1 Lock | Take `~/.tempergraph/schedules/tick.lock` without waiting; if held, exit 0 at once. One tick runs at a time per user |
| 2 Heartbeat | Write `schedules/tick.json`: `last_tick_at`, engine version, trigger kind, interval, and per executor the credential kinds the tick's environment resolves (§2.4, presence only) |
| 3 Settle ended fires | For every `started` fire with no `ended` event, read its thread's status (or orchestration status); when ended, append `ended` with exit, outcome and cost, and update the failure count ([SCH §2.5.3](83-schedules.spec.md)) |
| 4 Find due slots | For each `active` schedule in order of next slot: the slots passed since its last handled slot, as UTC instants from the canonical When ([SCH §2.3.3](83-schedules.spec.md)); apply `catch_up` and the window; record `missed` ones |
| 5 Decide each slot | In order: schedule still `active`; overlap against live fires ([SCH §2.5.2](83-schedules.spec.md)); period budget ([SCH §2.5.4](83-schedules.spec.md)); then the preflight: `run --check` (or `orchestrate validate`) with the schedule's options, which includes the credential check of §2.4; a refusal is a `refused` event and a failure, with no spend |
| 6 Start | Append `started` with the thread id, then launch the engine's `run` (or `orchestrate start`) detached, in its own process group, with the fire token (§2.3), `--schedule <fire_id>` and a hand-off ticket carrying the rendered request and inputs ([SEC §2.1](14-security.spec.md)); the tick never waits for the run |
| 7 Bound | At most 4 starts per tick and 20 s of wall time; what is left waits for the next tick, oldest slot first |
| 8 Release | Release the lock and exit 0. An unhandled error is logged in the engine code log ([LOS §2.3](33-local-observability-store.spec.md)), the heartbeat records it, and the next tick starts over |

The tick reads each schedule's repository through its state root, so a schedule in a repository that was moved or deleted is `refused` (`repo_missing`) at its next slot and, after the failure count, paused.

### 2.3 The fire token and the caller

Each schedule has a random **fire token** made at `add`; its SHA-256 is the entry's `token_digest`. The tick passes the token to the run it starts in `TEMPERGRAPH_SCHEDULE_TOKEN`, with `--schedule <fire_id>` on argv. The run's caller classification ([PRV §2.3](85-caller-provenance.spec.md)) checks the digest against the entry the fire id names and records caller kind `scheduler`, confidence `attested`, host `schedule`, with a `schedule` block `{schedule_id, fire_id, slot, created_by}` where `created_by` is the entry's `created.caller` kind and decider. A token that does not match is refused (`schedule_token_invalid`) before anything is written. The token is never on argv, in a record or in a step session's environment ([EXI §2.3](10-executor-interface.spec.md)), as for the supervisor's token ([ORC-B17](45-orchestration.spec.md)).

For an orchestration target, the tick's `orchestrate start` is classified `scheduler`; the supervisor's children are `orchestrator` as always, and their status shows both `parent` and the orchestration's `schedule`.

### 2.4 Unattended credentials

A fire runs in the OS trigger's environment, not in the person's shell: no shell profile, no agent host, no keychain prompt anyone can answer. Credentials for scheduled runs come from the operator's credentials profile under `~/.tempergraph/config/` (the profile the executors already read, [ECC](11-executor-claude-code.spec.md), [EAG](12-executor-antigravity.spec.md)), never from a value in the trigger entry. Each executor declares the credential kinds it can use unattended, a capability like any other (C15).

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

`tempergraph:schedule` ships in the engine plugin ([SHL](19-plugin-shell.spec.md)). It drives the verbs and holds no state of its own.

| # | Step | Verbs |
|---|---|---|
| 1 | Find the workflow, request and inputs from the person's words, as the run driver does | `list`, `run --check` |
| 2 | Write a phrase of the grammar from the person's words, keeping their own words where the grammar accepts them | — |
| 3 | Show the engine's echo verbatim; ask about each `needs` reading in the person's terms | `schedule parse` |
| 4 | State the run cost cap and, for a recurrence, propose a period budget from `stats --projection` ([CST §2.5](34-central-run-stats.spec.md)) | `stats` |
| 5 | Ask for one yes on the echo, the caps and the policies, then save | `schedule add … --yes --relayed` |
| 6 | Offer `schedule trigger install` when `status` shows no trigger, and name the platform's limits (logged-out, sleep) once | `schedule trigger status` |

The skill never fires a run from Claude Code's own scheduled tasks or `/loop`: they live as long as a session or the desktop app, catch up only the latest slot, and cost a model turn per fire ([R-095](../research/R-095-scheduling-runs-prior-art-and-gaps.rsrch.md) F10, F11). A person may still ask a desktop task to call the skill; the schedule it makes is fired by the tick.

**Who may create a schedule.** `add`, `edit`, `resume` and `fire` authorize unattended spend, so they need `decided_by: person` ([PRV §2.4](85-caller-provenance.spec.md)): a person at a terminal, or an agent with `--relayed` and a person turn in its host session within 10 minutes before the call (`turn_only` suffices; there is no pause word to name). Otherwise they are refused `schedule_not_by_person`. `pause`, `skip` and `remove` only lower spend and are accepted from any caller but `unknown`, recorded with their caller.

### 2.7 Probes

| Probe | Fact | Rests on it | State |
|---|---|---|---|
| P-SCH-1 | A systemd user timer fires while the user is logged out, with and without lingering, on a stock distribution | The "logged out" cell for Linux | not run |
| P-SCH-2 | A LaunchAgent tick can read a Claude Code `/login` sign-in from the Keychain while the screen is locked, and after a restart before login | `interactive_login` warning on macOS | not run |
| P-SCH-3 | Antigravity's cached sign-in works from a session home started by an OS trigger (with P-AG-1) | `interactive_login` for `antigravity` | not run |
| P-SCH-4 | Windows Task Scheduler runs a missed repetition after resume from sleep within its queue delay | The "after sleep" cell for Windows | not run |

## 3. Behaviours

**TCK-B1 Install once.** Given a machine with no trigger, when `schedule trigger install` runs twice, then exactly one platform entry exists, it names the shim's absolute path and `schedule tick` only, and `status` shows its kind, interval and `last_tick_at`.

**TCK-B2 One tick at a time.** Given a tick holding the lock, when a second tick starts, then it exits 0 within one second without reading any schedule.

**TCK-B3 Missed while asleep.** Given a laptop asleep from 08:50 to 09:40 with a schedule due at 09:00, when it wakes, then the OS runs one tick (launchd on wake, systemd `Persistent`, Windows `StartWhenAvailable`), the tick finds the 09:00 slot inside its window and starts it, and the run's `run_started` shows `slot` 09:00 and a start time of about 09:40.

**TCK-B4 A pause reaches a person.** Given a scheduled run that pauses at 08:20 with nobody at the machine, when the run exits 3, then the `paused` lifecycle hook fires with the facts file ([CLI §2.2](17-engine-cli.spec.md)), `attention` lists the pause with `schedule digest` and the resume command, the monitor shows it, and nothing answers it but a person.

**TCK-B5 Credential missing at a fire.** Given a schedule created with an API key in the profile, when the key is removed and the next slot comes due, then the preflight refuses with reason `credential`, the fire log records `refused`, no session starts, and `attention` lists `schedule_refused` once with the executor named.

**TCK-B6 Judge credential.** Given a `claude` schedule whose profile holds only `CLAUDE_CODE_OAUTH_TOKEN` and whose judges launch with `--bare`, when it is added, then it is refused with `judge_credential`, naming an API key, an `apiKeyHelper` or cloud credentials as the fix.

**TCK-B7 Stale trigger.** Given active schedules and a `last_tick_at` older than three intervals, when `schedule list`, `status` or `attention` runs, then each shows `trigger_stale` with the age and the `schedule trigger status` command; read-only verbs still write nothing.

**TCK-B8 Engine update between ticks.** Given an `update` that switches engines ([UPD](60-engine-update.spec.md)), when the next tick runs, then the shim starts the new engine, which reads the same schedules; the entry is rewritten only if the shim path changed.

**TCK-B9 Orchestration target.** Given a schedule whose target is `release-train.orch.json`, when its slot fires, then the tick runs `orchestrate start` with the schedule's args, records the orchestration id as the fire's, and on later ticks settles the fire from `orchestrate status`; a live orchestration is a live fire for `overlap`.

**TCK-B10 Agent-made schedule.** Given a Claude Code session that runs `schedule add … --yes` with no `--relayed`, when it is checked, then it is refused `schedule_not_by_person`; with `--relayed` and a person turn 2 minutes earlier, it is saved with `created.caller` of kind `agent`, `decided_by: person`, `relay: turn_only`.

**TCK-B11 Export refuses a moving offset.** Given `every weekday at 8:00` in `Europe/Warsaw`, when `schedule export digest --for github-actions` runs, then it exits 2 `export_needs_utc`; with `--pin-offset` it prints `0 7 * * 1-5` and a comment that the job runs at 09:00 local in summer.

## 4. Error conditions

| Condition | Result |
|---|---|
| No per-user scheduler available (no launchd, systemd user manager, cron or Task Scheduler access) | `trigger install` exits 2 `no_os_scheduler`; `add` still saves and warns that nothing will fire |
| The trigger entry exists but points at a missing shim | `trigger status` reports `broken`; `install` rewrites it |
| Fire token missing or wrong | Exit 2 `schedule_token_invalid`, nothing written |
| `--schedule` given by hand without a token | Exit 2 `schedule_reserved` |
| Credential kind not accepted for an executor | Exit 2 `credential_unattended` at `add`; `refused` at a fire |
| Judge binding without a usable credential | Exit 2 `judge_credential` |
| A schedule verb that authorizes spend without a person decider | Exit 2 `schedule_not_by_person` |
| Tick exceeds 20 s | Remaining slots wait for the next tick; the heartbeat records `deferred` |
| Home store unwritable | The tick exits non-zero without starting anything; `trigger status` shows the last error |

## 5. Design notes

- **A tick, not a daemon.** A resident engine service would itself need an OS entry to start and restart it, would hold state that an update or a crash loses, and would run model-free code all day for a handful of fires. A tick per interval costs one short process and recovers from anything by reading files ([ADR-0095](../adr/0095-one-per-user-os-trigger-runs-a-model-free-tick.adr.md)).
- **Supervisor and tick stay apart.** The supervisor lives as long as its orchestration; the tick lives for seconds. Merging them would make every orchestration a resident process or every tick a supervisor.
- **Credentials are a capability.** A fire that would stall on a sign-in nobody can answer is refused before spend, like any undeclared capability (C15). The Claude Code CLI's `/login` is allowed with a warning because it often works on a desktop that stays signed in; the token made for scripts is the recommended path.
- **Deadlines.** The tick is the scheduler that [FLX §2.3](74-flow-extensions.spec.md) assumed the owner would bring: a later slice may let it apply overdue deadlines with `resume --apply-deadline`, recorded with caller `scheduler`. Not in the first slice.
- **Assumptions** (owner unavailable): a 5-minute default interval is precise enough for workflow runs; four starts and 20 s per tick bound a burst after a long sleep; the 10-minute window for a relayed person turn matches the time a person takes to read an echo and say yes.

## 6. Acceptance criteria

- [ ] TCK-AC-1 On each platform, the entry `install` writes holds only the shim path and `schedule tick` (golden files), and `remove` leaves no trace.
- [ ] TCK-AC-2 With a fake clock, a tick that is killed at each step of §2.2 and run again never starts a slot twice and records every slot as exactly one of started, skipped, missed or refused.
- [ ] TCK-AC-3 The tick starts no model session and no process other than the engine's `run` or `orchestrate start` (process audit).
- [ ] TCK-AC-4 A scheduled run's `run_started.caller` is `scheduler` (`attested`) with the schedule block; the token appears in no record, argv or step environment (scan test).
- [ ] TCK-AC-5 Each row of the credential tables has a fixture: accepted kinds pass, others are refused at `add` and at a fire with the stated reason and no spend.
- [ ] TCK-AC-6 The skill's eval cases ([LIF §5](18-lifecycle-and-evals.spec.md)) cover a clear phrase, each `needs` row of [SCH §2.3.4](83-schedules.spec.md), a missing cost cap and an agent call without a person turn.

## Open questions

| Question | Owner |
|---|---|
| Should the engine offer to enable lingering on Linux, or only name it? Naming it is assumed. | Owner, after P-SCH-1 |
| May scheduled runs use the operator's Claude subscription through `setup-token`? The design allows it as the products document it; the Agent SDK question of [R-005](../research/R-005-claude-agent-sdk-executor.rsrch.md) is separate. | Owner |

## References

[SCH](83-schedules.spec.md) · [R-095](../research/R-095-scheduling-runs-prior-art-and-gaps.rsrch.md) · [ORC](45-orchestration.spec.md) · [PRV](85-caller-provenance.spec.md) · [SEC](14-security.spec.md) · [EXI](10-executor-interface.spec.md) · [UPD](60-engine-update.spec.md) · [SHL](19-plugin-shell.spec.md)
