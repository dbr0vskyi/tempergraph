# Version metadata of the engine and of workflows

## Purpose

The engine and its workflows are released apart, so they drift. This spec owns the metadata each side carries so that the engine update ([UPD](60-engine-update.spec.md)), the state migration ([MIG](62-state-and-run-migration.spec.md)) and the workflow upgrade ([WUP](63-workflow-upgrade.spec.md)) can decide by data what must move: the engine release record, the typed compatibility changelog, a workflow's version fields, its stamp record and its own change notes, and how the engine compares the two sides. Currency is decided by content, never by a version string alone ([LIF](18-lifecycle-and-evals.spec.md)), and the comparison never refuses a run by itself: a run refuses only when validation fails, which a release that tightens a rule causes by content ([WFM](02-workflow-model.spec.md)). Typed metadata on both sides is [ADR-0057](../adr/0057-typed-version-metadata-on-both-sides.adr.md); `stamp.json` and `changes/` sit at the package root ([PKG](88-workflow-package.spec.md)). Release engineers, workflow owners, the update and upgrade verbs and the catalog depend on it; design and build notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### VER-B7 The version facts, kept apart

WHEN a version fact is read or written THE engine SHALL keep apart the engine version (`release.json`, set by the release, read by every verb, run records and the audit header), the engine source digest (computed over the installed source by `update` for currency, [LIF-B1](18-lifecycle-and-evals.spec.md)), the plugin version (`plugin.json` of the `tempergraph` plugin, equal to the engine version, read by Claude Code's plugin cache and the session check of [UPD-B16](60-engine-update.spec.md)), the store layout and checkpoint format (`release.json` and each `manifest.json`, [LOS](33-local-observability-store.spec.md), moved by [MIG](62-state-and-run-migration.spec.md)), the workflow version (`WorkflowSpec.version` and the workflow plugin's `plugin.json`, set by its owner), the workflow content digest (computed at load), the engine range of a workflow (`requires_engine`, set by the owner, proposed by [WUP](63-workflow-upgrade.spec.md)) and the workflow stamp (`stamp.json`, mirrored in `verified_engine`, written by `upgrade --stamp` only), all versions semantic (`MAJOR.MINOR.PATCH`).

- GIVEN an engine install stamp and a workflow stamp WHEN read THEN each comes from its own file and neither stands for the other

### VER-B8 Engine release record

WHEN the engine is released THE release SHALL ship `tempergraph/data/release.json`, generated at release and checked by a drift test against the constants it names and the plugin's `plugin.json` version, with `schema_version` 1, `engine_version`, `loads_workflow_api_from` (the oldest `workflow_api` level it still loads, [PKG](88-workflow-package.spec.md)), `workflow_api` (the level of the workflow-facing interface: `WorkflowSpec` fields, declaration format, callable signatures, template grammar and engine keys, capability names and aliases, growing by one with every release that has a breaking `workflow`-audience entry), `store_layout`, `reads_store_layouts` (layouts it migrates forward), `checkpoint_format` (node naming, state keys and reducers, serializer), `resumes_checkpoint_formats` (a format absent here pins threads of that format, [MIG](62-state-and-run-migration.spec.md)), `schemas` (every persisted document of [CON-B14](01-contracts.spec.md) and its version), `python` (the interpreter range), `extras` (`agent-sdk`, `messages-api` and their pinned ranges), `executor_compat` (the table of [LIF-B10](18-lifecycle-and-evals.spec.md)) and `released_at`.

- GIVEN a constant changed without regenerating `release.json` WHEN the drift test runs THEN it fails

### VER-B6 Release parity

WHEN the repository check runs THE check SHALL fail a change to the engine's sources with no new changelog file and no version bump, and a bump of the engine version without the plugin version.

- GIVEN a source change with no changelog file and no bump WHEN checked THEN it fails
- GIVEN the engine version bumped and the plugin version not WHEN checked THEN it fails

### VER-B9 Compatibility changelog entries

