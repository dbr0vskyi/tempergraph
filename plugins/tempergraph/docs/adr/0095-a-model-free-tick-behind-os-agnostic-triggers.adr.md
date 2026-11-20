# ADR-0095 A model-free, OS-agnostic tick holds every schedule rule; a portable engine loop calls it, OS and other schedulers are optional adapters

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner asked for a schedule command that runs a workflow once or regularly, and then that the scheduler be **OS agnostic**, deterministic wherever possible, with no model needed ([R-095](../research/R-095-scheduling-runs-prior-art-and-gaps.rsrch.md)). Something must start the run when nobody is at a terminal. Recurring runs can rest on one per-user OS trigger running a tick at a fixed interval (R-095 F1, F2). OS schedulers differ in how they treat sleep, power-off and logout (F12 to F15), and Claude Code's own scheduled tasks live with a session or the desktop app (F10, F11). The orchestration supervisor is a detached, model-free process per orchestration, not a service (F7).

## Decision

We will put **every scheduling rule in one deterministic, model-free routine, the tick** (`tempergraph schedule tick`): it reads the engine's files, finds due slots, applies catch-up, overlap and budget, preflights, starts each due run through the engine's own `run` or `orchestrate start`, and exits. It is idempotent and lock-guarded, so it is safe from any number of callers at any frequency. It calls no model and answers no gate (contract C18).

What calls the tick is a **trigger**, and triggers carry no rule:

- **`loop`, the default**: `schedule loop`, a portable engine process in the engine's interpreter that ticks, sleeps until the next slot or 60 s, and repeats. It holds no state between ticks and uses no OS facility, so it works the same on macOS, Linux and Windows.
- **Optional adapters**: `host` (the plugin's `SessionStart` hook starts the loop), `os` (one per-user autostart entry that starts the loop at login, or a crontab line that calls the tick), `external` (any scheduler the owner runs calls the tick).

The supervisor and the tick stay separate processes. Specs: [SCH](../specs/83-schedules.spec.md), [TCK](../specs/84-schedule-ticks-and-unattended-fires.spec.md).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Tick with every rule; portable loop by default; adapters optional (chosen) | OS-agnostic; one behaviour everywhere; seconds-precise; nothing lost on crash or update; OS integration only if wanted | The loop must be started again after a reboot unless an adapter does it |
| One per-user OS trigger as the only trigger (the first draft) | Survives reboot by default | Three platform-specific entries to own and test; OS catch-up and logout rules leak into behaviour; slots up to one interval late |
| A stateful resident daemon | Exact timing | Holds state an update or crash loses; same reboot problem as the loop |
| One OS entry per schedule | Exact timing from the OS | Drifts from the store; per-OS catch-up; many entries  |
| Claude Code scheduled or desktop tasks | No install | Session- or app-scoped; latest-only catch-up; a model turn per fire; Claude Code only |

## Decision rationale

| Criterion | Tick + loop + adapters | OS trigger only | Daemon | Claude Code tasks |
|---|---|---|---|---|
| Same behaviour on every OS | yes | no | yes | no |
| No OS-specific code needed to work | yes | no | yes | yes |
| Model-free per fire | yes | yes | yes | no |
| Recovers from crash and update by reading files | yes | yes | partly | no |
| Fires after a reboot with nobody logging in | with the `os` adapter | per OS | no | no |

## Consequences

- Positive: the core is tested once with a fake clock and runs unchanged everywhere; an owner who already has cron, CI or a cluster scheduler points it at `schedule tick`.
- Negative: with the default loop alone, a reboot stops firing until the loop starts again. Mitigation: the `host` adapter restarts it at the first Claude Code session; the `os` adapter at login; missed slots follow the catch-up rule; `attention` and `list` show `trigger_stale`.
- Risk: two triggers race. Mitigation: the tick lock and slot identity make a second start impossible (SCH-B7).

## Assumptions

- A loop that ticks at least every 60 s settles ended fires promptly enough.
- Schedules are per user and per machine.

## Revisit when

A hosted runner or a shared state store exists, so schedules could fire off the owner's machine.
