---
task: spec-migration
complexity: complex
status: completed
specs: [plugins/tempergraph/docs/specs/*.spec.md, plugins/temperspec-tgraph/rules/spec.rule.md]
---

# Plan: move the engine's specs to temperspec's spec format

## 0. Hand-off

- Asked by the owner on 2026-11-22 ("Migrate tempergraph specs"), after the format and rules C1 to C8 of [R-127](../research/R-127-spec-format-behaviours-first-without-cascades.rsrch.md) were agreed on 2026-11-21 and the 400-line cap was set.
- The target format is temperspec's [spec rule](../../../temperspec-tgraph/rules/spec.rule.md): `# Title`, `## Purpose`, `## Behaviours` (`### PREFIX-Bn name`, one `WHEN … THE … SHALL …` line, `- GIVEN … WHEN … THEN …` scenarios), `## Acceptance criteria` (`- PREFIX-ACn (behaviour ids): …`), and `## Open questions` only while one is open. No front matter, no status, no version, no interface section, no contract tables, no design notes, no references list. At most 400 lines; this set also keeps its 30 KB budget ([test_spec_budget](../../engine/tests/test_spec_budget.py)).
- The check is temperspec's own parser, `workflow/temperspec/specfmt.py` (`parse_spec`), the same one its `ts-spec-form` gate runs. Every migrated spec passes it with no problem.
- Why one pass and not spec by spec as they are edited: the rule's last section would leave the set in two layouts for months, and every temperspec run on this repository that edits an engine spec fails `ts-spec-form` until the spec is migrated (stage M of temperspec's next-stages plan, in pull request 40).

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | Every engine spec is in the rule's layout and passes `specfmt.parse_spec` with no problem | every spec |
| R2 | AC 2 | No behaviour or criterion id defined on `main` before the migration is lost; criterion ids keep their number | every spec |
| R3 | AC 3 | Every section reference (`BUD §2.2`, `contract C13`) anywhere in the repository, outside the map below, is rewritten to the ids it became, and the map keeps every old reference resolvable | every spec |
| R4 | AC 4 | Every fact of a contract table, an error table or a design note that someone outside the capability depends on is kept, as a behaviour, a scenario or in a decision record or research note; what is dropped is dropped on purpose by the rules in section 2 | every spec |
| R5 | AC 5 | Engine tests that read spec text read the new layout and still guard the same drift | `test_contract_tables.py`, `test_spec_budget.py` |
| R6 | AC 6 | The docs README's spec rules, the overview and every guide or plan that describes the old layout say what is true after the migration | `docs/README.md`, `overview.spec.md` |

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
- A link to another spec is a link to its ids: `[EVT-B12](../specs/run-events.spec.md)`. While specs are migrated one by one, a migrated spec may still write an unmigrated spec's old `§` reference; the last phase rewrites them all from the map.
- The map (section 5) lists, for every numbered section of every spec, the ids it became. It is written as each spec is migrated and is frozen when the plan completes: an old reference in a branch made before the migration (or in a commit message) still resolves through it. The repository is then rewritten from it, and a test fails on any `PREFIX §n` reference outside this plan and R-150.
- The overview's engine-wide contracts C1 to C18 become overview behaviours; `contract Cn` references are rewritten from the map in the same way.

### Over the cap

A spec that would pass 400 lines or 30 KB is split by capability into two specs, each with its own prefix (the rule: one prefix per spec). The behaviours and criteria that move keep their old ids, so the new spec defines ids with the old prefix next to its own new ones; the old prefix is then retired for new ids in the new spec. Only then is compression tried: merging scenarios that prove the same thing. The new specs take free numbers (23 to 29, 36 to 39, 47 to 49, 52 to 54, 59, 66 to 69, 98).

### The contracts spec

R-127's rule C5 says a shared type lives in the spec that owns its behaviour, with no central contracts file. Dissolving CON moves types into some 25 specs and is a design change of its own. This migration moves CON into the new layout in place (split if over the cap) and leaves the dissolution as a follow-up, recorded in the backlog of section 6.

### Left as they are

- Workflow packages' own specs and the engine's scaffold, which still writes package specs in the earlier layout (spec `blueprint-and-scaffold`, SCF). Changing what the scaffold writes is an engine behaviour change with its own tests; it is a follow-up in section 6.
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

The engine's own test `tests/test_spec_form.py` holds the form, that the overview names every spec, and that no old reference is left. The form of every spec was also checked with temperspec's parser, run over `plugins/tempergraph/docs/specs/*.spec.md` (`specfmt.parse_spec` returns no problem and `legacy` is false), and every id defined on `main` before the migration is compared with the ids defined after it.

## 5. Section map

Frozen on 2026-11-22. Each line: a spec's prefix, then each old section reference and the ids it became; `Purpose` is the spec's Purpose, `R-150 X` the finding for that prefix in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md). The repository was rewritten from this map; an old reference in an older branch or commit message resolves here.

- OVR ([overview.spec.md](../specs/overview.spec.md)): §1 = OVR (Purpose) · §2 = OVR (Purpose) · §2.1 = OVR (Purpose) · §2.2 = OVR (Purpose) · §2.3 = OVR-B3 to OVR-B20 · §3 = OVR-B1, OVR-B2 · §4 = OVR-B21 · §5 = R-150 OVR · §6 = OVR-AC1
- CON ([contracts.spec.md](../specs/contracts.spec.md)): §2 = CON-B3 to CON-B15, SSN-B1 to SSN-B10 · §2.1 = CON-B4, CON-B5, CON-B6, CON-B7 · §2.2 = CON-B8 · §2.3 = CON-B9 · §2.4 = CON-B3 · §2.5 = CON-B11 · §2.6 = SSN-B1 to SSN-B6 · §2.7 = SSN-B7 · §2.8 = SSN-B8, SSN-B9, SSN-B10 · §2.9 = CON-B12, CON-B13 · §2.10 = CON-B14, CON-B1, CON-B15 · §3 = CON-B1 · §4 = CON-B8, CON-B3, CON-B11, SSN-B3, CON-B15 · §5 = ADR-0006 · §6 = CON-AC1 · §2.11 = AUD (moved) · §2.12 = RST (moved) · §2.13 = PRV (moved) · §2.14 = PKG, OUT (moved)
- WFM ([workflow-model.spec.md](../specs/workflow-model.spec.md)): §1 = WFM (Purpose) · §2 = WFM-B7 · §2.1 = WFM-B8, WFM-B9, WFM-B10, WFM-B11 · §2.2 = WFM-B12 · §3 = WFM-B1 to WFM-B6 · §4 = WFM-B7 · §5 = R-150 WFM · §6 = WFM-AC1
- CMP ([compiler-and-flow.spec.md](../specs/compiler-and-flow.spec.md)): §2 = CMP-B8 · §2.1 = CMP-B9 · §2.2 = CMP-B10 to CMP-B16 · §2.3 = CMP-B17 · §3 = CMP-B1 · §4 = CMP-B17, CMP-B18, CMP-B14 · §5 = ADR-0004 · §6 = CMP-AC1
- PRM ([prompt-rendering.spec.md](../specs/prompt-rendering.spec.md)): §2 = PRM-B1, PRM-B6 · §2.1 = PRM-B6 · §2.2 = PRM-B8 · §2.3 = PRM-B11 · §3 = PRM-B1 · §4 = PRM-B12, PRM-B13 · §5 = PRM-B14 · §6 = PRM-AC1
- JDG ([judge-and-verdict.spec.md](../specs/judge-and-verdict.spec.md)): §1 = JDG (Purpose) · §2 = JDG-B10 · §2.1 = JDG-B11, JDG-B12 · §2.2 = JDG-B13 · §3 = JDG-B1 to JDG-B9 · §4 = JDG-B3, JDG-B13, JDG-B11 · §5 = R-150 JDG · §6 = JDG-AC1
- GRD ([independence-guard.spec.md](../specs/independence-guard.spec.md)): §1 = GRD (Purpose) · §2 = GRD-B1, GRD-B8 · §2.1 = GRD-B7 · §2.2 = GRD-B8 · §3 = GRD-B1 to GRD-B6 · §4 = GRD-B6, GRD-B5, GRD-B8 · §5 = R-150 GRD · §6 = GRD-AC1
- HUM ([gate-and-human.spec.md](../specs/gate-and-human.spec.md)): §2 = HUM-B2 · §2.1 = HUM-B7 to HUM-B11 · §2.2 = HUM-B12 · §3 = HUM-B1 · §4 = HUM-B13 · §5 = ADR-0004 · §6 = HUM-AC1
- BUD ([budgets-and-failures.spec.md](../specs/budgets-and-failures.spec.md)): §1 = BUD (Purpose) · §2 = BUD-B8, BUD-B9 · §2.1 = BUD-B10 · §2.2 = BUD-B1, BUD-B11 · §2.3 = BUD-B12 · §3 = BUD-B1 to BUD-B7 · §4 = BUD-B8 · §5 = R-150 BUD · §6 = BUD-AC1
- DUR ([durability-and-resume.spec.md](../specs/durability-and-resume.spec.md)): §2 = DUR-B9, DUR-B11 · §2.1 = DUR-B9 · §2.2 = DUR-B11 · §3 = DUR-B1 · §4 = DUR-B10, DUR-B3, DUR-B11 · §5 = ADR-0014 · §6 = DUR-AC1
- EXI ([executor-interface.spec.md](../specs/executor-interface.spec.md)): §2 = EXI-B16 to EXI-B24 · §2.1 = EXI-B16, EXI-B17 · §2.2 = EXI-B18 · §2.3 = EXI-B2, EXI-B20, EXI-B21, EXI-B22, EXI-B23, EXI-B15 · §2.4 = EXI-B24 · §3 = EXI-B1 · §4 = EXI-B1, EXI-B6 · §5 = ADR-0006 · §6 = EXI-AC1
- ECC ([executor-claude-code.spec.md](../specs/executor-claude-code.spec.md)): §1 = ECC (Purpose) · §2 = ECC-B6 to ECC-B14 · §2.1 = ECC-B6 · §2.2 = ECC-B7 · §2.3 = ECC-B8, ECC-B9 · §2.4 = ECC-B10 · §2.5 = ECC-B11 · §2.6 = ECC-B12 · §2.7 = ECC-B13 · §2.8 = ECC-B14 · §3 = ECC-B1 to ECC-B5 · §4 = ECC-B13, ECC-B11 · §5 = R-150 ECC · §6 = ECC-AC1
- EAG ([executor-antigravity.spec.md](../specs/executor-antigravity.spec.md)): §2 = EAG-B8 to EAG-B14 · §2.1 = EAG-B8 · §2.2 = EAG-B9 · §2.3 = EAG-B10, EAG-B11, EAG-B5 · §2.4 = EAG-B12, EAG-B1 · §2.5 = EAG-B13 · §2.6 = EAG-B14 · §2.7 = R-150 EAG · §3 = EAG-B1 · §4 = EAG-B15, EAG-B10, EAG-B13 · §5 = R-150 EAG · §6 = EAG-AC1
- WSP ([workspace-and-concurrency.spec.md](../specs/workspace-and-concurrency.spec.md)): §2 = WSP-B8, WSP-B9, WSP-B11 · §2.1 = WSP-B11, WSP-B12 · §2.2 = WSP-B13, WSP-B7 · §2.3 = WSP-B10 · §2.4 = WSP-B15 to WSP-B18 · §3 = WSP-B1 · §4 = WSP-B4, WSP-B12, WSP-B16 · §5 = R-150 WSP · §6 = WSP-AC1
- SEC ([security.spec.md](../specs/security.spec.md)): §2 = SEC-B5 to SEC-B13 · §2.1 = SEC-B5, SEC-B6 · §2.2 = SEC-B7 · §2.3 = SEC-B8 to SEC-B11 · §2.4 = SEC-B12, SEC-B13 · §3 = SEC-B1 · §4 = SEC-B7, SEC-B8 · §5 = R-150 SEC · §6 = SEC-AC1
- OBS ([observability-and-cost.spec.md](../specs/observability-and-cost.spec.md)): §1 = OBS (Purpose) · §2 = OBS-B7, OBS-B10 · §2.1 = OBS-B7, OBS-B1, OBS-B8, OBS-B9 · §2.2 = OBS-B10 to OBS-B13 · §2.3 = OBS-B14 · §2.4 = OBS-B15 · §3 = OBS-B1 to OBS-B6 · §4 = OBS-B10, OBS-B7 · §5 = R-150 OBS · §6 = OBS-AC1
- SIL ([self-improvement.spec.md](../specs/self-improvement.spec.md)): §2 = SIL-B8, SIL-B10, SIL-B11, SIL-B12 · §2.1 = SIL-B8 · §2.2 = SIL-B10 · §2.3 = SIL-B11 · §2.4 = SIL-B12 to SIL-B16 · §3 = SIL-B1 · §4 = SIL-B19, SIL-B20 · §5 = SIL-B17, SIL-B18 · §6 = SIL-AC1 · §1 = SIL-B8
- CLI ([engine-cli.spec.md](../specs/engine-cli.spec.md)): §2 = CLI-B7, CLI-B8, CLI-B14 · §2.1 = ROP-B1 to ROP-B13 · §2.2 = HOK-B1 to HOK-B6 · §3 = CLI-B1 · §4 = CLI-B17, CLI-B18, CLI-B19 · §5 = CLI-AC7 · §6 = CLI-AC1
- LIF ([lifecycle-and-evals.spec.md](../specs/lifecycle-and-evals.spec.md)): §2 = LIF-B7 to LIF-B16 · §2.1 = LIF-B12 · §2.2 = LIF-B13 · §2.3 = LIF-B4, LIF-B3 · §3 = LIF-B1 · §4 = LIF-B7, LIF-B9 · §5 = R-150 LIF · §6 = LIF-AC1
- SHL ([plugin-shell.spec.md](../specs/plugin-shell.spec.md)): §2 = SHL-B5 · §2.1 = SHL-B9 · §2.2 = SHL-B14, SHL-B15 · §2.3 = SHL-B5, SHL-B12, SHL-B13 · §3 = SHL-B1 · §4 = SHL-B6 · §5 = SHL-B7, SHL-B8, SHL-B11 · §6 = SHL-AC1
- EMA ([executor-messages-api.spec.md](../specs/executor-messages-api.spec.md)): §2 = EMA-B6 to EMA-B13 · §2.1 = EMA-B6 · §2.2 = EMA-B7 · §2.3 = EMA-B8 · §2.4 = EMA-B9, EMA-B10, EMA-B3 · §2.5 = EMA-B11 · §2.6 = EMA-B12 · §2.7 = EMA-B13 · §3 = EMA-B1 · §4 = EMA-B14, EMA-B8, EMA-B12 · §5 = EMA-B9 · §6 = EMA-AC1
- EAS ([executor-agent-sdk.spec.md](../specs/executor-agent-sdk.spec.md)): §2.1 = EAS-B5 · §2.2 = EAS-B6 · §2.3 = EAS-B7 · §2.4 = EAS-B8 · §2.5 = EAS-B9 · §2.6 = EAS-B10 · §2.7 = EAS-B11 · §2.8 = EAS-B12 · §2.9 = R-150 EAS · §3 = EAS-B1 · §4 = EAS-B13, EAS-B15 · §5 = R-150 EAS · §6 = EAS-AC1
- THS ([tool-host.spec.md](../specs/tool-host.spec.md)): §2 = THS-B5 to THS-B11 · §2.1 = THS-B5, THS-B6 · §2.2 = THS-B7 · §2.3 = THS-B8 · §2.4 = THS-B9 · §2.5 = THS-B10 · §2.6 = THS-B11 · §3 = THS-B1 · §4 = THS-B6, THS-B4, THS-B10, THS-B11 · §5 = THS · §6 = THS-AC1
- EVT ([run-events.spec.md](../specs/run-events.spec.md)): §2 = EVT-B8 to EVT-B24 · §2.1 = EVT-B8, EVT-B9 · §2.2 = EVT-B10 to EVT-B16 · §2.3 = EVT-B17, EVT-B18, EVT-B7, EVT-B19 · §2.4 = EVT-B20 · §2.5 = EVT-B21 · §2.6 = EVT-B22, EVT-B23, EVT-B24 · §3 = EVT-B1 · §4 = EVT-B25 · §5 = R-150 EVT · §6 = EVT-AC1
- RDD ([run-detail-document.spec.md](../specs/run-detail-document.spec.md)): §2 = RDD-B7 to RDD-B15 · §2.1 = RDD-B7 to RDD-B11, RDD-B13, RDD-B15 · §2.2 = RDD-B12 · §2.3 = RDD-B14 · §3 = RDD-B1 · §4 = RDD-B16, RDD-B8, RDD-B12 · §5 = RDD · §6 = RDD-AC1
- RCT ([run-control.spec.md](../specs/run-control.spec.md)): §2 = RCT-B6, RCT-B7 · §3 = RCT-B1 · §4 = RCT-B8, RCT-B9, RCT-B10 · §5 = ADR-0028 · §6 = RCT-AC1
- LOS ([local-observability-store.spec.md](../specs/local-observability-store.spec.md)): §2 = LOS-B7 to LOS-B17 · §2.1 = LOS-B7, LOS-B8, LOS-B9 · §2.2 = LOS-B10, LOS-B11 · §2.3 = LOS-B13 · §2.4 = LOS-B14, LOS-B15 · §2.5 = LOS-B16 · §2.6 = LOS-B17 · §3 = LOS-B1 · §4 = LOS-B12, LOS-B18, LOS-B15 · §5 = R-150 LOS · §6 = LOS-AC1
- CST ([central-run-stats.spec.md](../specs/central-run-stats.spec.md)): §2 = CST-B8 to CST-B16 · §2.1 = CST-B8 · §2.2 = CST-B9 · §2.3 = CST-B10, CST-B12, CST-B13 · §2.4 = CST-B11 · §2.5 = CST-B14, CST-B15, CST-B16 · §3 = CST-B1 · §4 = CST-B10, CST-B14, CST-B8 · §5 = R-150 CST · §6 = CST-AC1
- TEL ([telemetry-export.spec.md](../specs/telemetry-export.spec.md)): §2 = TEL-B5 to TEL-B37 · §2.1 = TEL-B5 to TEL-B11 · §2.2 = TEL-B12 to TEL-B33 · §2.3 = TEL-B34 to TEL-B37 · §2.4 = TEL-B6, TEL-B8 · §3 = TEL-B1 · §4 = TEL-B38, TEL-B39 · §5 = R-150 TEL · §6 = TEL-AC1
- PRP ([improvement-proposals.spec.md](../specs/improvement-proposals.spec.md)): §2 = PRP-B11 to PRP-B22 · §2.1 = PRP-B11 · §2.2 = PRP-B12 · §2.3 = PRP-B13 · §2.4 = PRP-B14, PRP-B15 · §2.5 = PRP-B17 · §2.6 = PRP-B18, PRP-B19, PRP-B20 · §2.7 = PRP-B4, PRP-B12, PRP-B18, PRP-B21, PRP-B8, PRP-B22 · §3 = PRP-B1 · §4 = PRP-B16, PRP-B17, PRP-B20, PRP-B7, PRP-B8 · §5 = PRP-B23 · §6 = PRP-AC1
- FBK ([feedback-and-judge-reliability.spec.md](../specs/feedback-and-judge-reliability.spec.md)): §2 = FBK-B8 to FBK-B14 · §2.1 = FBK-B8 · §2.2 = FBK-B9 · §2.3 = FBK-B11, FBK-B12 · §2.4 = FBK-B13 · §2.5 = FBK-B14 · §3 = FBK-B1 · §4 = FBK-B10 · §5 = R-150 FBK · §6 = FBK-AC1
- LSN ([workflow-lessons.spec.md](../specs/workflow-lessons.spec.md)): §2 = LSN-B6 to LSN-B9 · §2.1 = LSN-B6, LSN-B7 · §2.2 = LSN-B8, LSN-B2 · §2.3 = LSN-B9 · §3 = LSN-B1 · §4 = LSN-B6, LSN-B7 · §5 = LSN · §6 = LSN-AC1
- IMD ([improvement-data.spec.md](../specs/improvement-data.spec.md)): §2 = IMD-B5 to IMD-B23 · §2.1 = IMD-B5 to IMD-B19 · §2.2 = IMD-B20 · §2.3 = IMD-B21 · §2.4 = IMD-B22 · §2.5 = IMD-B23 · §3 = IMD-B1 · §4 = IMD-B20, IMD-B16, IMD-B24 · §5 = IMD-B22 · §6 = IMD-AC1
- SRV ([session-review.spec.md](../specs/session-review.spec.md)): §2 = SRV-B11 to SRV-B23 · §2.1 = SRV-B11 · §2.2 = SRV-B12 · §2.3 = SRV-B13, SRV-B14, SRV-B15 · §2.4 = SRV-B16, SRV-B5 · §2.5 = SRV-B17 · §2.6 = SRV-B18, SRV-B19, SRV-B20 · §2.6.1 = SRV-B19 · §2.6.2 = SRV-B20 · §2.7 = SRV-B21 · §2.8 = SRV-B22 · §2.9 = SRV-B23 · §3 = SRV-B1 · §4 = SRV-B1, SRV-B20, SRV-B21, SRV-B22, SRV-B18 · §5 = R-150 SRV · §6 = SRV-AC1
- ORC ([orchestration.spec.md](../specs/orchestration.spec.md)): §2 = ORC-B18 to ORC-B25 · §2.1 = ORC-B18 · §2.2 = ORC-B19, ORC-B20 · §2.3 = ORC-B21 · §2.4 = ORC-B22 · §2.5 = ORC-B23 · §2.6 = ORC-B24, ORC-B2, ORC-B6, ORC-B10, ORC-B14 · §2.7 = ORC-B25 · §2.8 = ORC-B17, ORC-B24, ORC-B26 · §3 = ORC-B1 · §4 = ORC-B18, ORC-B3, ORC-B4, ORC-B20, ORC-B22 · §5 = R-150 ORC · §6 = ORC-AC1
- OSK ([orchestrator-skill.spec.md](../specs/orchestrator-skill.spec.md)): §2 = OSK-B8 to OSK-B15 · §2.1 = OSK-B8 · §2.2 = OSK-B9, OSK-B11 · §2.3 = OSK-B10, OSK-B1, OSK-B11, OSK-B12, OSK-B13, OSK-B14 · §2.4 = OSK-B13 · §2.5 = OSK-B14 · §2.6 = OSK-B15 · §3 = OSK-B1 · §4 = OSK-B13, OSK-B10, OSK-B11, OSK-B15 · §5 = R-150 OSK · §6 = OSK-AC1
- JCL ([judge-calibration.spec.md](../specs/judge-calibration.spec.md)): §2 = JCL-B9 to JCL-B18 · §2.1 = JCL-B9, JCL-B10 · §2.1.1 = JCL-B11 · §2.1.2 = JCL-B12 · §2.2 = JCL-B13 · §2.3 = JCL-B14 · §2.3.1 = JCL-B15 · §2.4 = JCL-B16 · §2.5 = JCL-B17 · §2.6 = JCL-B14, JCL-B18 · §3 = JCL-B1 · §4 = JCL-B9, JCL-B12, JCL-B14 · §5 = JCL-B9 · §6 = JCL-AC1
- EVS ([eval-suites.spec.md](../specs/eval-suites.spec.md)): §2 = EVS-B8 to EVS-B18 · §2.1 = EVS-B8 · §2.3 = EVS-B12 · §2.4 = EVS-B13, EVS-B14 · §2.5 = EVS-B15 · §2.6 = EVS-B16 · §2.7 = EVS-B17, EVS-B18 · §3 = EVS-B1 · §4 = EVS-B13, EVS-B12, EVS-B14 · §5 = EVS-B10 · §6 = EVS-AC1 · §2.2 = EVS-B9, EVS-B2, EVS-B10
- AUD ([workflow-audit.spec.md](../specs/workflow-audit.spec.md)): §1 = AUD (Purpose) · §2 = AUD-B11, AUD-B12 · §2.1 = AUD-B11, AUD-B6, AUD-B9 · §2.2 = AUD-B12, AUD-B13 · §2.3 = AUD-B7, AUD-B12 · §2.4 = AUD-B14 · §2.5 = R-150 AUD · §3 = AUD-B1 to AUD-B10 · §4 = AUD-B15, AUD-B9, AUD-B2 · §5 = R-150 AUD · §6 = AUD-AC1
- ARC ([audit-rule-catalog.spec.md](../specs/audit-rule-catalog.spec.md)): §2 = ARC-B6 to ARC-B16 · §2.1 = ARC-B6 · §2.2 = ARC-B7 · §2.3 = ARC-B8, ARC-B9 · §2.4 = ARC-B10 · §2.5 = ARC-B11 · §2.6 = ARC-B12 · §2.7 = ARC-B13 · §2.8 = ARC-B14 · §2.9 = ARC-B15 · §2.10 = ARC-B6, ARC-B10, ARC-B16 · §3 = ARC-B1 · §4 = ARC-B7 · §5 = ARC · §6 = ARC-AC1
- TSA ([tool-surface-audit.spec.md](../specs/tool-surface-audit.spec.md)): §2 = TSA-B6 to TSA-B12 · §2.1 = TSA-B6 · §2.2 = TSA-B7 · §2.3 = TSA-B8 · §2.4 = TSA-B9 to TSA-B12 · §3 = TSA-B1 · §4 = TSA-B9, TSA-B6, TSA-B7 · §5 = TSA · §6 = TSA-AC1
- PRA ([prompt-audit.spec.md](../specs/prompt-audit.spec.md)): §2 = PRA-B5 to PRA-B11 · §2.1 = PRA-B5 · §2.2 = PRA-B6 · §2.3 = PRA-B7 to PRA-B10 · §2.4 = PRA-B11 · §2.5 = PRA-B7 to PRA-B11 · §3 = PRA-B1 · §4 = PRA-B7, PRA-B5, PRA-B10 · §5 = PRA · §6 = PRA-AC1
- UPD ([engine-update.spec.md](../specs/engine-update.spec.md)): §2 = UPD-B10 to UPD-B24 · §2.1 = UPD-B10 · §2.2 = UPD-B11, UPD-B12, UPD-B13 · §2.3 = UPD-B14, UPD-B6 · §2.4 = UPD-B15 · §2.5 = UPD-B16 · §2.6 = UPD-B17 · §2.7 = UPD-B18, UPD-B19 · §2.8 = UPD-B20 to UPD-B24 · §3 = UPD-B1 · §4 = UPD-B19, UPD-B14, UPD-B11, UPD-B13, UPD-B22, UPD-B20 · §5 = R-150 UPD · §6 = UPD-AC1
- VER ([version-metadata.spec.md](../specs/version-metadata.spec.md)): §2 = VER-B7 to VER-B17, VER-B2 · §2.1 = VER-B7 · §2.2 = VER-B8 · §2.3 = VER-B9 · §2.3.1 = VER-B10 · §2.3.2 = VER-B11 · §2.3.3 = VER-B12 · §2.3.4 = VER-B13 · §2.4 = VER-B14, VER-B15 · §2.5 = VER-B16 · §2.6 = VER-B17 · §2.7 = VER-B2, VER-B5 · §3 = VER-B1 to VER-B6 · §4 = VER-B18 · §5 = R-150 VER · §6 = VER-AC1
- MIG ([state-and-run-migration.spec.md](../specs/state-and-run-migration.spec.md)): §2 = MIG-B8 to MIG-B18 · §2.1 = MIG-B8 · §2.2 = MIG-B9, MIG-B10, MIG-B5 · §2.3 = MIG-B11 · §2.4 = MIG-B12, MIG-B13, MIG-B14 · §2.5 = MIG-B15 · §2.6 = MIG-B17 · §2.7 = MIG-B18 · §3 = MIG-B1 to MIG-B7 · §4 = MIG-B16, MIG-B12, MIG-B10, MIG-B15 · §5 = R-150 MIG · §6 = MIG-AC1
- WUP ([workflow-upgrade.spec.md](../specs/workflow-upgrade.spec.md)): §2 = WUP-B10 to WUP-B21 · §2.1 = WUP-B10, WUP-B11, WUP-B12, WUP-B13 · §2.2 = WUP-B14, WUP-B7 · §2.3 = WUP-B15, WUP-B16 · §2.4 = WUP-B17 · §2.5 = WUP-B18 · §2.6 = WUP-B19 · §2.7 = WUP-B20, WUP-B21 · §3 = WUP-B1 to WUP-B9 · §4 = WUP-B11, WUP-B17, WUP-B15, WUP-B18, WUP-B21 · §5 = R-150 WUP · §6 = WUP-AC1
- UWF ([upgrade-workflow.spec.md](../specs/upgrade-workflow.spec.md)): §2 = UWF-B6 to UWF-B13 · §2.1 = UWF-B6, UWF-B5, UWF-B7 · §2.2 = UWF-B8, UWF-B9, UWF-B10 · §2.3 = UWF-B11 · §2.4 = UWF-B12, UWF-B13 · §3 = UWF-B1 to UWF-B5 · §4 = UWF-B7, UWF-B13, UWF-B12 · §5 = R-150 UWF · §6 = UWF-AC1
- LSK ([lifecycle-skills.spec.md](../specs/lifecycle-skills.spec.md)): §2 = LSK-B6 to LSK-B14 · §2.1 = LSK-B6 · §2.2 = LSK-B7, LSK-B8 · §2.3 = LSK-B9, LSK-B10 · §2.4 = LSK-B11, LSK-B12 · §2.5 = LSK-B13 · §2.6 = LSK-B9 · §3 = LSK-B1 to LSK-B5 · §4 = LSK-B12, LSK-B14 · §5 = R-150 LSK · §6 = LSK-AC1
- SCR ([script-units-and-hybrid-steps.spec.md](../specs/script-units-and-hybrid-steps.spec.md)): §2 = SCR-B5 to SCR-B9 · §2.1 = SCR-B5 · §2.2 = SCR-B7, SCR-B2 · §2.3 = SCR-B9 · §2.4 = SCR-B6 · §3 = SCR-B1 to SCR-B4 · §4 = SCR-B8, SCR-B9 · §5 = R-150 SCR · §6 = SCR-AC1
- CNL ([council-unit.spec.md](../specs/council-unit.spec.md)): §2 = CNL-B9 to CNL-B16 · §2.1 = CNL-B9, CNL-B10 · §2.2 = CNL-B11 · §2.3 = CNL-B12 · §2.4 = CNL-B13 · §2.5 = CNL-B14 · §2.6 = CNL-B16 · §3 = CNL-B1 to CNL-B8 · §4 = CNL-B15, CNL-B14, CNL-B12 · §5 = R-150 CNL · §6 = CNL-AC1
- CTS ([contest-unit.spec.md](../specs/contest-unit.spec.md)): §2 = CTS-B6 to CTS-B10 · §2.1 = CTS-B6 · §2.2 = CTS-B7 · §2.3 = CTS-B8 · §2.4 = CTS-B10 · §3 = CTS-B1 to CTS-B5 · §4 = CTS-B9 · §5 = R-150 CTS · §6 = CTS-AC1
- ASK ([ask-unit.spec.md](../specs/ask-unit.spec.md)): §2 = ASK-B5 to ASK-B9 · §2.1 = ASK-B5, ASK-B6 · §2.2 = ASK-B7 · §2.3 = ASK-B8 · §3 = ASK-B1 to ASK-B4 · §4 = ASK-B2, ASK-B9 · §5 = R-150 ASK · §6 = ASK-AC1
- FLX ([flow-extensions.spec.md](../specs/flow-extensions.spec.md)): §2 = FLX-B6 to FLX-B11 · §2.1 = FLX-B6 · §2.2 = FLX-B7 · §2.3 = FLX-B8 · §2.4 = FLX-B9 · §2.5 = FLX-B10 · §2.6 = FLX-B11 · §3 = FLX-B1 to FLX-B5 · §4 = FLX-B6, FLX-B8 · §5 = R-150 FLX · §6 = FLX-AC1
- CHK ([check-contract-and-command-runs.spec.md](../specs/check-contract-and-command-runs.spec.md)): §2 = CHK-B10 to CHK-B17 · §2.1 = CHK-B10 · §2.2 = CHK-B11 · §2.3 = CHK-B12, CHK-B13 · §2.4 = CHK-B14 · §2.5 = CHK-B17 · §2.6 = CHK-B16 · §3 = CHK-B1 to CHK-B9 · §4 = CHK-B15, CHK-B14, CHK-B10, CHK-B17 · §5 = R-150 CHK · §6 = CHK-AC1
- VAL ([step-values-and-template-keys.spec.md](../specs/step-values-and-template-keys.spec.md)): §2 = VAL-B5 to VAL-B8 · §2.1 = VAL-B5, VAL-B6 · §2.2 = VAL-B7 · §2.3 = VAL-B8 · §3 = VAL-B1 to VAL-B4 · §4 = VAL-B8, VAL-B5, VAL-B3 · §5 = R-150 VAL · §6 = VAL-AC1
- MAP ([map-unit.spec.md](../specs/map-unit.spec.md)): §2 = MAP-B7 to MAP-B11 · §2.1 = MAP-B7 · §2.2 = MAP-B8, MAP-B9, MAP-B10 · §2.3 = MAP-B11 · §3 = MAP-B1 to MAP-B6 · §4 = MAP-B8, MAP-B10, MAP-B9 · §5 = R-150 MAP · §6 = MAP-AC1
- FIN ([finalizer-contract.spec.md](../specs/finalizer-contract.spec.md)): §2 = FIN-B6 to FIN-B10 · §2.1 = FIN-B6 · §2.2 = FIN-B7 · §2.3 = FIN-B8 · §2.4 = FIN-B9 · §3 = FIN-B1 to FIN-B5 · §4 = FIN-B10, FIN-B7 · §5 = R-150 FIN · §6 = FIN-AC1
- SWM ([measured-switches.spec.md](../specs/measured-switches.spec.md)): §2 = SWM-B4 to SWM-B7 · §2.1 = SWM-B4 · §2.2 = SWM-B5 · §2.3 = SWM-B6 · §2.4 = SWM-B7 · §3 = SWM-B1 to SWM-B3 · §4 = SWM-B4, SWM-B5 · §5 = R-150 SWM · §6 = SWM-AC1
- RST ([run-settings-and-overrides.spec.md](../specs/run-settings-and-overrides.spec.md)): §2 = RST-B16 to RST-B32 · §2.1 = RST-B17 · §2.2 = RST-B18, RST-B19, RST-B20, RST-B21 · §2.3 = RST-B22, RST-B23 · §2.4 = RST-B24 · §2.5 = RST-B25 · §2.5.5 = RST-B22 · §2.6 = RST-B26 · §2.7 = RST-B27 · §2.8 = RST-B28, RST-B29, RST-B30 · §2.9 = RST-B31 · §3 = RST-B1 to RST-B15 · §4 = RST-B32 · §5 = R-150 RST · §6 = RST-AC1
- RRN ([reruns-and-feedback.spec.md](../specs/reruns-and-feedback.spec.md)): §2 = RRN-B12 to RRN-B20 · §2.1 = RRN-B12 · §2.2 = RRN-B14, RRN-B15 · §2.3 = RRN-B16 · §2.4 = RRN-B17, RRN-B18 · §2.5 = RRN-B19 · §2.6 = RRN-B20 · §3 = RRN-B1 to RRN-B11 · §4 = RRN-B16, RRN-B17, RRN-B18, RRN-B14, RRN-B15 · §5 = R-150 RRN · §6 = RRN-AC1
- WTR ([worktree-mode.spec.md](../specs/worktree-mode.spec.md)): §2 = WTR-B17 to WTR-B27 · §2.1 = WTR-B17 · §2.2 = WTR-B18 · §2.3 = WTR-B19 · §2.4 = WTR-B20 · §2.5 = WTR-B21 · §2.6 = WTR-B22 · §2.7 = WTR-B23 · §2.8 = WTR-B24 · §2.9 = WTR-B25 · §2.10 = WTR-B26 · §2.11 = WTR-B27 · §3 = WTR-B1 to WTR-B16 · §4 = WTR-B18, WTR-B20, WTR-B21, WTR-B22, WTR-B17, WTR-B23 · §5 = R-150 WTR · §6 = WTR-AC1
- SCH ([schedules.spec.md](../specs/schedules.spec.md)): §2 = SCH-B13 to SCH-B28 · §2.1 = SCH-B13 · §2.2 = SCH-B14 · §2.3 = SCH-B15, SCH-B16, SCH-B17 · §2.3.2 = SCH-B16 · §2.3.3 = SCH-B17 · §2.3.4 = SCH-B18 · §2.3.5 = SCH-B2 · §2.4 = SCH-B20 · §2.5 = SCH-B21 to SCH-B25 · §2.5.1 = SCH-B21 · §2.5.2 = SCH-B22 · §2.5.3 = SCH-B23 · §2.5.4 = SCH-B24 · §2.5.5 = SCH-B25 · §2.6 = SCH-B26 · §2.7 = SCH-B27 · §2.8 = SCH-B28 · §3 = SCH-B1 to SCH-B12 · §4 = SCH-B15, SCH-B16, SCH-B27, SCH-B24, SCH-B25, SCH-B22, SCH-B13, SCH-B28 · §5 = R-150 SCH · §6 = SCH-AC1
- TCK ([schedule-ticks-and-unattended-fires.spec.md](../specs/schedule-ticks-and-unattended-fires.spec.md)): §1 = TCK (Purpose) · §2.1 = TCK-B14, TCK-B15 · §2.2 = TCK-B16 · §2.3 = TCK-B17 · §2.4 = TCK-B18, TCK-B19 · §2.5 = TCK-B20 · §2.6 = TCK-B21, TCK-B22 · §2.7 = TCK-B23, TCK-B24 · §2.8 = TCK-AC8 · §3 = TCK-B1 to TCK-B13 · §4 = TCK-B14, TCK-B15, TCK-B17, TCK-B19, TCK-B22, TCK-B16 · §5 = R-150 TCK · §6 = TCK-AC1
- PRV ([caller-provenance.spec.md](../specs/caller-provenance.spec.md)): §1 = PRV (Purpose) · §2.1 = PRV-B11 · §2.2 = PRV-B12 · §2.3 = PRV-B13 · §2.4 = PRV-B14 · §2.4.1 = PRV-B15 · §2.5 = PRV-B16, PRV-B17 · §2.6 = PRV-B18 · §2.7 = PRV-B20 · §2.8 = PRV-B21, PRV-B22 · §3 = PRV-B1 to PRV-B10 · §4 = PRV-B5, PRV-B18, PRV-B17, PRV-B14, PRV-B13, PRV-B19, PRV-B15 · §5 = R-150 PRV · §6 = PRV-AC1
- SUP ([supervision-metrics.spec.md](../specs/supervision-metrics.spec.md)): §1 = SUP (Purpose) · §2.1 = SUP-B9 · §2.2 = SUP-B10 · §2.3 = SUP-B11 · §2.4 = SUP-B12 · §2.5 = SUP-B13 · §2.6 = SUP-B14, SUP-B15, SUP-B16 · §2.7 = SUP-B17 · §3 = SUP-B1 to SUP-B8 · §4 = SUP-B9, SUP-B10, SUP-B12, SUP-B15 · §5 = R-150 SUP · §6 = SUP-AC1
- SCO ([supervision-cost.spec.md](../specs/supervision-cost.spec.md)): §1 = SCO (Purpose) · §2.1 = SCO-B9 · §2.2 = SCO-B10, SCO-B11 · §2.3 = SCO-B12 · §2.4 = SCO-B13, SCO-B14 · §2.5 = SCO-B15 · §2.6 = SCO-B16 · §2.7 = SCO-B17 · §3 = SCO-B1 to SCO-B8 · §4 = SCO-B16, SCO-B11, SCO-B10 · §5 = R-150 SCO · §6 = SCO-AC1
- PKG ([workflow-package.spec.md](../specs/workflow-package.spec.md)): §1 = PKG (Purpose) · §2 = PKG-B13, PKG-B15 · §2.1 = PKG-B11, PKG-B12 · §2.2 = PKG-B13 · §2.2.1 = PKG-B14 · §2.3 = PKG-B15, PKG-B16, PKG-B17 · §2.3.1 = PKG-B18 · §2.4 = PKG-B19, PKG-B20 · §2.5 = PKG-B21, PKG-B22 · §2.6 = PKG-B23, PKG-B24 · §2.7 = PKG-B25 · §3 = PKG-B1 to PKG-B10 · §4 = PKG-B11, PKG-B13, PKG-B14, PKG-B17, PKG-B18, PKG-B19, PKG-B20, PKG-B23 · §5 = R-150 PKG · §6 = PKG-AC1
- AUT ([workflow-authoring.spec.md](../specs/workflow-authoring.spec.md)): §1 = AUT (Purpose) · §2.1 = AUT-B11, AUT-B12 · §2.2 = AUT-B13 · §2.3 = AUT-B14, AUT-B15 · §2.4 = AUT-B16, AUT-B17, AUT-B18 · §2.4.1 = AUT-B19, AUT-B20, AUT-B21 · §2.5 = AUT-B22 · §2.6 = AUT-B23 · §2.7 = AUT-B25 · §2.8 = AUT-B12, AUT-B15, AUT-B19, AUT-B24, AUT-B25 · §3 = AUT-B1 to AUT-B10 · §4 = AUT-B15, AUT-B17, AUT-B24, AUT-B12 · §5 = R-150 AUT · §6 = AUT-AC1
- OUT ([run-outcome.spec.md](../specs/run-outcome.spec.md)): §1 = OUT (Purpose) · §2 = OUT-B8 · §2.1 = OUT-B8, OUT-B9 · §2.2 = OUT-B10, OUT-B12 · §2.2.1 = OUT-B11 · §2.3 = OUT-B13, OUT-B14 · §2.4 = OUT-B15, OUT-B16, OUT-B17 · §2.5 = OUT-B18, OUT-B19 · §2.6 = OUT-B20, OUT-B21 · §3 = OUT-B1 to OUT-B7 · §4 = OUT-B22 · §5 = R-150 OUT · §6 = OUT-AC1
- SCF ([blueprint-and-scaffold.spec.md](../specs/blueprint-and-scaffold.spec.md)): §1 = SCF (Purpose) · §2.1 = SCF-B9, SCF-B11 · §2.1.1 = SCF-B10 · §2.2 = SCF-B12 · §2.3 = SCF-B13 · §2.4 = SCF-B14, SCF-B15, SCF-B16, SCF-B17 · §2.5 = SCF-B18, SCF-B19, SCF-B20, SCF-B21, SCF-B22 · §2.6 = SCF-B23 · §2.7 = SCF-B11, SCF-B13, SCF-B15, SCF-B16, SCF-B17, SCF-B18, SCF-B19, SCF-B20, SCF-B22 · §3 = SCF-B1 to SCF-B8 · §4 = SCF-B9, SCF-B10, SCF-B11, SCF-B14, SCF-B20, SCF-B21 · §5 = R-150 SCF · §6 = SCF-AC1
- LAD ([effort-ladder-and-model-escalation.spec.md](../specs/effort-ladder-and-model-escalation.spec.md)): §2 = LAD-B9 to LAD-B19 · §2.1 = LAD-B9 · §2.2 = LAD-B10 · §2.3 = LAD-B11 · §2.4 = LAD-B12 · §2.5 = LAD-B13 · §2.6 = LAD-B14 · §2.7 = LAD-B16, LAD-B17 · §2.8 = LAD-B18 · §3 = LAD-B1 · §4 = LAD-B14 · §5 = LAD-B11 · §6 = LAD-AC1
- JRK ([judge-model-by-risk.spec.md](../specs/judge-model-by-risk.spec.md)): §1 = JRK (Purpose) · §2 = JRK-B6 · §2.1 = JRK-B6 · §2.2 = JRK-B7 · §2.3 = JRK-B8 · §2.4 = JRK-B9, JRK-B5 · §2.5 = JRK-B10 · §3 = JRK-B1 to JRK-B5 · §4 = JRK-B6, JRK-B7, JRK-B2 · §5 = R-150 JRK · §6 = JRK-AC1
- CXR ([complexity-routing.spec.md](../specs/complexity-routing.spec.md)): §1 = CXR (Purpose) · §2.1 = CXR-B7 · §2.2 = CXR-B8 · §2.3 = CXR-B9 · §2.4 = CXR-B10, CXR-B1 · §2.5 = CXR-B4, CXR-B11, CXR-B7 · §2.6 = CXR-B12, CXR-B5 · §2.7 = CXR-B13 · §3 = CXR-B1 to CXR-B6 · §4 = CXR-B7, CXR-B4, CXR-B10 · §5 = R-150 CXR · §6 = CXR-AC1
- PRO ([promotion-check.spec.md](../specs/promotion-check.spec.md)): §1 = PRO (Purpose) · §2 = PRO-B6 · §2.1 = PRO-B7, PRO-B4 · §2.2 = PRO-B8 · §2.3 = PRO-B9 · §2.4 = PRO-B10 · §2.5 = PRO-B5, PRO-B11 · §2.6 = PRO-B11 · §3 = PRO-B1 to PRO-B5 · §4 = PRO-B6, PRO-B10, PRO-B9 · §5 = R-150 PRO · §6 = PRO-AC1
- CAR ([run-state-on-a-branch.spec.md](../specs/run-state-on-a-branch.spec.md)): §1 = CAR (Purpose) · §2 = CAR-B5 · §2.1 = CAR-B6 · §2.2 = CAR-B7, CAR-B2 · §2.3 = CAR-B8, CAR-B3 · §2.4 = CAR-B9, CAR-B4 · §2.5 = CAR-B10 · §3 = CAR-B1 to CAR-B4 · §4 = CAR-B5, CAR-B8, CAR-B11, CAR-B6 · §5 = R-150 CAR · §6 = CAR-AC1
- WIN ([windows-support.spec.md](../specs/windows-support.spec.md)): §1 = WIN (Purpose) · §2.1 = WIN-B1, WIN-B2, WIN-B4, WIN-B5, WIN-B6, WIN-B7 · §2.2 = WIN-B8 · §2.3 = WIN-B3 · §2.4 = WIN-B3 · §3 = WIN-B1 to WIN-B3 · §4 = WIN-B1, WIN-B5, WIN-B6 · §5 = R-150 WIN · §6 = WIN-AC1
- SWF ([subworkflow-unit.spec.md](../specs/subworkflow-unit.spec.md)): §1 = SWF (Purpose) · §2 = SWF-B7 · §2.1 = SWF-B7, SWF-B6 · §2.2 = SWF-B8 · §2.3 = SWF-B2, SWF-B5 · §2.4 = SWF-B9 · §3 = SWF-B1 to SWF-B6 · §4 = SWF-B6, SWF-B8, SWF-B7 · §5 = R-150 SWF · §6 = SWF-AC1

Engine-wide contracts of the overview: C1 = OVR-B3 · C2 = OVR-B4 · C3 = OVR-B5 · C4 = OVR-B6 · C5 = OVR-B7 · C6 = OVR-B8 · C7 = OVR-B9 · C8 = OVR-B10 · C9 = OVR-B11 · C10 = OVR-B12 · C11 = OVR-B13 · C12 = OVR-B14 · C13 = OVR-B15 · C14 = OVR-B16 · C15 = OVR-B17 · C16 = OVR-B18 · C17 = OVR-B19 · C18 = OVR-B20.

Renamed ids (applied before the generic `X-AC-n` to `X-ACn` rename): `IMD-R1` = IMD-B5 · `IMD-R2` = IMD-B6 · `IMD-R3` = IMD-B7 · `IMD-R4` = IMD-B8 · `IMD-R5` = IMD-B9 · `IMD-R6` = IMD-B10 · `IMD-R7` = IMD-B11 · `IMD-R8` = IMD-B12 · `IMD-R9` = IMD-B13 · `IMD-R10` = IMD-B14 · `IMD-R11` = IMD-B15 · `IMD-R12` = IMD-B16 · `IMD-R13` = IMD-B17 · `IMD-R14` = IMD-B18 · `IMD-R15` = IMD-B19 · `SCH-B1a` = SCH-B19 · `SCH-AC-1a` = SCH-AC3 · `SCH-AC-3` = SCH-AC4 · `SCH-AC-4` = SCH-AC5 · `SCH-AC-5` = SCH-AC6 · `SCH-AC-6` = SCH-AC7 · `SCH-AC-7` = SCH-AC8 · `TCK-B7a` = TCK-B12 · `TCK-B7b` = TCK-B13 · `TCK-AC-4a` = TCK-AC5 · `TCK-AC-5` = TCK-AC6 · `TCK-AC-6` = TCK-AC7 · `PKG-AC-8` = PKG-AC8.

## 6. Follow-ups

- Dissolve the contracts spec (R-127 C5): each shared type moves to the spec that owns its behaviour.
- The scaffold writes package specs in temperspec's layout, and the package docs check reads it (specs `workflow-package` PKG and 91 SCF).
- A generated index of specs in the overview's Purpose (R-127 C3), so adding a spec edits no hand-kept list.
- Dogfooding: spec `telemetry-export` TEL was migrated by a temperspec run (thread `t-4836f11b73`, 2026-11-22, about 25 minutes, $5.15 reported and $4.41 estimated against a $12 cap) and taken as it came out after review. The run surfaced three things for temperspec's backlog: its setup route wrote `.claude/rules/temperspec/`, `docs/templates/` and `CLAUDE.md` lines into a repository that already ships the rules under `plugins/temperspec-tgraph/rules/` (not taken into this change); a docs-only task ends in an escalation at the outcome gate because `ts-traced` and `ts-verify` are not applicable and the judge reads that as a gap; and the process stopped with an ImportError after the pause was recorded because `main` was merged into the editable engine install under the live run (operator error; the thread stayed paused and resumable).
