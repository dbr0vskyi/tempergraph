# tempergraph design docs

The design of the tempergraph engine, written the spec-driven way temperspec follows: **research → decision record → spec → plan → code**. Each link is a document the next link reads, so a fresh session can implement a component from its spec without a conversation.

Code for releases 1 and 2 lives in [`../engine/`](../engine/pyproject.toml) (engine `0.2.0`), built track by track; the live checks still open are in [plans/live-checks.plan.md](plans/live-checks.plan.md). Release 1 is scoped by [ADR-0090](adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md) and planned in [plans/first-release.plan.md](plans/first-release.plan.md); its readiness review is [R-090](research/R-090-implementation-readiness.rsrch.md). Release 2 is scoped by [ADR-0125](adr/0125-release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing.adr.md) and planned in [plans/second-release.plan.md](plans/second-release.plan.md), with readiness in [R-130](research/R-130-release-two-readiness-and-gaps.rsrch.md). Release 3 is proposed in [ADR-0132](adr/0132-release-three-is-workflows-that-compose-run-in-parallel-and-grade-in-the-pipeline.adr.md) and planned in [plans/third-release.plan.md](plans/third-release.plan.md), with readiness in [R-140](research/R-140-release-three-readiness-and-gaps.rsrch.md). Each track has its expanded plan in [plans/](plans/README.md).

## Where things live

