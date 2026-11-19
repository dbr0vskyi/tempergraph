# ADR-0006 Executors are capability-declaring adapters over headless agent CLIs

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Each step and judge needs an agent session with tools (read files, run commands, MCP), skills and rules. The design must support two very different CLIs ([R-003](../research/R-003-executor-capability-matrix.rsrch.md)): they differ in tool names, cost reporting, limits, and how a session can be restricted.

## Decision

We will define one executor protocol ([EXI](../specs/10-executor-interface.md), [CON §2.6](../specs/01-contracts.md)) whose implementations start a headless CLI as a child process through a shared, engine-owned session launcher, translate its stream into normalized events, and **declare** their capabilities as data. The preflight refuses, before any spend, any need an executor does not declare (contract C15). Timeouts, idle limits, process-tree lifetime and cost estimation are engine-owned, not delegated to a CLI.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| CLI adapters with declared capabilities and an engine-owned launcher (chosen) | Each CLI's own agent loop, tools, skills and MCP support are reused; unequal CLIs fail loudly, before spend | Must parse two evolving stream formats |
| Model APIs directly (Messages API, Gemini API) with an engine-owned tool loop | Full control, stable APIs | Rebuilds tools, skills, MCP and permissions for both families; loses each CLI's authoring surface |
| Agent SDKs per vendor | Typed interfaces | Two SDKs with different shapes; Antigravity has no documented SDK for this use; CI-only advantage |
| Lowest common denominator (use only what both CLIs offer) | One code path | Throws away Claude's tool restriction, cost cap and turn cap; judges would be weakest on both |

## Decision rationale

| Criterion | CLI adapters | Model APIs | SDKs | Lowest common |
|---|---|---|---|---|
| Reuses CLI tools, skills, MCP | yes | no | partly | yes |
| Honest about unequal capabilities | yes | n/a | partly | no |
| Effort for two executors | medium | high | high | low |
| Judge strength where available | full | full | full | weakest |

## Consequences

- Positive: workflow data stays executor-agnostic; a third executor (an SDK or a hosted service) plugs in without engine edits.
- Negative: stream formats and flags drift between CLI releases. Mitigation: record the CLI version on every session; conformance suite with recorded streams; unknown events are skipped and counted.
- Risk: a declared capability rests on a fact the real binary refutes. Mitigation: capabilities that rest on an unconfirmed fact are declared false until a probe result is recorded ([ADR-0010](0010-judge-isolation-per-executor.md)).

## Revisit when

Either CLI publishes a stable programmatic protocol (for example the Agent Client Protocol for `agy`) that replaces stream parsing.
