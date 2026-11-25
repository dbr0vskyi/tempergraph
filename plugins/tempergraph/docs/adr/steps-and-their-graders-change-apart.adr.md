# Steps and the gates that grade them change apart; weakening a gate is a person's act

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Once the loop proposes changes ([ADR `improvement-closes-through-measured-proposals`](improvement-closes-through-measured-proposals.adr.md)), the cheapest way to make a failing gate pass is to change the gate. The Darwin Gödel Machine removed the markers its hallucination check looked for; LLM judges carry known biases ([F5](../research/self-improving-agent-systems.rsrch.md)). In tempergraph the step and its gate live in the same workflow package, so a single patch can do both.

## Decision

We will classify every proposal from the parsed workflow into **producer** classes (prompt, lessons, limits, model, flow) and **grader** classes (brief, criterion, check, judge model). A proposal may touch one side only. Producer proposals are scored on trial runs; grader proposals are scored on human labels and calibration cases with no step session. A **weakening** (a criterion removed, a severity lowered, a check that passes where it failed, a widened judge view, a budget raised above twice) can only be authored by a person, and its pull request is labelled ([PRP-B14, PRP-B15](../specs/improvement-proposals.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| One side per proposal, weakening person-only (chosen) | Blocks the gaming path by construction; grader changes are judged against people, not against the step | Some real fixes need two proposals |
| Allow mixed proposals, rely on review | Fewer proposals | The trial score itself is corrupted by the gate change; review sees a green trial |
| Forbid grader proposals entirely | Simplest | Criteria do drift and need fixing, for example rule-like branching in judge prose that belongs in a check |

## Decision rationale

| Criterion | Chosen | Mixed | No grader changes |
|---|---|---|---|
| A trial measures the producer against an unchanged gate | yes | no | yes |
| Grader quality can improve | yes | yes | no |
| Gaming needs a person's act | yes | no | yes |

## Consequences

- Positive: a `shown_better` producer trial means the same gate passed more, not a softer gate.
- Negative: a fix that needs a new criterion and a prompt change takes two pull requests, grader first.
- Risk: a weakening detector misses a case. Mitigation: classification compares parsed structures and check behaviour on fixtures, not diff text; an acceptance test plants a weakening in a reordered file.

## Assumptions

- Judge views, severities and budgets are declared in workflow data that the engine can parse (true of [WFM](../specs/workflow-model.spec.md)).
