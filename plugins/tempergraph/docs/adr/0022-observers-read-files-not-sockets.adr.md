# ADR-0022 Observers follow a run through append-only files and read-only verbs, not a socket or a daemon

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner wants a live monitor that drills into a running tempergraph run, and a team view across machines ([R-021](../research/R-021-observer-needs-against-engine-documents.rsrch.md)). An observer needs a feed of what happens, as it happens. A socket suits the live progress file badly, because a read-only reader has nothing to connect to after the engine dies, and OVR-B4 says observability never changes a run. A Claude Code mod can read files, stat them and run a host command, but cannot hold a long-lived socket server of its own ([monitor R-001](../../../tempergraph-monitor/docs/research/R-001-claude-code-mods.rsrch.md)).

## Decision

We will expose run activity to observers only through files the engine already owns, made followable: a `seq` on every run-log record, an append-only activity journal per session, the live progress file, and read-only verbs that read them (`events`, `status --detail`, `logs`) ([EVT](../specs/30-run-events.spec.md), [RDD](../specs/31-run-detail-document.spec.md)). The engine opens no listening socket and runs no daemon. In-process observers exist only for exporters the operator enables ([ADR-0027](0027-in-process-observers-and-wider-hook-events.adr.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Append-only files plus read-only verbs (chosen) | Works after the engine dies; any number of readers; nothing for a reader to block; inspectable by hand | Readers poll; latency is the poll interval (about 1 s) |
| A local socket or HTTP server in the engine | Push, low latency | Port and permission handling; a reader can hold up a writer; nothing to read after a crash; one more attack surface |
| A per-machine daemon that collects from every run | One place to query; push to UIs | A service to install, upgrade and keep alive; a failure mode no run controls |
| Reading the checkpoint | No new file | Couples readers to LangGraph's storage; locks a database the run writes |

## Decision rationale

| Criterion | Files and verbs | Socket | Daemon | Checkpoint |
|---|---|---|---|---|
| Never changes or delays a run (C2) | yes | risk | risk | risk |
| Readable after a crash | yes | no | yes | yes |
| Fits a mod's `$.fs` and `$.process` | yes | no | partly | no |
| New moving parts | none | one | one service | none |
| Latency | ~1 s | ms | ms | ~1 s |

## Consequences

- Positive: the monitor, the troubleshooter skill and a shell user all read the same files; a dead run still shows its last state.
- Negative: polling. Mitigation: readers stat sizes and times first and read only the appended bytes, as `wait` already does ([DUR-B5](../specs/09-durability-and-resume.spec.md)).
- Risk: a reader reads a half-written line. Mitigation: readers drop a last line without a newline and read it next time.

## Assumptions

- One second of latency is good enough for a person watching a run; no consumer needs sub-second push.

## Revisit when

A consumer needs push across machines in real time, or the engine moves to a multi-host checkpoint ([ADR-0014](0014-sqlite-checkpointer.adr.md)).
