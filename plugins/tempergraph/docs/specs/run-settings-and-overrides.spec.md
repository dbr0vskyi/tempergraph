# Run settings and overrides

## Purpose

Every value that decides how much a run may spend, how long it may take, how often it may repeat, which executor and model do the work, and which workflow-declared switch is taken is a run setting: a key in one engine catalog, set at a scope (the run, all steps, all judges, one unit, one judge, one council member, chair or contest slot, one script) on one of fixed layers, from a flag to a machine default. The engine resolves every key alike, validates every override before spend, snapshots the result on the thread, reapplies it on resume, and records each value with its source ([ADR `one-catalog-of-run-settings-over-fixed-layers`](../adr/one-catalog-of-run-settings-over-fixed-layers.adr.md), [ADR `threads-snapshot-settings-and-reapply-them-on-resume`](../adr/threads-snapshot-settings-and-reapply-them-on-resume.adr.md), [research `config-overrides-and-reruns-gaps`](../research/config-overrides-and-reruns-gaps.rsrch.md)). What verifies the work is not a setting: criteria, checks, the presence of a judge, the judge's independence, flow targets, back targets and prompts cannot be overridden ([ADR `overrides-never-change-what-verifies-the-work`](../adr/overrides-never-change-what-verifies-the-work.adr.md)). Declared tools are the one part of a step a person may widen for a run, by a recorded tool grant, instead of editing the package ([ADR `a-person-may-grant-a-step-tools-for-a-run`](../adr/a-person-may-grant-a-step-tools-for-a-run.adr.md)). The model and timeout orders of [CON](contracts.spec.md) and [BUD](budgets-and-failures.spec.md) are instances of this spec's order. Operators, the CLI ([ROP](run-options.spec.md)), reruns ([RRN](reruns-and-feedback.spec.md)), orchestration, schedules and the improvement loop depend on it; design notes are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### RST-B16 One resolver

WHEN `run --check`, `run`, `resume`, `rerun`, `config show`, `orchestrate validate` or the batch parent needs settings THE engine SHALL call the same two pure, model-free functions, `resolve(spec, options, files) -> ResolvedSettings` and `validate_overrides(spec, options, files) -> list[Finding]`, over the shared types `SettingKey` (`<scope>.<name>` from the catalog), `SettingDecl`, `RunOptions` (`settings`, the snapshot of layer to key to `{value, ref, via?}` for the flag, profile and file layers; `profiles` in the order given; the non-setting options `alias`, `label`, `parent`, `schedule`, `origin`, `pause_before` and `dry_run`; `caller`, the `Caller` of the call that started or resumed the thread, classified per call and never snapshot, [PRV](caller-provenance.spec.md); and `rerun_of`, `{thread, unit, checkpoint_id, workflow_version}` or null), `ResolvedSettings` (`rows` per session scope and key with value, winning layer, `ref` and shadowed layers; `digest`, SHA-256 of the canonical table with `text` values entering as their digests) and `UnitRef` (`<unit>`, `<unit>.<item>` or `<unit>/<child unit>`).

- GIVEN `config show` and `run --check` with the same options WHEN both resolve THEN they call the same `resolve`

### RST-B17 Keys and scopes

WHEN a key `<scope>.<name>` is read THE engine SHALL take the scope as `run` (the run as a whole), `steps` (every step-side session: steps, council members and chair, contest slots), `judges` (every judge session, the audit judge's binding only through `run.audit_executor`), `<unit>` (one unit of any kind, `<unit>/<child unit>` inside a sub-workflow, one `/` per level), `judge:<unit>`, `<unit>.member:<name>`, `<unit>.chair` or `<unit>.slot:<name>` ([CNL](council-unit.spec.md), [CTS](contest-unit.spec.md)), `<unit>.before:<n>` or `<unit>.after:<n>` (a hybrid step's n-th script from 1, [SCR](script-units-and-hybrid-steps.spec.md)), or `settings` (`settings.<name>`), a map item sharing its unit's settings with a per-item model staying the item function ([MAP](map-unit.spec.md)); and keep as flags only, never settings, `--alias`, `--label`, `--parent`, `--as-agent`, `--pause-before` and `--dry-run` ([ROP](run-options.spec.md)), the legacy flags being spellings of `--set`.

