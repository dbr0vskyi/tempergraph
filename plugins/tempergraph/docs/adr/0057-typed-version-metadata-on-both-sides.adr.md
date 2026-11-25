# ADR-0057 Both sides carry typed version metadata: a release record and a typed changelog for the engine, a version, a range and a stamp record for a workflow

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner's upgrade command must "read workflow and engine metadata, understand what needs to be adjusted". Today the engine has a changelog of breaking flags, migrate steps and text-pattern detect rules, and a workflow has only `verified_engine` ([R-057](../research/R-057-engine-update-and-workflow-upgrade-gaps.rsrch.md) X1 to X3). A workflow has no declared version, though reports, proposals and lessons use one ([R-011](../research/R-011-design-gap-review.rsrch.md) G5). Public migration tools select migrations by version range and run them as code, and find locations deterministically before any model edits ([R-056](../research/R-056-automated-and-model-assisted-migrations.rsrch.md) M1 to M3).

## Decision

We will define the metadata in [VER](../specs/version-metadata.spec.md):

1. An engine **release record** naming the engine version, the workflow-facing interface level, the store layout and checkpoint format with what it can read, schema versions, Python and extras.
2. A **typed changelog**: each entry has an audience, a kind, a surface, typed detect rules (fields, symbols, template keys, tool references, finding codes, then text), one migrate action (`transform`, `assisted`, `owner`, `none`) and proof codes.
3. A fixed catalog of engine-shipped **transforms** for what a rule can express; a release check refuses `assisted` where a transform fits.
4. On a workflow: a declared `version`, an engine range `requires_engine`, an `UpgradePolicy`, a computed content digest and `workflow_version`, a **stamp record**, and optional **change notes** in the changelog's shape for parents that compose it.
5. Decide by content: the range and the stamp only warn; validation alone refuses.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Typed metadata on both sides (chosen) | Each hit carries who handles it; typed rules find by structure, not text; one shape serves engine and workflow change notes | More schema to keep; a release must write typed entries |
| Keep the untyped changelog (flags, steps, patterns) | Exists; no new schema | Cannot tell a rename from a judgement call; text patterns miss structure |
| Prose release notes read by a model | Least authoring work | Every upgrade spends; no deterministic plan; no proof of done |
| Migrations as engine code only (Angular style) | Exact | A workflow's prompts and briefs are text a transform cannot edit with judgement; nothing for the owner's questions |

## Decision rationale

| Criterion | Typed metadata | Untyped changelog | Prose notes | Code migrations only |
|---|---|---|---|---|
| Plan without a model | yes | yes | no | yes |
| Tells transform from judgement from owner | yes | no | no | partly |
| Proof that an entry is done | yes | partly | no | yes |
| Serves composed workflows | yes | no | partly | no |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | Semantic versions for both sides, and a PEP 440 range form for `requires_engine`. | VER-B14, VER-B15 |
| A2 | A workflow's `version` equals its plugin's `plugin.json` version, because Claude Code keys its cache by that string. | VER-B7 |
| A3 | Criteria, check sources and judge stances are protected from model edits by default. | VER-B14, VER-B15, UWF |

## Consequences

- Positive: the upgrade can plan, act and prove by data; reports and proposals get a version id.
- Negative: every engine release must write typed entries and tests for its transforms.
- Risk: an entry's detect rules miss a location. Mitigation: validation and the audit run after the upgrade (V2, V4 of [WUP-B19](../specs/workflow-upgrade.spec.md)); text rules remain as a low-confidence fallback.

## Revisit when

The workflow package layout and declaration format are specified ([R-011](../research/R-011-design-gap-review.rsrch.md) G2), which may add surfaces.
