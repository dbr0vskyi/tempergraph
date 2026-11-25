# Keep a local activity journal per session, with scrubbed and clipped tool input summaries

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner wants to "enter the run and go inside, check which shell it's running". The engine's normalized events carry tool names only ([SSN-B7](../specs/session-contract.spec.md)), and the time profile keeps program words only, by a deliberate rule ("never a command, a path or an output") made for records that are shared. The live progress file is a snapshot of the last ten names. An attempt can run for many minutes and many tool calls that no reader sees until it ends ([research `observer-needs-against-engine-documents`](../research/observer-needs-against-engine-documents.rsrch.md) N6, N7). A command line can hold a secret or a private path.

## Decision

We will add `input_summary` to the normalized `tool_started` event (one line, pattern-scrubbed, clipped to 200 characters, built per capability) and keep a per-session append-only activity journal of normalized events with receive times ([EVT-B17, EVT-B18, EVT-B7, EVT-B19](../specs/run-events.spec.md), [EVT-B21](../specs/run-events.spec.md)). Summaries appear only in the activity journal, the live progress file and the local detail document; no run-log record, ledger row, stats or sink row, export, finding or filed text carries them. An operator setting turns summaries off.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Local journal with scrubbed summaries (chosen) | Answers "what is it running now and what did it run" on every executor; bounded; stays on the machine | A command line is shown on screen; the scrubber is a floor, not a control |
| Names only, as today | Nothing sensitive is written | The owner's main drill-down question has no answer |
| Monitor parses each executor's raw stream itself | No engine change | Per-executor parsers in a mod; breaks on CLI releases; violates [ADR `normalized-session-event-stream`](normalized-session-event-stream.adr.md) |
| Full tool inputs and outputs in the journal | Complete | Large; outputs hold file contents and secrets; already in `raw.jsonl` for those who need it |

## Decision rationale

| Criterion | Summaries | Names only | Monitor parses raw | Full I/O |
|---|---|---|---|---|
| Shows the running shell command | yes | no | yes | yes |
| Same on four executors | yes | yes | no | yes |
| Size bound | yes | yes | n/a | no |
| Stays out of shared records | yes | yes | yes | risk |

## Consequences

- Positive: the monitor shows the open command and its elapsed time, the last ten calls and a full call history per session.
- Negative: the person at the screen sees commands a step ran; on a shared screen that may matter. Mitigation: `observe.tool_inputs = off`, and a monitor setting that hides summaries ([monitor MDD](../../../tempergraph-monitor/docs/specs/drill-down.spec.md)).
- Risk: a secret shape the scrubber misses. Mitigation: summaries never leave the machine; the canary test covers every shared record ([EVT-AC4](../specs/run-events.spec.md)).

## Assumptions

- The owner reads "which shell it's running" as "which command a step's shell tool is running", not as which shell binary. The process listing in the monitor covers the second reading.

## Revisit when

A workflow runs on a machine shared between people who must not see each other's commands.
