# R-095 Scheduling runs: what the design and the reference have, how schedulers behave, and what unattended fires need

## Problem statement

The owner asked on 2026-11-20: "Design schedule command with human readable dates and ability to schedule once or regularly to run a workflow."

The request is read as a `tempergraph schedule` command, with a matching skill, that starts a registered workflow (or a saved orchestration) at a time a person states in words, such as "tomorrow at 9", "in 2 hours", "every weekday at 8:00" or "every Monday", once or on a recurring basis. To design it, this note answers:

1. What the design set already says about schedules and triggers, and what shape a model-free schedule takes.
2. How the schedulers a schedule could rest on behave: the operating-system schedulers on the three desktop platforms, Claude Code's own scheduled tasks, and pipeline schedules.
3. What a run that starts with nobody present needs from each of the four executors' sign-ins, from cost caps, from pauses and from the records of who called.
4. What grammar for dates and recurrences can be parsed without a model and echoed back exactly.

The work was done standalone, without questions to the owner; assumptions are recorded in [ADR-0095](../adr/0095-one-per-user-os-trigger-runs-a-model-free-tick.adr.md) to [ADR-0099](../adr/0099-a-scheduled-fire-is-an-attested-caller-with-a-capped-unattended-spend.adr.md).

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S4 | This design on `main` after PR 13: R-006 deferral of the scheduler, ADR-0021, SEC §2.1 ticket row, FLX deadlines, ORC supervisor, PRV caller kinds, RST layers, OSK open question on schedules | Design set | [specs](../specs/00-overview.spec.md) |
| S5 | Claude Code, "Run prompts on a schedule" (session-scoped tasks, `/loop`, cron tools) | Official docs | https://code.claude.com/docs/en/scheduled-tasks.md |
| S6 | Claude Code, "Schedule recurring tasks in Claude Code Desktop" | Official docs | https://code.claude.com/docs/en/desktop-scheduled-tasks.md |
| S7 | Claude Code, "Authentication": credential order, `claude setup-token`, storage | Official docs | https://code.claude.com/docs/en/authentication.md |
| S8 | systemd 257, `systemd.timer(5)`: `Persistent=`, `RandomizedDelaySec=`, `AccuracySec=`, `OnCalendar=` | Official manual | https://www.freedesktop.org/software/systemd/man/257/systemd.timer.html |
| S9 | Apple Developer Forums thread 52369, quoting Apple's Daemons and Services Programming Guide on `StartCalendarInterval` | Vendor forum quoting vendor guide | https://developer.apple.com/forums/thread/52369 |
| S10 | Microsoft Learn, `TaskSettings.StartWhenAvailable` | Official docs | https://learn.microsoft.com/en-us/windows/win32/TaskSchd/tasksettings-startwhenavailable |
| S11 | Research notes [R-001](R-001-claude-code-cli-headless.rsrch.md), [R-002](R-002-antigravity-cli-headless.rsrch.md), [R-004](R-004-anthropic-messages-api-executor.rsrch.md), [R-005](R-005-claude-agent-sdk-executor.rsrch.md): each executor's credentials | Design set | research/ |
| S12 | IETF RFC 5545 (iCalendar), §3.3.10 RECUR and §3.3.5 DATE-TIME (local times in a gap or an overlap); Python `zoneinfo` (PEP 615) and `dateutil.rrule` | Standard, library docs | https://www.rfc-editor.org/rfc/rfc5545 , https://peps.python.org/pep-0615/ |

## Key findings

### What the design and the reference already have

