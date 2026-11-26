# Which sections should specs and decision records gain, and how should discovery find and close what a task leaves unsaid?

## Problem statement

Three questions, asked together because they feed each other:

1. Should the spec format gain `Responsibilities`, `Dependencies` and `Out of scope` sections?
2. Should the decision record format gain or name: context, current state, forces, constraints, options considered with how each works and its pros and cons, decision rationale, consequences, risks, and revisit when?
3. How should the discovery stage find the uncertainties and gaps in a task's initial intent, and close them through code discovery (a code graph or syntax tree where one is available), document discovery and questions to the owner?

This note recommends; it changes no rule, prompt or check.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Spec rule | rule | `plugins/temperspec-tgraph/rules/spec.rule.md` |
| Decision rule | rule | `plugins/temperspec-tgraph/rules/decision.rule.md` |
| Documents rule (cascade edits) | rule | `plugins/temperspec-tgraph/rules/documents.rule.md` |
| Task-notes rule (triage note, hand-off) | rule | `plugins/temperspec-tgraph/rules/task-notes.rule.md` |
| Research rule | rule | `plugins/temperspec-tgraph/rules/research.rule.md` |
| Triage, gap reading and discovery prompts | prompt | `plugins/temperspec-tgraph/prompts/triage.md`, `read_gap.md`, `discovery.md` |
| Format checks | code | `plugins/temperspec-tgraph/workflow/temperspec/specfmt.py` (`DECISION_HEADINGS`, line 41) |
| Capability list | spec | `plugins/temperspec-tgraph/docs/specs/capability-list.spec.md` (CAPL-B1) |
| The 137 specs and 147 decision records of this repository | documents, counted | `plugins/*/docs/specs/*.spec.md`, `plugins/*/docs/adr/*.adr.md` |
| The 58 triage notes of this repository | documents, counted | `plugins/*/docs/tasks/*.triage.md` |
| Engine source, parsed with Python's `ast` | code, measured | `plugins/tempergraph/engine/src` |
| MADR decision template | public | `https://raw.githubusercontent.com/adr/madr/develop/template/adr-template.md` |
| Spec Kit clarify command | public | `https://raw.githubusercontent.com/github/spec-kit/main/templates/commands/clarify.md` |
| Aider repository map | public | `https://raw.githubusercontent.com/Aider-AI/aider/main/aider/website/docs/repomap.md` |
| Nygard's decision record form, the arc42 building-block template, the pattern form's "forces" | public, from memory, not fetched in this session | none |

## Key findings

### F1 The behaviour headings already are the list of responsibilities `confirmed`

A spec's body is its behaviours, each under a heading with a short name (`spec.rule.md`, Behaviours). The capability list that prepare generates holds, for every spec, its path, title, first Purpose sentence and every behaviour heading (CAPL-B1). That is a responsibilities list, generated, always true. Counted over 137 specs: 1,625 behaviours, median 12 per spec, 90th percentile 24, largest 40.

A hand-written `Responsibilities` section would restate those headings one level up. Every new behaviour would then touch two places in the spec, against documents rule 7 (a line says what the system does now, in one place) and the spec rule's "one rule lives in one place". A spec whose behaviours no longer read as one list of duties is over the point where it should be split by capability, which the 400-line budget already forces.

### F2 Dependencies are already written by hand, in prose, unchecked `confirmed`

The Purpose is defined as "what the capability is for and who depends on it". In practice it carries the dependency information: all 107 specs in the current layout have links in their Purpose, 6.3 links on average. The Purpose's median size is 1,009 bytes, the 90th percentile 1,661, the largest 17,248, for a section the rule calls "one short paragraph".

Nothing checks that these links match the specs the behaviours actually refer to, and nothing separates "this capability uses that one" from "that one uses this". A list of "who links to me" is forbidden by documents rule 2; a list of what a spec itself uses is a forward link and is allowed. Things outside the repository that a capability needs (a command-line tool, a service, a file format someone else owns) have no place at all.

The arc42 building-block template states a component by its responsibility and its interfaces, and common component-spec practice splits interfaces into what the component provides, what it consumes and what it needs from outside the codebase. `supported` for that practice; the counts are `confirmed`.

### F3 "Out of scope" means two different things, and only one belongs in a spec `inferred`

