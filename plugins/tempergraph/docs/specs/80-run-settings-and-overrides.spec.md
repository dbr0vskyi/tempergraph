---
title: Run settings and overrides
type: component
status: ready-for-implementation
prefix: RST
adrs: [0070, 0071, 0072, 0080, 0008]
---

# Run settings and overrides

## 1. Overview

Every value that decides how much a run may spend, how long it may take, how often it may repeat, which executor and model do the work, and which workflow-declared switch is taken is a **run setting**: a key in one engine catalog (§2.2), set at a **scope** (the run, all steps, all judges, one unit, one judge, one council member, chair or contest slot, one script) on one of a fixed list of **layers** (§2.3), from a flag to a machine-wide default. The engine resolves every key the same way, validates every override before spend, snapshots the result on the thread, reapplies it on resume, and records each value with its source ([ADR-0070](../adr/0070-one-catalog-of-run-settings-over-fixed-layers.adr.md), [R-070](../research/R-070-config-overrides-and-reruns-gaps.rsrch.md)).

What verifies the work is not a setting: criteria, checks, the presence of a judge, the judge's independence, flow targets, back targets and prompts cannot be overridden ([ADR-0071](../adr/0071-overrides-never-change-what-verifies-the-work.adr.md)). Declared tools are the one part of a step a person may widen for a run, by a recorded **tool grant** (§2.9): a step that failed or paused because it could not reach a tool, a skill, an MCP server or a command is resumed with the grant instead of an edit of the package ([ADR-0080](../adr/0080-a-person-may-grant-a-step-tools-for-a-run.adr.md)). The model and timeout orders of [CON §2.4](01-contracts.spec.md) and [BUD §2.1](08-budgets-and-failures.spec.md) are instances of this spec's order.

## 2. Contract

```python
def resolve(spec: WorkflowSpec, options: RunOptions, files: ConfigFiles) -> ResolvedSettings: ...   # pure, model-free
def validate_overrides(spec: WorkflowSpec, options: RunOptions, files: ConfigFiles) -> list[Finding]: ...
```

`RunOptions`, `SettingKey`, `SettingValue` and `ResolvedSettings` are defined in [CON §2.12](01-contracts.spec.md). `run --check`, `run`, `resume`, `rerun` ([RRN](81-reruns-and-feedback.spec.md)), `config show`, `orchestrate validate` and the batch parent call these same two functions.

### 2.1 Keys and scopes

A key is `<scope>.<name>`. Scopes, narrowest last in each group:

| Scope | Addresses |
|---|---|
| `run` | Values of the run as a whole |
| `steps` | Every step-side session: steps, council members and chair, contest slots |
| `judges` | Every judge session, including the audit judge's binding only through `run.audit_executor` |
| `<unit>` | One unit of any kind; `<unit>/<child unit>` inside a sub-workflow (repeat `/` per level) |
| `judge:<unit>` | That unit's judge |
| `<unit>.member:<name>`, `<unit>.chair`, `<unit>.slot:<name>` | A council member, the chair, a contest slot ([CNL](71-council-unit.spec.md), [CTS](72-contest-unit.spec.md)) |
| `<unit>.before:<n>`, `<unit>.after:<n>` | A hybrid step's n-th script, from 1 ([SCR](70-script-units-and-hybrid-steps.spec.md)) |
| `settings` | Workflow-declared settings (§2.5): `settings.<name>` |

A map item has no scope of its own: items share their unit's settings, and a per-item model stays the item function of [CON §2.1](01-contracts.spec.md).

### 2.2 Catalog

