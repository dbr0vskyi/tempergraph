# ADR-0009 Executors translate CLI streams into one normalized session event stream

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Claude Code emits `stream-json` lines (`system/init`, `assistant`, `user` tool results, `system/api_retry`, `result`) ([R-001](../research/R-001-claude-code-cli-headless.rsrch.md)). Antigravity emits its own stream-json (`init`, `step_update`, `result`) with different field names and no cost ([R-002](../research/R-002-antigravity-cli-headless.rsrch.md)). The live progress file, the idle watchdog, the time profile, the run log, cost accounting and self-improvement causes all need session activity. Written against each CLI's raw stream, every one of them would exist twice and break on each CLI release.

## Decision

We will have each executor translate its CLI's stream into a small fixed set of normalized events ([SSN-B7](../specs/session-contract.spec.md)): `session_started`, `model_delta`, `tool_started`, `tool_finished`, `text`, `retrying`, `denied` and `result`. The launcher stamps each line with its receive time. Every engine consumer reads only normalized events. Raw lines are kept in the session's log file for diagnosis, and no consumer parses them.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Normalized events, raw lines archived (chosen) | One consumer per concern; a new executor adds one translator | The translator can drop detail a consumer later wants |
| Consumers read each raw stream | No translation layer | Every consumer duplicated per executor; drift breaks many places |
| Only the final result, no stream | Simplest | No idle watchdog, no live progress, no time profile |

## Decision rationale

| Criterion | Normalized | Raw per consumer | Result only |
|---|---|---|---|
| Consumers written once | yes | no | yes |
| Idle watchdog and live progress | yes | yes | no |
| Effect of a CLI format change | one translator | many consumers | small |
| Diagnosis of odd sessions | raw log kept | raw | weak |

## Consequences

- Positive: progress, metrics and the watchdog behave the same on both executors ([OBS](../specs/observability-and-cost.spec.md), [EXI](../specs/executor-interface.spec.md)).
- Negative: the event set is a lowest common shape; executor-only detail (for example Claude's per-retry error class) is kept only where an event has a field for it, such as `retrying.category`; the rest stays in the raw log.
- Risk: a CLI adds an event type the translator does not know. Mitigation: unknown lines are skipped and counted on the session record; a count above zero is a self-improvement cause attributed to the executor.

## Revisit when

Either CLI exposes a typed protocol (for example the Agent Client Protocol) that already carries normalized events.
