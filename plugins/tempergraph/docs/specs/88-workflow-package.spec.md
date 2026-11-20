---
title: Workflow package
type: component
status: ready-for-implementation
prefix: PKG
adrs: [0003, 0016, 0078, 0105, 0106, 0112, 0113, 0120]
---

# Workflow package

## 1. Overview

A **workflow package** is one folder that is at the same time a Claude Code plugin and a tempergraph workflow ([ADR-0105](../adr/0105-a-workflow-package-is-one-claude-plugin-with-a-python-part-and-a-docs-set.adr.md)). It has three halves:

- the **plugin half**: the prompts, judge briefs, skills and agents specific to the workflow, in the layout Claude Code reads ([R-105 A1, A2](../research/R-105-workflow-packages-authoring-and-good-outcomes.rsrch.md));
- the **Python half**: the declaration module the engine imports to build the `WorkflowSpec`, plus the checks, routes, resolver and finalizer it names, and the Python requirements the engine installs;
- the **docs half**: the workflow's own design set (specs, decision records, research notes) in the same shape as the engine's, provisional until temperspec owns the format ([ADR-0113](../adr/0113-the-workflow-docs-set-is-provisional-until-temperspec-owns-it.adr.md)).

Its good outcome, the data every gate's criteria come from, is a file of its own owned by [OUT](90-run-outcome.spec.md). Authoring writes a package through the scaffold ([SCF](91-blueprint-and-scaffold.spec.md)); a person never has to write one by hand, but may. This spec owns the layout, the engine manifest, the declaration format and builders, the callable signatures [CHK](75-check-contract-and-command-runs.spec.md) and [FIN](78-finalizer-contract.spec.md) do not already own, how the engine loads a package, what of the plugin reaches each executor, and the minimal package. It gives `load()` of [WFM §2](02-workflow-model.spec.md) its body. Registration and dependency installation stay in [UPD §2.8](60-engine-update.spec.md); version fields, digests and the stamp stay in [VER](61-version-metadata.spec.md).

## 2. Contract

```python
def load(package_path: Path) -> WorkflowSpec: ...                 # WFM §2; reads tempergraph.json, imports the entry
def read_manifest(package_path: Path) -> PackageManifest | list[Finding]: ...   # no import, no model
def package_files(package_path: Path) -> PackageInventory: ...    # what is where, for digests, audit and the docs check
```

### 2.1 Layout

Paths are relative to the package root, which is the plugin root. Every name below is fixed; a folder not listed is ignored by the engine and kept by every tool.

| Path | Half | Holds | Required |
|---|---|---|---|
| `.claude-plugin/plugin.json` | plugin | Claude Code's manifest: `name` (the workflow name plus `-tgraph`, §2.2.1), `version`, `description`, `author`, `license`, `dependencies` (naming `tempergraph`, [R-105 A11](../research/R-105-workflow-packages-authoring-and-good-outcomes.rsrch.md)). Only fields Claude Code reads ([R-105 A1](../research/R-105-workflow-packages-authoring-and-good-outcomes.rsrch.md)) | yes |
| `tempergraph.json` | engine | The engine manifest (§2.2) | yes |
| `outcome.json` | engine | The good outcome: final and intermediate outcomes and every criterion ([OUT §2.1](90-run-outcome.spec.md)) | yes |
| `workflow/pyproject.toml` | Python | `[project]` with `name = "tgwf-<name>"`, `requires-python`, `dependencies`; nothing else is read | yes |
| `workflow/<module>/` | Python | The declaration module and the callables it names (§2.4); `<module>` is the entry's module | yes |
| `prompts/<unit>.md` | plugin | One template per model step, per council member or contest slot where it differs ([CON §2.2](01-contracts.spec.md)) | per model step |
| `judges/<unit>.md` | plugin | The judge's stance, then its brief, under two fixed headings ([JDG](05-judge-and-verdict.spec.md)) | per judged gate |
| `skills/<name>/SKILL.md` | plugin | Workflow skills, declared by steps as `skill:<plugin>:<name>` ([ADR-0078](../adr/0078-skills-are-a-declared-tool-capability.adr.md)) | no |
| `agents/<name>.md` | plugin | Workflow subagents a step may start through `subagent` | no |
| `lessons/<unit>.json` | engine | Per-step lessons ([LSN](42-workflow-lessons.spec.md)) | no |
| `evals/` | engine | `cases.json` (the workflow case set, [PRP §2.5](40-improvement-proposals.spec.md), [EVS §2.3](51-eval-suites.spec.md)), `checks/<unit>/` (check fixtures), `calibration/<gate>/` (gold cases, [JCL §2.1](50-judge-calibration.spec.md)) | `cases.json` with one case |
| `blueprint.json` | engine | The approved blueprint ([SCF §2.1](91-blueprint-and-scaffold.spec.md)) | yes, once authored |
| `diagram/` | engine | Generated `workflow.md`, `workflow.svg`, `model.json` ([LIF](18-lifecycle-and-evals.spec.md)); never typed | yes |
| `authoring.json` | engine | The authoring record: entry path, source list with digests, verification decisions, assumptions ([AUT §2.6](89-workflow-authoring.spec.md)); metadata only | yes, once authored |
| `stamp.json`, `changes/<version>.json` | engine | [VER §2.5, §2.6](61-version-metadata.spec.md) | stamp once stamped |
| `tests/` | Python | Generated tests ([SCF §2.4](91-blueprint-and-scaffold.spec.md)) and the owner's own | yes |
| `docs/` | docs | The workflow's design set (§2.5) | yes |
| `README.md` | — | For people: what the workflow does, how to start it, its outcome statement | yes |