| Name | Scopes | Value | Engine default | Notes |
|---|---|---|---|---|
| `executor` | steps, judges, unit, judge, member, chair, slot | registered executor | workflow `default_executor` | A judge's still must declare `restricts_judge_tools` ([EXI](10-executor-interface.spec.md)) |
| `model` | steps, unit, member, chair, slot | alias, or a ladder of 1–8 aliases on steps and unit | `inherit` | Judges, members, chair and slots take one alias |
| `model` | judges, judge | alias | per CON §2.4 | Never a ladder |
| `subagent_model` | steps, unit | alias | the session's own alias | Only on executors that host subagents; elsewhere a warning |
| `effort` | every session scope | `low` \| `medium` \| `high` \| `max` | none | Unapplied is a warning (CON §4) |
| `session_cost_cap_usd` | every session scope | float > 0 | none | `SessionOptions.cost_cap_usd` |
| `turn_cap` | every session scope | int 1–500 | none | |
| `fallback_alias` | steps, unit, member, chair, slot | alias | none | Never on a judge |
| `timeout_s` | every session scope, script scopes | int 1–86 400 | 600 | Script default 600 ([SCR §2.1](70-script-units-and-hybrid-steps.spec.md)) |
| `idle_s` | every session scope | int 30–`timeout_s` | none (off) | |
| `retry_budget` | steps, unit | int 0–10 | 2 | Per visit ([BUD](08-budgets-and-failures.spec.md)) |
| `loop_budget` | steps, unit | int 0–5 | 1 | Per (unit, target) |
| `on_budget_spent` | steps, unit | `stop` \| `ask` \| `fallback` | gate's | `fallback` only where the gate declares a `fallback` target |
| `attempt_cost_cap_usd` | council or contest unit | float > 0 | the unit's `cost_cap_usd` | Per attempt |
| `concurrency` | contest unit | int 1–5 | 3 | |
| `arm` | switch unit | a declared arm | the switch function's pick | Replaces `--arm`; recorded in the `route` record |
| `deadline_s` | wait or ask unit | int > 0 | the unit's | [FLX §2.3](74-flow-extensions.spec.md) |
| `approve` | unit | `true` | the gate's `approval` | Tighten-only: adds a sign-off, never removes one the workflow declares |
| `infra_tries` | run | int 0–10 | 3 | In a row |
| `infra_backoff_max_s` | run | int 10–300 | 300 | Backoff doubles from 10 s up to this |
| `attempt_cap` | run | int 1–100 | 15 | Per invocation |
| `human_cap` | run | int 1–100 | 100 | |
| `run_cost_cap_usd` | run | float > 0 | workflow's, else none | |
| `auto_reopen` | run | int 0–10 | 0 | |
| `workspace` | run | `auto` \| `in_place` \| `worktree` | workflow's, else `auto` | `in_place` refused for a workflow with writer branches or writing items; fixed at start ([WTR §2.1](82-worktree-mode.spec.md)) |
| `worktree.root` | run | `sibling` \| `in_repo` \| `path:<absolute>` | `sibling` | Fixed at start ([WTR §2.4](82-worktree-mode.spec.md)) |
| `worktree.base` | run | `head` \| `default_branch` \| `ref:<name>` | workflow's `worktree.base`, else `head` | Fixed at start ([WTR §2.5](82-worktree-mode.spec.md)) |
| `worktree.branch_prefix` | run | 1–3 ref-safe components | `tg` | Fixed at start |
| `worktree.cleanup` | run | `never` \| `on_finish` | workflow's `worktree.cleanup`, else `never` | May change at resume ([WTR §2.7](82-worktree-mode.spec.md)) |
| `worktree.read_worktreeinclude` | run | bool | `true` | [WTR §2.3](82-worktree-mode.spec.md) |
| `enforce_tools`, `strict_permissions` | run | `true` | `false` | Tighten-only |
| `audit_rate` | run | float 0–1 | 0 | [JDG-B7](05-judge-and-verdict.spec.md) |
| `audit_executor` | run | registered executor | the gate judge's | |
| `<name>` | settings | the declared kind (§2.5) | the declared default | |
| `tools.add` | steps, unit, slot, chair | list of `ToolCapability` ([CON §2.5](01-contracts.spec.md)), including `mcp:<server>/<tool>` and `skill:<plugin>:<name>` | none | Widening; §2.8. Members and the chair take read-only capabilities only |
| `commands.add` | steps, unit, slot, `before:<n>`, `after:<n>` | list of command prefixes | none | Widening; adds the prefix to the step and to the run's allow-list; §2.9 |
| `views.add` | judge | list of read-only `ToolCapability` from the view catalog | none | Widening a judge's read view; §2.8 |

