---
title: Version metadata of the engine and of workflows
type: component
status: ready-for-implementation
prefix: VER
adrs: [0057, 0058]
---

# Version metadata of the engine and of workflows

## 1. Overview



## 2. Contract

### 2.1 The version facts, kept apart

| Fact | Where it lives | Set by | Read by |
|---|---|---|---|
| Engine version | `release.json` in the engine package (§2.2) | The engine release | Every verb; run records; the audit header |
| Engine source digest | Computed over the installed engine's source files | `update` | `update` (currency, [LIF-B1](18-lifecycle-and-evals.spec.md)) |
| Plugin version | `plugin.json` of the `tempergraph` plugin | The engine release, equal to the engine version | Claude Code's plugin cache; the session check of [UPD §2.5](60-engine-update.spec.md) |
| Store layout, checkpoint format | `release.json`; each state root's and the home folder's `manifest.json` ([LOS §2.1](33-local-observability-store.spec.md)) | The release; [MIG](62-state-and-run-migration.spec.md) on first write | MIG, LOS readers |
| Workflow version | `WorkflowSpec.version` (§2.4) and the workflow plugin's `plugin.json` | The workflow's owner | Reports, proposals, lessons, runs |
| Workflow content digest | Computed (§2.4) | The engine, at load | Runs, reports, the stamp |
| Engine range of a workflow | `WorkflowSpec.requires_engine` (§2.4) | The owner, proposed by [WUP](63-workflow-upgrade.spec.md) | The catalog's compatibility column (§2.7) |
| Workflow stamp | `stamp.json` in the package, mirrored in `verified_engine` (§2.5) | `upgrade --stamp` only | §2.7, the audit's host layer ([TSA](57-tool-surface-audit.spec.md), [PRA](58-prompt-audit.spec.md)) |


### 2.2 Engine release record (`release.json`)

| Field | Kind | Meaning |
|---|---|---|
| `schema_version` | int | `1` |
| `engine_version` | semver | This release |
| `loads_workflow_api_from` | int | The oldest `workflow_api` level this release still loads ([PKG §2.3](88-workflow-package.spec.md)) |
| `workflow_api` | int | The level of the workflow-facing interface: `WorkflowSpec` fields, the declaration format, callable signatures, template grammar and engine keys, capability names and aliases. It grows by one with every release that has a breaking `workflow`-audience entry (§2.3). |
| `store_layout` | int | The state-root and home layout this release writes ([LOS](33-local-observability-store.spec.md)) |
| `reads_store_layouts` | list of int | Layouts it can migrate forward ([MIG §2.2](62-state-and-run-migration.spec.md)) |
| `checkpoint_format` | int | The checkpoint shape: node naming, state keys and reducers, serializer |
| `resumes_checkpoint_formats` | list of int | Formats it resumes; a format absent here makes threads of that format **pinned** ([MIG §2.4](62-state-and-run-migration.spec.md)) |
| `schemas` | map document → version | Every persisted document of [CON §2.10](01-contracts.spec.md) |
| `python` | version range | Interpreter the environment needs |
| `extras` | map name → requirement | Optional executor packages (`agent-sdk`, `messages-api`) and their pinned ranges |
| `executor_compat` | ref | The executor compatibility table of [LIF](18-lifecycle-and-evals.spec.md) |
| `released_at` | date | |

The record is plain data in the package (`tempergraph/data/release.json`), generated at release and checked by a drift test against the constants it names, and against the plugin's `plugin.json` version.

### 2.3 Compatibility changelog

One file per release, `changelog/<engine_version>.json`, with `schema_version` and a list of **entries**. An entry describes one change a consumer may have to act on.

| Field | Kind | Meaning |
|---|---|---|
| `id` | `E<version>-<n>` | Stable; recorded in a stamp and in upgrade reports |
| `audience` | `workflow` \| `operator` \| `state` \| `integration` | Who must act: a workflow's owner, the person running the engine, the store (handled by MIG, no person), or a tool reading engine documents (hooks, the monitor) |
| `kind` | `added` \| `deprecated` \| `renamed` \| `removed` \| `changed` \| `tightened` \| `behaviour` \| `executor` | `tightened`: validation now refuses what it accepted. `behaviour`: the same declaration now runs differently. `executor`: an executor's tool name, flag or default changed under the same capability. |
| `breaking` | bool | True when a consumer that does nothing is refused or behaves differently. `added` is never breaking. |
| `surface` | one of §2.3.1 | What part of the interface changed |
| `subject` | text | The field path, symbol, key, tool or verb |
| `detect` | list of detect rules (§2.3.2) | How the upgrade finds what this entry touches in a workflow |
| `migrate` | one migrate action (§2.3.3) | What the upgrade does about each hit |
| `proof` | list of finding codes or detect rule ids | What must be absent after the upgrade: the validation codes a `tightened` entry raises, or the entry's own detect rules |
| `note` | one paragraph | For people: what changed and why; read by the model only through the brief of [UWF](64-upgrade-workflow.spec.md) |
| `removal_in` | semver, for `deprecated` | The release that will remove it; at least the next major |

