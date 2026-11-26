# Shared contracts

## Purpose

The workflow declaration every workflow package writes and the engine reads ([ADR `workflows-as-data`](../adr/workflows-as-data.adr.md)), the template grammar, input and routing declarations, model aliases, tool capabilities, the run and thread values and exit codes every caller reads, and the rules every persisted document follows. Workflow authors, the builders of `tempergraph.api`, every component spec and every caller of the CLI depend on these exact names. What a session request, result and judgement hold is [25 Session contract](session-contract.spec.md). Neutral tool and model names keep a workflow portable across executors at the cost of one mapping table per executor ([ADR `executors-as-capability-adapters`](../adr/executors-as-capability-adapters.adr.md), [ADR `portable-model-aliases`](../adr/portable-model-aliases.adr.md)).

## Depends on

- `ask-unit.spec.md`: answering (ASK-B8)
- `budgets-and-failures.spec.md`: budgets, failures and timeouts
- `central-run-stats.spec.md`: central run stats
- `check-contract-and-command-runs.spec.md`: mechanical failure costs no judge (CHK-B1); the check preview (CHK-B17)
- `compiler-and-flow.spec.md`: order and routes (CMP-B10); step-node forms (CMP-B16)
- `contest-unit.spec.md`: contest unit
- `council-unit.spec.md`: council unit
- `durability-and-resume.spec.md`: durability and resume
- `effort-ladder-and-model-escalation.spec.md`: effort ladder and one-step model escalation
- `engine-cli.spec.md`: engine cli
- `engine-update.spec.md`: engine install and update
- `feedback-and-judge-reliability.spec.md`: feedback labels and judge reliability
- `finalizer-contract.spec.md`: what it returns (FIN-B8)
- `flow-extensions.spec.md`: fallback target (FLX-B9)
- `improvement-proposals.spec.md`: improvement proposals and trials
- `local-observability-store.spec.md`: local observability store
- `map-unit.spec.md`: map unit
- `observability-and-cost.spec.md`: observability and cost
- `prompt-rendering.spec.md`: sections and their order (PRM-B6)
- `reruns-and-feedback.spec.md`: rewind (RRN-B16)
- `run-detail-document.spec.md`: run detail document
- `run-outcome.spec.md`: trust (OUT-B13); coverage (OUT-B14)
- `run-settings-and-overrides.spec.md`: session keys (RST-B18); gate and unit keys (RST-B19); run keys (RST-B20); worktree keys (RST-B21); layers (RST-B22); three rules that keep the guarantees (RST-B23); workflow-declared settings and profiles (RST-B25)
- `script-units-and-hybrid-steps.spec.md`: script units and hybrid steps
- `self-improvement.spec.md`: code host unreachable (SIL-B19); daily cap (SIL-B20)
- `session-contract.spec.md`: session contract
- `session-review.spec.md`: review setting (SRV-B13); probation and trials (SRV-B14); plan record (SRV-B15)
- `state-and-run-migration.spec.md`: state and run migration across releases
- `step-values-and-template-keys.spec.md`: the value artifact kind (VAL-B5); storing a value (VAL-B6); template keys (VAL-B8)
- `subworkflow-unit.spec.md`: a child's key in a template (SWF-B12)
- `version-metadata.spec.md`: range selection and compatibility states (VER-B2); never refuses on its own (VER-B5); workflow version fields (VER-B14); digests and the workflow version id (VER-B15)
- `workflow-audit.spec.md`: workflow audit
- `workflow-lessons.spec.md`: workflow lessons
- `workflow-model.spec.md`: structure and flow refusals (WFM-B8); executor, judge, tool and prompt refusals (WFM-B9); settings, routing and release refusals (WFM-B10); refusals owned elsewhere (WFM-B11)
- `workflow-package.spec.md`: layout (PKG-B11); refused plugin parts (PKG-B12)
- `workflow-upgrade.spec.md`: workflow upgrade
- `worktree-mode.spec.md`: resolving auto (WTR-B18); workflow declaration (WTR-B19)

## Behaviours

### CON-B4 Workflow fields

