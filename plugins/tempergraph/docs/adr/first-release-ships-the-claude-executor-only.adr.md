# The first release ships the Claude Code executor only; the other three follow by release

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — (orders the delivery of [ADR `add-messages-api-and-agent-sdk-executors`](add-messages-api-and-agent-sdk-executors.adr.md); the four-executor design stands) |

## Context

The design must support four executors: the Claude Code CLI, the Claude Agent SDK, the Messages API and the Antigravity CLI ([ADR `add-messages-api-and-agent-sdk-executors`](add-messages-api-and-agent-sdk-executors.adr.md)). The owner's requirement is on the design; the first build need not ship all four. Two owner questions are open: whether Antigravity may be scripted on a consumer sign-in, and whether the Agent SDK may run on a subscription sign-in ([overview](../specs/overview.spec.md)). Each executor brings its own probes ([§E](../research/implementation-readiness.rsrch.md)) and, for the Messages API, a whole tool host ([THS](../specs/tool-host.spec.md)). The first release's scope is [ADR `first-release-is-simple-trusted-workflows-on-one-machine`](first-release-is-simple-trusted-workflows-on-one-machine.adr.md).

## Decision

We will ship **`claude`** as the only registered executor in release 1 and release 2, and **`agent-sdk`**, **`messages-api`** with its tool host and **`antigravity`** in release 3. The owner postponed every executor but the Claude Code CLI on 2026-11-20; promotion to the pipeline in release 2 runs `claude` headless there.

In release 1:

1. The executor interface is built in full: registry, capability declarations, preflight refusals (OVR-B17), the shared launcher, judge executor selection, the normalized stream and the conformance suite ([EXI](../specs/executor-interface.spec.md)).
2. The conformance suite runs against a recorded stand-in of `claude` and against **scripted stand-ins that carry the declared capability sets of all four executors**, so cross-executor judging, estimate-only cost, missing caps and every refusal path are tested before the second adapter exists. The four tool maps and capability tables ship as test data, so CON-AC5 and WFM-AC5 pass against them and are re-run when each adapter ships.
3. `claude` declares `judge_mcp = false` until the judge's filtering MCP proxy ships in release 2; a judge view of an MCP server is then deferred and its criterion renders out of reach, the path [GRD-B5](../specs/independence-guard.spec.md) already specifies.
4. A workflow naming another executor is refused at preflight with exit 2, `unknown executor`, as today ([EXI-B1, EXI-B6](../specs/executor-interface.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **`claude` only (chosen)** | The owner's own host; strongest judge restriction; reported cost, cost and turn caps, so every release 1 guarantee holds without cross-executor judging; fewest probes; no open licence question | Portability proven by stand-ins, not by a second live adapter |
| `claude` and `agent-sdk` | Same tool names; CI-ready | Open sign-in question; its probes (P-AS-1 to P-AS-4) and worker process before any workflow is proven; the pipeline it serves is a release 2 feature |
| `claude` and `messages-api` | Judge restriction by construction; a second live adapter | The tool host is a large extra surface; estimated cost only; no skills or subagents |
| All four | Meets the requirement at once | Four probe sets, two open owner questions, cross-executor judging live from day one |

## Decision rationale

| Criterion | `claude` only | + `agent-sdk` | + `messages-api` | All four |
|---|---|---|---|---|
| Release 1 guarantees hold on the shipped executor | yes | yes | partly (estimated cost) | partly |
| Waits on an owner answer | no | yes | no | yes |
| Executor probe facts to record (P-CC, P-AS, P-AG) | 8 | 12 | 8 | 21 |
| Interface kept honest for all four | stand-ins | stand-ins + 1 | stand-ins + 1 | live |

## Consequences

- Positive: release 1 needs only P-CC-2, P-CC-5 and P-CC-6 as hard probes; the shell, supervision hooks and the monitor share the executor's host.
- Negative: the four-executor requirement is met in release 3; a team without Claude Code cannot use release 1.
- Risk: the interface drifts toward Claude Code's shape. Mitigation: the stand-ins with the other three capability sets are in the conformance suite from the first phase, and the source-scan rule EXI-AC1 keeps concrete executors out of the core.

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| E1 | The owner runs Claude Code on the machines that run release 1. | Shell, PRV host profile, SCO hooks |
| E2 | `claude -p` runs in a pipeline with an API key, so promotion in release 2 does not need `agent-sdk`. | ADR `graduate-a-workflow-from-local-to-pipeline-by-measured-criteria`, EAS |

## Revisit when

A user without Claude Code needs release 1 or 2, or the owner answers the Agent SDK sign-in question and wants it sooner.