#### 2.3.1 Surfaces

| Surface | Examples |
|---|---|
| `spec_field` | A `WorkflowSpec`, `StepSpec`, `GateSpec` or `JudgeSpec` field |
| `declaration` | A builder name or argument in the package's declaration module |
| `callable` | The signature or state view of a check, route, resolver, finalizer or command resolver |
| `template` | Template grammar, an engine key a template may name |
| `capability` | A tool capability name, a model alias tier, a session option |
| `tool_name` | A concrete tool name of an executor or the tool host ([THS](22-tool-host.spec.md)), as a prompt may name it |
| `cli` | A verb, option or exit code |
| `document` | A persisted or published document's schema |
| `state` | Store layout, checkpoint format |

#### 2.3.2 Detect rules

Typed rules run first; a text pattern is the fallback for what has no parsed form.

| Kind | Matches | Over |
|---|---|---|
| `field` | A field path with an optional value test (`units.*.gate.on_budget_spent == "ask"`) | The parsed `WorkflowSpec` |
| `symbol` | An imported name or call of the engine's public interface | The package's Python sources, by syntax tree |
| `template_key` | An engine key or grammar form in a template | Parsed templates and briefs |
| `tool_ref` | A tool name in model-facing text or in declared tools | The text set of [PRA](58-prompt-audit.spec.md) and the declarations of [TSA](57-tool-surface-audit.spec.md) |
| `finding` | A validation or audit finding code | `validate` and `audit --layer definition` run under the new engine |
| `text` | A regular expression, with a file glob | Package files; each hit is marked `confidence: low` |

Every hit carries the file, the field path or line, and the rule id.

#### 2.3.3 Migrate actions

| Action | Carries | Done by |
|---|---|---|
| `transform` | A transform id from §2.3.4 and its parameters | The engine, deterministically ([WUP §2.4](63-workflow-upgrade.spec.md)) |
| `assisted` | An instruction for the model: the intent of the change, what a correct result looks like, what must not change | The upgrade workflow ([UWF](64-upgrade-workflow.spec.md)), gated |
| `owner` | The question only the owner can answer, with any choices | A pause of the upgrade workflow; the model may draft an answer, never choose it |
| `none` | A reason (informational, or handled by MIG) | Nobody |

An entry whose detect rules all have a deterministic match **must** carry `transform` when one of §2.3.4 expresses the change; `assisted` is for what no transform can express.

#### 2.3.4 Engine-shipped transforms

| Transform | Does |
|---|---|
| `rename_field(from, to)` | Moves a declared value to a new field path |
| `set_field(path, value)` / `drop_field(path)` | Writes an explicit value (to keep old behaviour under a changed default) or removes a retired field whose value equals its default |
| `rename_symbol(from, to)` | Rewrites an import or call of the public interface, by syntax tree |
| `rename_template_key(from, to)` | Rewrites a field in templates and briefs |
| `rename_tool(executor, from, to)` | Rewrites a tool name in declarations and in model-facing text where the name stands alone |
| `map_capability(from, to)` | Rewrites a capability name or alias tier in declarations |
| `model_list_to_escalation()` | Release 2: rewrites a step's `model` list as its first alias plus an `escalation` to the second when it is one tier up; any other list becomes an owner item ([LAD §2.8](92-effort-ladder-and-model-escalation.spec.md)) |

Transforms are pure functions over the package files, each idempotent and each tested on a before and after fixture.

### 2.4 Workflow version fields

Appended last to `WorkflowSpec` ([CON §2.1](01-contracts.spec.md)), each with a default so older workflows load unchanged ([WFM-B5](02-workflow-model.spec.md)).

