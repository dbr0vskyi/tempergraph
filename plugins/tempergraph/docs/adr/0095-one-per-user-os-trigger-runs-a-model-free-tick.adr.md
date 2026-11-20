# ADR-0095 One per-user OS trigger runs a model-free tick; no resident engine process

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context


## Decision

We will install **one per-user OS trigger** per machine (a LaunchAgent, a systemd user timer with a crontab fallback, or a Task Scheduler task) that runs `tempergraph schedule tick` every 5 minutes by default. The tick is a short model-free engine call: it takes a lock, settles ended fires, finds due slots, applies the schedule's policies, preflights, and starts each due run through the engine's own `run` or `orchestrate start`, detached, then exits. It calls no model and answers no gate (contract C18). The supervisor and the tick stay separate processes. Specs: [SCH](../specs/83-schedules.spec.md), [TCK](../specs/84-schedule-ticks-and-unattended-fires.spec.md).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| A resident engine daemon | Exact timing; could also apply deadlines and serve the monitor | Needs an OS entry anyway to start and restart it; loses in-memory state on crash or update; a long-lived process running all day for a few fires |
| Claude Code scheduled tasks or desktop tasks | Already exist; no install | Session-scoped or app-scoped; latest-only catch-up; a model turn per fire; not available on other executors' hosts |
| Make the orchestration supervisor resident and let it fire schedules | One background process | Turns every orchestration's supervisor into a service; mixes per-orchestration locks with machine-wide timing |

## Decision rationale

| Criterion | Tick | Daemon | Entry per schedule | Claude Code tasks |
|---|---|---|---|---|
| Fires with no terminal or app open | yes | yes | yes | no |
| Same catch-up and overlap rule everywhere | yes | yes | no | no |
| Recovers from crash and update by reading files | yes | partly | yes | no |
| Model-free per fire | yes | yes | yes | no |
| Timing precision | interval | exact | exact | up to 30 min late |

## Consequences

- Positive: scheduling adds one verb family and one OS entry, no service; the tick is the scheduler FLX deadlines assumed the owner would bring.
- Negative: a slot fires up to one interval late. Mitigation: `--every 1m` for owners who need it; the echo states the interval.
- Risk: the trigger stops ticking (removed, broken shim, logged out). Mitigation: a heartbeat file; `list`, `status` and `attention` show `trigger_stale` after three missed intervals.
- Risk: the OS scheduler does not run while logged out (macOS, Windows; Linux per P-SCH-1). Mitigation: stated at install; missed slots follow the catch-up rule.

## Assumptions

- Schedules are per user and per machine.

## Revisit when

A hosted runner or a shared state store exists, so schedules could fire off the owner's machine.