| # | Finding | Confidence |
|---|---|---|
| F1 | Recurring runs can rest on **one per-user OS trigger** that runs a tick every 15 minutes while the engine decides what is due (the latest slot has passed, no attempt is live, failures are within the retry count); a slot missed while the machine slept then runs at the next tick, and nothing starts twice. | inferred |
| F2 | A trigger per schedule would drift from the engine's store, and Claude Code's own cron lives only as long as a session (F10). A recurring run also needs a live record of each fire, or nobody can see what fired. | inferred |
| F3 | A schedule target can also be a **declared program**: a deterministic scan that decides whether a run is needed, started detached with no shell, its exit recorded like a run, the due rule and catch-up equal to workflow schedules; an undeclared name is refused. | inferred |
| F4 | A detached scheduled run gets its data through a hand-off ticket: this design's SEC-B5, SEC-B6 already lists "schedule" among the ticket users, though no spec owns a schedule (S4). | confirmed |
| F5 | This design deferred the scheduler: R-006 marks "Token-free schedule for declared programs" deferred ("no scheduler in the first release") and asks the owner whether a recurring scheduler is in scope; ADR-0021 defers "batch, schedule or multi-repository orchestration"; OSK defers a recurring schedule for orchestration templates "with schedules" (S4). | confirmed |
| F6 | FLX deadlines need no resident process: "an owner who wants deadlines to act on time schedules `resume --apply-deadline` from their own scheduler" (S4). A wait timeout that acts on time therefore needs a scheduler. | confirmed |
| F7 | The orchestration supervisor is a detached, model-free process **per orchestration**, held by a file lock, which exits when its orchestration ends; it is not a resident engine service (S4, ORC §2.1). | confirmed |
| F8 | PRV lists `pipeline` for "a cron job" and has no kind for a schedule the engine itself fires; `origin` in the status document has no `schedule` value (S4). | confirmed |
| F9 | `mode: unattended` is reserved and refused for orchestrations until a delegation policy exists; every pause stays with a person (ADR-0039, S4). | confirmed |

### How the candidate schedulers behave