| Field | Kind | Default | Meaning |
|---|---|---|---|
| `version` | semver | `0.0.0` | The owner's release of this workflow; equal to its plugin's `plugin.json` version |
| `requires_engine` | version range (PEP 440 form, `>=1.4,<2`) | none | The engine releases the owner states the workflow works with |
| `upgrade` | `UpgradePolicy` | see below | What the upgrade may touch |

`UpgradePolicy`: `protected` (list of field paths or file globs the model may not edit; default the criteria, check sources and judge stances), `assist` (`allowed` \| `off`, default `allowed`), `executor` (the executor the upgrade workflow's steps use, default `claude`).

The engine computes, at load:

| Value | Over | Use |
|---|---|---|
| `content_digest` | The spec's canonical JSON, `outcome.json`, every template, brief, lessons file, skill and agent file, every Python source under `workflow/` and the `dependencies` of its `pyproject.toml`; never `docs/`, `diagram/`, `evals/`, `authoring.json` or `README.md` ([PKG-AC-7](88-workflow-package.spec.md)) | What a run actually ran |
| `shape_digest` | The diagram model ([LIF](18-lifecycle-and-evals.spec.md)) | Whether the graph changed |
| `workflow_version` | `<version>+<first 12 hex of content_digest>` | The id reports, proposals (`base_version`), lessons (`added_in`) and runs record |

`content_digest` leaves out `verified_engine`, which mirrors `stamp.json`, so a stamp never changes the id it records.

A changed `content_digest` under an unchanged `version` in a package installed from a marketplace is a validation **warning** (`version-not-bumped`), because the plugin cache is keyed by the version string ([R-055](../research/R-055-updating-a-tool-with-long-lived-runs.rsrch.md) U3).

### 2.5 Stamp record (`stamp.json`)

Written in the package only by `upgrade --stamp` after every check of [WUP §2.6](63-workflow-upgrade.spec.md) passes; `verified_engine` on the spec mirrors `engine_version`.

| Field | Meaning |
|---|---|
| `schema_version` | `1` |
| `engine_version`, `workflow_api` | The engine stamped against |
| `workflow_version` | The workflow's version and content digest at the stamp |
| `entries_applied[]` | Changelog entry ids handled, each with `by` ∈ `transform`, `model`, `person`, `none` |
| `docs_digest`, `shape_digest` | The docs half's digest ([PKG §2.5](88-workflow-package.spec.md)) and the diagram's, at the stamp |
| `baseline` | Counts of validation and audit findings by severity at the stamp |
| `stamped_at` | |

### 2.6 Workflow change notes

A workflow may ship `changes/<version>.json` in the shape of §2.3 with `audience: workflow` and surfaces narrowed to what another workflow can depend on: its `input` parameters, its produced artifact keys, and its units named by a parent's sub-workflow unit ([ADR-0040](../adr/0040-take-script-steps-attention-and-composition-from-archon.adr.md)). A parent's upgrade reads them as it reads the engine's changelog ([WUP-B6](63-workflow-upgrade.spec.md)).

### 2.7 Compatibility of a workflow with the running engine

Computed by the catalog, `run --check`, `update` and `upgrade --check`; model-free and read-only.

| State | When |
|---|---|
| `current` | The stamp equals the running engine, or no changelog entry between them has a hit |
| `stamp_behind` | Entries lie between the stamp and the engine and none is breaking for the workflow, or none has a hit |
| `needs_upgrade` | At least one breaking `workflow` entry between the stamp and the engine has a hit |
| `out_of_range` | The engine lies outside `requires_engine` |
| `unstamped` | No stamp; every entry since `workflow_api` 1 is considered |

The changelog files are `tempergraph/data/changelog/<engine_version>.json`; the catalog shows the state in `list` as `compatibility`. Only `needs_upgrade` with a hit whose entry is `tightened` makes the workflow fail validation, and that is validation's own finding. Every other state is a warning line in the catalog, at run start and in `update`, naming `tempergraph upgrade <workflow>`.

## 3. Behaviours

**VER-B1 Content, not the string.** Given a workflow whose `version` is unchanged and one template edited, when it loads from a marketplace copy, then its `workflow_version` shows a new digest, a `version-not-bumped` warning is raised, and runs record the new id.

**VER-B2 Range selection.** Given a workflow stamped at 1.2.0 and an engine at 1.5.1, when compatibility is computed, then the changelog files 1.2.1 up to and including 1.5.1 are read, oldest first, and 1.2.0 itself is not.

| Stamp | Engine | Entries read | Hits | State |
|---|---|---|---|---|
| 1.5.1 | 1.5.1 | none | — | `current` |
| 1.2.0 | 1.5.1 | 1.2.1–1.5.1 | none | `current` |
| 1.2.0 | 1.5.1 | 1.2.1–1.5.1 | one non-breaking | `stamp_behind` |
| 1.2.0 | 2.0.0 | 1.2.1–2.0.0 | one breaking | `needs_upgrade` |
| none | 2.0.0 | all | — | `unstamped` |

**VER-B3 Typed before text.** Given an entry with a `field` rule and a `text` rule for the same rename, when both hit the same location, then one hit is reported, from the `field` rule, at `confidence: high`.

**VER-B4 Transform required where it fits.** Given a draft changelog entry of kind `renamed` on surface `spec_field` with `migrate: assisted`, when the release check runs, then it fails, naming `rename_field` as the transform that expresses it.

**VER-B5 Never refuses on its own.** Given a workflow `out_of_range` whose package validates under the running engine, when a run starts, then it starts with one warning line; the start record carries the state.

**VER-B6 Release parity.** Given a change to the engine's sources with no new changelog file and no version bump, when the repository check runs, then it fails; given a bump of the engine version without the plugin version, it fails too.

## 4. Error conditions

| Condition | Result |
|---|---|
| `release.json` missing or unreadable in an installed engine | `update` reinstalls; other verbs warn and read the version from the package metadata |
| A changelog file with an unknown `schema_version` major | Entries skipped with one warning; compatibility reads `unknown` for the affected range, never `current` |
| A detect rule that cannot parse a file | That file's hits are `text`-level only, marked `confidence: low` |
| `stamp.json` and `verified_engine` disagree | `stamp.json` wins; a validation warning names both |
| `requires_engine` not a valid range | Validation error |

## 5. Design notes

- The changelog becomes typed because an upgrade needs to know, per hit, whether a rule, a model or a person handles it ([ADR-0057](../adr/0057-typed-version-metadata-on-both-sides.adr.md), [R-056](../research/R-056-automated-and-model-assisted-migrations.rsrch.md) conclusion 2).
- `workflow_api` exists apart from the engine major so a release that breaks only the CLI or a document does not ask every workflow owner to upgrade.
- `workflow_version` closes gap G5 of [R-011](../research/R-011-design-gap-review.rsrch.md): a declared version for people and a digest for measurement.
- The package layout and declaration format are [PKG](88-workflow-package.spec.md); `stamp.json` and `changes/` sit at the package root. The stamp also records `docs_digest`, the digest of the package's `docs/` folder ([PKG §2.5](88-workflow-package.spec.md)), and `release.json` records `loads_workflow_api_from`, the oldest declaration level the engine still loads ([PKG §2.3](88-workflow-package.spec.md)).
- **As built (R2-T6.3).** `package/transforms.py` holds the eight transforms of §2.3.4 as pure text edits found by Python's own parser, so comments and layout outside the edited span keep their bytes. A transform that cannot say what the new value should be (a model list whose members are not one step apart, a field written through a variable) changes nothing and returns the item to its owner. The release 2 changelog entry that carries the model-list transform ships with the version bump (release 2 plan R2-T9).

## 6. Acceptance criteria

- [ ] VER-AC-1 `release.json` equals the engine's constants by a generated drift test.
- [ ] VER-AC-2 Every changelog entry validates against the schema of §2.3, and every `renamed` entry on a surface §2.3.4 covers carries a transform (release check).
- [x] VER-AC-3 Each transform of §2.3.4 passes its before and after fixture and is idempotent (applied twice, same bytes).
- [ ] VER-AC-4 Every row of VER-B2's table is a test.
- [ ] VER-AC-5 A workflow written before §2.4 loads with the defaults and validates unchanged.
- [ ] VER-AC-6 The repository check of VER-B6 fails on each of its two fixtures.

## Open questions

| Question | Owner | Release 1 default |
|---|---|---|
| Should `requires_engine` also be written into the workflow plugin's `plugin.json` as a dependency on the `tempergraph` plugin with a version range, so Claude Code refuses a mismatched install ([R-055](../research/R-055-updating-a-tool-with-long-lived-runs.rsrch.md) U6)? The design proposes it but does not rely on it. | Owner | No: `plugin.json` names `tempergraph` without a range |

## References

