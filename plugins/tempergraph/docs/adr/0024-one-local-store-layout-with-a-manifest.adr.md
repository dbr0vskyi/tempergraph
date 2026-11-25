# ADR-0024 One versioned layout for everything a repository's runs leave, under the state root, with manual retention

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner asked for a `.tempergraph` folder per repository "with all the logs of local repos runs: logs from all sessions of agents, logs from code, stats etc." The state root already exists at `<main checkout>/.tempergraph/` and holds checkpoints, run logs, locks, the ledger, batches and scratch ([WSP](../specs/workspace-and-concurrency.spec.md)), but no spec fixes where a session's raw stream, the engine's own code log, check output or hook output go, nor how long they live ([R-021](../research/R-021-observer-needs-against-engine-documents.rsrch.md) N10). Four executors produce four stream shapes. Per-user stats already live on the operator's machine ([OBS-B15](../specs/observability-and-cost.spec.md)).

## Decision

We will fix one layout for the state root and one for a per-user home folder `~/.tempergraph/`, each versioned by a `manifest.json`, with a folder per run and a folder per session named by a stable `session_key` ([LOS](../specs/local-observability-store.spec.md)). Every session keeps its full raw stream as `raw.jsonl`, whatever the executor. The engine writes its own Python logging there as JSON lines. Retention is a rule a verb applies on request; nothing is deleted automatically.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| One layout in the state root plus a home folder (chosen) | Everything for a repository in one place; one reader for every executor; manifest allows change | The state root grows; a person must prune |
| Logs in the user's home only | Survives deleting a checkout | Splits a run from its checkpoint; breaks "the state root is the main checkout" (C10) |
| Rely on each executor's own transcript store | No duplicate | Four places, four formats; judges run with isolation that may disable them; `messages-api` has none |
| Automatic rotation | No growth | Deletes evidence a person may need for a failed run |

## Decision rationale

| Criterion | One layout | Home only | Native stores | Auto rotation |
|---|---|---|---|---|
| A session's full log on all four executors | yes | yes | no | yes |
| Run, checkpoint and logs together | yes | no | no | yes |
| A person keeps failed-run evidence | yes | yes | varies | no |
| Readers written once | yes | yes | no | yes |

## Consequences

- Positive: the monitor, troubleshooter and a shell all find a session's log by `session_key`; `store export` gives a person one archive to share by hand.
- Negative: disk use. Mitigation: `store usage`, a size warning in `status`, and a default prune rule with the shortest life for bulky command output.
- Risk: a layout change breaks readers. Mitigation: the manifest's layout version and tolerant readers (OVR-B14).

## Assumptions

- Repositories are on local disks where a few hundred MB per month of runs is acceptable.
- Keeping raw streams locally does not conflict with any executor's terms of use.

## Revisit when

Runs move to hosts without a persistent checkout (ephemeral CI), where the store would need shipping elsewhere at exit.