WHEN a workflow is loaded THE engine SHALL read these fields of `WorkflowSpec`: `name` (a slug unique in the manifest), `order` (the default forward order of unit names), `units` (name to `UnitSpec`), `flow` (unit to `FlowSpec`, where a pass goes when not next in `order`), `input` (CON-B8), `workspace` (`auto`, `in_place` or `worktree`, default `auto`, [WTR-B18](worktree-mode.spec.md)), `worktree` (include patterns, setup commands and submodules, [WTR-B19](worktree-mode.spec.md)), `finalizer` and `finalizer_outcomes` (required with a finalizer, [FIN-B8](finalizer-contract.spec.md)), `default_executor`, `model_profile` (CON-B3), `issue_repository` (`owner/name`, required), `routing` (CON-B9), `improvement_mode` (`dev` or `stable`), `daily_cap_usd` ([SIL-B19, SIL-B20](self-improvement.spec.md)), `session_review` (`auto`, `full`, `signals` or `off`, [SRV-B13, SRV-B14, SRV-B15](session-review.spec.md)), `verified_engine`, `command_resolver` ([WFM](workflow-model.spec.md)), `run_cost_cap_usd` ([BUD](budgets-and-failures.spec.md)), `version` (semver, default `0.0.0`, [VER-B14, VER-B15](version-metadata.spec.md)), `requires_engine` (a range that only warns, [VER-B2, VER-B5](version-metadata.spec.md)), `upgrade` ([VER-B14, VER-B15](version-metadata.spec.md)), `settings` and `profiles` ([RST-B25](run-settings-and-overrides.spec.md)), `outcome` (read from `outcome.json` at load, [OUT](run-outcome.spec.md)), `allow_commands` (the workflow-wide allow-list, [WFM-B8, WFM-B9, WFM-B10, WFM-B11](workflow-model.spec.md)), and the engine-set `builtin` and `package_root`.

- GIVEN a workflow with no `issue_repository` WHEN it is loaded THEN validation fails
- GIVEN a workflow with no `version` WHEN its `workflow_version` is formed THEN it uses `0.0.0` with the content digest
- GIVEN a `finalizer` with no `finalizer_outcomes` WHEN it is loaded THEN validation fails

### CON-B5 Unit fields

WHEN a unit is declared THE engine SHALL read `kind` (`step`, `route`, `switch`, `parallel`, `map`, `subworkflow`, `wait`, `script`, `council`, `contest` or `ask`; owners [CMP-B10 to CMP-B16](compiler-and-flow.spec.md), [FLX](flow-extensions.spec.md), [SCR](script-units-and-hybrid-steps.spec.md), [CNL](council-unit.spec.md), [CTS](contest-unit.spec.md), [ASK](ask-unit.spec.md), [MAP](map-unit.spec.md)), `step` (for `step`, `map` and `contest`), the kind's own spec field (`script`, `council`, `contest`, `ask`, `map`), `gate` (required for every kind), and `route`, `route_targets` or `switch` (`predicate`, `arms`, `default`, `sticky`).

- GIVEN a unit of kind `wait` WHEN its gate declares a judge THEN validation fails, because a `wait` or `ask` gate holds only checks
- GIVEN a `script` unit WHEN its gate is read THEN it holds the built-in check and an optional judge
- GIVEN a `route` unit with an empty gate WHEN it is loaded THEN it is valid

### CON-B6 Step fields

WHEN a step is declared THE engine SHALL read `executor` (falling back to `default_executor`), `prompt` (inline text, a file ref or `default`, [PRM-B6](prompt-rendering.spec.md)), `tools` (CON-B11), `commands` (prefixes within the allow-list), `produces` (key to artifact kind: `file`, `url`, `wiki_page`, `tracker_issue`, `pull_request` or `value`, a one-line value with optional `choices` and `pattern`, [VAL-B5, VAL-B6](step-values-and-template-keys.spec.md)), `model` (one alias or an item function ref, [LAD](effort-ladder-and-model-escalation.spec.md)), `timeout_s` and `idle_s` (positive ints), `session_options` ([SSN](session-contract.spec.md)), `before` and `after` (model-free scripts around the session, [SCR](script-units-and-hybrid-steps.spec.md)), `self_check` (default false, [CHK-B17](check-contract-and-command-runs.spec.md)), `summary` (at most 60 characters, for diagrams) and `subagent_model` ([RST-B18, RST-B19, RST-B20, RST-B21](run-settings-and-overrides.spec.md)).

- GIVEN a step with no `executor` WHEN it is bound THEN it runs on the workflow's `default_executor`
- GIVEN `produces: {verdict: value}` with `choices: [yes, no]` WHEN the step writes `maybe` THEN the output check fails

### CON-B7 Gate, judge and criterion fields

WHEN a gate is declared THE engine SHALL read `check` (a model-free callable that writes no state, `(ctx: CheckContext) -> CheckResult`, [CHK](check-contract-and-command-runs.spec.md)), `check_timeout_s` (default 1800), `judge` (required on model steps), `criteria` (at least one when a judge is present, filled from the unit's intermediate outcome, [OUT-B13, OUT-B14](run-outcome.spec.md)), `on_fail` (`retry`, `stop`, `fallback` or `back`, [HUM-B15](gate-and-human.spec.md)), `on_budget_spent` (`stop`, `ask` or `fallback`), `fallback` ([FLX-B9](flow-extensions.spec.md)), `approval`, `back_targets`, `loop_budget` (default 1) and `retry_budget` (default 2); a judge's `stance`, `brief`, `references` (each `required` or `optional`), `subject`, `executor`, `model`, `timeout_s`, `idle_s`, `session_options` and `tools` (which may only narrow the derived views); and a criterion's `text`, `check_method` (shown to the judge only), `severity` (`blocker` or `warning`), `id`, `unverified_system`, `no_change_policy` (`escalate` or `retry`, default `escalate`) and `mechanical` (default false: when true the check verifies it, a check FAIL costs no judge and the judge takes the check's finding as given, [CHK-B1, B2](check-contract-and-command-runs.spec.md)).