WHEN a release records changes a consumer may have to act on THE release SHALL ship `tempergraph/data/changelog/<engine_version>.json` with `schema_version` and a list of entries, each with `id` (`E<version>-<n>`, stable, recorded in stamps and upgrade reports), `audience` (`workflow`, `operator`, `state` handled by MIG with no person, or `integration` for hooks and the monitor), `kind` (`added`, `deprecated`, `renamed`, `removed`, `changed`, `tightened` where validation now refuses what it accepted, `behaviour` where the same declaration runs differently, or `executor` where a tool name, flag or default changed under the same capability), `breaking` (true when a consumer that does nothing is refused or behaves differently, never for `added`), `surface`, `subject` (field path, symbol, key, tool or verb), `detect` (a list of rules), `migrate` (one action), `proof` (the finding codes or detect rule ids that must be absent after the upgrade), `note` (one paragraph for people, read by a model only through the brief of [UWF](64-upgrade-workflow.spec.md)) and, for `deprecated`, `removal_in` at least the next major.

- GIVEN an `added` entry marked `breaking` WHEN the release check runs THEN it fails

### VER-B10 Surfaces

WHEN an entry names its surface THE entry SHALL use one of `spec_field` (a `WorkflowSpec`, `StepSpec`, `GateSpec` or `JudgeSpec` field), `declaration` (a builder name or argument), `callable` (the signature or state view of a check, route, resolver, finalizer or command resolver), `template` (grammar or an engine key), `capability` (a tool capability, alias tier or session option), `tool_name` (a concrete tool name of an executor or the [tool host](22-tool-host.spec.md) as a prompt may name it), `cli` (a verb, option or exit code), `document` (a persisted or published schema) or `state` (store layout, checkpoint format).

- GIVEN an entry with surface `config` WHEN the release check runs THEN it fails naming the surface

### VER-B11 Detect rules

