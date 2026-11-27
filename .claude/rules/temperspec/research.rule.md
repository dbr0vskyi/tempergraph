---
paths:
  - "**/*.rsrch.md"
---

# Research note

A research note answers one unknown, so that a spec or a decision does not rest on a guess.

## Structure

The example below is also installed as the fill-in template `docs/templates/research.template.md`, generated from this file. Change this rule, never the template.

```markdown
# <The question>

## Problem statement

The unknown, and which gap of the task it blocks.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Session middleware | code | `src/auth/session.py` |

## Key findings

### F1 <finding> `confirmed`

What was found, with the path and line or the quote that shows it.

## Conclusions

Numbered statements that follow from the findings.

## Open questions

What the sources could not answer.
```

## Rules

- Every finding carries one confidence mark: `confirmed` (several sources agree), `supported` (one source), `inferred` (reasoned from sources, not stated by them) or `uncertain`.
- A claim about the code is a hypothesis until it is read in the code. Cite the path.
- Sources rank: the tool's or library's official documentation, then its source code, then its maintainers' own announcements and issue answers, then any other writing. A finding rests on the highest source that holds it; a lower source that disagrees with a higher one is reported, never followed. The `Type` column names the rank (`docs`, `code`, `maintainer`, `other`), and the confidence mark is still given by how many sources agree.
- Prefer an existing note: extend it when it covers the same question, do not write a second one.
- A conclusion never goes beyond the findings. What the sources leave open goes to `Open questions`.
- A question only a person can answer (a product choice, an unknown outside contract) is recorded as open. It is never settled by a guess.
