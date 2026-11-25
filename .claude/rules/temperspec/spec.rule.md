---
paths:
  - "**/*.spec.md"
---

# Behaviour spec

A spec states what one capability does, as seen from outside it. Behaviours are the body. Acceptance criteria prove them. Everything else stays out.

## Structure

The example below is also installed as the fill-in template `docs/templates/spec.template.md`, generated from this file. Change this rule, never the template.

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

- The heading is `### <PREFIX>-B<n> <short name>`. The prefix is two to eight capital letters or digits, the same for the whole spec, and no other spec uses it, except that a behaviour moved by a split keeps its id: a spec split from another may define ids with the prefix of the spec it was split from, next to its own.
- The first line under the heading is one sentence in the fixed pattern `WHEN <event> THE <capability> SHALL <result>`, with the three key words in capitals.
- At least one scenario follows, each one list item: `- GIVEN <state> WHEN <event> THEN <result>`.
- A behaviour states a result that someone outside the capability can observe. It names a file, a command, a field or a message only when someone outside depends on that exact name. It never names a class, a function, a module or a variable.
- A fact about an interface is a behaviour like any other (`WHEN a client sends a request without a token THE service SHALL answer 401`).
- One behaviour, one result. A sentence that needs "and" between two results is two behaviours.
- The `WHEN … SHALL` sentence is at most 500 characters. Detail goes into the scenarios; a sentence that lists several results or options is split into behaviours.
- A behaviour, like a criterion, uses no word that two readers could measure differently ("fast", "robust", "secure", "intuitive", "appropriate", "reasonable") and no placeholder left from drafting (`TODO`, `TBD`, `???`, `<…>`). One concept keeps one name: a term another spec defines is used with that spec's meaning.

## Naming a spec

A spec is named for the capability it owns, never for the task that created it: no task id, issue number or work verb (add, fix, support, remove, update) in its file name or its title. When a neighbouring spec could be mistaken for the owner of a rule, the Purpose says in one sentence what this spec does not own. Before a new spec is written, the existing specs are searched for the capability: a rule that belongs to an existing capability goes into its spec, not into a near-duplicate.

## General rules, not cases

A spec outlives the task that changed it. A reader who never saw the task must find each behaviour natural and true.

- A behaviour is a rule of the capability that holds in every case, written as if the capability had always worked this way. It never refers to a task, an issue, a bug, an earlier limit or what the capability did before: no "no longer", "any more", "again", "known limit", "this change". The task, its wording and its history stay in the task notes.
- Name the rule, not the defect. Not "A retry is not refused", but "A retry runs in worktrees of its own".
- A capability that other software uses names none of its users. A spec outside a workflow package names no workflow, and never describes a workflow's units or its shape ("a planning step followed by a map"). Placeholders stand in: `a`, `b`, "a step", "an earlier unit".
- A scenario is an example that makes the rule concrete, at most three per behaviour, set on the rule's boundary: where the rule has one, one case on each side of it. It is not a test: no issue numbers, session keys, branch names or other values copied from a test fixture.
- A task that changes no behaviour changes no spec. No behaviour is written only so that a criterion or a check has something to name.
- A reason, a trade-off or who wanted it goes in a decision record, linked by id, never inside the behaviour.
- One rule lives in one place. When the same rule holds for several capabilities, state it once in the spec that owns the mechanism they share, and link it from the others. Moving a rule there is a change to a behaviour, not collateral.

## Acceptance criteria

- One list item each: `- <PREFIX>-AC<n> (<behaviour ids>): <what an observer can verify>`.
- Every criterion names at least one behaviour of this spec in its brackets. Every behaviour is named by at least one criterion.
- A criterion is one checkable statement. It does not use "works", "correctly", "properly" or "as expected".
- A test that proves a criterion carries the criterion's id in its name or in a comment.

## Ids and links

- An id is defined once in the whole repository and is never renumbered. A removed behaviour retires its id.
- A behaviour moved by a split keeps its id. A criterion may name the id of a behaviour that moved to another spec, and a criterion of a spec split from another may name the ids of the spec it was split from; the structure check reads each id as defined in the one spec that defines it.
- Another spec is referenced by a behaviour or criterion id, or by its file path. Never restate another spec's behaviour.

## Length

A spec has at most 400 lines and at most 30 KB (30,720 bytes). A spec that would pass either is split by capability into two specs, or compressed: merge scenarios that prove the same thing, remove prose that restates a behaviour.

## Editing a spec

Edit only the behaviours and criteria the task changes, in place. Do not touch other specs to "keep them consistent" unless one of their behaviours or criteria changes. Follow `documents.rule.md` for the rules against cascade edits.

## The overview spec

Every repository has one overview spec, `docs/specs/overview.spec.md`, in this same structure. Its Purpose says what the system is and names every component spec by its path. Its behaviours are the ones that belong to the system as a whole and to no single component. A new component spec is added to the overview's Purpose in the change that creates it; that edit is not collateral.

## Specs in an earlier layout

A spec with numbered sections such as `## 1. Overview` and `## 2. Contract` is in an earlier layout. Leave its layout as it is when you edit it; follow this rule for every new spec.
