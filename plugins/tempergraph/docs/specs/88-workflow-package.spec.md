# Workflow package

## Purpose

A workflow package is one folder that is at the same time a Claude Code plugin and a tempergraph workflow ([ADR-0105](../adr/0105-a-workflow-package-is-one-claude-plugin-with-a-python-part-and-a-docs-set.adr.md)), with three halves: the plugin half (the prompts, judge briefs, skills and agents specific to the workflow, in the layout Claude Code reads, [R-105](../research/R-105-workflow-packages-authoring-and-good-outcomes.rsrch.md) A1, A2); the Python half (the declaration module the engine imports to build the `WorkflowSpec`, the checks, routes, resolver and finalizer it names, and the Python requirements the engine installs); and the docs half (the workflow's own design set in the engine's shape, provisional until temperspec owns the format, [ADR-0113](../adr/0113-the-workflow-docs-set-is-provisional-until-temperspec-owns-it.adr.md)). Its good outcome is a file of its own owned by [OUT](90-run-outcome.spec.md); authoring writes a package through the scaffold ([SCF](91-blueprint-and-scaffold.spec.md)), and a person may write one by hand. This spec owns the layout, the engine manifest, the declaration format and builders, the callable signatures [CHK](75-check-contract-and-command-runs.spec.md) and [FIN](78-finalizer-contract.spec.md) do not already own, how the engine loads a package, what of the plugin reaches each executor, and the minimal package; it gives `load()` of [WFM](02-workflow-model.spec.md) its body. Registration and dependency installation stay in [UPD](60-engine-update.spec.md); version fields, digests and the stamp in [VER](61-version-metadata.spec.md). Design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### PKG-B1 One folder, two readers

WHEN a package is installed from a marketplace THE package SHALL be listed by Claude Code as a plugin with its version, and reconciling by `install` or `update` SHALL give the registry an entry of kind `plugin` whose path is the cache folder of that version, `list` showing the workflow as loaded.

- GIVEN the minimal package installed from a marketplace WHEN `update` reconciles THEN the registry holds a `plugin` entry at the version's cache folder and `list` shows it loaded

### PKG-B2 Version from one place

WHEN a package is built THE engine SHALL set `WorkflowSpec.version` from `plugin.json`, a declaration that passes `version` or `name` to `Workflow` failing at build with a `TypeError` naming the field.

- GIVEN `plugin.json` at `0.2.0` and a declaration passing `version="0.3.0"` WHEN the package loads THEN the build fails naming `version`
- GIVEN the same declaration without `version` WHEN it loads THEN `WorkflowSpec.version` is `0.2.0`

### PKG-B3 Two packages, same module names

WHEN two registered packages with same-named modules run checks in one check worker process THE engine SHALL import each package's modules under its private name so neither sees the other's.

- GIVEN two packages that both have `checks.py` WHEN a run of each uses its check in one worker THEN each imports its own module

### PKG-B4 Engine internals refused

WHEN a declaration imports an engine module other than `tempergraph.api` THE engine SHALL report `private-engine-import` as an error naming the file and line without executing the import.

- GIVEN a declaration that imports `tempergraph.compiler` WHEN the package is validated THEN `private-engine-import` names the file and line and the import never ran

### PKG-B5 Hooks refused

WHEN a package ships `hooks/hooks.json` THE engine SHALL report `plugin-hooks` as an error with the remedy "declare the tools the step needs; lifecycle hooks are registered with `tempergraph hooks add`" ([HOK](17-engine-cli.spec.md)).

- GIVEN a package with `hooks/hooks.json` WHEN it is validated THEN `plugin-hooks` is an error with that remedy

### PKG-B6 Interface levels

WHEN a package declares a `workflow_api` level THE engine SHALL load it when the level is at most the engine's and at least the oldest level the engine still loads (`release.json` field `loads_workflow_api_from`); give `not_loaded: workflow_api_newer` with the remedy `update` for a newer level; give `not_loaded: workflow_api_retired` with the remedy `upgrade` for a retired one, a registered entry being pinned to an engine that loads it ([UPD-B20](60-engine-update.spec.md)); and warn `workflow_api_behind` with the remedy `upgrade` for a loadable level below the engine's when the releases that raised the level past it have breaking `workflow` entries.