| Folder | Document type | Holds | Rule |
|---|---|---|---|
| [specs/](specs/00-overview.spec.md) | Behaviour specs | **What** the engine does: contracts, Given/When/Then behaviours, error conditions, acceptance criteria. Never implementation code. | [Spec rules](#spec-rules) |
| [adr/](adr/README.md) | Architecture decision records | **Why**: one decision each, its options, trade-offs and consequences. Links specs, restates none. | [Decision rules](#decision-rules) |
| [research/](research/README.md) | Research notes | Background findings that answer an unknown, with sources and confidence marks. | [Research rules](#research-rules) |
| [guides/](guides/README.md) | How-to guides | **How to use** tempergraph, for people who run and author workflows: install, run, author, improve. Restate no requirement; link the spec instead. | Same truth ranking: a guide never outranks a spec |
| [plans/](plans/README.md) | Implementation plans | **In what order**: the release plan's tracks and phases, then one expanded plan per track. | Release 2 tracks follow temperspec's [plan rule](../../temperspec-tgraph/rules/plan.rule.md) |
| [tasks/](tasks/) | Task notes | Per release 2 track: its triage note (`*.triage.md`) and its code report (`*.report.md`). | temperspec's [task-notes rule](../../temperspec-tgraph/rules/task-notes.rule.md) |

Read in this order before planning or coding a component: the [overview spec](specs/00-overview.spec.md), the [contracts spec](specs/01-contracts.spec.md), the component spec, then the decision records and research notes it links.

## File naming

Every SDD artifact carries its type in a double suffix, `<name>.<type>.md`, so a tool or a rule can tell an artifact's type from its path alone, without reading it. temperspec's rule files ([`rules/`](../../temperspec-tgraph/rules/documents.rule.md)) now hold the same rule for repositories it sets up; for this set, this table is the rule ([ADR-0017](adr/0017-artifact-type-suffixes.adr.md)).

| Artifact type | Suffix | Name pattern | Folder |
|---|---|---|---|
| Behaviour spec (overview, contracts, component) | `.spec.md` | `NN-short-title.spec.md` | `specs/` |
| Architecture decision record | `.adr.md` | `NNNN-short-title.adr.md` | `adr/` |
| Research note | `.rsrch.md` | `R-NNN-short-title.rsrch.md` | `research/` |
| Implementation plan (skeleton or expanded) | `.plan.md` | `<component>.plan.md` | `plans/` |
| Task, story or request | `.task.md` | `<work-item>.task.md` | `tasks/` |
| Triage note (gap list and route) | `.triage.md` | `<work-item>.triage.md` | `tasks/` |
| Code report | `.report.md` | `<work-item>.report.md` | `tasks/` |
| How-to guide | `.guide.md` | `<topic>.guide.md` | `guides/` |
| Rule file | `.rule.md` | `<artifact-type>.rule.md` | the repo's rule folder |

- Specs, decision records, research notes, plans, guides, triage notes and code reports exist in this set today; the other types are reserved so the next links in the chain need no new decision.
- A folder index is `README.md` and carries no suffix: it lists artifacts, it is not one.
- Short titles are lower-case words joined by `-`. Numbers are never reused, and a rename keeps the number.
- A check for this rule fails on any Markdown file in `specs/`, `adr/` or `research/` other than `README.md` whose name lacks its folder's suffix.

## Truth ranking

Acceptance criteria rank above specs and decision records, then plans, then code. Where a spec and a decision record disagree, the spec's acceptance criteria win and the record is amended.

## Naming

"The executor" in this set means the adapter that starts one headless agent session; the four supported executors are the **Claude Code CLI** (`claude`), the **Claude Agent SDK** (`agent-sdk`), Anthropic's **Messages API** (`messages-api`) and the **Antigravity CLI** (`antigravity`, binary `agy`). "Claude SDK" in a request means the Agent SDK; the plain client library is part of the Messages API executor ([R-005](research/R-005-claude-agent-sdk-executor.rsrch.md)).

## Spec rules

Taken from the temperspec reference (artifact 3.5), applied here:

- **Types.** One **overview** spec (the index of the set, no component requirement), one **contracts** spec (the only definition of a type two specs share) and one **component** spec per unit of work.
- **Six numbered sections**: 1 Overview, 2 Contract (signatures and types, no bodies), 3 Behaviours (Given/When/Then with example tables), 4 Error conditions (a table of types, not classes), 5 Design notes (prose, links to decision records), 6 Acceptance criteria (verifiable checkboxes). Then, unnumbered: Open questions (with an owner) and References.
- **Header.** YAML front matter with `title`, `type`, `status`, `prefix` and `adrs`. Status is one of `draft`, `review`, `ready-for-implementation`, `implemented`, set once at file level.
- **Ids.** Acceptance criteria are `PREFIX-AC-n`; each spec owns one prefix, listed in the overview.
- **Budget.** At most 400 lines and 30 KB per spec. An over-budget spec is split, never extended.
- **Updating.** A row says what the engine does now. A change rewrites the rows it affects; no dated or versioned notes, no list of proving tests, no copy of a list another document owns.
- **Behaviour, not code.** Contracts are given as typed field tables and Python-flavoured signatures without bodies.

## Decision rules

Taken from the temperspec reference (artifact 3.4):

- One decision per record, in `adr/NNNN-short-title.adr.md`, numbered above the folder's highest.
- Header: status (`proposed`, `accepted`, `rejected`, `deprecated`, `superseded`), date, authors, supersedes.
- Sections: **Context**, **Decision** ("We will …"), **Options considered** (pros and cons each), **Decision rationale** (a comparison table), **Consequences** (positive, negative, risks with mitigations), and optionally **Revisit when**.
- A record holds the decision and links the specs; it restates none of their requirements.
- Because this set was written without the owner available, every record states the **assumptions** it rests on, so a reviewer can overturn exactly those.

## Research rules

Taken from the temperspec reference (artifact 3.3):

- Sections: problem statement, **Sources consulted** (source, type, where), **Key findings** each with a confidence mark, **Conclusions** (assertions only), **Open questions**.
- Confidence marks: `confirmed` (several sources), `supported` (one source), `inferred`, `uncertain`.
- Speculation beyond the sources is forbidden. A fact about a third-party binary that no probe has confirmed stays `supported` or `uncertain`, and no control may rest on it alone.

## Readiness flags


A flag moves to `LIVE-PROVEN` only with a written result: the date, the machine, the executor and its version, and what was run, recorded in the spec's probe table or acceptance criterion. A passing test against a stand-in moves a capability no further than `BUILT, AWAITING LIVE CHECK`.