- GIVEN a model step whose gate has no judge WHEN it is validated THEN it fails
- GIVEN a gate with no `retry_budget` WHEN it retries THEN it allows 2 retries per visit
- GIVEN a judge whose `tools` add a capability the derived view set lacks WHEN it is validated THEN it fails

### CON-B8 Template grammar

WHEN a template is validated THE engine SHALL accept only literal text, `{{` and `}}` for literal braces, and plain fields `{name}` naming a key of [VAL-B8](step-values-and-template-keys.spec.md), `settings.<name>` for a declared setting ([RST-B25](run-settings-and-overrides.spec.md)) or `<unit>.<key>` for a key a sub-workflow unit exposes ([SWF-B12](subworkflow-unit.spec.md)), and refuse any other text between braces with exit 2.

- GIVEN `{task_id}` WHEN rendered THEN the run's task id replaces it
- GIVEN `{a.b()}` WHEN the workflow is validated THEN it is invalid and the command exits 2
- GIVEN a field with no value at run time WHEN rendered THEN it renders as `⟨missing:name⟩` and the step record lists it

### CON-B9 Input and routing declarations

WHEN a workflow declares how a run starts THE engine SHALL read `input` with `kind` (`any`, `tracker_key`, `file`, `text` or `resolver`), `parameters` (each `{name, meaning, example, when_asked}`), `examples` (2 to 3 whole requests that must resolve), `prerequisites` (shown, never checked) and `resolver` (read-only, model-free, returning `status` `ok`, `needs` or `error`, a stable `task_id` that names the thread, branch, log and lock, and on `needs` its `questions` as `{name, question, choices?}`), and `routing` with `description` (one line starting with a verb), `when_to_use` (2 to 4 sentences ending in "Not for: …") and `task_kind` (`ticket`, `prompt`, `symptom`, `repository` or `findings`).

- GIVEN an example request that does not resolve WHEN the workflow is validated THEN it fails
- GIVEN a resolver that answers `needs` WHEN `run --check` runs THEN it prints the resolver's questions with their choices

### CON-B3 Model aliases and their resolution

WHEN a step or judge model is resolved THE engine SHALL accept only `inherit`, a tier `small`, `medium` or `large`, or an executor-qualified alias `<executor>:<name>` (never a deployment id), take a `model_profile` entry per step name and per `judge:<step name>`, resolve a step attempt by the operator layers of [RST-B22, RST-B23](run-settings-and-overrides.spec.md), an arm in force that names the step, the step's model, the workflow default, project and user defaults, then `inherit`, resolve a judge by the same operator layers on judge scopes only (`judge:<unit>`, then `judges`), the gate's judge model, the step's model, the workflow default, project and user defaults, then `inherit`, and record the alias, its source layer and the executor that bound it.

- GIVEN a step with model `large` on executor `antigravity` WHEN the alias is resolved THEN the executor's binding table maps `large` to its configured slug and the record shows `alias=large, bound_by=antigravity`
- GIVEN an alias no executor binds WHEN the run is preflighted THEN it exits 2 before spend
- GIVEN `--judge-model small` and a gate judge model `medium` WHEN the judge is resolved THEN it runs on `small` with source `flag`

### CON-B11 Tool capabilities

