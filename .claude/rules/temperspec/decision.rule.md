---
paths:
  - "**/*.adr.md"
---

# Decision record

A decision record says why: the context, the options and the consequences of one decision that affects structure, is costly to change, or will be questioned later. One decision per record.

## Structure

The example below is also installed as the fill-in template `docs/templates/decision.template.md`, generated from this file. Change this rule, never the template.

```markdown
# <The decision in a few words>

## Context

What forces the decision. Facts read in the code or in a cited document.

## Decision

We will ...

## Options considered

### <Option A>

For: ... Against: ...

### <Option B>

For: ... Against: ...

## Consequences

What becomes easier, what becomes harder, and each risk with what limits it.
```

An optional `## Revisit when` names the event that reopens the decision.

## Rules

- The record holds the decision and its reasons. It links the specs it affects by path or id and restates none of their behaviours.
- At least two options are compared, and the one chosen is named in `Decision`.
- A decision that only a person can take is not taken by a step. Write it as an open question in the hand-off, with the options and what each would mean, and do not write a record for it.
- A record that replaces an earlier one says so in its `Context` with a link. The earlier record is not edited.
- The file name is a slug of the decision, or the task id and a topic. Never a claimed "next number".
