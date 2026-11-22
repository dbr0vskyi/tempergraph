# ADR-0037 The orchestrating session is woken only when a person is needed, in batches

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

An orchestrating session woken on every event pays for it: a wake after the prompt cache has expired re-writes the whole context into the cache, and most events need no person to see them: a run started, a gate passed. Dynamic workflows report progress in a view, not in the conversation, and post one result at the end ([R-035](../research/R-035-dynamic-workflows-as-orchestration-model.rsrch.md) D5).

## Decision

We will give the orchestrator skill one blocking, model-free `orchestrate wait` that returns only when the attention set changes (a run paused, an approval is due, an `ask` failure, a lost supervisor) or the orchestration ends, and that waits a settle window (default 30 s) after the first change so pauses that arrive together cost one wake. Progress between wakes goes to the monitor, not the conversation. The skill runs this wait in the background and never polls.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Attention-only wait with a settle window (chosen) | Wakes equal pause batches plus the end; nothing to parse between | A person reading only the conversation sees no progress until a need; the monitor fills that |
| Wake on every run's exit (the run driver's rule, applied per run) | No new verb | One wake per run and per pause; each wake after an idle spell re-writes the context into the cache |
| Timed status checks | Simple | Wakes at fixed cost whether anything happened; cache rewrites after idle |
| Lifecycle hooks into the conversation | Event-driven | Hooks are fire-and-forget commands ([HOK-B1 to HOK-B6](../specs/24-lifecycle-hooks.spec.md)); they cannot wake a conversation without a host feature |

## Decision rationale

| Criterion | Attention wait | Per-run exit | Timed checks | Hooks |
|---|---|---|---|---|
| Wakes per orchestration | pause batches + 1 | runs + pauses | time-bound | events |
| Model cost while nothing needs a person | none | some | some | none |
| Works in any host with background commands | yes | yes | yes | no |

## Assumptions

- The host can run a background command and resume the conversation when it exits, as Claude Code does.
- A 30 s settle window is an unmeasured default; it trades a short delay on the first pause for fewer wakes.

## Consequences

- Positive: the orchestrating session's cost scales with decisions, not with runs ([OSK-AC2](../specs/46-orchestrator-skill.spec.md)).
- Negative: a failure under `skip_dependants` does not wake the skill until the end. Mitigation: a node can use `ask` to make a failure a need.
- Risk: the background wait dies with the host. Mitigation: the orchestration goes on without it; the `orchestration_attention` hook ([ORC-B17, ORC-B24, ORC-B26](../specs/45-orchestration.spec.md) N6) can notify a person, and the skill re-attaches from status.

## Revisit when

The host offers a native event channel into the conversation, or live measurement shows the settle window delays people noticeably.