- **The boundary of a capability**: a rule a reader could expect here that another spec owns. The spec rule already asks for this ("the Purpose says in one sentence what this spec does not own") when a neighbour could be mistaken for the owner. Nine of 137 specs say it.
- **The boundary of a task**: what this piece of work leaves out or defers. In delivery formats that carry it well, it sits with the unit of work, each item with the reason it is left out, never in the lasting spec.

A spec section called `Out of scope` invites the second meaning: a list of things not built yet. That is scope, which this repository keeps in issues, and it breaks "a line says what the system does now". The task-level boundary has no home today: the triage note has no place for it, and the discovery judge grades scope ("each changed document must serve a gap row", `judges/discovery.md`) with no stated boundary to grade against.

### F4 The decision rule lags what the repository's own records do `confirmed`

The rule defines four sections (`Context`, `Decision`, `Options considered`, `Consequences`) and an optional `Revisit when`; the check requires only the four. Counted over 147 records:

| Section | Records that have it | In the rule |
|---|---|---|
| Context | 145 | required |
| Decision | 147 | required |
| Options considered | 145 | required |
| Consequences | 145 | required |
| Decision rationale | 124 | not mentioned |
| Revisit when | 118 | optional |
| Assumptions | 104 | not mentioned |

Other counts: 21 records name no risk anywhere. 127 records give their options as one table or list, 20 use a heading per option as the rule's example does. 128 records carry a status or date although documents rule 1 allows none. Median size 3.4 KB, 90th percentile 6.7 KB.

So three of the sections asked about (rationale, revisit when, and the unlisted assumptions) are already the habit; the rule neither asks for them nor says what a good one holds.

### F5 What each decision section adds, against the current form `inferred`

| Section | Today | What a named section adds |
|---|---|---|
| Context | "What forces the decision. Facts read in the code or in a cited document." | Nothing new; it should shrink to the problem and why it needs deciding now |
| Current state | Mixed into Context | A place where every sentence must cite a path or an id. It makes the writer read the code before proposing, and gives a judge one checkable rule |
| Forces | The word appears in the Context line only | The yardstick the options are measured with. Without named forces, "For" and "Against" are free text and options cannot be compared on the same terms. MADR calls these decision drivers |
| Constraints | None | A force that cannot be traded. An option that breaks one is out in one line, which keeps weak options from padding the record |
| Options: how it works | "For: … Against: …" under a title | Today an option is known by its title. One to three sentences on what would be built or changed make the pros and cons checkable. MADR's per-option description does the same |
| Decision rationale | Not in the rule, in 124 records | Why the chosen option wins, stated in terms of the forces. The common habit here is a table of criteria against options, which is the forces applied |
| Consequences | "easier, harder, and each risk with what limits it" | Unchanged, minus the risks |
| Risks | Inside Consequences; 21 records have none | Consequences are certain, risks are not. A section that may say `None known` makes the writer consider it; each risk carries what limits it and how it would be noticed |
| Revisit when | Optional, in 118 records | A decision with no reopening event is kept past its reasons. Required, and observable: an event or a measurement, never "if needs change" |

Order matters for a model that writes top to bottom: options written after the decision tend to be built to lose. The title already states the decision for the reader, so the body can run in reasoning order.

### F6 Triage finds what the documents lack, almost never what the task lacks `confirmed`

Triage copies the task's acceptance criteria unchanged and lists, as gaps, each concept the task needs that no spec covers (`prompts/triage.md`, steps 2 to 4). Counted over the 58 triage notes in the repository, 193 gap rows:

| Kind | Rows |
|---|---|
| spec update | 109 |
| spec gap | 66 |
| existing behaviour | 9 |
| decision needed | 8 |
| research needed | 0 |

Three rows in three notes are sorted `Owner decision`. Nothing in the procedure asks whether a criterion is ambiguous, whether two criteria conflict, what the task leaves out, which assumptions triage made to read it, or what the code touched by the task does today beyond the one search of step 4. The owner pause comes directly after triage, before any reading session has looked at the code, so a question is put to the owner before anyone knows whether the code or a document answers it.

### F7 A fixed list of categories is how ambiguity scans stay complete `supported`

Spec Kit's clarify command scans a specification against a fixed taxonomy (scope and behaviour, including explicit out-of-scope statements; data model; interaction flow; quality attributes; integrations and external dependencies; edge cases and failures; constraints and trade-offs; terminology; completion signals), marks each category clear, partial or missing, and asks at most five questions, the ones with the highest impact. General practice around it adds three points that fit temperspec: route work by what is unknown, not by its size; classify each gap by impact (blocks the spec, shapes the design, or is a detail the plan can settle); and always probe side effects (what is written, notified or logged), because they are the part of a change most often missed.

