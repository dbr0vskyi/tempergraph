# ADR-0020 The Messages API executor runs an engine-owned loop over a minimal engine tool host

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The Messages API executes no client tool ([R-004 M1, M3](../research/R-004-anthropic-messages-api-executor.rsrch.md)). A step needs to read, search, list, edit and write files and run declared commands; a judge needs only to read. [ADR-0006](0006-executors-as-capability-adapters.adr.md) rejected rebuilding tools for both model families as the only executor shape, because it loses each CLI's skills and MCP support. One API executor next to three agent harnesses is a different question: the engine then owns one small tool set for one executor.

## Decision

We will drive the Messages API with an engine-owned manual loop and a minimal **tool host** ([THS](../specs/tool-host.spec.md)) in the worker process: engine-defined client tools for `read`, `search`, `list`, `edit`, `write` and `shell` (declared command prefixes only, list argv, no shell), Anthropic server tools for `web_search` and `web_fetch` where the bound model and platform offer them, and declared MCP tools through an engine MCP client for local servers. The session offers exactly the declared tools; a judge is offered exactly its view set. No subagent tool exists.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Manual loop and engine tool host (chosen) | The engine executes every call, so restriction, path confinement and command checks are engine facts; one loop for cost and turn caps | The engine maintains six tools and their tests |
| The client SDK's beta tool runner | Less loop code | Beta dependency; the engine still writes every tool; per-turn caps and event emission fit a manual loop better |
| Anthropic's schema-less bash and text-editor tools | Models are trained on them | The text editor mixes read and write, so a judge cannot have it; bash takes free shell text, which the declared-prefix rule refuses |
| Code execution server tool for everything | No local tools | Runs in Anthropic's sandbox, not the workspace; cannot change the repository |

## Decision rationale

| Criterion | Engine host | Tool runner | Built-in tools | Code execution |
|---|---|---|---|---|
| Judge can be read-only | yes | yes | no | no |
| Commands limited to declared prefixes | yes | yes | no | no |
| Works on the workspace | yes | yes | yes | no |
| No beta dependency | yes | no | yes | yes |

## Consequences

- Positive: `restricts_judge_tools`, `enforces_step_tools` and `isolates_user_config` are true by construction and tested by contract tests, not probes.
- Positive: cost and turn caps are enforced between responses with exact usage, unlike on Antigravity.
- Negative: models may work less well with engine-defined tools than with the tools they were trained on. Mitigation: tool names and schemas follow the common read, search, edit shape; calibration sets measure judges on this executor before a gate relies on it.
- Risk: the tool host becomes a second agent harness that grows. Mitigation: its scope is fixed to the ten capability names of [CON-B11](../specs/contracts.spec.md); a step that needs more runs on another executor.

## Revisit when

Anthropic ships client tools with a read-only mode and a declared-command mode, or a hosted sandbox can mount the workspace.
