# tempergraph design docs

The design of the tempergraph engine, written the spec-driven way temperspec follows: **research → decision record → spec → plan → code**. Each link is a document the next link reads, so a fresh session can implement a component from its spec without a conversation.

Code for releases 1 and 2 lives in [`../engine/`](../engine/pyproject.toml) (engine `0.2.0`), built track by track; the live checks still open are in [plans/live-checks.plan.md](plans/live-checks.plan.md). Release 1 is scoped by [ADR-0090](adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md) and planned in [plans/first-release.plan.md](plans/first-release.plan.md); its readiness review is [R-090](research/R-090-implementation-readiness.rsrch.md). Release 2 is scoped by [ADR-0125](adr/0125-release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing.adr.md) and planned in [plans/second-release.plan.md](plans/second-release.plan.md), with readiness in [R-130](research/R-130-release-two-readiness-and-gaps.rsrch.md). Release 3 is proposed in [ADR-0132](adr/0132-release-three-is-workflows-that-compose-run-in-parallel-and-grade-in-the-pipeline.adr.md) and planned in [plans/third-release.plan.md](plans/third-release.plan.md), with readiness in [R-140](research/R-140-release-three-readiness-and-gaps.rsrch.md). Each track has its expanded plan in [plans/](plans/README.md).

## Where things live

| Folder | Document type | Holds | Rule |
|---|---|---|---|
| [specs/](specs/00-overview.spec.md) | Behaviour specs | **What** the engine does: a purpose, `WHEN … THE … SHALL …` behaviours with Given/When/Then scenarios, acceptance criteria. Never implementation code. | [Spec rules](#spec-rules) |
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

Since 2026-11-22 the engine's specs follow temperspec's [spec rule](../../temperspec-tgraph/rules/spec.rule.md) ([spec-migration plan](plans/spec-migration.plan.md)); the engine test `tests/test_spec_form.py` holds the set to it:

- **Sections.** `# Title`, `## Purpose`, `## Behaviours`, `## Acceptance criteria`, and `## Open questions` only while a question is open. No front matter, no status, no numbered sections, no contract or error tables, no design notes, no references list, no code blocks, no checkboxes.
- **Behaviours.** `### PREFIX-Bn Name`, then one line `WHEN <event> THE <system> SHALL <response>`, then at least one scenario `- GIVEN … WHEN … THEN …`. A verb, an option, a field, a file path, a default, an exit code or a record kind that someone outside the capability depends on is named in a behaviour.
- **Criteria.** `- PREFIX-ACn (behaviour ids): <what an observer can verify>`. Every behaviour is named by at least one criterion.
- **Open questions.** One item each: the question, `Until answered:` the default the engine applies, `Owner:`. Work a spec describes and the code does not hold yet is a `Not built yet:` item with its owner.
- **Ids.** Each spec owns one prefix, and the overview's Purpose names every spec by its path. Ids are never renumbered; a new behaviour takes the next free number. A behaviour moved by a split keeps its old id. A link to another spec names its ids: `[EVT-B12](specs/30-run-events.spec.md)`.
- **Types.** The contracts spec (CON, with the session contract SSN) is still the only definition of a type two specs share; dissolving it into the owning specs is a follow-up of the migration plan.
- **Why.** The reasons behind a behaviour live in the decision record or research note the Purpose links; what the specs held before 2026-11-22 as design notes, release notes and probe observations is in [R-150](research/R-150-rationale-carried-from-the-engine-specs.rsrch.md). An old `PREFIX §n` reference resolves through section 5 of the migration plan.
- **Budget.** At most 400 lines and 30 KB per spec. An over-budget spec is split by capability, never extended.

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

## Readiness

Specs describe intended behaviour and carry no status or maturity flag. What releases 1 and 2 built, track by track, and what each track left open, is in the [plans index](plans/README.md) and the track plans; what a spec describes and the code does not hold yet is a `Not built yet:` item in its Open questions. What is proven against a real executor is in the [live-checks plan](plans/live-checks.plan.md): a capability counts as live-proven only with a written result there (the date, the machine, the executor and its version, and what was run). A passing test against a stand-in proves it built, never live.
