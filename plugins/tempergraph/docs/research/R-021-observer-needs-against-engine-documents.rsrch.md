# R-021 What a live observer needs against what the engine writes

## Problem statement

The owner asked for a monitor that shows a tempergraph run the way Claude Code shows a dynamic workflow, lets a person "enter the run and go inside" down to which shell command a step is running, and shows gates, judges, observability and cost ([monitor overview](../../../tempergraph-monitor/docs/specs/00-overview.spec.md)). The owner also asked for a local `.tempergraph` folder holding every log of a repository's runs and for one place that gathers numbers from all machines. This note checks each need against the documents the engine already defines, so the engine extensions in specs 30 to 35 rest on a gap list, not on taste.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Engine specs as of PR 2 | This design set | [OBS](../specs/15-observability-and-cost.spec.md), [DUR](../specs/09-durability-and-resume.spec.md), [WSP](../specs/13-workspace-and-concurrency.spec.md), [CLI](../specs/17-engine-cli.spec.md), [CON](../specs/01-contracts.spec.md) |
| Claude Code mods and the dynamic workflows view | Research note of the monitor | [monitor R-001](../../../tempergraph-monitor/docs/research/R-001-claude-code-mods.rsrch.md), [monitor R-002](../../../tempergraph-monitor/docs/research/R-002-dynamic-workflows-view.rsrch.md) |

## Key findings

| # | Need | What exists | Gap | Confidence |
|---|---|---|---|---|
| N1 | List runs of this repository with state, alias, label, origin, cost | Status document ([DUR-B11](../specs/09-durability-and-resume.spec.md)) | None for one state root | confirmed |
| N2 | List runs of every repository on this machine | Nothing: status reads one state root | A machine index of state roots | confirmed |
| N3 | The declared plan (units in graph order, kinds, fan-out) | Diagram model ([LIF](../specs/18-lifecycle-and-evals.spec.md)) and the run overlay (counts only) | A per-thread detail document joining plan, visits, attempts and verdicts | confirmed |
| N4 | A unit's attempts with check result, judge verdict, blockers, confidence, route | `gate` and `agent_run` records in the run log; no `check` record; the judge's criteria are not in the log | A `check` record and a judge summary on the gate record, both additive | confirmed |
| N5 | The session in flight, with its session id and where its transcript is, while it runs | `attempt_start` has no session id; `agent_run` is written only when the session ends | A `session_opened` record written when the executor reports its session id | confirmed |
| N6 | Live tool activity: open tool, last calls, durations | Live progress file ([OBS-B14](../specs/15-observability-and-cost.spec.md)): a snapshot of the open tool and the last ten names | A history, not only a snapshot: a long attempt makes many more calls than the last ten, and no reader sees the rest | confirmed |
| N7 | "Which shell it is running": the command a shell tool runs, its elapsed time, its child processes | Normalized `tool_started` carries the name only ([SSN-B7](../specs/25-session-contract.spec.md)); the time profile keeps the program word only | An input summary on `tool_started` (scrubbed, clipped, local only) and the session's process group id | confirmed |
| N8 | Follow a run without polling the checkpoint | `wait` blocks; the run log is append-only JSON lines | A sequence number on every record, so a reader resumes from an offset | inferred |
| N9 | Stop a runaway run from the monitor | Stop contract exists inside the launcher ([EXI-B2, EXI-B20, EXI-B21, EXI-B22, EXI-B23, EXI-B15](../specs/10-executor-interface.spec.md)); no verb | A `stop` verb with drain | confirmed |
| N10 | Every agent session's full log, every engine code log, check output, in one folder | Raw lines are "kept in the session's log file" ([ADR-0009](../adr/0009-normalized-session-event-stream.adr.md)); no folder layout, no engine code log, no check output store, no retention | A specified store layout with manifest and retention | confirmed |
| N11 | Numbers from every machine in one place | Monthly per-user stats rows on one machine, "nothing is sent anywhere" ([OBS-B15](../specs/15-observability-and-cost.spec.md)) | Opt-in export of metadata rows; an aggregate reader | confirmed |
| N12 | Third-party extensions (a tracker plugin, an exporter, the monitor) react to run events | Four lifecycle hook events (`started`, `paused`, `finished`, `failed`) as detached commands ([HOK-B1 to HOK-B6](../specs/24-lifecycle-hooks.spec.md)) | More events, and an in-process observer interface for exporters | confirmed |
| N13 | The monitor must not leak into headless sessions | A tool a user-level plugin registers can reach a judge, and the guard then discards the verdict ([R-001](R-001-claude-code-cli-headless.rsrch.md) F17) | A rule in the monitor, not the engine; engine side already loads no user plugins in judges on `claude` and `agent-sdk` | confirmed |
| N14 | Health: a run alive but silent, a gate waiting for a person, cost burning toward a cap | Idle watchdog inside the session; `stalled` flag after the fact | Derived health fields in the detail document | inferred |

## Conclusions

1. The status document is enough for a list; everything below the list needs new, additive engine documents. None of them changes a run (OVR-B4) and none is published (OVR-B11).
2. The gaps fall into six engine specs: observer events and the activity journal ([EVT](../specs/30-run-events.spec.md)), the detail document ([RDD](../specs/31-run-detail-document.spec.md)), the stop verb ([RCT](../specs/32-run-control.spec.md)), the local store ([LOS](../specs/33-local-observability-store.spec.md)), cross-machine stats ([CST](../specs/34-central-run-stats.spec.md)) and OTLP export ([TEL](../specs/35-telemetry-export.spec.md)).
3. Shell commands are the most sensitive new data: they are shown locally to the person who owns the machine and are never exported, filed or summarised into a shared record ([ADR-0023](../adr/0023-local-activity-journal-with-tool-input-summaries.adr.md)).
4. N13 is a monitor rule; the engine adds nothing for it.

## Open questions

| Question | Owner |
|---|---|
| Is showing a step's shell commands in the monitor acceptable on shared machines (pair sessions, screen shares)? The design shows them locally and offers a setting to hide them. | Owner |
