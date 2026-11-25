# One SQLite checkpoint database per workflow; Postgres stays a seam

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

LangGraph needs a checkpointer for durable pauses and resume ([ADR `langgraph-graph-runtime`](langgraph-graph-runtime.adr.md)). tempergraph runs on one operator machine, often with several runs of one workflow in parallel processes. SQLite in WAL mode lets readers go on while one writer commits, and a busy timeout makes a concurrent writer wait rather than fail.

## Decision

We will keep one SQLite database per workflow under the state root `.tempergraph/`, opened in WAL mode with a 60 s busy timeout, one graph per process. Postgres is a documented seam behind the same checkpointer interface, not shipped in the first release.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| SQLite per workflow (chosen) | No server; WAL and a busy timeout serve the expected load; easy to copy or delete | Single host; write contention beyond tens of writers |
| One SQLite database for all workflows | One file | Unrelated workflows contend; deleting one workflow's state is harder |
| Postgres | Multi-host, high concurrency | A server to run; heavy for a single-operator tool |
| In-memory | Fast | No resume after exit, which pauses require |

## Decision rationale

| Criterion | Per workflow | Shared | Postgres | Memory |
|---|---|---|---|---|
| Resume after process exit | yes | yes | yes | no |
| Setup | none | none | server | none |
| Serves the expected load | yes | partly | yes | no |
| Multi-host | no | no | yes | no |

## Consequences

- Positive: a workflow's state is one file the operator can inspect, back up or reset.
- Negative: no multi-host runs. Mitigation: the Postgres seam; the move is recommended above about 50 concurrent runs.
- Risk: network file systems break SQLite locking. Mitigation: the state root must be on a local disk, which the docs state as an operator requirement.

## Revisit when

Runs need more than one host, or measured contention exceeds the busy timeout.
