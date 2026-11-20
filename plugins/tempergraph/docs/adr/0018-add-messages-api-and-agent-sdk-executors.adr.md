# ADR-0018 Add two Anthropic executors: the Messages API and the Claude Agent SDK

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | [ADR-0007](0007-two-first-class-executors.adr.md) |

## Context

The owner asked for two more executors: Anthropic's Messages API and the "Claude SDK". [ADR-0007](0007-two-first-class-executors.adr.md) ships the two CLIs; [ADR-0006](0006-executors-as-capability-adapters.adr.md) chose CLI adapters over model APIs as the shape of an executor, and its "Revisit when" admits an SDK or hosted executor behind the same protocol. Research: [R-004](../research/R-004-anthropic-messages-api-executor.rsrch.md) (API), [R-005](../research/R-005-claude-agent-sdk-executor.rsrch.md) (Agent SDK).

## Decision

We will add two executors behind the unchanged protocol ([EXI](../specs/10-executor-interface.spec.md)):

- `agent-sdk` ([EAS](../specs/21-executor-agent-sdk.spec.md)): the Claude Agent SDK, which runs Claude Code as a library. It shares Claude Code's tool names, view catalog rows and authoring surface, and adds an in-process gatekeeper hook for judges.
- `messages-api` ([EMA](../specs/20-executor-messages-api.spec.md)): the Messages API with an engine-owned loop and tool host ([ADR-0020](0020-engine-owned-tool-loop-for-the-messages-api.adr.md)). It has no authoring surface and no subagents.

"Claude SDK" is read as the Agent SDK: the client SDK is how the Messages API executor calls the API, so it is not a separate executor. Both run inside an engine worker process ([ADR-0019](0019-in-process-executors-run-in-a-worker-process.adr.md)). `claude` stays the default judge executor; the registration order is `claude`, `agent-sdk`, `messages-api`, `antigravity`.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Both, behind the same protocol (chosen) | Meets the request; a CI path with no interactive sign-in; the API executor's restriction needs no probe | Two more executors to maintain; the API one needs an engine tool host |
| Agent SDK only | Little new code: Claude Code semantics, typed messages | The owner asked for both; no executor whose tool set the engine fully owns |
| Messages API only | Full control, smallest dependency | Loses skills, subagents and Claude Code's tools; the owner asked for both |
| Read "Claude SDK" as the client SDK | One executor fewer | The client SDK is the Messages API; this would satisfy one request twice and the other not at all |

## Decision rationale

| Criterion | Both | SDK only | API only | Client SDK reading |
|---|---|---|---|---|
| Meets the owner's request | yes | partly | partly | partly |
| CI without interactive sign-in | yes | yes | yes | yes |
| A judge whose restriction rests on no third-party binary | yes | no | yes | yes |
| Reuses Claude Code's tools and authoring surface | yes (SDK) | yes | no | no |
| New engine code | tool host, two workers | one worker | tool host, one worker | tool host |

## Assumptions

- The operator uses API-key or cloud-platform credentials for both executors. The Agent SDK's documentation forbids offering claude.ai login in third-party products unless approved; whether an operator's own engine counts is **open** for the owner.
- The Python Agent SDK bundles a compatible Claude Code CLI; the executor records both versions.

## Consequences

- Positive: a workflow step can move between four executors by one field; judges can run on three Claude-family executors and, once probed, on Gemini.
- Positive: the Messages API executor is the reference for "restriction by construction", which the conformance suite can test without a real binary.
- Negative: a step moved to `messages-api` loses its CLAUDE.md, skills and subagents. Mitigation: validation warns when a prompt names a skill or agent and its executor declares no authoring surface ([WFM](../specs/02-workflow-model.spec.md)).
- Risk: the API changes request shapes per model (thinking, effort defaults, forced tool choice). Mitigation: request parameters come from a per-model profile in the binding table, and every session records the client library and API version.

## Revisit when

A hosted agent service (for example Managed Agents) is wanted for CI, or the Agent SDK documents a stable protocol that removes the bundled CLI.