WHEN workflow data declares tools THE engine SHALL take only the capability names `read`, `search`, `list`, `web_fetch` and `web_search` (read-only), `edit`, `write` and `shell` (a declared command prefix), `subagent` (inheriting its caller's restriction), `mcp:<server>/<tool>` (classified by the engine catalog, never by name pattern) and `skill:<plugin>:<name>` (adds no tool of its own, [ADR `skills-are-a-declared-tool-capability`](../adr/skills-are-a-declared-tool-capability.adr.md)), and map each name to an executor's tools by that executor's `tool_map`, the view catalog being keyed by executor and tool name.

- GIVEN a step that declares `edit` on an executor whose `tool_map` lacks it WHEN the run is preflighted THEN it exits 2 before spend
- GIVEN a workflow that names only neutral aliases and `read`, `search`, `list`, `edit`, `write` and `shell` WHEN it is validated against each executor THEN it is valid on all four

### CON-B12 Thread states and decisions

WHEN a thread's state or a person's decision is written THE engine SHALL use only the thread states `none`, `running` (lock held), `paused`, `unfinished`, `stopped` and `finished`, the decisions `proceed`, `retry`, `back:<unit>`, `rewind:<unit>` ([RRN-B16](reruns-and-feedback.spec.md)), `stop`, `event:<name>=<value>` and `answer:<name>=<value>` ([ASK-B8](ask-unit.spec.md)), and the thread id `<workflow>/<task_id>`.

- GIVEN a thread whose state is not `none` WHEN a fresh `run` names it THEN the run is refused with exit 2 ([ADR `exit-codes-as-caller-contract`](../adr/exit-codes-as-caller-contract.adr.md))
- GIVEN `resume --decision rewind:plan` WHEN `plan` is a completed unit THEN the thread rewinds to it

### CON-B13 Exit codes

WHEN the engine CLI exits THE engine CLI SHALL exit with `0` finished, `1` internal error, `2` usage or preflight refusal with nothing spent or created, `3` paused for a person, `4` stopped, `5` budget spent or infra failure, `6` an advisory verb found issues (`audit --fail-on`, [AUD](workflow-audit.spec.md)), or `127` engine not installed (the shim).

- GIVEN a run that pauses at an approval WHEN the process ends THEN it exits 3
- GIVEN a run whose infra tries are spent WHEN it ends THEN it exits 5

### CON-B14 Persisted documents are versioned

WHEN the engine writes a persisted document THE engine SHALL write its schema version: the run log as JSON lines with a `schema` key on the first line ([OBS](observability-and-cost.spec.md)); and `schema_version` in the status document ([DUR](durability-and-resume.spec.md)), the catalog ([CLI](engine-cli.spec.md)), the detail document ([RDD](run-detail-document.spec.md)), the store manifest and machine index ([LOS](local-observability-store.spec.md), [CST](central-run-stats.spec.md)), every sink row, proposals, trials and case sets ([PRP](improvement-proposals.spec.md)), the lessons file ([LSN](workflow-lessons.spec.md)), the audit report ([AUD](workflow-audit.spec.md)), the engine release record, changelog, stamp record and change notes ([VER](version-metadata.spec.md)), the engine pointers and workflow registry ([UPD](engine-update.spec.md)), the thread engine file ([MIG](state-and-run-migration.spec.md)), upgrade plans, baselines and reports ([WUP](workflow-upgrade.spec.md)), settings files ([RST](run-settings-and-overrides.spec.md)), rerun lineage ([RRN](reruns-and-feedback.spec.md)) and the package files `tempergraph.json`, `outcome.json`, `authoring.json` and `blueprint.json` ([PKG-B11, PKG-B12](workflow-package.spec.md)).

- GIVEN any persisted document of that list WHEN it is written THEN its schema version is present
- GIVEN findings, the ledger and labels ([SIL](self-improvement.spec.md), [FBK](feedback-and-judge-reliability.spec.md)) WHEN they are written THEN they hold metadata only: names, counts and hashes

### CON-B1 Tolerant read

WHEN a reader meets an unknown key or record kind THE reader SHALL ignore it, and read a missing key as "not recorded", never as zero.

- GIVEN a run log line with an unknown event kind WHEN the analyzer reads it THEN it skips the line and counts it under `unknown_kinds`
- GIVEN a status row with no `cost` key WHEN a report reads it THEN the cost is shown as not recorded, not as 0

### CON-B15 A newer major schema is refused

WHEN a reader meets a document with a newer major schema version THE reader SHALL exit with its own refusal and write nothing; renaming, removing or reinterpreting a key bumps the schema version.

- GIVEN a status document of schema version 3 and a reader of version 2 WHEN it is read THEN the reader refuses and the state root is unchanged

## Acceptance criteria

- CON-AC1 (CON-B4, CON-B5, CON-B6, CON-B7): Every field these behaviours name is accepted by the builders of `tempergraph.api`, and a field outside them is refused at load
- CON-AC2 (CON-B8): A rendered template contains no unrendered field, and a missing value renders as the marker and is recorded
- CON-AC3 (CON-B1): No persisted document records unknown usage as 0
- CON-AC4 (CON-B14, CON-B1, CON-B15): Every persisted document carries a schema version, its readers pass a test with an unknown key and an unknown record kind, and a newer major version is refused
- CON-AC5 (CON-B3, CON-B11): A workflow that names only neutral aliases and the capabilities `read`, `search`, `list`, `edit`, `write` and `shell` validates against all four executors' binding and tool tables
- CON-AC6 (CON-B13): The exit codes in CON-B13 equal the engine's constants, checked by a drift test
- CON-AC7 (CON-B9): A workflow whose input examples do not resolve fails validation, and a `needs` answer carries its questions
- CON-AC8 (CON-B12): A fresh `run` on a thread not in state `none` exits 2, and every recorded state and decision is one CON-B12 names