Refused in a workflow package (validation `error`, code in parentheses): `hooks/hooks.json` or a `hooks` manifest key (`plugin-hooks`); `.mcp.json` or `mcpServers` (`plugin-mcp`); `bin/` (`plugin-bin`); `.lsp.json`, `settings.json` with an `agent` key (`plugin-session-settings`); a `CLAUDE.md` or `AGENTS.md` at the root (`plugin-instruction-file`, because Claude Code does not read it, [R-105 A2](../research/R-105-workflow-packages-authoring-and-good-outcomes.rsrch.md)). The reasons are in [ADR-0112](../adr/0112-plugin-content-reaches-each-executor-by-a-declared-route-or-is-refused.adr.md): the plugin is loaded into the engine's step sessions, and what runs there is only what the step declares. A workflow that needs an MCP server declares its tools (`mcp:<server>/<tool>`); the server is configured on the machine.

### 2.2 Engine manifest (`tempergraph.json`)

| Field | Kind | Meaning |
|---|---|---|
| `schema_version` | int | `1` |
| `name` | slug | The **workflow name** (§2.2.1): the built `WorkflowSpec.name`; `plugin.json` `name` is this plus `-tgraph` |
| `entry` | `<module>:<function>` | The builder function; `<module>` is a folder under `workflow/` |
| `workflow_api` | int | The level of the declaration interface the package was written for ([VER §2.2](61-version-metadata.spec.md)) |
| `docs` | `provisional` \| `<rule set id>` | Which rules the docs half follows (§2.5); `provisional` until temperspec ships rule files |
| `surfaces` | map executor → `SurfaceForm`, optional | Per-executor forms of the plugin content (§2.6); absent means the defaults of §2.6 |
| `audit` | `{ignore: [{rule, unit?, reason, until?}]}`, optional | Accepted audit findings ([AUD §2.4](55-workflow-audit.spec.md)); an entry without a reason is the validation error `audit-ignore-invalid` |

The version is **not** repeated: the builder reads `version` from `plugin.json` and sets `WorkflowSpec.version` from it ([VER §2.4](61-version-metadata.spec.md)), so the two can never disagree. `requires_engine` and `upgrade` stay on the spec (VER).

#### 2.2.1 Names

A workflow package has two names, one derived from the other ([ADR-0120](../adr/0120-a-workflow-plugin-name-is-the-workflow-name-plus-tgraph.adr.md)):

| Name | Where | Example | Used for |
|---|---|---|---|
| Workflow name | `tempergraph.json` `name` | `release-notes` | `tempergraph run`, the registry key, run folders and thread ids, `tgwf-<name>`, the private module `tgwf_<name>` |
| Plugin name | `plugin.json` `name`, the marketplace entry, the plugin folder | `release-notes-tgraph` | Claude Code: plugin lists, `--plugin-dir`, the skill namespace (`skill:release-notes-tgraph:<skill>`) |

