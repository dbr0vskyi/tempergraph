# ADR-0032 Lessons learned are versioned workflow content, not run-time memory

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Experience-memory systems (ExpeL, Agent Workflow Memory, ACE, LangMem's procedural memory) carry lessons from past tasks into later prompts and report gains; ACE also reports that rewriting such contexts wholesale erodes them ([R-030 F4](../research/R-030-self-improving-agent-systems.rsrch.md)). A fix fitted to one request narrows a workflow for every other. tempergraph promises reproducible, versioned workflows whose prompts carry a digest.

## Decision

We will keep lessons as a small itemised file per step inside the workflow package, rendered into the step's prompt only, capped at 12 entries and 2,500 characters, changed only by a reviewed proposal that adds, edits or retires at most two entries ([LSN](../specs/workflow-lessons.spec.md)). No run writes lessons, and no judge sees them.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Versioned lessons file, changed by proposals (chosen) | Reproducible; reviewed; digest per run; delta-only | Learning waits for a merge |
| Run-time memory store updated after each run | Learns immediately (ExpeL, LangMem) | Two runs of one version see different prompts; no review; one odd run leaks into all |
| No lessons; every fix is a template edit | One mechanism | Template edits are larger and harder to retire; no cheap place for a one-line rule |

## Decision rationale

| Criterion | Chosen | Run-time memory | Template only |
|---|---|---|---|
| Same version, same prompt | yes | no | yes |
| Reviewed by a person | yes | no | yes |
| Cheap to add and retire | yes | yes | no |

## Consequences

- Positive: lessons are measurable like any change and splittable in reports by digest.
- Negative: slower learning than run-time memory.
- Risk: lessons accrete. Mitigation: the budget, and retirement needs only "no loss shown".

## Assumptions

- Prompt rendering can append a block after the tools block on every executor (true of [PRM](../specs/prompt-rendering.spec.md)).

## Revisit when

A trial shows run-time retrieval of lessons beats the versioned file on a workflow's case set.
