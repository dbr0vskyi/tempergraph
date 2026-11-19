# tempergraph design docs

The design of the tempergraph engine, written the spec-driven way temperspec follows: **research → decision record → spec → plan → code**. Each link is a document the next link reads, so a fresh session can implement a component from its spec without a conversation.

This set is docs only. No plan and no code exists yet. The next link in the chain is an implementation plan per component spec.

## Where things live

| Folder | Document type | Holds | Rule |
|---|---|---|---|
| [specs/](specs/00-overview.md) | Behaviour specs | **What** the engine does: contracts, Given/When/Then behaviours, error conditions, acceptance criteria. Never implementation code. | [Spec rules](#spec-rules) |
| [adr/](adr/README.md) | Architecture decision records | **Why**: one decision each, its options, trade-offs and consequences. Links specs, restates none. | [Decision rules](#decision-rules) |
| [research/](research/README.md) | Research notes | Background findings that answer an unknown, with sources and confidence marks. | [Research rules](#research-rules) |

Read in this order before planning or coding a component: the [overview spec](specs/00-overview.md), the [contracts spec](specs/01-contracts.md), the component spec, then the decision records and research notes it links.

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

- One decision per record, in `adr/NNNN-short-title.md`, numbered above the folder's highest.
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