Run options that are not settings stay flags only: `--alias`, `--label`, `--parent`, `--as-agent`, `--pause-before`, `--dry-run` ([CLI §2.1](17-engine-cli.spec.md)).

### 2.3 Layers

Resolution is layer-major: the highest layer that sets a key at any scope matching the session wins; inside that layer the narrowest matching scope wins.

| Rank | Layer | Source |
|---|---|---|
| 1 | `flag` | `--set <key>=<value>` and the named flags of CLI §2.1 on `run`, `resume` or `rerun`; an orchestration node's `options`, a batch's shared options and a schedule's `options` arrive here, recorded with `via` = `cli`, `orchestration`, `batch`, `schedule` ([SCH §2.5.5](83-schedules.spec.md)) or `rerun` |
| 2 | `profile` | The named profiles chosen with `--profile <name>` (repeatable; a later profile wins per key) |
| 3 | `project:overrides` | `<state root>/config/settings.json`, `overrides` entries matching the workflow |
| 4 | `user:overrides` | `~/.tempergraph/config/settings.json`, `overrides` entries matching the workflow |
| 5 | `arm:<switch>.<arm>` | While a switch arm is in force, the workflow-declared per-arm values of `model`, `timeout_s`, `idle_s` and `effort` for the units the arm names ([SWM](79-measured-switches.spec.md)) |
| 6 | `workflow:unit` | The unit's own field: a step's `model` (its ladder rung for the attempt), `timeout_s`, a gate's budgets, a member's `executor` |
| 7 | `workflow:default` | Workflow-wide values: `default_executor`, `model_profile`, `run_cost_cap_usd`, `workspace`, `worktree.base` and `worktree.cleanup` ([WTR §2.3](82-worktree-mode.spec.md)), a declared setting's default |
| 8 | `project:defaults` | `<state root>/config/settings.json`, `defaults` |
| 9 | `user:defaults` | `~/.tempergraph/config/settings.json`, `defaults` |
| 10 | `engine` | The engine default of §2.2 |

Three rules keep the existing guarantees:

