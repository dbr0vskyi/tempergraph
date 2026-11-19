# ADR-0035 An orchestration of runs is data executed by a model-free engine supervisor

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — (narrows [ADR-0021](0021-scope-of-planned-work.adr.md)'s deferral of batch orchestration for the scope of [ORC](../specs/45-orchestration.spec.md)) |

## Context

The owner asked for an orchestrator skill that manages many tempergraph runs the way Claude Code's dynamic workflows manage a graph of subagents. Something must hold the plan (which runs, in what order, how many at once), start runs, notice when they end or pause, and apply a policy when one fails. A Claude session that does this by hand adds to the run cost, mostly from being woken and re-reading its own context ([R-035](../research/R-035-dynamic-workflows-as-orchestration-model.rsrch.md) B1, B2). Dynamic workflows solve the same problem by moving the plan into a script that a runtime, not the model, executes (R-035 D1). ADR-0021 deferred batch and multi-run orchestration from the first design; the owner's request brings it in.

## Decision

We will describe an orchestration as a versioned data file (nodes, `after` edges, maps, approval nodes, `k`, caps, failure policies) that the engine validates before any spend and executes in a detached **supervisor** process that calls no model and never answers a gate. The orchestrator skill writes the file with the person and reacts only to the supervisor's attention signal. The supervisor starts and resumes runs only through the engine's own verbs. This is contract C16, owned by [ORC](../specs/45-orchestration.spec.md).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Data file run by a model-free engine supervisor (chosen) | No model cost per wake; plan validated before spend; works from CLI, CI and any shell; same "workflows are data" stance as [ADR-0003](0003-workflows-as-data.adr.md) | New engine component and verbs; plans are less free-form than a script |
| The skill orchestrates turn by turn in the conversation | No engine change | A model wake and a context re-read on every event; the queue lives in a context that compacts; the skill can quietly answer gates (R-035 B4) |
| A Claude Code dynamic workflow script, one agent per run | Ready-made runtime, progress view and resume | A model session in front of every start and wait; no mid-run input, so a pause ends the agent; positional replay reruns paid runs (R-035 D4, D11); Claude Code only, not CLI or CI |
| A LangGraph graph whose nodes start child runs | Durable checkpoint and interrupts for free | Many pauses at once against one interrupt per gate (C6); one graph per process (C11) is about runs; the child runs are processes with their own checkpoints anyway |

## Decision rationale

| Criterion | Data + supervisor | Conversation | Dynamic workflow | LangGraph supervisor |
|---|---|---|---|---|
| Model cost per wake | none | high | one agent per run | none |
| Refusal before spend | yes | partly | no | yes |
| Keeps runs moving while one pauses | yes | yes, by hand | no | awkward |
| Usable outside Claude Code | yes | no | no | yes |
| Gate answering stays with a person | yes | by prose only | by prose only | yes |

## Assumptions

- An orchestration runs on one machine; runs on several local repositories are allowed.
- Runs per orchestration are at most 50 and in flight at most 16, the limits the batch already has ([WSP](../specs/13-workspace-and-concurrency.spec.md)).

## Consequences

- Positive: the skill's session sleeps between needs; plans can be saved, reviewed in git and rerun as templates.
- Positive: the monitor gets one document to render, like `/workflows` renders a workflow run.
- Negative: a plan that needs judgement to decide the next runs (for example, from a run's prose output) must express it as an artifact list (`targets_from`) or an approval node. Mitigation: the skill can draft a new orchestration from a finished one's results with the person.
- Risk: the supervisor's view drifts from the runs. Mitigation: node state is always derived from run status ([ADR-0036](0036-orchestration-state-is-a-file-and-an-event-log.adr.md)).

## Revisit when

A hosted runner or CI must run orchestrations, or dynamic workflows gain durable mid-run human input.