- GIVEN an engine at level 3 that loads from 2 WHEN packages at 3, 2, 1 and 4 load THEN 3 loads, 2 loads with `workflow_api_behind` if breaking entries exist, 1 is `workflow_api_retired` and 4 is `workflow_api_newer`

### PKG-B7 A skill on each executor

WHEN a step declares a `skill:<plugin>:<name>` capability THE engine SHALL give a `claude` step `--plugin-dir <package root>` and an allow rule for that skill only, an `agent-sdk` step the `plugins` option with the init message listing the plugin, and refuse it before spend on `messages-api` (exit 2 `capability_unmapped: skill`) and on `antigravity` until P-AG-10 is recorded.

- GIVEN a step declaring `skill:release-notes-tgraph:style` WHEN it runs on `messages-api` THEN it is refused before spend with `capability_unmapped: skill`

### PKG-B8 A delivery workflow as a package

WHEN a workflow ships rule sets, agents, checks and a finalizer THE package SHALL hold its rule sets as skills (one per artifact type), its agents as `agents/*.md`, its checks in `workflow/<module>/checks.py`, its finalizer in `workflow/<module>/finalizer.py`, its outcome in `outcome.json` and one spec per unit in its docs half, its plugin named `<workflow>-tgraph` and its workflow name short, with nothing in the engine naming it (contract C8, [ADR-0129](../adr/0129-the-engine-names-no-workflow-and-takes-requests-as-general-capabilities.adr.md)).

- GIVEN any package under `plugins/` WHEN the engine's source and tests are scanned THEN neither names it

### PKG-B9 Docs drift

WHEN a criterion's text changed in `outcome.json` and not in its unit's spec THE engine SHALL warn `docs-drift` in `dev` mode with the criterion id and both files, and refuse the workflow in `stable` mode.

- GIVEN a changed criterion text WHEN `validate` runs in `dev` mode THEN `docs-drift` warns naming the id and both files

### PKG-B10 Recognisable by name

WHEN a package loads or a blueprint is checked THE engine SHALL name the workflow from `tempergraph.json` and the plugin as that name plus `-tgraph`, give `not_loaded: manifest` with `plugin-name-suffix` naming the expected plugin name when `plugin.json` differs, and refuse a blueprint whose workflow name ends in `-tgraph` with the remedy naming the short name.

- GIVEN the minimal package with `plugin.json` `name` `release-notes` or `release-notes.tgflow` WHEN it loads THEN it is `not_loaded: manifest` with `plugin-name-suffix` naming `release-notes-tgraph`
- GIVEN a blueprint named `release-notes-tgraph` WHEN `blueprint check` runs THEN it is refused with the remedy "name the workflow `release-notes`"

### PKG-B11 Layout

