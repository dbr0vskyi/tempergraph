# ADR-0038 A batch is a one-node map orchestration

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The engine already has `batch <workflow> <targets…> -k N`: a parent process runs one workflow over many targets, writes a batch file and an append-only event file, and skips targets whose thread exists on a re-run ([WSP §2.2](../specs/13-workspace-and-concurrency.spec.md)). An orchestration ([ORC](../specs/45-orchestration.spec.md)) needs the same parent, the same files, the same concurrency and the same re-run rule, plus dependencies, approvals and failure policies. Two mechanisms would drift.

## Decision

We will implement `batch` as a front end that writes a one-node `map` orchestration and starts it. The batch file and batch event file become the orchestration file and event log; the batch's concurrency, limits and `throttled` back-off are the orchestration's. The `batch` verb, its options and its exit codes stay as they are.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Batch as a one-node orchestration (chosen) | One parent, one file format, one monitor view | Batch output now names an orchestration id |
| Two parents, batch and orchestration | No change to the batch | Two implementations of concurrency, re-run, events and status |
| Drop the `batch` verb | One way in | Breaks the simplest and most used multi-run path |

## Decision rationale

| Criterion | One-node orchestration | Two parents | Drop batch |
|---|---|---|---|
| One implementation of scheduling and re-run | yes | no | yes |
| Simple command kept | yes | yes | no |
| Monitor shows both the same way | yes | no | yes |

## Assumptions

- No batch exists in the field yet; the batch file format can change without a migration.

## Consequences

- Positive: a batch gains failure policies, infra re-open, edits and the orchestration report for free.
- Negative: [WSP §2.2](../specs/13-workspace-and-concurrency.spec.md) now points at ORC for the file formats.
- Risk: none beyond the migration assumption.

## Revisit when

A batch need appears that an orchestration cannot express.