### F8 A code map is cheap to build and small enough to search `confirmed`

Measured on the engine's source with Python's standard `ast` module: 215 files, 3,220 definitions, 2,600 imports and 30,575 call sites parsed in 0.95 seconds. An outline of public definitions with line numbers is 45 KB against 2.68 MB of source (1.7%). The tests: 245 files, 3,770 definitions, 0.82 seconds.

A limit, also measured: 316 of 2,536 distinct names are defined more than once, so a name-only index points to the wrong definition for about one name in eight. A map built from names is a lead to confirm in the file, which is the rule reading sessions already work under (findings are claims to confirm, PRL-B12).

Aider's repository map shows the pattern at scale: definitions and references extracted per file with tree-sitter, a graph of files joined by references, and a ranking that keeps only what fits a token budget.

### F9 The tools for code discovery form a ladder `inferred`

| Rung | Gives | Cost |
|---|---|---|
| Language server | Exact definitions and references, types | A server per language, a warm-up, an executor that offers it |
| tree-sitter tags | Definitions and references by name, many languages | One dependency with prebuilt grammars; no type resolution |
| Language's own parser (`ast` for Python) | The same for one language | No dependency |
| Text search | Any string | What steps do today; no structure, misses renamed imports, finds comments |

Reading sessions have no shell and no extra tools: read, search and list only. A map written as plain files (one line per definition, one line per reference: name, kind, path, line) is searchable with the tools they already have, the way the capability list is. No new tool surface is needed for the first step.

## Conclusions

### Specs

1. **Responsibilities: do not add.** The behaviour headings are the list, and the capability list already prints it (F1). Adding the section would duplicate every behaviour.
2. **Dependencies: add, outgoing only, as `## Depends on`.** One row per thing the capability uses: another spec (by path, with what is used) or something outside the repository. Three properties make it worth its cost (F2): it replaces prose the Purposes already carry, so it is not new upkeep; a model-free check can hold it to the behaviours (a behaviour that links a spec the list does not name is a finding; a listed spec no behaviour links is a warning); and prepare can generate the reverse direction ("used by") into the capability list, where discovery reads the reach of a change. "Used by" is never written by hand.
3. **Out of scope: do not add under that name.** Add `## Does not own` instead, optional, one row per rule a reader could expect here, each naming the spec that owns it. A row with no owner is not allowed: work nobody has built is an issue, not a spec line (F3). This turns the sentence the rule already asks for into a form a check can read.
4. **The task's own boundary goes into the triage note**, as `In scope` and `Out of scope` lines (conclusion 9). That gives the scope judge something to grade against.
5. The Purpose then returns to what the rule says it is: one short paragraph. Existing specs keep their form until a task changes them, as the rule already says of the earlier layout.

Proposed shape:

```markdown
## Purpose

One short paragraph: what the capability is for.

## Depends on

- `session-store.spec.md`: reads and ends session records
- Outside: the system clock

## Does not own

- Sign-in and the creation of a session: `sign-in.spec.md`
```

### Decision records

6. **Adopt all the sections asked about, with two merges**, in reasoning order. The check reads headings, not their order, so the 147 existing records still pass the four required ones.

```markdown
# <The decision in a few words>

## Context

The problem, and why it needs deciding now. A record that replaces another links it here.

## Current state

What exists today, each sentence with a path or an id. `Nothing exists yet.` when that is the case.

## Forces

- C1 (constraint): what every option must satisfy, and where that comes from
- F1: what pulls one way
- F2: what pulls the other

## Options considered

### <Option A>

How it works: one to three sentences on what would be built or changed.
For: … (F1) Against: … (F2)

### <Option B>

How it works: …
Against: breaks C1.

## Decision

We will ...

## Decision rationale

Why this option over the others, in terms of the forces. A table of forces against options is allowed.

## Consequences

What becomes easier and what becomes harder.

## Risks

- <risk>. Limited by: … Noticed by: …

## Revisit when

The event or measurement that reopens the decision.
```

