---
paths:
  - "**/*.adr.md"
---

# Decision record

A decision record says why: the problem, what exists today, the forces that pull on the choice, the options measured against them, the one chosen and what follows from it, for one decision that affects structure, is costly to change, or will be questioned later. One decision per record.

## Structure

The example below is also installed as the fill-in template `docs/templates/decision.template.md`, generated from this file. Change this rule, never the template.

The sections run in the order a decision is reasoned, so the options are weighed before the choice is written: options written after the decision tend to be built to lose. The title already tells the reader what was decided.

```markdown
# <The decision in a few words>

## Context

The problem, and why it needs deciding now. A record that replaces another links it here.

## Current state

What exists today, each sentence with a path, a link or an id. `Nothing exists yet.` when that is the case.

## Forces

- C1 (constraint): what every option must satisfy. Source: the spec id, document, file or person it comes from
- F1: what pulls one way
- F2: what pulls the other

## Options considered

### <Option A>

How it works: one to three sentences on what would be built or changed.
For: … (F1). Against: … (F2).

### <Option B>

How it works: …
Against: breaks C1.

## Decision

We will ...

## Decision rationale

Why this option over the others, answering each force by its id: met by the chosen option, or given up and why.

## Consequences

What becomes easier and what becomes harder.

## Risks

- <What could go wrong>. Limited by: … Noticed by: …

## Assumptions

- A1: what was taken as true without being checked. Check: how it could be checked. If wrong: what it costs

## Revisit when

The event or measurement that reopens the decision.
```

## Rules

- The record holds the decision and its reasons. It links the specs it affects by path or id and restates none of their behaviours.
- `Current state` holds facts only, and every sentence cites the code or a document by a path, a link or an id, so that a reader can check it and the writer has read the code before proposing. `Nothing exists yet.` is the whole section when nothing does.
- `Forces` is one list, constraints first. A constraint (`C1`, `C2`, …) is a force no option may trade away, and it names its source after `Source:`; one with no source is an assumption and goes under `Assumptions`. Every other force (`F1`, `F2`, …) is something an option can do better or worse. The ids are local to the record.
- At least two options are compared under `Options considered`, each under its own `###` heading with a `How it works:` line and its `For:` and `Against:` in terms of the forces, citing their ids. The chosen option is one of them, described like the others. Each option is one a competent person would defend; doing nothing counts when it is plausible. An option that breaks a constraint is set aside in one line.
- `Decision` names the chosen option.
- `Decision rationale` answers every force by its id: met by the chosen option, or given up and why. A table of forces against options is allowed.
- `Consequences` are what follows for certain. `Risks` are what may follow: each carries what limits it (`Limited by:`) and how it would be noticed (`Noticed by:`). `None known.` is a valid `Risks` section, written after the risks were looked for.
- `Assumptions` lists what was taken as true without being checked, each with an id, how it could be checked (`Check:`) and what it costs if it is wrong (`If wrong:`). `None.` is a valid section. An assumption whose cost is high is a candidate for `Revisit when`.
- `Revisit when` names something observable: an event or a measurement, never "if needs change".
- A small decision fills each section with one line. The sections are a checklist of thought, not a quota of text. A record is at most about 10 KB; a longer one holds two decisions.
- A decision that only a person can take is not taken by a step. Write it as an open question in the hand-off, with the options and what each would mean, and do not write a record for it.
- A record that replaces an earlier one says so in its `Context` with a link. The earlier record is not edited.
- The file name is a slug of the decision, or the task id and a topic. Never a claimed "next number".