WHEN an upgrade looks for what an entry touches THE engine SHALL run typed rules first and a text pattern last: `field` (a field path with an optional value test such as `units.*.gate.on_budget_spent == "ask"`, over the parsed `WorkflowSpec`), `symbol` (an imported name or call of the public interface, by syntax tree over the package's Python), `template_key` (over parsed templates and briefs), `tool_ref` (over the text set of [PRA](58-prompt-audit.spec.md) and the declarations of [TSA](57-tool-surface-audit.spec.md)), `finding` (a code from `validate` and `audit --layer definition` under the new engine) and `text` (a regular expression with a file glob, each hit `confidence: low`), every hit carrying the file, the field path or line and the rule id; a file a rule cannot parse gets `text`-level hits only.

- GIVEN a package file that does not parse WHEN its entry's rules run THEN its hits are `confidence: low`

### VER-B3 Typed before text

WHEN a typed rule and a `text` rule of one entry hit the same location THE engine SHALL report one hit, from the typed rule, at `confidence: high`.

- GIVEN a `field` rule and a `text` rule for one rename hitting one location WHEN detected THEN one `field` hit is reported at `confidence: high`

### VER-B12 Migrate actions

WHEN an entry says what is done about each hit THE entry SHALL carry one action: `transform` (a transform id and its parameters, done by the engine deterministically, [WUP](63-workflow-upgrade.spec.md)), `assisted` (an instruction with the change's intent, what a correct result looks like and what must not change, done by the gated [upgrade workflow](64-upgrade-workflow.spec.md)), `owner` (the question only the owner can answer, with any choices, a pause where a model may draft an answer and never choose it) or `none` (a reason: informational, or handled by MIG).

- GIVEN an `owner` action WHEN the upgrade meets it THEN it pauses for the owner

### VER-B4 Transform required where it fits

WHEN the release check reads an entry whose detect rules all have a deterministic match and whose change a shipped transform expresses THE check SHALL fail unless the entry carries `transform`, naming the transform.

- GIVEN a draft entry of kind `renamed` on `spec_field` with `migrate: assisted` WHEN the release check runs THEN it fails naming `rename_field`

### VER-B13 Engine-shipped transforms

WHEN a `transform` action runs THE engine SHALL offer `rename_field(from, to)`, `set_field(path, value)` (an explicit value to keep old behaviour under a changed default), `drop_field(path)` (a retired field whose value equals its default), `rename_symbol(from, to)` (by syntax tree), `rename_template_key(from, to)` (templates and briefs), `rename_tool(executor, from, to)` (declarations, and model-facing text where the name stands alone), `map_capability(from, to)` and `model_list_to_escalation()` (a step's `model` list becomes its first alias plus an `escalation` to the second when one tier up, any other list an owner item, [LAD](92-effort-ladder-and-model-escalation.spec.md)), each a pure, idempotent text edit over the package files that keeps bytes outside the edited span, and changing nothing and returning the item to its owner when it cannot say what the new value is.

- GIVEN a model list whose members are not one tier apart WHEN `model_list_to_escalation` runs THEN nothing changes and an owner item is returned

### VER-B14 Workflow version fields

WHEN a workflow declares its version THE spec SHALL take, appended last to `WorkflowSpec` ([CON](01-contracts.spec.md)) with defaults so older workflows load unchanged ([WFM-B5](02-workflow-model.spec.md)), `version` (semver, default `0.0.0`, equal to its plugin's `plugin.json` version), `requires_engine` (a PEP 440 range such as `>=1.4,<2`, default none, an invalid range a validation error) and `upgrade` (`UpgradePolicy`: `protected` field paths or file globs a model may not edit, default the criteria, check sources and judge stances; `assist` `allowed` or `off`, default `allowed`; `executor` for the upgrade workflow's steps, default `claude`).

- GIVEN a workflow written before these fields WHEN it loads THEN it validates unchanged with the defaults

### VER-B15 Digests and the workflow version id

WHEN a workflow loads THE engine SHALL compute `content_digest` over the spec's canonical JSON, `outcome.json`, every template, brief, lessons file, skill and agent file, every file the package declares in `step_files` ([PKG-B13](88-workflow-package.spec.md)), every Python source under `workflow/` and the `dependencies` of its `pyproject.toml`, never `docs/`, `diagram/`, `evals/`, `authoring.json`, `README.md` or `verified_engine` ([PKG](88-workflow-package.spec.md)); `shape_digest` over the diagram model ([LIF-B11](18-lifecycle-and-evals.spec.md)); and `workflow_version` as `<version>+<first 12 hex of content_digest>`, the id reports, proposals (`base_version`), lessons (`added_in`) and runs record.

- GIVEN a stamp written WHEN the workflow loads again THEN its `workflow_version` is unchanged

### VER-B1 Content, not the string

WHEN a package installed from a marketplace loads with a changed `content_digest` under an unchanged `version` THE engine SHALL record the new `workflow_version` and raise the validation warning `version-not-bumped`, since the plugin cache is keyed by the version string.

- GIVEN an unchanged `version` and one edited template WHEN it loads from a marketplace copy THEN `workflow_version` shows a new digest, `version-not-bumped` is raised and runs record the new id

### VER-B16 Stamp record

WHEN `upgrade --stamp` writes `stamp.json` in the package, only after every check of [WUP](63-workflow-upgrade.spec.md) passes THE engine SHALL write `schema_version` 1, `engine_version` and `workflow_api`, `workflow_version`, `entries_applied[]` (changelog ids handled over the package's life, each `by` `transform`, `model`, `person` or `none`, a restamp keeping prior entries and adding only those met since), `docs_digest` and `shape_digest`, `tool_set` (per executor, the tool names the steps and judges were checked against, the baseline of [TSA](57-tool-surface-audit.spec.md) and [PRA](58-prompt-audit.spec.md)), `baseline` (validation and audit finding counts by severity), `audit` (findings at `warning` or above by rule and location) and `outcome_revision` (revision 1 when absent), and `stamped_at`, mirroring `engine_version` in `verified_engine`; where the two disagree `stamp.json` wins with a validation warning naming both.

- GIVEN a restamp of a package already current WHEN written THEN `entries_applied` gains no entry

### VER-B17 Workflow change notes

WHEN a workflow ships `changes/<version>.json` THE engine SHALL read it in the changelog's shape with `audience: workflow` and surfaces narrowed to what another workflow can depend on (its `input` parameters, its produced artifact keys and units a parent's sub-workflow unit names, [ADR-0040](../adr/0040-take-script-steps-attention-and-composition-from-archon.adr.md)), and a parent's upgrade SHALL read it as it reads the engine's changelog ([WUP-B6](63-workflow-upgrade.spec.md)).

- GIVEN a child that renamed a produced key in its change notes WHEN its parent is upgrade-checked THEN the parent's reference is a hit

### VER-B2 Range selection and compatibility states

WHEN the catalog, `run --check`, `update` or `upgrade --check` computes a workflow's compatibility, model-free and read-only THE engine SHALL read the changelog files after the stamp up to and including the running engine, oldest first, and give `current` (the stamp equals the engine, or no entry between has a hit), `stamp_behind` (entries lie between and none breaking for the workflow has a hit), `needs_upgrade` (a breaking `workflow` entry between has a hit), `out_of_range` (the engine is outside `requires_engine`) or `unstamped` (no stamp; every entry since `workflow_api` 1 is considered), shown in `list` as `compatibility`, and SHALL read `unknown`, never `current`, for a range whose changelog file has an unknown `schema_version` major, skipping its entries with one warning.

- GIVEN stamp 1.5.1 and engine 1.5.1 WHEN computed THEN no entry is read and it is `current`
- GIVEN stamp 1.2.0 and engine 1.5.1 with no hit WHEN computed THEN 1.2.1 to 1.5.1 are read, 1.2.0 is not, and it is `current`
- GIVEN stamp 1.2.0 and engine 1.5.1 with one non-breaking hit WHEN computed THEN it is `stamp_behind`
- GIVEN stamp 1.2.0 and engine 2.0.0 with one breaking hit WHEN computed THEN it is `needs_upgrade`
- GIVEN no stamp and engine 2.0.0 WHEN computed THEN every entry is read and it is `unstamped`

### VER-B5 Never refuses on its own

WHEN a run starts for a workflow in any compatibility state THE engine SHALL start it unless validation fails, a `needs_upgrade` hit on a `tightened` entry failing only through validation's own finding, and show every other state as a warning line in the catalog, at run start and in `update` naming `tempergraph upgrade <workflow>`, the start record carrying the state.

- GIVEN a workflow `out_of_range` that validates WHEN a run starts THEN it starts with one warning line and the start record carries the state

### VER-B18 Missing release record

WHEN `release.json` is missing or unreadable in an installed engine THE engine SHALL reinstall on `update`, and on every other verb warn and read the version from the package metadata.

- GIVEN an installed engine without `release.json` WHEN `status` runs THEN it warns and prints the package metadata version

## Acceptance criteria

- VER-AC1 (VER-B7, VER-B8, VER-B18): `release.json` equals the engine's constants by a generated drift test, and a missing record warns or reinstalls
- VER-AC2 (VER-B9, VER-B10, VER-B12, VER-B4): Every changelog entry validates against its schema, and every `renamed` entry on a surface a transform covers carries a transform (release check)
- VER-AC3 (VER-B13): Each transform passes its before and after fixture and is idempotent (applied twice, same bytes)
- VER-AC4 (VER-B2, VER-B5): Every scenario of VER-B2 is a test, and a run in each state other than a failing validation starts with its warning
- VER-AC5 (VER-B14, VER-B15, VER-B1): A workflow written before the version fields loads with the defaults and validates unchanged, and an edited template under an unchanged version raises `version-not-bumped`
- VER-AC6 (VER-B6): The repository check fails on each of its two fixtures
- VER-AC7 (VER-B11, VER-B3, VER-B16, VER-B17): Fixtures cover a typed hit beating a text hit, an unparseable file, a restamp that adds no entry and a parent reading a child's change notes

## Open questions

- Should `requires_engine` also be written into the workflow plugin's `plugin.json` as a dependency on the `tempergraph` plugin with a version range, so Claude Code refuses a mismatched install ([R-055](../research/R-055-updating-a-tool-with-long-lived-runs.rsrch.md) U6)? Until answered: no, `plugin.json` names `tempergraph` without a range. Owner: owner.