| Rule | Detail |
|---|---|
| Suffix | The plugin name is the workflow name plus `-tgraph`, always, so any plugin ending in `-tgraph` is a tempergraph workflow. Any other plugin name is refused (`plugin-name-suffix`). The engine and monitor plugins are not workflows |
| Workflow name | Kebab-case (`[a-z0-9][a-z0-9-]*`); does not itself end in `-tgraph`; does not start with a prefix Claude Code reserves (`claude-`, `anthropic-`, `anthropics-`, `cc-plugin-`); at most 57 characters, so the plugin name stays within 64 |
| Either name is accepted | A CLI argument naming a workflow may be given as the plugin name: `run release-notes-tgraph …` runs `release-notes` |

### 2.3 Loading

| Step | Rule | Failure |
|---|---|---|
| 1 Manifests | Read `plugin.json` and `tempergraph.json`; the workflow name follows §2.2.1 and the plugin name is it plus `-tgraph`; `schema_version` known | `not_loaded: manifest`; a plugin name without the suffix carries the finding `plugin-name-suffix` naming the expected name |
| 2 Interface level | `workflow_api` ≤ the engine's, and ≥ the oldest level the engine still loads (`release.json` gains `loads_workflow_api_from`) | newer: `not_loaded: workflow_api_newer` (remedy: update the engine); older: `not_loaded: workflow_api_retired` (remedy: `upgrade`); loadable but below the engine's: the warning `workflow_api_behind` naming the breaking `workflow` entries of the releases that raised the level past it (none, no warning) |
| 3 Import | The dependency gate (§2.3.1) and the source scan run first. The entry module is imported from `workflow/` under a private name `tgwf_<name>` (`-` as `_`) so two packages' `checks` modules never collide; its own modules import each other relatively (`from . import checks`). Imports are limited to the standard library, the requirements in `pyproject.toml`, the package's own modules and `tempergraph.api` | Scan, before import: any other `tempergraph` module is `private-engine-import`, an absolute import of the entry folder's name is `own-module-absolute-import` (both `not_loaded` with that code, file and line), any other import is `undeclared-import` (warning: a distribution's import name may differ from its project name). An exception is `not_loaded: import` with its type only ([WFM §4](02-workflow-model.spec.md)) |
| 4 Build | Call the entry with no argument; it returns a `WorkflowSpec` built by the builders of §2.4; the engine sets `name`, `version` and `package_root` | Not a `WorkflowSpec`, or a raise: `not_loaded: build` (a builder's own `TypeError` shows its text, which names the field) |
| 5 Outcome | Read `outcome.json` and attach it (`WorkflowSpec.outcome`); fill each gate's criteria from the unit's intermediate outcomes ([OUT §2.3](90-run-outcome.spec.md)) | Per OUT §4 |
| 6 Validate | [WFM](02-workflow-model.spec.md) `validate`, then the package rules of this spec | Findings; a start exits 2 |

Loading is read-only and calls no model (C13). Every load imports the package afresh, so a changed source is what runs. A callable is recorded as `tgwf_<name>.<module>:<qualname>`; a child process gets the map of private names to folders in its context document ([CHK §2.6](75-check-contract-and-command-runs.spec.md)). The Python half is **imported from the package folder, never installed** as a distribution: a cache repoint after a plugin update ([UPD §2.8](60-engine-update.spec.md)) is enough to run the new code. Only `[project].dependencies` is installed, by UPD's rules. Loading happens in the engine process and again in the check worker ([CHK §2.6](75-check-contract-and-command-runs.spec.md)), so a callable must be importable by its reference alone.

#### 2.3.1 The dependency gate

Each `[project].dependencies` line must be a plain requirement: a name, optional extras, optional version specifiers and an optional environment marker. A direct reference (`name @ url`), a path, an installer option, or the engine itself (`tempergraph`) is refused: `not_loaded: dependency_refused`. No package text reaches an installer's argv ([UPD §2.8](60-engine-update.spec.md)).

### 2.4 Declaration format

The declaration is Python that calls typed builders from the engine's one public module, `tempergraph.api` ([ADR-0106](../adr/0106-declare-workflows-with-typed-python-builders-and-text-in-files.adr.md)). Each builder produces one type of [CON §2.1](01-contracts.spec.md) and takes the same field names as keyword arguments; an unknown argument is a `TypeError` at build time, so a misspelt field never becomes a default.

| Builder | Produces | Notes |
|---|---|---|
| `Workflow(order=…, units=…, input=…, routing=…, …)` | `WorkflowSpec` | `name` and `version` come from the manifests, never from arguments |
| `Step(…)`, `Script(…)`, `Route(…)`, `Switch(…)`, `Parallel(…)`, `Map(…)`, `Ask(…)`, `Wait(…)`, `Council(…)`, `Contest(…)`, `Subworkflow(…)` | `UnitSpec` of that kind | Each takes its owning spec's fields; kinds outside the current release are refused at validation with `not_in_release` ([ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md)) |
| `Gate(check=…, judge=…, …)` | `GateSpec` | `criteria` is normally omitted: it is filled from `outcome.json` (step 5 of §2.3). Inline criteria remain valid for older packages ([WFM-B5](02-workflow-model.spec.md)); an id given both inline and in `outcome.json` is `criterion-declared-twice` |
| `Judge(file="judges/<unit>.md", references=…, subject=…)` | `JudgeSpec` | Stance and brief are read from the file's two headings |
| `Input(…)`, `Param(…)`, `Routing(…)`, `Models(…)` | §2.3 and §2.4 of CON | |
| `text("prompts/<unit>.md")` | file ref | Any template or brief. A path outside the package is refused. Inline text is valid but the scaffold never writes it |

Callables are passed as Python function objects. The builder records each as a reference `<module>:<qualname>` relative to `workflow/`; a lambda, a nested function or a bound method is refused (`callable-not-importable`), because the check worker and the self-improvement child re-import by reference.

| Callable | Signature | Owner of its context |
|---|---|---|
| Check, outcome check | `(ctx: CheckContext) -> CheckResult` | [CHK §2.1](75-check-contract-and-command-runs.spec.md); the outcome check gets the run's final state ([OUT §2.3](90-run-outcome.spec.md)) |
| Route, switch predicate | `(view: RouteView) -> str` | This spec: `RouteView` in [CON §2.14](01-contracts.spec.md); returns a target or an arm name |
| Input resolver | `(request: RawRequest) -> ResolveResult` | This spec: `RawRequest` in [CON §2.14](01-contracts.spec.md); `ResolveResult` in [CON §2.3](01-contracts.spec.md) |
| Command resolver | `(text: str, workdir: Path, main_checkout: Path) -> ResolvedCommand \| CommandRefusal` | [CHK §2.2](75-check-contract-and-command-runs.spec.md) |
| Finalizer | `(ctx: FinalizerContext) -> FinalizerResult` | [FIN §2.1](78-finalizer-contract.spec.md) |
| Script unit or hybrid script | per [SCR §2.1](70-script-units-and-hybrid-steps.spec.md) | SCR |
| Model item function | `(item: ItemView) -> str` (an alias) | [MAP](77-map-unit.spec.md) |

Every callable above but the script and the finalizer is pure over its input and the files it may read, and calls no model; validation calls each resolver and route on the declared examples twice and compares ([WFM-B6](02-workflow-model.spec.md)).

### 2.5 The docs half

The package carries its own design set, written by the scaffold from the authoring record and kept by its owner ([ADR-0113](../adr/0113-the-workflow-docs-set-is-provisional-until-temperspec-owns-it.adr.md)). Until `tempergraph.json` `docs` names a temperspec rule set, the rules are the engine's own ([docs README](../README.md): six-section specs, type suffixes, decision and research rules), applied to one workflow.

| Path | Holds | Written first by |
|---|---|---|
| `docs/README.md` | The rules in force (a link to the engine's docs README while `provisional`), the reading order, the file-naming table | Scaffold |
| `docs/specs/00-overview.spec.md` | The workflow overview: the outcome statement, the deliverables, the unit map with each unit's intermediate outcome, the inputs, the executors. §6 lists one acceptance criterion per **final** outcome criterion | Scaffold, from `outcome.json` and the blueprint |
| `docs/specs/NN-<unit>.spec.md` | One component spec per unit: what it receives and produces, its intermediate outcome, its failure and approval policy, its open questions. §6 lists one acceptance criterion per criterion of the unit | Scaffold |
| `docs/adr/NNNN-<title>.adr.md` | Decisions taken in authoring: step boundaries, a criterion dropped as not observable, an outcome accepted with no trustworthy verification, an executor choice and its consequence ([SHL-B3](19-plugin-shell.spec.md)) | Authoring, one per recorded decision |
| `docs/research/R-001-sources.rsrch.md` | The intake dossier: every source the outcome and the verifications came from, with its kind, digest and confidence ([AUT §2.3](89-workflow-authoring.spec.md)); never the source's text when it is private | Authoring |

| Rule | Detail |
|---|---|
| One source per fact | A criterion's text lives in `outcome.json`. The docs name it by id (`- [ ] <criterion id> <text>`) and explain why; the docs check compares ids and text digests, so a spec never silently disagrees with the data |
| Docs check (`docs-drift`) | Every unit has a spec; every criterion id appears as an acceptance criterion in exactly the spec of its unit (the overview for final criteria) with the same text; no acceptance criterion names an unknown id; every link resolves. A miss is a `warning`; in `stable` mode an `error` |
| Not in the run | `docs/` is outside the content digest ([VER §2.4](61-version-metadata.spec.md)) and never read by a step or a judge; it has its own `docs_digest` in the stamp |

### 2.6 What reaches each executor

The engine renders every prompt, brief and stance itself ([PRM](04-prompt-rendering.spec.md)), so text files need no plugin on any executor. Skills and agents do; each executor reaches them by one declared route or the step is refused before spend (contract C15, [ADR-0112](../adr/0112-plugin-content-reaches-each-executor-by-a-declared-route-or-is-refused.adr.md)).

| Content | `claude` | `agent-sdk` | `messages-api` | `antigravity` |
|---|---|---|---|---|
| Prompts, briefs, stances, lessons | Rendered by the engine | same | same | same |
| Skills | Step sessions get `--plugin-dir <package root>`; `skill:` allow rules per [ECC](11-executor-claude-code.spec.md) (P-CC-8, P-CC-9) | `plugins=[{"type": "local", "path": <root>}]`; the init message must list the plugin, else `session_failed: plugin_not_loaded` | Not mapped: a step declaring `skill:` is refused ([EMA](20-executor-messages-api.spec.md)) | Not mapped until P-AG-10; then copied into the session's isolated config home ([ADR-0011](../adr/0011-isolated-config-home-for-antigravity.adr.md)) |
| Agents | Through the loaded plugin and the `subagent` capability | same | None; a template naming an agent warns ([WFM §2.2](02-workflow-model.spec.md)) | None |
| Judge sessions | Never load the workflow plugin (`--bare` or `--setting-sources ""`, [GRD](06-independence-guard.spec.md)) | `setting_sources=[]`, no `plugins` | n/a | n/a |

`SurfaceForm` (optional, per executor in `tempergraph.json`) names a second form of a skill for an executor that reads another layout, for example `skills_dir: "forms/antigravity/skills"`; it is used only once that executor's probe confirms the route. A skill shipped for more than `claude` keeps to the six standard frontmatter fields ([R-105 A6](../research/R-105-workflow-packages-authoring-and-good-outcomes.rsrch.md)); prompt audit flags others (`skill-frontmatter-nonstandard`, [PRA](58-prompt-audit.spec.md)).

### 2.7 The minimal package

The smallest valid package, which the scaffold writes for a one-step blueprint and which runs with defaults only ([R-011 G3](../research/R-011-design-gap-review.rsrch.md)):

```text
release-notes-tgraph/
  .claude-plugin/plugin.json        {"name": "release-notes-tgraph", "version": "0.1.0", "description": …, "author": {…}, "license": …, "dependencies": ["tempergraph"]}
  tempergraph.json                  {"schema_version": 1, "name": "release-notes", "entry": "release_notes:workflow", "workflow_api": 1, "docs": "provisional"}
  outcome.json                      one final outcome, one intermediate outcome for "draft", three criteria (OUT §3)
  workflow/pyproject.toml           name = "tgwf-release-notes", dependencies = []
  workflow/release_notes/__init__.py  def workflow() -> WorkflowSpec   (routing, issue_repository, one Step, one Gate with a check and a Judge)
  workflow/release_notes/checks.py    def draft_check(ctx: CheckContext) -> CheckResult
  prompts/draft.md, judges/draft.md
  evals/cases.json (1 case), evals/checks/draft/ (1 must-pass, 1 must-fail)
  blueprint.json, authoring.json, diagram/, tests/, docs/, README.md
```

Defaults it relies on: executor `claude`, model `medium` for the step and the judge, `retry_budget` 2, `on_fail: retry`, `on_budget_spent: ask`, no approval, workspace `auto`, `improvement_mode: dev`. The outcome gate ([OUT §2.4](90-run-outcome.spec.md)) is compiled from `outcome.json` with no declaration.

## 3. Behaviours

**PKG-B1 One folder, two readers.** Given the minimal package installed from a marketplace, when Claude Code loads it, then it lists the plugin with its version and no skill; when `install` or `update` reconciles, then the registry gains an entry of kind `plugin` whose path is the cache folder of that version, and `list` shows the workflow as loaded.

**PKG-B2 Version from one place.** Given `plugin.json` at `0.2.0` and a declaration that passes `version="0.3.0"` to `Workflow`, when the package loads, then the build fails with `TypeError` naming `version`; a declaration without it loads with `WorkflowSpec.version = 0.2.0`.

**PKG-B3 Two packages, same module names.** Given two registered packages that both have `checks.py`, when a run of each uses its check in the same check worker process, then each imports its own module under its private name and neither sees the other's.

**PKG-B4 Engine internals refused.** Given a declaration that imports `tempergraph.compiler`, when the package is validated, then `private-engine-import` is an error naming the file and line, and the import was never executed.

**PKG-B5 Hooks refused.** Given a package with `hooks/hooks.json`, when it is validated, then `plugin-hooks` is an error with the remedy "declare the tools the step needs; lifecycle hooks are registered with `tempergraph hooks add`" ([CLI §2.2](17-engine-cli.spec.md)).

**PKG-B6 Interface levels.** Given an engine at `workflow_api` 3 that loads from 2:

| Package `workflow_api` | State | Remedy shown |
|---|---|---|
| 3 | loaded | — |
| 2 | loaded, compatibility warning if the changelog has breaking `workflow` entries since 2 | `upgrade` |
| 1 | `not_loaded: workflow_api_retired`; a registered entry is pinned to an engine that loads it, as UPD §2.8 pins | `upgrade` |
| 4 | `not_loaded: workflow_api_newer` | `update` |

**PKG-B7 A skill on each executor.** Given a step declaring `skill:temperspec-tgraph:spec-authoring`:

| Step executor | Result |
|---|---|
| claude | `--plugin-dir` on the step launch, allow rule for that skill only |
| agent-sdk | `plugins` option; the init message lists `temperspec-tgraph` |
| messages-api | refused before spend, exit 2, `capability_unmapped: skill` |
| antigravity | refused before spend until P-AG-10 is recorded |


**PKG-B9 Docs drift.** Given a criterion whose text changed in `outcome.json` and not in its unit's spec, when `validate` runs in `dev` mode, then `docs-drift` warns with the criterion id and both files; `stable` mode refuses the workflow.

**PKG-B10 Recognisable by name.** Given the minimal package, when it loads, then its `WorkflowSpec.name` is `release-notes` and its plugin is `release-notes-tgraph`; given the same package with `plugin.json` `name` `release-notes` (or `release-notes.tgflow`), when it loads, then it is `not_loaded: manifest` with `plugin-name-suffix` naming `release-notes-tgraph`; given a blueprint named `release-notes-tgraph`, when `blueprint check` runs, then it is refused with the remedy "name the workflow `release-notes`".

## 4. Error conditions

| Condition | Result |
|---|---|
| No `tempergraph.json` | Not a workflow package: `register` refuses, reconcile skips the plugin silently |
| `plugin.json` `name` is not the workflow name plus `-tgraph` | `not_loaded: manifest` with `plugin-name-suffix`, both names and the expected one shown |
| A workflow name that is not kebab-case, ends in `-tgraph`, starts with a reserved prefix or is over 57 characters | `not_loaded: manifest`, the rule broken shown |
| Entry module or function missing | `not_loaded: build` |
| A text reference outside the package or missing | Validation error `text-ref` with the path |
| A refused plugin part (§2.1) | Validation error with its code |
| `pyproject.toml` with a dependency the dependency gate refuses | `not_loaded: dependency_refused` (§2.3.1) |
| `workflow/pyproject.toml` missing or unreadable; its `name` not `tgwf-<name>` | Validation error `pyproject-missing`, `pyproject-invalid`, `pyproject-name` |
| `outcome.json` missing | Validation error `outcome-missing` |
| `README.md`, `docs/`, `tests/`, `diagram/` or `evals/cases.json` missing | Validation warning `package-file-missing` |
| An unknown `tempergraph.json` field | Warning `manifest-field-unknown` |
| A callable that is not module-level | `callable-not-importable` at build |
| A skill capability whose `skills/<name>/SKILL.md` is missing from this package or an installed dependency | Validation error (the `skill:` row of [WFM §2.1](02-workflow-model.spec.md)) |

## 5. Design notes

- **Why one folder.** The owner's product form is a workflow that is itself a Claude plugin with a Python part ([R-011 G2](../research/R-011-design-gap-review.rsrch.md)); one folder means one version, one install and one digest. The alternatives are in [ADR-0105](../adr/0105-a-workflow-package-is-one-claude-plugin-with-a-python-part-and-a-docs-set.adr.md).
- **Why a second manifest.** Claude Code strips unknown keys from `plugin.json` ([R-105 A1](../research/R-105-workflow-packages-authoring-and-good-outcomes.rsrch.md)), so engine fields cannot live there.
- **Why builders.** Typed builders give an error at the misspelt field, keep callables as real functions the check worker can import, and let the later `tempergraph` Python package expose the same surface ([ADR-0106](../adr/0106-declare-workflows-with-typed-python-builders-and-text-in-files.adr.md)). Long text lives in files so prompt audit, lessons and the improvement loop edit text, not code.
- **Isolation is by rule.** A package is imported into the engine process ([WFM §5](02-workflow-model.spec.md)); the import scan and the dependency gate are the controls, not a sandbox.
- **Release 1.** The minimal package passes `claude plugin validate --strict` on Claude Code 2.1.329 (model-free, 2026-11-20); `--strict` asks for `author`, so the scaffold writes it. `claude` only ([ADR-0091](../adr/0091-first-release-ships-the-claude-executor-only.adr.md)): §2.6's other columns are designed and refused with `not_in_release` until their release. The docs half and its check ship in release 1, the check as a warning.

## 6. Acceptance criteria

- [ ] PKG-AC-1 The minimal package of §2.7 passes `claude plugin validate`, loads, validates, compiles and runs on scripted stand-ins with no field beyond those listed.
- [ ] PKG-AC-2 Every refused part of §2.1 and every failure of §2.3 and §4 has a fixture package that fails with its own code.
- [ ] PKG-AC-3 Two packages with same-named modules load in one process without either seeing the other's (PKG-B3).
- [ ] PKG-AC-4 A builder given an unknown keyword, or `name` or `version`, fails at build; the built spec's name and version equal the manifests'.
- [ ] PKG-AC-5 No judge session of any executor loads a workflow plugin (checked on the session-started record of each conformance fixture).
- [ ] PKG-AC-6 The docs check passes on the scaffold's output, and fails with `docs-drift` on each of: a unit without a spec, a missing criterion id, an unknown id, a changed text.
- [ ] PKG-AC-8 A package whose plugin name lacks the `-tgraph` suffix (or carries `.tgflow`, `-tg-graph`) fails to load with `plugin-name-suffix`; each workflow name rule of §2.2.1 has a fixture; `run <workflow>-tgraph` starts the same workflow as `run <workflow>`; the scaffold writes `<name>-tgraph` (PKG-B10).
- [ ] PKG-AC-7 The content digest changes when any of `outcome.json`, a prompt, a brief, a skill, an agent, a Python source or `pyproject.toml` dependencies changes, and not when only `docs/`, `diagram/`, `evals/`, `authoring.json` or `README.md` changes.

## Open questions

| Question | Owner | Release 1 default |
|---|---|---|
| Should a workflow plugin's `dependencies` pin a `tempergraph` plugin range? Left to [VER](61-version-metadata.spec.md)'s open question on the plugin dependency range. | Owner | No: the scaffold writes the bare name |
| May a workflow ship a skill meant for the **person** (for example "start a release-notes run"), invoked in the person's own session rather than a step? A skill no step declares is never loaded into a step, and the run driver stays the engine's. | Owner | Yes |

## References

