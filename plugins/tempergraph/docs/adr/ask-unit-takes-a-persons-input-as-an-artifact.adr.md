# An ask unit takes a person's mid-run input as a validated artifact, in the human node

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

LangGraph's main human-in-the-loop use of `interrupt` is to ask a person for input the graph then uses ([research `node-types-against-langgraph`](../research/node-types-against-langgraph.rsrch.md) L11). The design lets a person supply input only at the start (`ResolveResult.needs`) or decide at a pause. Delivery-pipeline workflows need mid-run input: answers to a discovery step's open questions, a choice of option, a value only a person knows. Today an author would wire a `wait` unit and an event value, which carries one value and no prompt.

## Decision

We will add a unit kind **`ask`** ([ASK](../specs/ask-unit.spec.md)):

1. It declares questions (name, text, answer kind, choices, required, default) or reads them from a list artifact an earlier step produced.
2. It pauses in the unit's **human node** with pause kind `input`. A person answers with `answer:<name>=<value>` decisions or an answers file.
3. Answers are validated by declared kind and an optional pure check; they become the artifact `answers`, which later steps read as a reference.
4. It has no model and no judge; the person's input is the bar. An agent's answer is recorded apart, as at any pause.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Ask unit in the human node (chosen) | One interrupt rule; answers are an artifact; questions may come from a step | A new kind and a new decision word |
| Wait unit with event values | Exists | One value per event, no questions shown, no kinds |
| A model step that asks in its session | No new kind | Sessions are headless; the question would be lost or answered by the model |
| Approval with feedback | Exists | Feedback is free text for a retry, not data for later steps |

## Decision rationale

| Criterion | Ask unit | Wait | Model asks | Approval |
|---|---|---|---|---|
| Questions shown, answers typed | yes | no | no | no |
| Questions from an earlier step | yes | no | yes | no |
| Keeps one interrupt per gate | yes | yes | n/a | yes |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| Q1 | An ask runs on the main chain or in a sub-workflow child, not in a branch or a map item. | ASK-B7 |

## Consequences

- Positive: interview-style and clarify-then-continue workflows are one declared unit; `attention` lists open asks like any pause.
- Negative: a new pause kind for the monitor, `attention` and the run detail.
- Risk: a workflow asks too much and stalls. Mitigation: the audit's existing pause-rate rules apply, and deadlines ([FLX](../specs/flow-extensions.spec.md)) bound how long an ask waits.

## Revisit when

A workflow needs per-item asks inside a map.