- GIVEN `--set plan.member:a.model=large` where `plan` is not a council WHEN validated THEN it is refused `setting_not_for_kind`

### RST-B18 Session keys

WHEN a session's settings are resolved THE catalog SHALL hold `executor` (steps, judges, unit, judge, member, chair, slot; a registered executor; default the workflow's `default_executor`; a judge's must still declare `restricts_judge_tools`, [EXI](executor-interface.spec.md)), `model` (steps, unit, member, chair, slot: one alias, default `inherit`, a list refused, [LAD](effort-ladder-and-model-escalation.spec.md); judges, judge: an alias by the judge chain of [CON-B3](contracts.spec.md)), `loop_model` (run; default `medium`; the loop's own sessions, [SIL-B17](self-improvement.spec.md)), `loop_effort` (run; `low`, `medium`, `high`, `xhigh` or `max`; default `max`; the effort of those sessions, [SIL-B17](self-improvement.spec.md)), `subagent_model` (steps, unit; default the session's alias; a warning on executors that host no subagents), `effort` (every session scope; `low`, `medium`, `high`, `xhigh` or `max`; none; unapplied warns, [CON-B3](contracts.spec.md); pins an effort ladder), `session_cost_cap_usd` (every session scope, float above 0, `SessionOptions.cost_cap_usd`), `turn_cap` (every session scope, 1 to 500), `fallback_alias` (steps, unit, member, chair, slot; never a judge), `timeout_s` (every session and script scope, 1 to 86,400, default 600) and `idle_s` (every session scope, 30 to `timeout_s`, default off).

- GIVEN `--set judge:code.fallback_alias=small` WHEN validated THEN it is refused `setting_not_for_kind`

### RST-B19 Gate and unit keys

WHEN a unit's limits are resolved THE catalog SHALL hold `retry_budget` (steps, unit; 0 to 10; default 2 per visit, [BUD](budgets-and-failures.spec.md)), `loop_budget` (steps, unit; 0 to 5; default 1 per unit and target), `on_budget_spent` (steps, unit; `stop`, `ask` or `fallback` only where the gate declares a fallback target, else `no_fallback_target`; default the gate's), `attempt_cost_cap_usd` (council or contest unit; float above 0; default the unit's `cost_cap_usd`, per attempt), `concurrency` (contest unit; 1 to 5; default 3), `arm` (switch unit; a declared arm; default the switch function's pick; replaces `--arm` and is recorded in the `route` record), `deadline_s` (wait or ask unit; above 0; default the unit's, [FLX-B8](flow-extensions.spec.md)) and `approve` (unit; tighten-only `true`; default the gate's `approval`, adding a sign-off and never removing one).

- GIVEN `--set plan.deadline_s=60` where `plan` is a step WHEN validated THEN it is refused with its own finding code

### RST-B20 Run keys

