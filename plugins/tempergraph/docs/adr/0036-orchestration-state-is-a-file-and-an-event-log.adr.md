# ADR-0036 Orchestration state is the file plus an append-only event log; runs hold the truth; nodes are known by id

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

A supervisor can be killed, a run can end while no supervisor watches it, and a person can edit a running orchestration. The state must survive all three without starting a paid run twice. A design that survives them keeps intent in a versioned file, truth in the engine's status and history in an append-only event file, and re-attaches to live runs through the lock probe. Dynamic workflows instead replay by position: the first changed or failed call and everything after it runs again ([R-035](../research/R-035-dynamic-workflows-as-orchestration-model.rsrch.md) D11).

## Decision

We will keep an orchestration's state as its file (intent), an append-only event log (history) and each node's run status (truth). A node's state is derived from its thread's status on every pass; the log never overrides it. Each node has a stable id, and its thread id is derived from the orchestration id and the node id, so a resumed supervisor finds every started run by name and never starts it again.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| File, event log, truth from run status, identity by node id (chosen) | Crash-safe without a second checkpoint; edits and reordering never rerun work; matches the batch's re-run rule ([WSP-B7](../specs/workspace-and-concurrency.spec.md)) | Every pass reads run status; node ids must never be reused |
| Positional replay as in dynamic workflows | Simple runtime; no ids | A failed or reordered node reruns finished paid runs after it |
| A database table of node states owned by the supervisor | Fast queries | A second source of truth that can disagree with the runs after a crash |

## Decision rationale

| Criterion | File + log + run truth | Positional replay | Own table |
|---|---|---|---|
| A paid run never starts twice | yes | no | only if the table is right |
| Survives a supervisor kill at any point | yes | yes | partly |
| Live edits safe | yes | no | yes |
| Extra store | none | cache | one database |

## Assumptions

- Reading the status of up to 50 threads per pass is cheap enough; the run lifecycle stream requested from the observability design ([ORC-B17, ORC-B24, ORC-B26](../specs/orchestration.spec.md) N2) makes it cheaper.

## Consequences

- Positive: the monitor and the skill read one derived document; nothing can show a node "done" that its run does not show finished.
- Negative: removing a started node is refused; a person who wants it gone stops it, and it stays in the history.
- Risk: a thread deleted by hand leaves a node unknowable. Mitigation: its dependants fail with `input_missing`, never silently pass.

## Revisit when

Orchestrations span machines and the run status is no longer local.