7. The rules that make the sections earn their place:
   - `Constraints` and `Forces` are one section, constraints first and marked. Two sections would split one yardstick (F5).
   - `Current state` is its own section because its rule is different from every other section's: each sentence cites.
   - The chosen option is one of the options, described like the others. At least two options are real: one a competent person would defend. Doing nothing counts when it is plausible.
   - `Risks` may say `None known.` `Revisit when` is required and names something observable.
   - `Assumptions` (in 104 records today) is recognised as optional: what was taken as true without being checked, each one a candidate for `Revisit when`.
   - A record is at most about 10 KB (today's 90th percentile is 6.7 KB). A longer one holds two decisions.
   - A small decision fills each section with one line. The sections are a checklist of thought, not a quota of text.
8. The same option form (how it works, for, against) should be used for the `Owner decisions` of the triage note, so the owner chooses between described options and not between labels.

### Discovery

9. **Triage states the intent before it lists gaps.** Two new sections in the triage note:

```markdown
## Intent

- Goal: one sentence
- In scope: …
- Out of scope: … (stated by the task, or assumed)
- Assumptions: A1 what triage took as true that the task does not say

## Uncertainties

- U1 scope: Does idle expiry apply to API tokens? Blocks AC 1. Route: owner
- U2 existing behaviour: What does a request on an idle session get today? Shapes G1. Route: code
- U3 failure: What happens to a request in flight when the session ends? Detail. Route: plan
```

10. **The scan uses a fixed list of categories**, each marked clear, partial or missing, and every category that is not clear yields a row (F7): goal and success (a criterion two readers would measure differently, a goal with no criterion, two criteria that conflict); scope boundary; actors and triggers; data and state (identity, life cycle); names others depend on; side effects (written, notified, logged); failures and edges (empty, boundary, concurrent, retried); limits (time, size, cost); dependencies inside and outside; existing behaviour and what the change could break; terms used with two meanings.
11. **Each row carries an impact and a route.** Impact: `blocks` (no behaviour can be written without it), `shapes` (the answer changes the design) or `detail` (the plan settles it). Route, tried in this order because each is cheaper and more certain than the next: `code`, `docs`, `source` (a public source), `owner`. Only `blocks` and `shapes` rows are worked in discovery; `detail` rows go to the plan through the hand-off. A `blocks` row keeps a task out of the quick lane.
12. **Code discovery works from a generated code map.** Prepare writes it next to the capability list, as plain files the read and search tools can query: definitions (name, kind, path, line), references (name, path, line), imports (file to file) and, from those, which tests reach which source files. Reading sessions use it to answer four questions for each thing the task touches: where it is defined, what uses it, what it uses, which tests pin it. The answers are the task's reach, and they feed the `existing behaviour` gaps and the plan's reading list. The map is built by the best rung available (F9) and every hit is confirmed in the file (F8). In the engine this is a general capability, stated without any workflow: a script that indexes a repository's code.
13. **Document discovery gains two generated aids**: the "used by" direction of the spec dependencies (conclusion 2), and the list of every decision record's `Revisit when` line, so that triage can see when a task is the event that reopens a decision. For public sources the research rule should rank them (official documentation, then source code, then the maintainers' own announcements, then other writing) and keep its existing confidence marks.
14. **The owner is asked last and once.** The pause moves from after triage to after the reading sessions. A row routed `owner` is asked as before; a row routed `code` or `docs` that the reading could not close becomes an owner question then, carrying what was found. The questions are ordered by impact, each with its options in the form of conclusion 8, a default and the cost of a wrong default, as today.
15. **Discovery ends when every row has an end state**: answered (with the path or source that answers it), decided (by the owner or by a default), passed to the plan, or open. The hand-off lists them, so the judge and the owner can see what was assumed and what was found.
16. **Build in four steps, each useful alone**: (a) the `Intent` and `Uncertainties` sections, their form check and one judge criterion with seeds, which needs prompts and rules only; (b) the code map as an engine capability and its use by reading sessions; (c) the pause after reading; (d) the spec and decision format changes, with checks that apply to new and changed documents only. Step (a) is the one that addresses F6 directly.

## Open questions

- Whether the executor's unattended mode offers language-server queries (definitions and references) to a step. Until answered: the code map is built by a parser and read as files.
- Whether tree-sitter may become an optional dependency of the engine, which today depends on three packages. Until answered: Python's own parser for Python, text search for other languages.
- How often a later gate has sent a run back to discovery, and how often the owner corrected a run after the fact, for want of a question that an intent scan would have raised. The triage notes show what triage listed (F6), not what it missed. Until answered: step (a) is justified by the absence of any scan, and its effect is measured on the next runs by counting `blocks` rows and returns to discovery.
- Whether the cap on owner questions in one pause should fall from 20 toward the five that Spec Kit uses, once questions are ordered by impact. Until answered: 20.
