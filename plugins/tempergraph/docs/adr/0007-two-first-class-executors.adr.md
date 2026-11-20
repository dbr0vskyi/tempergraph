# ADR-0007 Ship two first-class executors: Claude Code CLI and Antigravity CLI

| | |
|---|---|
| Status | superseded by [ADR-0018](0018-add-messages-api-and-agent-sdk-executors.adr.md) (four executors) |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner's requirement: the design supports two executors, Claude CLI and Antigravity CLI. Research ([R-001](../research/R-001-claude-code-cli-headless.rsrch.md), [R-002](../research/R-002-antigravity-cli-headless.rsrch.md)) shows Claude Code meets every need of both step and judge sessions by documented flags, while Antigravity meets the step needs but cannot restrict a session by flag, reports no cost, and has no turn or cost cap.

## Decision

We will ship two concrete executors, `claude` ([ECC](../specs/11-executor-claude-code.spec.md)) and `antigravity` ([EAG](../specs/12-executor-antigravity.spec.md)), both able to run any step. `claude` is the default judge executor. `antigravity` hosts judges only after its isolation probes pass; until then the engine moves its steps' judges to `claude` automatically ([ADR-0013](0013-cross-executor-judging.adr.md)). Both record their CLI version on every session; the engine keeps a per-executor table of CLI versions its probe facts were recorded for.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Two full executors, judge capability declared honestly (chosen) | Meets the requirement; no weakened judge; mixed-family judging | Antigravity-only installs cannot run gated workflows until the probes pass |
| Antigravity as step-only executor, permanently | Simple | Gives up a path to Gemini judges even after the probes pass |
| Treat both as equal, rely on the guard alone for Antigravity judges | Antigravity-only installs work now | A judge with write tools present can change an external system before the guard sees it |
| Claude only, Antigravity later | Least work | Fails the requirement |

## Decision rationale

| Criterion | Chosen | Step-only | Guard-only | Claude-only |
|---|---|---|---|---|
| Meets the two-executor requirement | yes | yes | yes | no |
| Judge independence holds | yes | yes | weak | yes |
| Antigravity-only operator can run gated workflows today | no | no | yes | no |
| Path to Gemini judges | yes | no | yes | no |

## Assumptions

- Operators who use Antigravity also have Claude Code available for judges, or accept that gated workflows are refused until the probes pass.
- Account-based Antigravity use as a child process is permitted for the operator's account; otherwise API-key mode is the supported auth. **Open:** the terms were not read; the owner must confirm.

## Consequences

- Positive: workflows run steps on Gemini or Claude models by changing one field; judges can be on another model family than the producer by default.
- Negative: two stream parsers, two tool maps, two binding tables and two probe suites to maintain.
- Risk: `agy` self-updates and changes behaviour silently. Mitigation: version recorded per session, a warning outside the probed range, and capability facts marked projected for that run.

## Revisit when

Probes P-AG-1 to P-AG-3 are run, or Google documents per-invocation settings or tool restriction for `agy`.