WHEN a run's limits are resolved THE catalog SHALL hold at scope `run` `infra_tries` (0 to 10, default 3 in a row), `infra_backoff_max_s` (10 to 300, default 300, backoff doubling from 10 s), `attempt_cap` (1 to 100, default 15 attempts counted per invocation, [CMP-B19](compiler-and-flow.spec.md)), `self_check_limit` (1 to 10, default 3 previews per attempt, [CHK-B17](check-contract-and-command-runs.spec.md)), `human_cap` (1 to 100, default 100), `run_cost_cap_usd` (above 0, default the workflow's, else none), `auto_reopen` (0 to 10, default 0), `workspace` (`auto`, `in_place` or `worktree`, default the workflow's else `auto`, `in_place` refused for a workflow with writer branches or writing items, fixed at start, [WTR](worktree-mode.spec.md)), `session_review` (`auto`, `full`, `signals` or `off`, default the workflow's else `auto`, the operator's setting lowering the workflow's and never raising it, [SRV-B13](session-review.spec.md)), `daily_cap_usd` (at least 0, default the workflow's else $50, stable mode's loop budget per UTC day, none in dev mode, [SIL-B19](self-improvement.spec.md)), `loop_autonomy` (`record`, `file`, `propose` or `trial`, default the workflow's declared level, the operator's setting lowering it and never raising it, resolved with the settings files as they are at each final exit, [PRP-B31](improvement-proposals.spec.md)), `enforce_tools` and `strict_permissions` (tighten-only `true`, default `false`), `audit_rate` (0 to 1, default 0, [JDG](judge-and-verdict.spec.md)) and `audit_executor` (a registered executor, default the gate judge's), and at scope `settings` each declared `<name>` with its declared kind and default.

- GIVEN `--set run.attempt_cap=0` WHEN validated THEN it is refused `setting_value`

### RST-B21 Worktree keys

WHEN worktree settings are resolved THE catalog SHALL hold at scope `run` `worktree.root` (`sibling`, `in_repo` or `path:<absolute>`, default `sibling`, fixed at start), `worktree.base` (`head`, `default_branch` or `ref:<name>`, default the workflow's else `head`, fixed at start), `worktree.branch_prefix` (1 to 3 ref-safe components, default `tg`, fixed at start), `worktree.cleanup` (`never` or `on_finish`, default the workflow's else `never`, changeable at resume) and `worktree.read_worktreeinclude` (bool, default `true`) ([WTR](worktree-mode.spec.md)).

- GIVEN `--set run.worktree.root=elsewhere` WHEN validated THEN it is refused `setting_value`

### RST-B22 Layers

WHEN a key is resolved THE engine SHALL resolve layer-major, the highest layer that sets the key at any scope matching the session winning and the narrowest matching scope winning inside it, over the ranks `flag` (`--set <key>=<value>` and the named flags on `run`, `resume` or `rerun`, an orchestration node's `options`, a batch's shared options and a schedule's `options` arriving here recorded with `via` `cli`, `orchestration`, `batch`, `schedule` ([SCH](schedules.spec.md)) or `rerun`), `profile` (`--profile <name>`, repeatable, a later profile winning per key), `project:overrides` and `user:overrides` (the state root's and home folder's `settings.json` `overrides` entries matching the workflow), `arm:<switch>.<arm>` (an arm's `model`, `timeout_s`, `idle_s` and `effort` for the units it names while in force, [SWM](measured-switches.spec.md)), `workflow:unit` (the unit's own field), `workflow:default` (`default_executor`, `model_profile`, `run_cost_cap_usd`, `workspace`, `worktree.base`, `worktree.cleanup`, a declared setting's default), `project:defaults`, `user:defaults` and `engine`; and SHALL never read an environment variable as a layer ([EXI-B16](executor-interface.spec.md)).

- GIVEN `steps.model=medium` in the user file and `--set steps.model=large` WHEN resolved THEN `large` wins from `flag`

### RST-B1 One order for every key

WHEN values for one key sit on several layers THE engine SHALL give each session the value of its highest layer.

- GIVEN user `defaults: {"steps.timeout_s": 900}`, project `overrides` setting `code.timeout_s` 7200, `code` declaring 3000, `review` 1800, `plan` and `triage` none, and `--set plan.timeout_s=1200` WHEN resolved THEN `plan` gets 1200 (`flag`), `code` 7200 (`project:overrides`), `review` 1800 (`workflow:unit`), `triage` 900 (`user:defaults`) and the `code` judge 600 (`engine`)

### RST-B23 Three rules that keep the guarantees

WHEN layers are resolved THE engine SHALL let no `steps` or `<unit>` key reach a judge, the one step-to-judge inheritance being that at the workflow layers a judge with no model of its own takes the step's model; let `steps` and `<unit>` values of `model` and `executor` reach a member, chair or slot only when the workflow declares none for it, running the council's diversity check on the resolved values ([CNL-B16](council-unit.spec.md)); and refuse `false` for the tighten-only keys `approve`, `enforce_tools` and `strict_permissions` at any layer (`tighten_only`).

- GIVEN a property test over random layer assignments WHEN resolved THEN no `steps` key reaches a judge and no tighten-only key ends `false`

### RST-B2 Judges apart

WHEN `steps.model` is set THE engine SHALL apply it to every step, member, chair and slot without a declared model and resolve every judge on the judge chain alone.

- GIVEN `--set steps.model=small` WHEN resolved THEN a judge with no model takes its step's declared model, never `small`

### RST-B3 Diversity kept

WHEN a unit model is set on a council THE engine SHALL leave members that declare models unchanged, and refuse the start with exit 2 naming the rule when members that declare none all take it and the diversity rule then fails.

- GIVEN members declaring `claude:opus` and `antigravity:gemini-pro` WHEN `--set review.model=small` is given THEN the members keep their models

### RST-B6 Tighten-only

WHEN a tighten-only key is set THE engine SHALL refuse `false` and apply `true`.

- GIVEN a gate declaring `approval: true` and a project file setting `code.approve=false` WHEN the run starts THEN it exits 2
- GIVEN `--set code.approve=true` on a gate without approval WHEN it runs THEN the pause is added

### RST-B24 Configuration files

WHEN the engine reads `settings.json` in the operator config folder of the state root or of the home folder ([LOS-B7](local-observability-store.spec.md)), owner-only and versioned ([CON-B14](contracts.spec.md)) THE engine SHALL read `schema_version` 1, `defaults` (key to value, layer `project:defaults` or `user:defaults`, replacing the engine default for every workflow, an entry naming a unit refused `unit_in_defaults`), `overrides` (a list of `{workflow, set}`, `workflow` a name or `*`, a named entry beating `*` per key inside a layer), `profiles` (name to key to value) and `observe` (capture and observers, read from the files only and never a run layer, [LOS-B17](local-observability-store.spec.md)); look a profile name up in the project file, then the user file, then the workflow's `profiles`, using the first found whole, never merged, an unknown name refused `unknown_profile`; and exit 2 naming a file that does not parse or has a newer major `schema_version`, `config validate` showing the line.

- GIVEN a `defaults` entry `code.timeout_s` WHEN read THEN it is refused `unit_in_defaults`

### RST-B8 Profiles

WHEN `--profile <name>` names a profile in the user file and the workflow THE engine SHALL use the file's whole, put its values on the `profile` layer and record it in `run_started.profiles` with its source.

- GIVEN the workflow's profile `cheap: {"steps.model": "small", "run.run_cost_cap_usd": 5}` and a user-file `cheap` WHEN `--profile cheap` is given THEN the user file's is used whole and `run_started.profiles` is `["cheap"]`

### RST-B25 Workflow-declared settings and profiles

WHEN a workflow declares `settings` (name to `SettingDecl`: `kind` `int`, `float`, `bool`, `choice`, `duration_s` or `text`; a required `default`; `choices` for `choice`; `min` and `max` for numbers and durations; a one-line `meaning` shown by `config show` and the catalog) and `profiles` (named bundles such as `thorough` or `cheap`), both appended to `WorkflowSpec` ([CON-B4](contracts.spec.md)) THE engine SHALL give code the resolved table in its context (`ScriptContext.settings`, the check's and route's state view) and templates the key `settings.<name>` ([VAL-B8](step-values-and-template-keys.spec.md)), never render a `text` setting into a script's argv and scrub it in every record, other kinds being checked numbers or constants ([SEC](security.spec.md)).

- GIVEN a `text` setting named in a script's `run` argv WHEN validated THEN it is refused

### RST-B7 Workflow settings

WHEN `--set settings.<name>` is given THE engine SHALL validate it against the declaration, give it to every reader and reapply it on resume.

- GIVEN `test_budget_s` (`duration_s`, default 1800, max 7200), `code_mode` (`choice` of `per_phase` or `single`), `publish` (`bool`, default true) WHEN `run --set settings.code_mode=single --set settings.test_budget_s=3600` starts THEN the switch reads `single`, the check reads 3600, the finalizer reads `publish = true`, and a resume reapplies both
- GIVEN `--set settings.code_mode=fast` WHEN validated THEN it exits 2 listing the choices

### RST-B26 Snapshot and resume

WHEN a thread starts, resumes or is rerun THE engine SHALL at start read both files once, resolve, and store the flag, profile and file layers' values in `RunOptions.settings`, the workflow layers coming from the content the thread runs; at resume reapply the snapshot, `--set` adding or replacing a flag value, `--unset <key>` removing one, `--profile` replacing the profile list looked up in the files as they are now while the file layers stay, and `--reload-settings` reading both files again, the workflow layers following the content resumed on ([MIG-B15](state-and-run-migration.spec.md)); at a rerun copy the source's snapshot and apply the rerun's own flags ([RRN](reruns-and-feedback.spec.md)); and apply a changed `retry_budget` or `loop_budget` at the next gate decision against the counter already used in the visit or pair (a lowered value at or under the count spent at the next failure), `run_cost_cap_usd` at once (a thread drained for `cost_cap` continuing when the new cap is above its cost), `timeout_s`, `idle_s`, session options and `executor` from the next session, `attempt_cap` and `infra_tries` per invocation from this one, and `arm` and `settings.<name>` from the next read, a switch already decided in the visit keeping its arm.

- GIVEN a thread paused, its files edited, and resumed without `--reload-settings` WHEN resolved THEN `settings_digest` is unchanged

### RST-B4 Raise at resume

WHEN a run stopped with its retry budget spent is resumed with a raised budget THE engine SHALL refuse it without a decision and, with `retry`, give the visit the new budget.

- GIVEN `expand` stopped with its budget of 2 spent WHEN `resume --set expand.retry_budget=4` is given without a decision THEN it exits 2 because a stopped thread needs `retry` or `back`
- GIVEN `resume --decision retry --set expand.retry_budget=4` WHEN resumed THEN the visit gets 4 and `settings_resolved.changed_keys` lists the key

### RST-B27 Effective settings record

WHEN settings are resolved for a segment THE engine SHALL write `settings_resolved` after `run_started` on start, each resume and a rerun ([EVT](run-events.spec.md)), with `settings_digest`, `rows[]` of `{key, value, layer, ref, shadowed[]}` for every key set above `engine` (`ref` the flag, the file path and entry, the profile name or the workflow field path; a `text` value replaced by its digest) and `changed_keys` since the last segment; add `settings_digest`, `profiles` and `overridden_keys` (keys whose winning layer is `flag` to `user:overrides`) to `run_started`; give each value already on `attempt_start` and `agent_run` its layer and `ref`; and add `settings_digest` and `overridden_keys` (names only) to the status, stats and ledger rows, the status row adding `settings_stale` when the files now resolve differently from the snapshot ([DUR-B11](durability-and-resume.spec.md)).

- GIVEN a `text` setting WHEN `settings_resolved` is written THEN its value appears only as a digest

### RST-B11 Shadowed values are shown

WHEN a higher layer shadows a lower one THE engine SHALL show both in `config show` and warn nothing at the start.

- GIVEN user `steps.model=medium` and `--set steps.model=large` WHEN `config show` runs THEN the row shows `large` from `flag` with `user:overrides` shadowed

### RST-B12 Overrides reach the improvement loop

WHEN self-improvement reads a run whose failing unit ran under an override THE loop SHALL carry `overridden_keys` on the finding and not file it as a workflow fault unless the same cluster also holds runs without that override ([SIL](self-improvement.spec.md)).

- GIVEN `code` failing three times on `small` from a `flag` override WHEN read THEN the finding carries `overridden_keys: [code.model]` and is not filed as a workflow fault alone

### RST-B28 Tool grants

WHEN `tools.add` (steps, unit, slot, chair: `ToolCapability` values of [CON-B11](contracts.spec.md) including `mcp:<server>/<tool>` and `skill:<plugin>:<name>`, members and the chair read-only only), `commands.add` (steps, unit, slot, `before:<n>`, `after:<n>`: command prefixes added to the step and the run's allow-list) or `views.add` (judge: read-only capabilities from the view catalog) is set THE engine SHALL take it only from the `flag` layer given by a person or a workflow's own profiles, refusing a file entry or user-file profile (`widening_in_file`), a schedule's options (`widening_in_schedule`, [SCH](schedules.spec.md)) and a caller whose decider is not a person (`widening_by_agent`; an agent relaying a person's grant needs a named person turn, [PRV](caller-provenance.spec.md)); pass a grant through the declaration's own checks with their finding codes ([WFM](workflow-model.spec.md)): the executor's `tool_map` maps it, a command prefix holds no shell metacharacter and its resolver argv is safe, an MCP server is configured on this machine (`mcp-server-not-configured`), a skill's plugin is installed and the executor hosts an authoring surface; never grant a path outside the workspace (C10), a write, edit, shell or writing MCP tool to a judge, member or chair, a judge view outside the read-only catalog (a judge takes no `mcp:` view grant, `judge-view-unclassified`, while no read-only MCP catalog exists), or anything that removes `strict_permissions` or enforcement, the judge staying on an executor that declares `restricts_judge_tools` with the guard of [GRD](independence-guard.spec.md) on the widened view; list granted tools as declared ones in the tools block ([PRM-B8](prompt-rendering.spec.md)), mark each `widening: true` in `settings_resolved` and list grants apart in the pause payload and `config show`; and keep a grant in the snapshot, reapplied on later resumes and copied into a rerun, `--unset <unit>.tools.add` removing it.

- GIVEN a user file `overrides` entry with `code.tools.add` WHEN read THEN it exits 2 `widening_in_file`

### RST-B29 Escalation for tool access

WHEN an attempt failed or ended blocked and its session recorded a `denied` event or a declared tool missing from its start tool list THE gate SHALL escalate with cause `tool_access`, spending no retry ([BUD](budgets-and-failures.spec.md)), and the pause payload ([HUM-B7](gate-and-human.spec.md)) SHALL list each refused or missing name with its refusal class ([TSA-B7](tool-surface-audit.spec.md)) and its fix: for `undeclared_tool` or a missing MCP tool or skill `resume … --decision retry --grant <unit>=<capability>`, the host step first for a server not configured or a plugin not installed; for `needed_command` `resume … --decision retry --allow-command <unit>=<prefix>`; for `shell_for_read` and `dir_change_then_command` no grant, `retry` with feedback naming the permitted form; for `outside_workspace` no grant, `retry` with feedback or `stop`; for `missing_at_start` the host step then `retry`; release 1 classifying by tool name only, a refused shell call being `unclassified`.

- GIVEN a `needed_command` refusal WHEN the pause is shown THEN it offers `--allow-command <unit>=<prefix>`

### RST-B13 Resume a run blocked on a tool

WHEN a step ends blocked on an undeclared tool THE engine SHALL escalate it with `tool_access`, offer the grant, and run the next attempt with the grant applied.

- GIVEN `triage` calling the undeclared `mcp:tracker/get_issue` and ending `BLOCKED` WHEN the gate decides THEN it escalates with `tool_access`, spends no retry and offers `--grant triage=mcp:tracker/get_issue`, and `resume --decision retry --grant …` runs with the tool and a later resume keeps it
- GIVEN the same grant and the server configured WHEN applied THEN it is recorded `widening: true`
- GIVEN the server not configured WHEN granted THEN it exits 2 `mcp-server-not-configured` and nothing is written
- GIVEN `--grant judge:triage=edit` WHEN validated THEN it exits 2, a judge taking views only
- GIVEN `--set judge:triage.views.add=mcp:tracker/get_issue` WHEN validated THEN it applies only when the catalog classifies the tool read-only
- GIVEN `--allow-command code="npm run build; rm"` WHEN validated THEN it exits 2 for a shell metacharacter

### RST-B14 A missing skill fails before spend

WHEN a step declares a skill whose plugin is not installed THE preflight SHALL exit 2 naming the plugin and the install command, no grant replacing an install.

- GIVEN `skill:review-kit:security` with the plugin not installed WHEN preflighted THEN it exits 2 naming the plugin and the install command

### RST-B30 Grants are tracked

WHEN a grant takes effect THE engine SHALL write a `grant` run-log record ([EVT](run-events.spec.md)), note it in the intervention row of the resume that gave it ([HUM-B6](gate-and-human.spec.md)) and in the ledger row's `grants[]` with whether a later attempt used it ([SIL-B12](self-improvement.spec.md), [IMD-B18](improvement-data.spec.md)), and count a grant used on a passing attempt as a `grant_missing` finding against the workflow, reported by the audit's history layer as `granted-at-run` ([TSA-B9](tool-surface-audit.spec.md)) and drafted by the improvement loop as a `tools` proposal that declares it ([PRP-B14](improvement-proposals.spec.md)).

- GIVEN a grant used on a passing attempt WHEN the ledger row is written THEN `grants[]` marks it used and a `grant_missing` finding is recorded

### RST-B15 Grants feed the loop

WHEN several runs needed the same grant and passed with it THE loop SHALL cluster the findings into one workflow issue whose remedy is the declaration and, at `propose` autonomy, draft a pull request that declares it.

- GIVEN five runs on two machines granting `triage` `mcp:tracker/get_issue`, each next attempt passing WHEN self-improvement reads them THEN one cluster, one issue and one draft pull request adding the tool name the five runs

### RST-B31 The config verb

WHEN `config show <workflow> [--thread <t>] [--set …] [--profile …] [--key <glob>] [--json]`, `config validate [--file <path>]` or `config paths` runs THE engine SHALL print the resolved table for a start with these options or for the thread's next resume (value, winning layer and `ref`, shadowed layers, findings); validate both files or one against the catalog and every registered workflow they name; or print the two file paths and whether each exists; writing nothing and spending nothing, the files being edited by hand or by a skill.

- GIVEN `config paths` WHEN run THEN it prints both paths and writes nothing

### RST-B9 Show equals run

WHEN `config show` and `run --check` run with the same options THE engine SHALL print in `config show` the table the run then writes as `settings_resolved` rows.

- GIVEN a corpus of workflows and options WHEN both run THEN the tables are equal

### RST-B32 Refusals before spend

WHEN an override is validated THE engine SHALL exit 2 before any file is created under the state root with `unknown_setting` and the nearest name for an unknown key, scope or setting; `setting_not_for_kind` for a key not valid for the scope's unit kind; `setting_value` for a value outside type or range or an undeclared choice; `not_a_setting`, naming [ADR `overrides-never-change-what-verifies-the-work`](../adr/overrides-never-change-what-verifies-the-work.adr.md), for a key of the verification surface; and `setting_not_in_release` for a key whose feature is not in this release (the council, wait and ask keys); and SHALL record as a warning a setting the executor cannot apply (`effort`, [CON-B3](contracts.spec.md)).

- GIVEN an unknown key WHEN validated THEN nothing is created under the state root (hash test)

### RST-B5 Not a setting

WHEN an override names what verifies the work THE engine SHALL refuse it with `not_a_setting` and create nothing.

- GIVEN `--set code.criteria=…`, `--set judge:code.tools=edit` or `--set code.prompt=…` WHEN validated THEN each exits 2 `not_a_setting`

### RST-B10 Misaimed override

WHEN an override names a unit that does not exist or a scope its unit lacks THE engine SHALL refuse it with its own finding code and, for an unknown name, the nearest declared one.

- GIVEN `--set plann.model=large` on a workflow with a unit `plan` WHEN validated THEN it exits 2 naming `plan`

## Acceptance criteria

- RST-AC1 (RST-B17, RST-B18, RST-B19, RST-B20, RST-B21, RST-B22, RST-B1): Every catalog key has a fixture that resolves it from each layer and records the winning layer and `ref`
- RST-AC2 (RST-B32, RST-B5, RST-B10, RST-B24): Every refusal has a fixture refused before any file is created under the state root (hash test)
- RST-AC3 (RST-B23, RST-B2, RST-B3, RST-B6): A property test over random layer assignments finds no case where a `steps` or `<unit>` key reaches a judge, or where a tighten-only key ends `false`
- RST-AC4 (RST-B9, RST-B16, RST-B31, RST-B11): `config show` output equals the run's `settings_resolved` rows on a corpus of workflows and options
- RST-AC5 (RST-B26, RST-B27): A thread started, paused, its files edited, and resumed without `--reload-settings` resolves the same `settings_digest`; with it, the digest and `changed_keys` reflect the edit
- RST-AC6 (RST-B26, RST-B4): Every counter rule of RST-B26 is tested on resume
- RST-AC7 (RST-B25, RST-B7, RST-B8): No `text` setting value appears in argv, a ledger row, a stats row or a finding (canary test, [SEC-B2](security.spec.md))
- RST-AC8 (RST-B28, RST-B29, RST-B13, RST-B14, RST-B30, RST-B15, RST-B12): Every scenario of RST-B13 holds, and a property test finds no grant that gives a judge, member or chair a non-read-only tool

## Open questions

- Should a team be able to commit a shared settings file in the repository (a third file layer), with cost caps limited to lowering? Until answered: no. Owner: owner.
- Should an organisation be able to impose a managed layer above `flag` (hard ceilings), as Claude Code's managed settings do? Until answered: no. Owner: owner.
