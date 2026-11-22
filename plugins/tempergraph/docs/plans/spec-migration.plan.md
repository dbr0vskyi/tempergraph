---
task: spec-migration
complexity: complex
status: in-progress
specs: [plugins/tempergraph/docs/specs/*.spec.md, plugins/temperspec-tgraph/rules/spec.rule.md]
---

# Plan: move the engine's specs to temperspec's spec format

## 0. Hand-off

- Asked by the owner on 2026-11-22 ("Migrate tempergraph specs"), after the format and rules C1 to C8 of [R-127](../research/R-127-spec-format-behaviours-first-without-cascades.rsrch.md) were agreed on 2026-11-21 and the 400-line cap was set.
- The target format is temperspec's [spec rule](../../../temperspec-tgraph/rules/spec.rule.md): `# Title`, `## Purpose`, `## Behaviours` (`### PREFIX-Bn name`, one `WHEN … THE … SHALL …` line, `- GIVEN … WHEN … THEN …` scenarios), `## Acceptance criteria` (`- PREFIX-ACn (behaviour ids): …`), and `## Open questions` only while one is open. No front matter, no status, no version, no interface section, no contract tables, no design notes, no references list. At most 400 lines; this set also keeps its 30 KB budget ([test_spec_budget](../../engine/tests/test_spec_budget.py)).
- The check is temperspec's own parser, `workflow/temperspec/specfmt.py` (`parse_spec`), the same one its `ts-spec-form` gate runs. Every migrated spec passes it with no problem.
- Why one pass and not spec by spec as they are edited: the rule's last section would leave the set in two layouts for months, and every temperspec run on this repository that edits an engine spec fails `ts-spec-form` until the spec is migrated (stage M of temperspec's [next-stages plan](../../../temperspec-tgraph/docs/plans/next-stages.plan.md)).

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | Every engine spec is in the rule's layout and passes `specfmt.parse_spec` with no problem | every spec |
| R2 | AC 2 | No behaviour or criterion id defined on `main` before the migration is lost; criterion ids keep their number | every spec |
| R3 | AC 3 | Every section reference (`BUD §2.2`, `contract C13`) anywhere in the repository, outside the map below, is rewritten to the ids it became, and the map keeps every old reference resolvable | every spec |
| R4 | AC 4 | Every fact of a contract table, an error table or a design note that someone outside the capability depends on is kept, as a behaviour, a scenario or in a decision record or research note; what is dropped is dropped on purpose by the rules in section 2 | every spec |
| R5 | AC 5 | Engine tests that read spec text read the new layout and still guard the same drift | `test_contract_tables.py`, `test_spec_budget.py` |
| R6 | AC 6 | The docs README's spec rules, the overview and every guide or plan that describes the old layout say what is true after the migration | `docs/README.md`, `00-overview.spec.md` |

## 2. How each part of an engine spec moves

| Part today | Becomes |
|---|---|
| Front matter (`title`, `type`, `status`, `prefix`, `adrs`) | Dropped (R-127 C1, C2). The title is the `#` heading; the prefix stays the prefix of every id; the overview's Purpose names each spec by path. Status lives in the plans and the live-checks plan, as it already did for what is built |
| `## 1. Overview` | `## Purpose`: one short paragraph. Goals and non-goals that matter become behaviours (overview) or stay in the decision record that holds them |
| `## 2. Contract` tables and their subsections | Behaviours. A row someone outside the capability depends on (a verb, an option, a field, a file path, a default, an exit code, a record kind) becomes a behaviour, or a scenario of the behaviour it belongs to, and keeps its exact names. Rows that list one shape compactly (a set of fields, a set of values) become one behaviour whose statement names the whole set. A row that only describes how the engine does it is dropped |
| `## 3. Behaviours` (`**X-Bn Name.** Given … when … then …`) | Kept with the same id: the heading `### X-Bn Name`, a new `WHEN … THE … SHALL …` statement, the old sentence as the first scenario. An embedded table becomes scenarios |
| `## 4. Error conditions` | Behaviours: one per result, or a scenario of the behaviour whose input is refused |
| `## 5. Design notes` | Dropped from the spec. A note whose reason is in a linked decision record or research note is already kept there; the Purpose links that record. The rest move, unchanged in substance, to [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md), one section per prefix |
| Probe tables and maturity flags (`LIVE-PROVEN`, `BUILT, AWAITING LIVE CHECK`, …) | Probe definitions and their results move to R-150 under the spec's prefix, and the live-checks plan keeps every pending row it had. A maturity flag is dropped (R-127 C1) |
| `## 6. Acceptance criteria` (`- [ ] X-AC-n text`) | `- X-ACn (X-Bm, …): text`, same number. Every criterion names the behaviours it proves; a behaviour no criterion names gets a new criterion with the next free number |
| `## Open questions` table | A list, one question per item, with its owner and the default the engine applies until it is answered. A question already answered by a ruling is removed and its answer is a behaviour |
| `## References` | Dropped (R-127 C2): links stay inline where they are used |

### Ids and links

- Behaviour ids keep their number and their meaning. New behaviours take the next free number of the prefix. Ids are never renumbered.
- `X-AC-n` becomes `X-ACn` everywhere in the repository in one mechanical rename. Nothing else about a criterion id changes.
- A link to another spec is a link to its ids: `[EVT-B12](30-run-events.spec.md)`. While specs are migrated one by one, a migrated spec may still write an unmigrated spec's old `§` reference; the last phase rewrites them all from the map.
- The map (section 5) lists, for every numbered section of every spec, the ids it became. It is written as each spec is migrated and is frozen when the plan completes: an old reference in a branch made before the migration (or in a commit message) still resolves through it. The repository is then rewritten from it, and a test fails on any `PREFIX §n` reference outside this plan and R-150.
- The overview's engine-wide contracts C1 to C18 become overview behaviours; `contract Cn` references are rewritten from the map in the same way.

### Over the cap

A spec that would pass 400 lines or 30 KB is split by capability into two specs, each with its own prefix (the rule: one prefix per spec). The behaviours and criteria that move keep their old ids, so the new spec defines ids with the old prefix next to its own new ones; the old prefix is then retired for new ids in the new spec. Only then is compression tried: merging scenarios that prove the same thing. The new specs take free numbers (23 to 29, 36 to 39, 47 to 49, 52 to 54, 59, 66 to 69, 98).

### The contracts spec

R-127's rule C5 says a shared type lives in the spec that owns its behaviour, with no central contracts file. Dissolving CON moves types into some 25 specs and is a design change of its own. This migration moves CON into the new layout in place (split if over the cap) and leaves the dissolution as a follow-up, recorded in the backlog of section 6.

### Left as they are

- Workflow packages' own specs and the engine's scaffold, which still writes package specs in the earlier layout (spec 91, SCF). Changing what the scaffold writes is an engine behaviour change with its own tests; it is a follow-up in section 6.
- The monitor's spec set (`plugins/tempergraph-monitor/docs/specs`): its own design set. Only its references to engine sections are rewritten.

## 3. Phases

### Phase 1: Plan and pilot

Goal: this plan, the check script, and three migrated specs that pass the parser: a small one (32 RCT), one that tests read (17 CLI, split into CLI, run options and lifecycle hooks) and a release 2 spec (92 LAD).
Weight: light

### Phase 2: The rest, in number order

Goal: every other spec migrated and passing the parser, its map rows written. Specs that the open pull request 39 edits (00, 02, 05, 06, 08, 11, 15, 55, 61, 62, 75, 91, and the new 99) go last, from `main` after it merges.
Weight: heavy (large-context)

### Phase 3: References, tests and docs

Goal: every `§` and `contract Cn` reference rewritten from the map, every `X-AC-n` renamed, the engine tests that read spec text moved to the new layout, the docs README's spec rules and the plans index updated, and a test that no old reference is left.
Weight: heavy (refactor)

## 4. Verification

- `cd plugins/tempergraph/engine && python -m pytest`
- `cd plugins/tempergraph/engine && ruff check src tests`
- `cd plugins/tempergraph/engine && mypy`

The form of every spec is checked with temperspec's parser, run over `plugins/tempergraph/docs/specs/*.spec.md` (`specfmt.parse_spec` returns no problem and `legacy` is false), and every id defined on `main` before the migration is compared with the ids defined after it.

## 5. Section map

Filled in per spec as it is migrated; complete when the plan is `completed`. Each line: an old reference, then what it became.

## 6. Follow-ups

- Dissolve the contracts spec (R-127 C5): each shared type moves to the spec that owns its behaviour.
- The scaffold writes package specs in temperspec's layout, and the package docs check reads it (specs 88 PKG and 91 SCF).
- A generated index of specs in the overview's Purpose (R-127 C3), so adding a spec edits no hand-kept list.
