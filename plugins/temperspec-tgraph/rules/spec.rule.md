---
paths:
  - "**/*.spec.md"
---

# Behaviour spec

A spec states what one capability does, as seen from outside it. Behaviours are the body. Acceptance criteria prove them. Everything else stays out.

## Structure

Sections in this order, with these headings:

```markdown
# <Capability name>

## Purpose

One short paragraph: what the capability is for and who depends on it.

## Behaviours

### SES-B1 Idle sessions end

WHEN a session has been idle for 30 minutes THE service SHALL end the session.

- GIVEN a session idle for 31 minutes WHEN a request arrives THEN the request is refused as signed out
- GIVEN a session idle for 29 minutes WHEN a request arrives THEN the request is served

## Acceptance criteria

- SES-AC1 (SES-B1): A request on a session idle for 31 minutes is refused as signed out
```

An `## Open questions` section may follow, only while a question is open. Remove it when the last question is answered. No other section exists: no interface section, no contract tables, no status, no history.

## Behaviours

- The heading is `### <PREFIX>-B<n> <short name>`. The prefix is two to eight capital letters or digits, the same for the whole spec, and no other spec uses it.
- The first line under the heading is one sentence in the fixed pattern `WHEN <event> THE <capability> SHALL <result>`, with the three key words in capitals.
- At least one scenario follows, each one list item: `- GIVEN <state> WHEN <event> THEN <result>`.
- A behaviour states a result that someone outside the capability can observe. It names a file, a command, a field or a message only when someone outside depends on that exact name. It never names a class, a function, a module or a variable.
- A fact about an interface is a behaviour like any other (`WHEN a client sends a request without a token THE service SHALL answer 401`).
- One behaviour, one result. A sentence that needs "and" between two results is two behaviours.

## Acceptance criteria

- One list item each: `- <PREFIX>-AC<n> (<behaviour ids>): <what an observer can verify>`.
- Every criterion names at least one behaviour of this spec in its brackets. Every behaviour is named by at least one criterion.
- A criterion is one checkable statement. It does not use "works", "correctly", "properly" or "as expected".
- A test that proves a criterion carries the criterion's id in its name or in a comment.

## Ids and links

- An id is defined once in the whole repository and is never renumbered. A removed behaviour retires its id.
- Another spec is referenced by a behaviour or criterion id, or by its file path. Never restate another spec's behaviour.

## Length

A spec has at most 400 lines. A spec that would pass the cap is split by capability into two specs, or compressed: merge scenarios that prove the same thing, remove prose that restates a behaviour.

## Editing a spec

Edit only the behaviours and criteria the task changes, in place. Do not touch other specs to "keep them consistent" unless one of their behaviours or criteria changes. Follow `documents.rule.md` for the rules against cascade edits.

## The overview spec

Every repository has one overview spec, `docs/specs/overview.spec.md`, in this same structure. Its Purpose says what the system is and names every component spec by its path. Its behaviours are the ones that belong to the system as a whole and to no single component. A new component spec is added to the overview's Purpose in the change that creates it; that edit is not collateral.

## Specs in an earlier layout

A spec with numbered sections such as `## 1. Overview` and `## 2. Contract` is in an earlier layout. Leave its layout as it is when you edit it; follow this rule for every new spec.