| Rule | Effect |
|---|---|
| Judges apart | `steps` and `<unit>` keys never reach a judge. The one step-to-judge inheritance is CON §2.4's: at the workflow layers, a judge with no model of its own takes the step's model (its ladder's last rung). |
| Declared diversity kept | `steps` and `<unit>` values of `model` and `executor` reach a member, chair or slot only when the workflow declares none for it; the council's diversity check runs on the resolved values ([CNL §2.6](71-council-unit.spec.md)). |
| Tighten-only keys | `approve`, `enforce_tools` and `strict_permissions` can only be set to `true`; a `false` is refused at any layer. |

An environment variable is never a layer: settings come from flags and files that are recorded, never from the environment ([EXI §2.1](10-executor-interface.spec.md)).

### 2.4 Configuration files

`settings.json` in the operator config folder of the state root and of the home folder ([LOS §2.1](33-local-observability-store.spec.md)), owner-only, versioned ([CON §2.10](01-contracts.spec.md)):

| Field | Kind | Meaning |
|---|---|---|
| `schema_version` | int | 1 |
| `defaults` | map key → value | Layer 8 or 9: replaces the engine default for every workflow |
| `overrides` | list of `{workflow, set}` | Layer 3 or 4; `workflow` is a name or `*`; inside a layer a named entry beats `*` per key |
| `profiles` | map name → map key → value | Profiles available to every workflow |

A key in `defaults` may not name a unit (units belong to one workflow); `overrides` and profiles may. A profile name is looked up in the project file, then the user file, then the workflow's `profiles`; the first found is used whole, never merged.

### 2.5 Workflow-declared settings and profiles

Two fields appended to `WorkflowSpec` ([CON §2.1](01-contracts.spec.md)):

| Field | Kind | Meaning |
|---|---|---|
| `settings` | map name → `SettingDecl` | Typed switches the workflow's checks, routes, switch functions, scripts, finalizer and templates read |
| `profiles` | map name → map key → value | Named bundles the author ships, such as `thorough` or `cheap` |

| `SettingDecl` field | Kind | Meaning |
|---|---|---|
| `kind` | `int` \| `float` \| `bool` \| `choice` \| `duration_s` \| `text` | |
| `default` | value of `kind` | Required |
| `choices` | list of slugs | `choice` only |
| `min`, `max` | numbers | `int`, `float`, `duration_s` |
| `meaning` | one line | Shown by `config show` and the catalog |

Code reads a setting from the resolved table passed in its context (`ScriptContext.settings`, the check's and route's state view); a template names it as the engine key `settings.<name>` ([CON §2.2](01-contracts.spec.md)). A `text` setting is never rendered into a script's argv and is scrubbed in every record; other kinds are checked numbers or constants, so they may ([SEC](14-security.spec.md)).

### 2.6 Snapshot and resume

| Moment | Engine does |
|---|---|
| Start | Reads both files once, resolves, stores the flag, profile and file layers' values in `RunOptions.settings`; the workflow layers come from the content the thread runs |
| Resume | Reapplies the snapshot. `--set` adds or replaces a flag value; `--unset <key>` removes one; `--profile` replaces the profile list; `--reload-settings` reads both files again. The workflow layers follow the content the thread resumes on ([MIG §2.5](62-state-and-run-migration.spec.md)) |
| Rerun | Copies the source's snapshot, then applies the rerun's own flags ([RRN §2.4](81-reruns-and-feedback.spec.md)) |

A changed value meets the counters already spent as follows:

| Key | Takes effect |
|---|---|
| `retry_budget`, `loop_budget` | At the next gate decision, against the counter already used in the current visit or pair; a lowered value at or under the count used is spent at the next failure |
| `run_cost_cap_usd` | At once; a thread drained with reason `cost_cap` continues when the new cap is above its cost |
| `model` ladder | From the next attempt, at the rung for its number in the current budget |
| `timeout_s`, `idle_s`, session options, `executor` | From the next session |
| `attempt_cap`, `infra_tries` | Per invocation, from this one |
| `arm`, `settings.<name>` | From the next read; a switch already decided in this visit keeps its arm |

### 2.7 Effective settings record

| Record | Written | Fields |
|---|---|---|
| `settings_resolved` (run log, [EVT §2.2](30-run-events.spec.md)) | After `run_started`, on start, each resume and a rerun | `settings_digest` (SHA-256 of the canonical resolved table); `rows[]` of `{key, value, layer, ref, shadowed[]}` for every key set on any layer above `engine`; `changed_keys` since the last segment. `ref` is the flag, the file path and its entry, the profile name, or the workflow field path. A `text` value is replaced by its digest |
| `run_started` | As today | adds `settings_digest`, `profiles`, `overridden_keys` (keys whose winning layer ranks 1 to 4) |
| `attempt_start`, `agent_run` | As today | each value already recorded carries its layer and `ref` |
| Status row, stats row, ledger row | As today | add `settings_digest` and `overridden_keys` (names only, [CON §2.10](01-contracts.spec.md)); the status row adds `settings_stale` when the files now resolve differently from the thread's snapshot ([DUR §2.2](09-durability-and-resume.spec.md)) |

### 2.8 Tool grants

The three widening keys above, `tools.add`, `commands.add` and `views.add`, follow every rule of this spec and five more:

| Rule | Detail |
|---|---|
| Who | Only the `flag` layer, given by a person, and a workflow's own profiles. A settings file entry or a user-file profile that widens is refused (`widening_in_file`): a machine file would widen every run unseen. A schedule's options are refused the same way (`widening_in_schedule`, [SCH §2.5.5](83-schedules.spec.md)). A caller whose decider is not a person cannot widen (`widening_by_agent`); an agent relaying a person's grant needs a named person turn ([PRV §2.8](85-caller-provenance.spec.md)) |
| What | A grant passes the same checks as a declaration ([WFM §2.1](02-workflow-model.spec.md)): the executor's `tool_map` maps it, a command prefix holds no shell metacharacter and its resolver argv is safe, an MCP server is configured on this machine, a skill's plugin is installed and the executor hosts an authoring surface. A grant that fails one is refused with the declaration's own finding code |
| Never | A path outside the workspace (C10); a write, edit, shell or writing MCP tool for a judge, a council member or the chair; a judge view outside the read-only catalog; any grant that removes `strict_permissions` or enforcement. The judge stays on an executor that declares `restricts_judge_tools`, and the guard of [GRD](06-independence-guard.spec.md) runs on the widened view |
| Shown | The step's tools block lists granted tools as declared ones ([PRM §2.2](04-prompt-rendering.spec.md)); `settings_resolved` marks each grant `widening: true`; the pause payload and `config show` list grants apart |
| Kept | In the thread's snapshot like any flag (§2.6): reapplied on later resumes and copied into a rerun; `--unset <unit>.tools.add` removes it |

When an attempt failed, or ended blocked, and the session recorded a `denied` event or a declared tool missing from its start tool list, the gate escalates with cause `tool_access` and spends no retry ([BUD §2.2](08-budgets-and-failures.spec.md)). The pause payload ([HUM §2.1](07-gate-and-human.spec.md)) lists each refused or missing name with its refusal class ([TSA §2.2](57-tool-surface-audit.spec.md)) and what fixes it:

| Class | Payload offers |
|---|---|
| `undeclared_tool`, a missing MCP tool or skill | `resume … --decision retry --grant <unit>=<capability>`; for a server not configured or a plugin not installed, the host step first |
| `needed_command` | `resume … --decision retry --allow-command <unit>=<prefix>` |
| `shell_for_read`, `dir_change_then_command` | No grant: these calls had a permitted form. `retry` with feedback naming the form |
| `outside_workspace` | No grant is possible; `retry` with feedback, or `stop` |

Every grant is tracked: a `grant` run-log record when it takes effect ([EVT §2.2](30-run-events.spec.md)), the intervention row of the resume that gave it ([HUM-B6](07-gate-and-human.spec.md)), and an entry of the ledger row's `grants[]` saying whether a later attempt used it ([SIL §2.4](16-self-improvement.spec.md), [IMD-R14](43-improvement-data.spec.md)). A grant used on a passing attempt is a `grant_missing` finding against the workflow; the audit's history layer reports it (`granted-at-run`, [TSA §2.4](57-tool-surface-audit.spec.md)), and the improvement loop drafts a `tools` proposal that declares it ([PRP §2.4](40-improvement-proposals.spec.md)), so a grant needed on every run ends up in the package once.

### 2.9 The `config` verb

| Verb | Does | Writes | Spends |
|---|---|---|---|
| `config show <workflow> [--thread <t>] [--set …] [--profile …] [--key <glob>] [--json]` | The resolved table for a start with these options, or for the thread's next resume: value, winning layer and `ref`, shadowed layers, and findings | no | no |
| `config validate [--file <path>]` | Validates both files (or one) against the catalog and every registered workflow they name | no | no |
| `config paths` | The two file paths and whether each exists | no | no |

Files are edited by hand or by a skill; the engine has no write verb for them.

## 3. Behaviours

**RST-B1 One order for every key.** Given the user file `defaults: {"steps.timeout_s": 900}`, the project file `overrides: [{workflow: "temperspec", set: {"code.timeout_s": 7200}}]`, the step `code` declaring `timeout_s: 3000` and `plan` declaring none, when a run starts with `--set plan.timeout_s=1200`, then:

| Session | Value | Layer |
|---|---|---|
| `plan` step | 1200 | `flag` |
| `code` step | 7200 | `project:overrides` |
| `review` step (declares 1800) | 1800 | `workflow:unit` |
| `triage` step (declares none) | 900 | `user:defaults` |
| `code` judge | 600 | `engine` (a judge never reads a step's value) |

**RST-B2 Judges apart.** Given `--set steps.model=small`, when the run resolves, then every step, member, chair and slot without a declared model uses `small`, and every judge resolves on the judge chain alone; a judge with no model of its own takes its step's declared model (workflow layer), never `small`.

**RST-B3 Diversity kept.** Given a council whose members declare `claude:opus` and `antigravity:gemini-pro`, when `--set review.model=small` is given, then the members keep their models; a council whose members declare none all take `small`, and if its diversity rule then fails the start is refused with exit 2 naming the rule.

**RST-B4 Raise at resume.** Given a run stopped with its retry budget of 2 spent at `expand` (exit 5), when `resume --set expand.retry_budget=4` is given without a decision, then the resume is refused with exit 2 because a stopped thread needs `retry` or `back`; when `resume --decision retry --set expand.retry_budget=4` is given, then the visit gets a fresh budget of 4 and `settings_resolved.changed_keys` lists the key.

**RST-B5 Not a setting.** Given `--set code.criteria=…`, `--set judge:code.tools=edit` or `--set code.prompt=…`, when validated, then each is refused with exit 2, finding `not_a_setting`, naming [ADR-0071](../adr/0071-overrides-never-change-what-verifies-the-work.adr.md); nothing is created.

**RST-B6 Tighten-only.** Given a gate declaring `approval: true`, when a project file sets `code.approve=false`, then validation refuses the file entry with exit 2 at the start; `--set code.approve=true` on a gate without approval adds the pause.

**RST-B7 Workflow settings.** Given temperspec declaring `test_budget_s` (`duration_s`, default 1800, max 7200), `code_mode` (`choice`: `per_phase`, `single`; default `per_phase`), `publish` (`bool`, default true) and `base_branch` (`text`), when `run --set settings.code_mode=single --set settings.test_budget_s=3600` starts, then the switch function reads `single`, the code check reads 3600, the finalizer reads `publish = true`, and a resume reapplies both; `--set settings.code_mode=fast` is refused with exit 2 listing the choices.

**RST-B8 Profiles.** Given the workflow's profile `cheap: {"steps.model": "small", "run.run_cost_cap_usd": 5}` and a user-file profile `cheap` with other values, when `--profile cheap` is given, then the user file's profile is used whole, its values sit on the `profile` layer, and `run_started.profiles` is `["cheap"]` with its source.

**RST-B9 Show equals run.** Given any workflow, files and options, when `config show` and `run --check` run with the same options, then the table `config show` prints equals the `settings_resolved` rows the run then writes; both call `resolve`.

**RST-B10 Misaimed override.** Given `--set plann.model=large` on a workflow with a unit `plan`, or `--set plan.member:a.model=large` where `plan` is not a council, or `--set plan.deadline_s=60` where `plan` is a step, when validated, then each is refused with exit 2 with its own finding code and, for an unknown name, the nearest declared one.

**RST-B11 Shadowed values are shown.** Given the user file sets `steps.model=medium` and the run passes `--set steps.model=large`, when `config show` runs, then the row shows `large` from `flag` with `user:overrides` shadowed; nothing warns at the start.

**RST-B13 Resume a run blocked on a tool.** Given a `triage` step whose session called `mcp:tracker/get_issue`, which it does not declare, and ended `BLOCKED`, when the gate decides, then it escalates with cause `tool_access`, no retry is spent, and the payload offers `--grant triage=mcp:tracker/get_issue`; `resume --decision retry --grant triage=mcp:tracker/get_issue` runs the next attempt with the tool, and a later resume keeps the grant.

| Grant | Result |
|---|---|
| `--grant triage=mcp:tracker/get_issue`, server configured | applied, recorded `widening: true` |
| the same, server not configured on this machine | exit 2, `mcp-server-not-configured`, nothing written |
| `--grant judge:triage=edit` | exit 2: a judge takes views only |
| `--set judge:triage.views.add=mcp:tracker/get_issue` | applied when the catalog classifies the tool read-only |
| `--allow-command code="npm run build; rm"` | exit 2: shell metacharacter |
| a user file `overrides` entry with `code.tools.add` | exit 2, `widening_in_file` |

**RST-B15 Grants feed the loop.** Given five runs on two machines in which a person granted `triage` the tool `mcp:tracker/get_issue` and each next attempt used it and passed, when self-improvement reads them, then each ledger row lists the grant as used, the five `grant_missing` findings form one cluster, one workflow issue is filed with the declaration as its remedy, and at `propose` autonomy a draft pull request adds `mcp:tracker/get_issue` to `triage`'s tools, naming the five runs.

**RST-B14 A missing skill fails before spend.** Given a step declaring `skill:review-kit:security` whose plugin is not installed, when a run or resume preflights, then it exits 2 naming the plugin and the install command; no grant can replace an install.

**RST-B12 Overrides reach the improvement loop.** Given a run whose `code` step used `small` from a `flag` override and failed its gate three times, when self-improvement reads it, then the finding carries `overridden_keys: [code.model]` and the friction lens does not file it as a workflow fault unless the same cluster also holds runs without that override ([SIL](16-self-improvement.spec.md)).

## 4. Error conditions

| Condition | Result |
|---|---|
| Unknown key, scope or setting name | Exit 2, finding `unknown_setting` with the nearest name; nothing created |
| Key not valid for the scope's unit kind | Exit 2, `setting_not_for_kind` |
| Value outside type or range; a choice not declared | Exit 2, `setting_value` |
| A key of the verification surface (§1) | Exit 2, `not_a_setting` |
| A widening key from a file, a user-file profile or an agent caller | Exit 2, `widening_in_file` or `widening_by_agent` |
| A grant that fails a declaration check or a never rule of §2.8 | Exit 2 with the declaration's finding code |
| `false` for a tighten-only key | Exit 2, `tighten_only` |
| `on_budget_spent=fallback` where the gate has no `fallback` | Exit 2, `no_fallback_target` |
| Unknown profile name | Exit 2, `unknown_profile` |
| A configuration file that does not parse, or a newer major `schema_version` | Exit 2 naming the file; `config validate` shows the line |
| A file `defaults` entry that names a unit | Exit 2, `unit_in_defaults` |
| A setting the executor cannot apply (`effort`) | Warning, recorded (CON §4) |

## 5. Design notes

- **Files above and below the workflow.** `overrides` serve an operator who must change a workflow's value on this machine (a slow host's longer limit, a team's model choice); `defaults` serve every workflow that states nothing. Both are per machine: a committed repository file is not a layer in the first release, so a pull request cannot raise anyone's cost cap.
- **Snapshot, not live files.** A paused thread resumes days later with the settings it started with unless the operator says otherwise, so a run's record explains its behaviour ([ADR-0072](../adr/0072-threads-snapshot-settings-and-reapply-them-on-resume.adr.md)).
- **Provenance is data for the loop.** Settings digests let reports compare like with like and stop the loop blaming a workflow for an operator's cheaper model ([IMD](43-improvement-data.spec.md)).
- The legacy flags of [CLI §2.1](17-engine-cli.spec.md) stay as spellings of `--set`; the mapping is in that table.

## 6. Acceptance criteria

- [ ] RST-AC-1 Every row of §2.2 has a fixture that resolves it from each layer of §2.3 and records the winning layer and `ref`.
- [ ] RST-AC-2 Every row of §4 has a fixture refused before any file is created under the state root (hash test).
- [ ] RST-AC-3 A property test over random layer assignments finds no case where a `steps` or `<unit>` key reaches a judge, or where a tighten-only key ends `false`.
- [ ] RST-AC-4 `config show` output equals the run's `settings_resolved` rows on a corpus of workflows and options (RST-B9).
- [ ] RST-AC-5 A thread started, paused, its files edited, and resumed without `--reload-settings` resolves the same `settings_digest`; with it, the digest and `changed_keys` reflect the edit.
- [ ] RST-AC-6 Every row of the §2.6 counters table is tested on resume.
- [ ] RST-AC-8 Every row of the RST-B13 table holds, and a property test finds no grant that gives a judge, member or chair a non-read-only tool.
- [ ] RST-AC-7 No `text` setting value appears in argv, a ledger row, a stats row or a finding (canary test, [SEC-B2](14-security.spec.md)).

## Open questions

| Question | Owner | Release 1 default |
|---|---|---|
| Should a team be able to commit a shared settings file in the repository (a third file layer), with cost caps limited to lowering? | Owner | No |
| Should an organisation be able to impose a managed layer above `flag` (hard ceilings), as Claude Code's managed settings do? | Owner | No |

## References