WHEN a package is read, with paths relative to the package root, which is the plugin root THE engine SHALL require `.claude-plugin/plugin.json` (only fields Claude Code reads: `name`, `version`, `description`, `author`, `license`, `dependencies` naming `tempergraph`, R-105 A1, A11), `tempergraph.json` (PKG-B13), `outcome.json` ([OUT](90-run-outcome.spec.md)), `workflow/pyproject.toml` (`[project]` with `name = "tgwf-<name>"`, `requires-python`, `dependencies`, nothing else read), `workflow/<module>/` (the entry's module and the callables it names), `prompts/<unit>.md` per model step (and per council member or contest slot where it differs, [CON-B8](01-contracts.spec.md)), `judges/<unit>.md` per judged gate (stance then brief under two fixed headings, [JDG](05-judge-and-verdict.spec.md)), `evals/cases.json` with one case, `diagram/` (generated, [LIF](18-lifecycle-and-evals.spec.md)), `tests/`, `docs/`, `README.md`, and once authored `blueprint.json` ([SCF](91-blueprint-and-scaffold.spec.md)) and `authoring.json` ([AUT](89-workflow-authoring.spec.md)); read optional `skills/<name>/SKILL.md` ([ADR-0078](../adr/0078-skills-are-a-declared-tool-capability.adr.md)), `agents/<name>.md`, `lessons/<unit>.json` ([LSN](42-workflow-lessons.spec.md)), `evals/checks/<unit>/`, `evals/steps/<unit>/` and `evals/calibration/<gate>/` ([PRP-B17](40-improvement-proposals.spec.md), [EVS-B12](51-eval-suites.spec.md), [JCL-B9](50-judge-calibration.spec.md)), and `stamp.json` and `changes/<version>.json` ([VER-B16](61-version-metadata.spec.md), [VER-B17](61-version-metadata.spec.md)); ignore and keep every other folder; and report `pyproject-missing`, `pyproject-invalid`, `pyproject-name` and `outcome-missing` as errors and a missing `README.md`, `docs/`, `tests/`, `diagram/` or `evals/cases.json` as the warning `package-file-missing`.

- GIVEN a package without `outcome.json` WHEN it is validated THEN `outcome-missing` is an error

### PKG-B12 Refused plugin parts

WHEN a package ships `hooks/hooks.json` or a `hooks` key (`plugin-hooks`), `.mcp.json` or `mcpServers` (`plugin-mcp`), `bin/` (`plugin-bin`), `.lsp.json` or a `settings.json` with an `agent` key (`plugin-session-settings`), or a root `CLAUDE.md` or `AGENTS.md` (`plugin-instruction-file`, because Claude Code does not read it) THE engine SHALL report a validation error with that code, because the plugin is loaded into the engine's step sessions and what runs there is only what the step declares ([ADR-0112](../adr/0112-plugin-content-reaches-each-executor-by-a-declared-route-or-is-refused.adr.md)), a workflow that needs an MCP server declaring its tools (`mcp:<server>/<tool>`) with the server configured on the machine.

- GIVEN a package with `.mcp.json` WHEN it is validated THEN `plugin-mcp` is an error

### PKG-B13 Engine manifest

WHEN `tempergraph.json` is read by `read_manifest(package_path) -> PackageManifest | list[Finding]`, with no import and no model THE engine SHALL read `schema_version` (`1`); `name` (the workflow name, PKG-B14); `entry` (`<module>:<function>`, `<module>` a folder under `workflow/`); `workflow_api` (the declaration interface level, [VER-B8](61-version-metadata.spec.md)); `docs` (`provisional` or a rule set id, PKG-B21); optional `surfaces` (executor to `SurfaceForm`, PKG-B24); and optional `audit` `{ignore: [{rule, unit?, reason, until?}]}` of accepted findings ([AUD](55-workflow-audit.spec.md)), an entry without a reason being the error `audit-ignore-invalid`; warn `manifest-field-unknown` on any other field; never repeat the version, which comes from `plugin.json` ([VER-B14](61-version-metadata.spec.md)); treat a folder with no `tempergraph.json` as not a workflow package, `register` refusing it and reconcile skipping the plugin silently; and give `package_files(package_path) -> PackageInventory`, what is where, to digests, audit and the docs check.

- GIVEN a plugin folder without `tempergraph.json` WHEN `workflows register` runs on it THEN it is refused

### PKG-B14 Names

WHEN a package's names are checked ([ADR-0120](../adr/0120-a-workflow-plugin-name-is-the-workflow-name-plus-tgraph.adr.md)) THE engine SHALL use the workflow name (`tempergraph.json` `name`, for example `release-notes`) for `tempergraph run`, the registry key, run folders, thread ids, `tgwf-<name>` and the private module `tgwf_<name>`; use the plugin name (`plugin.json` `name`, the marketplace entry and the plugin folder, for example `release-notes-tgraph`) for Claude Code's plugin lists, `--plugin-dir` and the skill namespace; require the plugin name to be the workflow name plus `-tgraph`, else `plugin-name-suffix`, the engine and monitor plugins not being workflows; require the workflow name to be kebab-case (`[a-z0-9][a-z0-9-]*`), not ending in `-tgraph`, not starting with a prefix Claude Code reserves (`claude-`, `anthropic-`, `anthropics-`, `cc-plugin-`) and at most 57 characters, else `not_loaded: manifest` with the rule broken; and accept either name wherever a CLI argument names a workflow.

- GIVEN the minimal package WHEN `run release-notes-tgraph …` runs THEN it starts `release-notes`

### PKG-B15 Loading manifests and levels

WHEN `load(package_path) -> WorkflowSpec` runs THE engine SHALL first read `plugin.json` and `tempergraph.json` with a known `schema_version` and the names of PKG-B14, else `not_loaded: manifest`, then check the interface level as PKG-B6, before importing anything.

- GIVEN `schema_version` 2 WHEN the package loads THEN it is `not_loaded: manifest` and nothing was imported

### PKG-B16 Import

WHEN a package's Python half is imported THE engine SHALL run the dependency gate (PKG-B18) and a source scan first, refusing an import of any `tempergraph` module but `tempergraph.api` (`private-engine-import`) and an absolute import of the entry folder's name (`own-module-absolute-import`) as `not_loaded` with code, file and line, and warning `undeclared-import` on any import outside the standard library, the `pyproject.toml` requirements and the package's own modules; import the entry module from `workflow/` under the private name `tgwf_<name>` (`-` as `_`), its modules importing each other relatively; never install the Python half as a distribution, so a cache repoint after a plugin update is enough to run new code ([UPD-B20](60-engine-update.spec.md)); import afresh on every load; record each callable as `tgwf_<name>.<module>:<qualname>`; give a child process the map of private names to folders in its context document ([CHK-B16](75-check-contract-and-command-runs.spec.md)); and report an exception in import as `not_loaded: import` with its type only ([WFM](02-workflow-model.spec.md)).

- GIVEN a declaration that writes `from release_notes import checks` WHEN it loads THEN it is `not_loaded: own-module-absolute-import` with file and line

### PKG-B17 Build, outcome and validation

WHEN the entry is imported THE engine SHALL call it with no argument and require a `WorkflowSpec` built by the builders, setting `name`, `version` and `package_root` itself, else `not_loaded: build` (also for a missing entry module or function), a builder's own `TypeError` showing its text, which names the field; read `outcome.json`, attach it as `WorkflowSpec.outcome` and fill each gate's criteria from the unit's intermediate outcomes ([OUT](90-run-outcome.spec.md)); then run the WFM validation and this spec's package rules, findings making a start exit 2; loading being read-only and model-free (contract C13), in the engine process and again in the check worker.

- GIVEN an entry that returns a dict WHEN the package loads THEN it is `not_loaded: build`

### PKG-B18 Dependency gate

WHEN `[project].dependencies` is read THE engine SHALL accept only plain requirements (a name, optional extras, optional version specifiers and an optional environment marker) and refuse a direct reference (`name @ url`), a path, an installer option or the engine itself (`tempergraph`) with `not_loaded: dependency_refused`, no package text reaching an installer's argv ([UPD-B20](60-engine-update.spec.md)).

- GIVEN `dependencies = ["requests @ https://example.com/r.whl"]` WHEN the package loads THEN it is `not_loaded: dependency_refused` and nothing is installed

### PKG-B19 Builders

WHEN a declaration is written THE engine SHALL offer typed builders from its one public module `tempergraph.api` ([ADR-0106](../adr/0106-declare-workflows-with-typed-python-builders-and-text-in-files.adr.md)), each producing one contract type ([CON-B4](01-contracts.spec.md)) with the same field names as keyword arguments and raising `TypeError` on an unknown one: `Workflow(order=…, units=…, input=…, routing=…, …)` for `WorkflowSpec` (name and version from the manifests); `Step`, `Script`, `Route`, `Switch`, `Parallel`, `Map`, `Ask`, `Wait`, `Council`, `Contest` and `Subworkflow` for a `UnitSpec` of that kind, kinds outside the current release refused at validation `not_in_release` ([ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md)); `Gate(check=…, judge=…, …)` with `criteria` normally filled from `outcome.json`, inline criteria valid for older packages ([WFM](02-workflow-model.spec.md)) and an id given both ways being `criterion-declared-twice`; `Judge(file="judges/<unit>.md", references=…, subject=…)`; `Input`, `Param`, `Routing` and `Models` ([CON-B9](01-contracts.spec.md)); and `text("prompts/<unit>.md")` for any template or brief, a path outside the package or missing being the error `text-ref`, inline text valid but never written by the scaffold.

- GIVEN `Step(promt=…)` WHEN the package builds THEN it fails with `TypeError` naming `promt`

### PKG-B20 Callables and their views

WHEN a builder is given a callable THE engine SHALL record it as a module-level reference `<module>:<qualname>` relative to `workflow/`, refusing a lambda, a nested function or a bound method with `callable-not-importable`; use the signatures check and outcome check `(ctx: CheckContext) -> CheckResult` ([CHK-B10](75-check-contract-and-command-runs.spec.md), the outcome check getting the run's final state), route and switch predicate `(view: RouteView) -> str` returning a target or an arm name, input resolver `(request: RawRequest) -> ResolveResult` ([CON-B9](01-contracts.spec.md)), command resolver `(text, workdir, main_checkout) -> ResolvedCommand | CommandRefusal` ([CHK-B11](75-check-contract-and-command-runs.spec.md)), finalizer `(ctx: FinalizerContext) -> FinalizerResult` ([FIN-B6](78-finalizer-contract.spec.md)), script unit or hybrid script per [SCR-B5](70-script-units-and-hybrid-steps.spec.md) and model item function `(item: ItemView) -> str` ([MAP](77-map-unit.spec.md)); define `RouteView` as a read-only `{unit, visit, values, facts, artifact_keys (present keys only), settings}` and `RawRequest` as `{args, inputs, main_checkout (read-only)}`; and require every callable but the script and the finalizer to be pure over its input and the files it may read and to call no model, validation calling each resolver and route on the declared examples twice and comparing.

- GIVEN a route given as a lambda WHEN the package builds THEN it fails `callable-not-importable`

### PKG-B21 The docs half

WHEN a package carries its design set, written first by the scaffold from the authoring record and kept by its owner THE package SHALL follow the engine's own docs rules ([docs README](../README.md)) applied to one workflow while `tempergraph.json` `docs` is `provisional`, and hold `docs/README.md` (the rules in force, the reading order, the file-naming table); `docs/specs/00-overview.spec.md` (the outcome statement, deliverables, unit map with each unit's intermediate outcome, inputs, executors, and one acceptance criterion per final outcome criterion); `docs/specs/NN-<unit>.spec.md` per unit (what it receives and produces, its intermediate outcome, failure and approval policy, open questions, one acceptance criterion per criterion of the unit); `docs/adr/NNNN-<title>.adr.md` per decision taken in authoring (step boundaries, a criterion dropped as not observable, an outcome accepted with no trustworthy verification, an executor choice, [SHL-B3](19-plugin-shell.spec.md)); and `docs/research/R-001-sources.rsrch.md`, the intake dossier of every source with kind, digest and confidence ([AUT](89-workflow-authoring.spec.md)), never a private source's text; `docs/` being outside the content digest ([VER-B14](61-version-metadata.spec.md)), never read by a step or a judge, with its own `docs_digest` in the stamp.

- GIVEN a change to `docs/` only WHEN the content digest is computed THEN it is unchanged

### PKG-B22 Docs check

WHEN `validate` runs the docs check THE engine SHALL keep a criterion's text only in `outcome.json`, the docs naming it by id and explaining why, and report `docs-drift` when a unit has no spec, a criterion id does not appear as an acceptance criterion in exactly the spec of its unit (the overview for final criteria) with the same text digest, an acceptance criterion names an unknown id, or a link does not resolve, as a warning and in `stable` mode an error.

- GIVEN a unit without a spec WHEN `validate` runs in `stable` mode THEN `docs-drift` refuses the workflow

### PKG-B23 What reaches each executor

WHEN plugin content is needed in a session THE engine SHALL render every prompt, brief, stance and lesson itself on every executor ([PRM](04-prompt-rendering.spec.md)); reach skills and agents by one declared route per executor or refuse the step before spend (contract C15, [ADR-0112](../adr/0112-plugin-content-reaches-each-executor-by-a-declared-route-or-is-refused.adr.md)): on `claude` through `--plugin-dir` with `skill:` allow rules ([ECC](11-executor-claude-code.spec.md), P-CC-8, P-CC-9); on `agent-sdk` through `plugins=[{"type": "local", "path": <root>}]`, an init message that does not list the plugin being `session_failed: plugin_not_loaded`; on `messages-api` not at all ([EMA](20-executor-messages-api.spec.md)), a template naming an agent warning; on `antigravity` not until P-AG-10, then copied into the session's isolated config home ([ADR-0011](../adr/0011-isolated-config-home-for-antigravity.adr.md)); agents through the loaded plugin and the `subagent` capability; never load the workflow plugin into a judge session (`--bare` or `--setting-sources ""`, `setting_sources=[]` with no `plugins`, [GRD](06-independence-guard.spec.md)); refuse a skill capability whose `skills/<name>/SKILL.md` is missing from the package or an installed dependency; and refuse the other executors' routes `not_in_release` while only `claude` ships ([ADR-0091](../adr/0091-first-release-ships-the-claude-executor-only.adr.md)).

- GIVEN a judged gate on `claude` WHEN its judge session starts THEN its launch loads no workflow plugin

### PKG-B24 Surface forms

WHEN `tempergraph.json` `surfaces` names a `SurfaceForm` for an executor (for example `skills_dir: "forms/antigravity/skills"`) THE engine SHALL use that second form of the skills only once that executor's probe confirms the route, and a skill shipped for more than `claude` SHALL keep to the six standard frontmatter fields (R-105 A6), prompt audit flagging others `skill-frontmatter-nonstandard` ([PRA](58-prompt-audit.spec.md)).

- GIVEN a skill with a seventh frontmatter field and an `antigravity` surface WHEN prompt audit runs THEN it flags `skill-frontmatter-nonstandard`

### PKG-B25 The minimal package

WHEN the scaffold writes a one-step blueprint THE scaffold SHALL write the smallest valid package, which runs with defaults only ([R-011](../research/R-011-design-gap-review.rsrch.md) G3): `plugin.json` (`name` `<workflow>-tgraph`, `version` `0.1.0`, `description`, `author`, `license`, `dependencies: ["tempergraph"]`), `tempergraph.json` (`schema_version` 1, `name`, `entry` `<module>:workflow`, `workflow_api` 1, `docs` `provisional`), `outcome.json` with one final outcome, one intermediate outcome and three criteria, `workflow/pyproject.toml` with `name = "tgwf-<workflow>"` and no dependencies, a declaration module with routing, issue repository, one Step and one Gate with a check and a Judge, `checks.py` with the check, one prompt and one judge file, `evals/cases.json` with one case and one must-pass and one must-fail check fixture, `blueprint.json`, `authoring.json`, `diagram/`, `tests/`, `docs/` and `README.md`; relying on executor `claude`, model `medium` for the step and the judge, `retry_budget` 2, `on_fail: retry`, `on_budget_spent: ask`, no approval, workspace `auto` and `improvement_mode: dev`, the outcome gate compiled from `outcome.json` with no declaration ([OUT](90-run-outcome.spec.md)).

- GIVEN the minimal package WHEN `claude plugin validate --strict` runs THEN it passes

## Acceptance criteria

- PKG-AC1 (PKG-B1, PKG-B11, PKG-B13, PKG-B25): The minimal package passes `claude plugin validate`, loads, validates, compiles and runs on scripted stand-ins with no field beyond those listed
- PKG-AC2 (PKG-B4, PKG-B5, PKG-B6, PKG-B12, PKG-B15, PKG-B16, PKG-B17, PKG-B18, PKG-B20): Every refused part, every loading failure and every package error has a fixture package that fails with its own code
- PKG-AC3 (PKG-B3, PKG-B16): Two packages with same-named modules load in one process without either seeing the other's
- PKG-AC4 (PKG-B2, PKG-B19): A builder given an unknown keyword, or `name` or `version`, fails at build; the built spec's name and version equal the manifests'
- PKG-AC5 (PKG-B7, PKG-B23, PKG-B24): No judge session of any executor loads a workflow plugin (checked on the session-started record of each conformance fixture), and each executor's skill route or refusal has a fixture
- PKG-AC6 (PKG-B9, PKG-B21, PKG-B22): The docs check passes on the scaffold's output, and fails with `docs-drift` on each of a unit without a spec, a missing criterion id, an unknown id and a changed text
- PKG-AC7 (PKG-B21): The content digest changes when any of `outcome.json`, a prompt, a brief, a skill, an agent, a Python source or `pyproject.toml` dependencies changes, and not when only `docs/`, `diagram/`, `evals/`, `authoring.json` or `README.md` changes
- PKG-AC8 (PKG-B8, PKG-B10, PKG-B14): A package whose plugin name lacks the `-tgraph` suffix (or carries `.tgflow`, `-tg-graph`) fails to load with `plugin-name-suffix`; each workflow name rule has a fixture; `run <workflow>-tgraph` starts the same workflow as `run <workflow>`; the scaffold writes `<name>-tgraph`; and no engine source or test names a package

## Open questions

- Should a workflow plugin's `dependencies` pin a `tempergraph` plugin range? Until answered: the scaffold writes the bare name, left to [VER](61-version-metadata.spec.md)'s open question on the plugin dependency range. Owner: owner.
- May a workflow ship a skill meant for the person (for example "start a release-notes run"), invoked in the person's own session rather than a step? Until answered: yes; a skill no step declares is never loaded into a step, and the run driver stays the engine's. Owner: owner.