| # | Finding | Confidence |
|---|---|---|
| F10 | Claude Code's session-scoped tasks fire only while the session runs and is idle; recurring tasks expire after 7 days; a missed interval fires once when the session becomes idle, not once per missed interval; recurring tasks fire up to 30 minutes late (half the interval below an hour) by design; times are local (S5). | supported (S5) |
| F11 | Claude Code Desktop's local scheduled tasks fire only while the app is open and the computer awake; on start or wake it runs exactly one catch-up for the most recently missed time within seven days and discards older ones; a tool needing approval stalls the run until a person approves (S6). Each fire is a model session. | supported (S6) |
| F12 | systemd `Persistent=true` (calendar timers only) stores the last trigger time and triggers once at activation if at least one elapse was missed; several elapses during one sleep give a single activation; the catch-up is still subject to `RandomizedDelaySec=` (S8). | supported (S8) |
| F13 | The user service manager "is generally started on first login only" (S8). Whether a per-user timer fires while the user is logged out depends on lingering, which the page does not describe. | uncertain |
| F14 | launchd `StartCalendarInterval`: a job due while the Mac sleeps runs on wake; a job due while it is off does not run until the next due time (S9). Whether several missed fires coalesce is not stated. | supported (S9) |
| F15 | Windows `StartWhenAvailable` lets Task Scheduler start a task after a missed time, queued with a default 10-minute delay (S10). | supported (S10) |
| F16 | Every OS scheduler has its own catch-up rule (F12, F14, F15) and none knows whether the previous run is still live or paused. A tick that decides from the engine's own store gives the same rule on every platform (F1). | inferred |
| F17 | Pipeline schedules (for example a CI system's cron trigger) run in UTC on the provider's clock, and delays under load are normal for such services; the engine cannot see a pipeline's slots it was not started for. | inferred |

### What an unattended fire needs

| # | Finding | Confidence |
|---|---|---|
| F18 | Claude Code accepts, for scripts with no browser, `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` (a one-year token that can only make model requests and is not saved by the command), `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, an `apiKeyHelper`, or cloud-provider credentials; a `/login` subscription sign-in lives in the macOS Keychain or `~/.claude/.credentials.json` and, when it expires, requests fail and unattended sessions stall (S7). | supported (S7) |
| F19 | In `-p` mode an `ANTHROPIC_API_KEY` present in the environment is always used (S7), so a scheduled run inherits whichever credential the trigger's environment carries; a person's shell profile is not read by an OS trigger. | supported (S7), inferred for OS triggers |
| F20 | The Agent SDK executor assumes API or cloud credentials only, and its probe fails with `credential` when only a claude.ai sign-in exists (R-005 S3, EAS §4). The Messages API executor resolves credentials as the client library does (R-004 M13). Both work with no person present once a key is resolvable. | confirmed (S11) |
| F21 | Antigravity headless uses cached credentials from an interactive login, or API-key mode with `GEMINI_API_KEY`; an unauthenticated non-TTY run exits with "authentication required" (R-002 A1, A11). Whether a cached sign-in survives in a session home started by an OS trigger is P-AG-1, not run. | supported (S11), uncertain for triggers |
| F22 | An unattended run spends with no one to stop it; the design's only per-run limit is `run.run_cost_cap_usd`, which is optional ([BUD](../specs/08-budgets-and-failures.spec.md)). A recurring schedule multiplies any overspend by its fire count. | inferred |
| F23 | A scheduled run that pauses waits for a person like any other (C6). If the next fire starts anyway, paused runs pile up and each holds a branch or worktree; a "no live attempt" rule before a slot fires (F1) prevents it. | inferred |

### Dates and recurrences

| # | Finding | Confidence |
|---|---|---|
| F24 | RFC 5545 RECUR (`FREQ`, `INTERVAL`, `BYDAY` with ordinals, `BYMONTHDAY` including `-1`, `BYHOUR`, `BYMINUTE`, `COUNT`, `UNTIL`) expresses every recurrence in the owner's examples, and `dateutil.rrule` implements it in Python (S12). | confirmed |
| F25 | RFC 5545 interprets a local time that falls in a daylight-saving gap with the offset from before the gap (so 02:30 becomes 03:30 on a spring-forward day), and a time that occurs twice as the first occurrence (S12). Python's `zoneinfo` gives the same through the `fold` attribute (PEP 615). | supported (S12) |
| F26 | Natural-language date libraries resolve ambiguous words ("next Friday", "9", "03/04") by settings and locale, silently. A small fixed grammar can instead return "ambiguous" with the readings, which C13 (input resolution calls no model) and the design's `needs` status already support. | inferred |
| F27 | Interval recurrences ("every 2 hours") are elapsed time, while calendar recurrences ("every day at 9") are wall-clock time; across a daylight-saving change the two differ by an hour. | confirmed (S12) |

## Conclusions

1. The core is a model-free tick that decides what is due from the engine's own store, with slots that have identities so nothing starts twice (F1, F2), and it is made OS-agnostic. Since OS schedulers differ in catch-up, sleep and logout behaviour (F12 to F16), no rule may live in them: the default caller of the tick is a portable engine loop with no state, and OS schedulers, the plugin host and external schedulers are optional adapters that only call the tick or start the loop.
2. Claude Code's scheduled tasks are not the engine's trigger: they die with the session or the app, catch up only the latest slot, and spend a model session per fire (F10, F11). The schedule skill may still be called from them, but the engine never relies on them.
3. The engine applies its own catch-up and overlap rules on every platform; OS catch-up options are set only to make the tick run soon after a wake (F12, F14, F15, F16).
4. Unattended fires need a credential that works with no person and no keychain prompt; the Claude Code CLI's interactive sign-in is the weakest case and is flagged at creation; a credential failure is a refusal before spend at fire time (F18 to F21).
5. Every scheduled run carries a cost cap and a schedule carries a period cap (F22). A live or paused previous run skips the next slot by default (F23).
6. A schedule fire is a caller of its own, attested by a token like the supervisor's, since `pipeline` would hide the person who created the schedule and `engine` would hide the schedule (F8).
7. The grammar is a fixed, table-tested set of phrases mapped to an instant or an RFC 5545 subset in a named zone, echoed back with the next fire times; an ambiguous phrase is a `needs` with readings, never a guess (F24 to F27).

## Open questions

| Question | Owner | Next step |
|---|---|---|
| Does a systemd user timer fire while the user is logged out on the owner's Linux machines, with or without lingering? | Implementer | Probe P-SCH-1 ([TCK](../specs/84-schedule-ticks-and-unattended-fires.spec.md)) |
| Can a LaunchAgent tick read a Claude Code `/login` sign-in from the Keychain while the screen is locked? | Implementer | Probe P-SCH-2 |
| Does Antigravity's cached sign-in work from a session home started by an OS trigger (P-AG-1)? | Implementer | Probe P-SCH-3 |
| Is scheduling in the first release? | Owner | This note recommends the slice named in [SCH §5](../specs/83-schedules.spec.md) for the release after the first |
