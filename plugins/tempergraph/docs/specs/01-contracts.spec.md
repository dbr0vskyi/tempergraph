---
title: Shared contracts
type: contracts
status: review
prefix: CON
adrs: [0003, 0005, 0006, 0008, 0009, 0012, 0015, 0018, 0062, 0070, 0073, 0074, 0075, 0078]
---

# Shared contracts

## 1. Overview

This spec is the only definition of a type that two or more component specs share. Component specs name a section here and restate nothing. Types are given as field tables and Python-flavoured signatures without bodies. Every persisted or published document listed here is versioned and read by tolerant readers (§2.10).

## 2. Contract

### 2.1 Workflow specification

A workflow is data ([ADR-0003](../adr/0003-workflows-as-data.adr.md)). The engine reads it through the registry and never names one.

| Type | Field | Kind | Meaning |
|---|---|---|---|
| `WorkflowSpec` | `name` | slug | Unique in the manifest. |
| | `order` | list of unit names | The default forward order. |
| | `units` | map name → `UnitSpec` | Steps and flow units. |
| | `flow` | map unit → `FlowSpec` | Where a pass goes when it is not the next in `order`. |
| | `input` | `InputDeclaration` | How a run starts (§2.3). |
| | `workspace` | `in_place` \| `worktree` | Default workspace mode. |
| | `finalizer` | callable ref, optional | Runs once after the last pass; calls no model; never changes the run's exit code ([FIN](78-finalizer-contract.spec.md)). |
| | `finalizer_outcomes` | list of slugs, required with `finalizer` | The outcomes the finalizer may report ([FIN §2.3](78-finalizer-contract.spec.md)). |
| | `default_executor` | executor name | Used when a step names none. |
| | `model_profile` | `ModelProfile` | Default aliases per step and judge (§2.4). |
| | `issue_repository` | `owner/name` | Required. Receives the workflow's improvement issues. |
| | `routing` | `RoutingMetadata` | Description, when to use, task kind. |
| | `improvement_mode` | `dev` \| `stable` | Self-improvement mode. |
| | `verified_engine` | version string, optional | The engine release the workflow was last stamped against. |
| | `command_resolver` | callable ref, optional | Maps a declared command prefix to the argv a check or the tool host runs, so gates work for a non-Python repository ([WFM](02-workflow-model.spec.md)). |
| | `run_cost_cap_usd` | float, optional | Spend cap for one run, children included ([BUD](08-budgets-and-failures.spec.md)). |
| | `version` | semver, default `0.0.0` | The owner's release of the workflow; with the content digest it forms `workflow_version` ([VER §2.4](61-version-metadata.spec.md)). |
| | `requires_engine` | version range, optional | Engine releases the owner states it works with; warns only ([VER §2.7](61-version-metadata.spec.md)). |
| | `upgrade` | `UpgradePolicy`, optional | What a workflow upgrade may touch ([VER §2.4](61-version-metadata.spec.md)). |
| | `settings` | map name → `SettingDecl`, optional | Typed workflow switches an operator may override ([RST §2.5](80-run-settings-and-overrides.spec.md)). |
| | `profiles` | map name → map `SettingKey` → value, optional | Named bundles of settings ([RST §2.5](80-run-settings-and-overrides.spec.md)). |
| `UnitSpec` | `kind` | `step` \| `route` \| `switch` \| `parallel` \| `map` \| `subworkflow` \| `wait` \| `script` \| `council` \| `contest` \| `ask` | Kinds and their owning specs: [CMP §2.2](03-compiler-and-flow.spec.md) and [FLX](74-flow-extensions.spec.md) for flow kinds; [SCR](70-script-units-and-hybrid-steps.spec.md), [CNL](71-council-unit.spec.md), [CTS](72-contest-unit.spec.md), [ASK](73-ask-unit.spec.md) for the others. |
| | `step` | `StepSpec`, for kind `step`, `map` and `contest` | |
| | `script`, `council`, `contest`, `ask`, `map` | `ScriptSpec`, `CouncilSpec`, `ContestSpec`, `AskSpec`, `MapSpec`, for their kind | Defined in the owning spec ([MAP](77-map-unit.spec.md) for `MapSpec`); used by it and by WFM only. A `switch` unit's fields are in [CMP §2.2](03-compiler-and-flow.spec.md) and [SWM §2.1](79-measured-switches.spec.md). |
| | `gate` | `GateSpec` | Required for every kind. A `wait` or `ask` gate holds only checks; a `script` gate holds the built-in check and an optional judge. |
| `StepSpec` | `executor` | executor name, optional | Falls back to `default_executor`. |
| | `prompt` | inline text \| file ref \| `default` | Template; grammar in §2.2. |
| | `tools` | list of `ToolCapability` (§2.5) | Declared tools. |
| | `commands` | list of command prefixes | Within the workflow-wide allow-list. |
| | `produces` | map key → `ArtifactKind` | `file`, `url`, `wiki_page`, `tracker_issue`, `pull_request`, `value` (one line, with optional `choices` and `pattern`, [VAL §2.1](76-step-values-and-template-keys.spec.md)). |
| | `model` | alias \| list of up to 8 aliases (ladder) \| item function ref | |
| | `timeout_s`, `idle_s` | positive int, optional | |
| | `session_options` | `SessionOptions` (§2.6), optional | |
| | `before`, `after` | list of `ScriptSpec`, optional | Hybrid step: model-free scripts in the same attempt, around the session ([SCR](70-script-units-and-hybrid-steps.spec.md)). |
| | `self_check` | bool, default false | The step may run its gate's check from inside its attempt ([CHK §2.5](75-check-contract-and-command-runs.spec.md)). |
| | `summary` | text ≤ 60 chars | For diagrams. |
| | `subagent_model` | alias, optional | The model of the subagents the step starts, where its executor hosts them ([RST §2.2](80-run-settings-and-overrides.spec.md)). |
| `GateSpec` | `check` | callable ref, optional | Model-free, writes no state; `(ctx: CheckContext) -> CheckResult` ([CHK](75-check-contract-and-command-runs.spec.md)). |
| | `check_timeout_s` | positive int, default 1800 | Wall limit of the whole check ([CHK §2.6](75-check-contract-and-command-runs.spec.md)). |
| | `judge` | `JudgeSpec` | Required on model steps. |
| | `criteria` | list of `Criterion` | At least one when a judge is present. |
| | `on_fail` | `retry` \| `stop` \| `fallback` | Hard-failure policy. |
| | `on_budget_spent` | `stop` \| `ask` \| `fallback` | |
| | `fallback` | forward unit name or `finalizer`, optional | Where `fallback` goes; the run is marked degraded ([FLX §2.4](74-flow-extensions.spec.md)). |
| | `approval` | bool | Pause for sign-off after a pass. |
| | `back_targets` | list of unit names | Earlier units a failure may send the run to. |
| | `loop_budget` | int ≥ 0, default 1 | Trips per (unit, target). |
| | `retry_budget` | int ≥ 0, default 2 | Retries per visit. |
| `JudgeSpec` | `stance`, `brief` | text | Stance first; brief holds repository specifics only. |
| | `references` | list of artifact keys, each `required` or `optional` | The bar. |
| | `subject` | artifact keys | What is graded. |
| | `executor`, `model`, `timeout_s` | optional | Resolved on the judge's own layer. |
| | `tools` | list of `ToolCapability` | May only narrow the derived view set. |
| `Criterion` | `text` | text | Shown to the step and the judge. |
| | `check_method` | text | Shown to the judge only. |
| | `severity` | `blocker` \| `warning` | |
| | `id` | slug, optional | Echoed by the judge. |
| | `unverified_system` | text, optional | A system the author knowingly leaves unread. |
| | `no_change_policy` | `escalate` \| `retry`, default `escalate` | What a blocker the judge marks `no_change` does (§2.8, [JDG](05-judge-and-verdict.spec.md)). |
| | `mechanical` | bool, default false | The gate's check verifies this criterion; a check FAIL on it costs no judge, and the judge takes the check's finding as given ([CHK-B1, B2](75-check-contract-and-command-runs.spec.md)). |

### 2.2 Template grammar

A template contains literal text, doubled braces `{{` `}}` for literal braces, and plain fields `{name}` where `name` is an engine key, a declared input name, or `settings.<name>` for a declared workflow setting ([RST §2.5](80-run-settings-and-overrides.spec.md)). Nothing else between braces is valid. At run time a field without a value renders as the visible marker `⟨missing:name⟩` and is recorded on the step record. The engine keys, item keys and earlier-artifact pointers a field may name are listed in [VAL §2.3](76-step-values-and-template-keys.spec.md).

### 2.3 Input and routing declarations

| Type | Field | Meaning |
|---|---|---|
| `InputDeclaration` | `kind` | `any` \| `tracker_key` \| `file` \| `text` \| `resolver` |
| | `parameters` | list of `{name, meaning, example, when_asked}` |
| | `examples` | 2–3 whole start requests that must resolve |
| | `prerequisites` | plain sentences, shown, never checked |
| | `resolver` | callable ref; read-only, model-free |
| `ResolveResult` | `status` | `ok` \| `needs` \| `error` |
| | `task_id` | stable id; names thread, branch, log and lock |
| | `questions` | on `needs`: list of `{name, question, choices?}` |
| `RoutingMetadata` | `description` | one line starting with a verb |
| | `when_to_use` | 2–4 sentences ending in "Not for: …" |
| | `task_kind` | `ticket` \| `prompt` \| `symptom` \| `repository` \| `findings` |

### 2.4 Models

- **Alias grammar.** `inherit`, an engine-neutral tier `small` \| `medium` \| `large`, or an executor-qualified alias `<executor>:<name>` (for example `claude:opus`, `antigravity:gemini-pro`, `agent-sdk:sonnet`, `messages-api:opus`). Never a deployment id. Binding is per executor ([ADR-0008](../adr/0008-portable-model-aliases.adr.md)).
- **`ModelProfile`**: map from step name and from `judge:<step name>` to an alias or a ladder.
- **Resolution order for a step attempt:** the operator layers of [RST §2.3](80-run-settings-and-overrides.spec.md) (flags per unit then per run, profiles, project and user overrides), an arm in force that names the step, the step's model (ladder rung n for attempt n, last rung repeats), workflow default, project and user defaults, `inherit`.
- **Resolution order for a judge:** the same operator layers on the judge scopes only (`judge:<unit>`, then `judges`), the gate's judge model, the step's model (its ladder's last rung), workflow default, project and user defaults, `inherit`.
- Every record carries the alias, its source layer and the executor that bound it.

### 2.5 Tool capabilities

Workflow data declares tools by engine-neutral capability name. Each executor maps a name to its own tools (§ in each executor spec). The view catalog is keyed by `(executor, tool name)`.

| Capability | Read-only | Meaning |
|---|---|---|
| `read` | yes | Read a file in the workspace. |
| `search` | yes | Search file contents. |
| `list` | yes | List or glob paths. |
| `edit` | no | Change an existing file. |
| `write` | no | Create or overwrite a file. |
| `shell` | no | Run a declared command prefix. |
| `web_fetch` | yes | Fetch a URL. |
| `web_search` | yes | Search the web. |
| `subagent` | inherits | Start a sub-session; inherits the caller's restriction. |
| `mcp:<server>/<tool>` | per catalog | One MCP tool; classified by the engine catalog, never by name pattern. |
| `skill:<plugin>:<name>` | no | One skill of an installed plugin, named by plugin path; adds no tool of its own ([ADR-0078](../adr/0078-skills-are-a-declared-tool-capability.adr.md)). |

### 2.6 Executor protocol

```python
class Executor(Protocol):
    name: str                              # constant: "claude", "agent-sdk", "messages-api", "antigravity"
    def capabilities(self) -> Capabilities: ...
    def probe(self) -> ProbeReport: ...    # read-only, model-free; version and facts
    def run_step(self, req: SessionRequest, sink: EventSink) -> SessionResult: ...
    def run_judge(self, req: SessionRequest, views: ViewSet, sink: EventSink) -> SessionResult: ...
```

Neither run method raises for a session failure; failure is a field of the result.

| Type | Field | Meaning |
|---|---|---|
| `SessionRequest` | `kind` | `step` \| `retry` \| `judge` \| `judge_reask` \| `grouping` \| `member` \| `member_reask` \| `chair` (council sessions, [CNL](71-council-unit.spec.md)); executors treat the last three as step sessions with read-only tools |
| | `prompt` | rendered text; delivered off argv |
| | `workdir` | absolute workspace path from state |
| | `alias` | resolved alias (§2.4) |
| | `tools` | declared `ToolCapability` list (step) |
| | `commands` | declared command prefixes (step) |
| | `timeout_s`, `idle_s` | resolved limits and their sources |
| | `options` | `SessionOptions` |
| | `credentials_profile` | judge-only profile name, optional |
| `SessionOptions` | `effort` | `low` \| `medium` \| `high` \| `max`, optional |
| | `cost_cap_usd` | float, optional |
| | `fallback_alias` | alias, optional; never for a judge |
| | `turn_cap` | int, optional |
| `Capabilities` | `binds_aliases` | set of aliases this executor can bind |
| | `families` | map alias → model family label (for example `anthropic`, `google`); read by council diversity checks |
| | `prompt_off_argv`, `streams_events`, `reports_actions`, `reports_tokens`, `reports_cost` | bool |
| | `enforces_step_tools`, `restricts_judge_tools`, `step_allow_rules`, `judge_mcp`, `isolates_user_config`, `fresh_session` | bool |
| | `hosts_authoring_surface` | bool; the session loads instruction files, skills and agents ([ADR-0016](../adr/0016-portable-authoring-surface.adr.md)) |
| | `session_options` | set of supported option names |
| | `tool_map` | map `ToolCapability` → executor tool names |
| | `version` | version string seen by `probe`: the CLI's, or for a library executor the library's plus any bundled CLI's |
| `SessionResult` | `ok` | bool |
| | `text` | final answer text |
| | `session_id` | executor's id |
| | `usage` | `Usage` |
| | `tool_calls` | list of `{name, ok, subagent: bool}` in call order |
| | `timed_out`, `stalled`, `partial` | bool |
| | `infra_cause` | `InfraCause` \| null |
| | `error_kind` | `model` \| `refused` \| `cap_reached` \| `turn_cap` \| `denied` \| `auth` \| `unknown` \| null; `refused` is a typed model refusal (a stop reason, never text) |
| | `applied_options` | names of options actually applied |
| | `cli_version` | string; same meaning as `Capabilities.version` |
| `Usage` | `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `thinking_tokens` | int \| null |
| | `reported_cost_usd` | float \| null; never 0 when unknown |
| | `estimated_cost_usd` | float \| null; engine price table, kept apart |
| | `by_model` | map model name → partial `Usage` |
| | `turns`, `peak_context_tokens` | int \| null |
| `InfraCause` | enum | `spawn_failed`, `prompt_not_delivered`, `no_output`, `no_result`, `broken_pipe`, `connection`, `out_of_memory`, `request_timed_out`, `slow_host`, `throttled` |

### 2.7 Normalized session events

Every executor translates its CLI's stream into these events and pushes them to the `EventSink` ([ADR-0009](../adr/0009-normalized-session-event-stream.adr.md)).

| Event | Fields |
|---|---|
| `session_started` | `session_id`, `model`, `cli_version`, `tools` (as listed by the CLI) |
| `model_delta` | `chars` (count only) |
| `tool_started` | `name`, `subagent: bool`, `call_id`, `input_summary?` (scrubbed, clipped one-line summary of the input; local records only, [EVT §2.5](30-run-events.spec.md)) |
| `tool_finished` | `call_id`, `ok`, `error_kind?` |
| `text` | `last_line` (scrubbed, clipped to 200 chars) |
| `retrying` | `category` (from the CLI's retry event, if any) |
| `denied` | `name` (a refused or soft-denied tool) |
| `result` | `ok`, `usage` |

### 2.8 Judgement and verdict

The judgement block is the last fenced JSON block of the judge's answer.

| Field | Kind | Meaning |
|---|---|---|
| `criteria[]` | `{n, id?, status, evidence, place, fix, defect_in?, no_change?}` | `status` ∈ `MET`, `PARTIAL`, `UNMET`, `N/A`, `UNVERIFIABLE`. `defect_in` names an earlier artifact key. `no_change` (bool) says the step's own output cannot fix it: a missing source, a person's decision, or an outside system. |
| `coverage` | `{requirements, traced, orphans}` | ints |
| `gap` | bool | A source is missing or the task is unclear. |
| `confidence` | float in [0,1] | Anchors: 0.95 verified, 0.85 checked, 0.7 partly inferred, 0.5 contested. |
| `summary` | one line | |

`Verdict` ∈ `PROCEED`, `RETRY`, `BACK`, `ESCALATE`, `STOP`. Only the engine derives it ([JDG](05-judge-and-verdict.spec.md)). A confidence value carries `source` ∈ `judge`, `engine_placeholder`.

`CheckResult` is `result` ∈ `PASS`, `MAYBE`, `FAIL`, with `evidence` (bounded text), `environmental: bool`, `untracked_only: bool`, `findings` (list of `CheckFinding`), `facts` (map of at most 20 slugs to strings ≤ 200 chars) and `runs` (the check's command runs, added by the engine). A `CheckFinding` is `{criterion?, status, place, fix, message}` with `status` ∈ `pass`, `maybe`, `fail`, `n_a`. Rules: [CHK §2.4](75-check-contract-and-command-runs.spec.md).

### 2.9 Runs, threads and exit codes

| Type | Values |
|---|---|
| `ThreadState` | `none`, `running` (lock held), `paused`, `unfinished`, `stopped`, `finished` |
| `Decision` | `proceed`, `retry`, `back:<unit>`, `rewind:<unit>` (a person's return to any completed unit, [RRN §2.3](81-reruns-and-feedback.spec.md)), `stop`, `event:<name>=<value>`, `answer:<name>=<value>` (an ask, or a council's no-decision pause, [ASK §2.3](73-ask-unit.spec.md)) |
| `ExitCode` | `0` finished · `1` internal error · `2` usage or preflight refusal, nothing spent or created · `3` paused for a person · `4` stopped · `5` budget spent or infra failure · `6` an advisory verb found issues at the level asked for (`audit --fail-on`, [AUD](55-workflow-audit.spec.md)) · `127` engine not installed (shim) |

`thread_id = <workflow>/<task_id>`. A fresh start on a thread whose state is not `none` is refused with exit 2 ([ADR-0015](../adr/0015-exit-codes-as-caller-contract.adr.md)).

### 2.10 Persisted documents

| Document | Owner spec | Shape |
|---|---|---|
| Run log | [OBS](15-observability-and-cost.spec.md) | JSON lines, one event per line, `schema` key on the first line |
| Status document | [DUR](09-durability-and-resume.spec.md) | JSON, `schema_version`, one row per thread |
| Findings | [SIL](16-self-improvement.spec.md) | JSON, metadata only |
| Ledger | [SIL](16-self-improvement.spec.md) | JSON lines, names, counts, hashes |
| Catalog | [CLI](17-engine-cli.spec.md) | JSON, `schema_version`, one row per workflow |
| Diagram model | [LIF](18-lifecycle-and-evals.spec.md) | JSON with digest |
| Detail document | [RDD](31-run-detail-document.spec.md) | JSON, `schema_version`, one thread; built on demand, never stored |
| Activity journal | [EVT](30-run-events.spec.md) | JSON lines per session |
| Store manifest, machine index | [LOS](33-local-observability-store.spec.md), [CST](34-central-run-stats.spec.md) | JSON, `schema_version` |
| Sink rows (`run`, `heartbeat`, `session`) | [CST](34-central-run-stats.spec.md) | JSON lines and one JSON file, `schema_version` per row |
| Labels | [FBK](41-feedback-and-judge-reliability.spec.md) | JSON lines, metadata only |
| Proposals, trials, case sets | [PRP](40-improvement-proposals.spec.md) | JSON, `schema_version`, metadata only (the patch lives on its branch) |
| Lessons file | [LSN](42-workflow-lessons.spec.md) | JSON in the workflow package, `schema_version` |
| Loop parameters | [IMD](43-improvement-data.spec.md) | JSON, one record per named threshold with provenance |
| Audit report | [AUD](55-workflow-audit.spec.md) | JSON, `schema_version`, printed only, never stored |
| Engine release record, compatibility changelog | [VER](61-version-metadata.spec.md) | JSON in the engine package, `schema_version` |
| Stamp record, workflow change notes | [VER](61-version-metadata.spec.md) | JSON in the workflow package, `schema_version` |
| Engine pointers (`current.json`, `previous.json`), workflow registry (`registry.json`) | [UPD](60-engine-update.spec.md) | JSON in the home folder, `schema_version` |
| Thread engine file | [MIG](62-state-and-run-migration.spec.md) | JSON per thread, `schema_version` |
| Upgrade plan, baseline, report | [WUP](63-workflow-upgrade.spec.md) | JSON per upgrade, `schema_version` |
| Settings files (`settings.json`, project and user) | [RST](80-run-settings-and-overrides.spec.md) | JSON, `schema_version` |
| Rerun lineage (`lineage.json` per source run) | [RRN](81-reruns-and-feedback.spec.md) | JSON, `schema_version` |

Every reader ignores unknown keys and reads a missing key as "not recorded", never as zero. Renaming, removing or reinterpreting a key bumps the schema version.

### 2.11 Audit findings

Shared by [AUD](55-workflow-audit.spec.md), [ARC](56-audit-rule-catalog.spec.md), [TSA](57-tool-surface-audit.spec.md) and [PRA](58-prompt-audit.spec.md).

| Type | Field | Meaning |
|---|---|---|
| `AuditFinding` | `rule` | Catalog rule id, or `validate:<code>` and `<owner>:<code>` for owned rules |
| | `layer` | `definition` \| `host` \| `history` |
| | `severity`, `confidence` | `error` \| `warning` \| `info`; `high` \| `medium` \| `low` |
| | `cause` | Cause code from the self-improvement list ([SIL §2.3](16-self-improvement.spec.md)) |
| | `unit`, `item`, `session` | Where; `session` is `step` or `judge` |
| | `statement` | One line, no run text |
| | `evidence` | Numbers with their `n`, field paths, tool and rule names; never request or output text |
| | `remedy`, `widening` | The rule's fixed remedy; `widening` true when it adds a grant |
| | `location` | Package file and field path, line where known |
| | `ignored` | null, or `{reason, until?}` |
| `AuditReport` | `schema_version`, `workflow`, `version`, `engine_version` | |
| | `layers_run`, `layers_skipped`, `rules_skipped` | Skipped entries carry a reason and, for samples, `n` and `min_n` |
| | `findings[]`, `hot_spots[]`, `owned[]`, `summary` | Per [AUD §2.2](55-workflow-audit.spec.md) |

### 2.12 Run settings, run options and feedback

Shared by [RST](80-run-settings-and-overrides.spec.md), [RRN](81-reruns-and-feedback.spec.md), [DUR](09-durability-and-resume.spec.md), [CLI](17-engine-cli.spec.md) and [ORC](45-orchestration.spec.md).

| Type | Field | Meaning |
|---|---|---|
| `SettingKey` | string | `<scope>.<name>` from the catalog of [RST §2.2](80-run-settings-and-overrides.spec.md) |
| `SettingDecl` | `kind`, `default`, `choices?`, `min?`, `max?`, `meaning` | A workflow-declared setting ([RST §2.5](80-run-settings-and-overrides.spec.md)) |
| `RunOptions` | `settings` | Snapshot: map `SettingKey` → `{value, layer, ref, via?}` for the flag, profile and file layers ([RST §2.6](80-run-settings-and-overrides.spec.md)) |
| | `profiles` | Profile names in the order given |
| | `alias`, `label`, `parent`, `origin`, `pause_before`, `dry_run` | The run options that are not settings ([CLI §2.1](17-engine-cli.spec.md)) |
| | `caller` | The `Caller` of the call that started or resumed the thread (§2.13); classified per call, never snapshot |
| | `rerun_of` | `{thread, unit, checkpoint_id, workflow_version}` for a rerun, else null |
| `ResolvedSettings` | `rows` | Per session scope and key: value, winning layer, `ref`, shadowed layers |
| | `digest` | SHA-256 of the canonical table; `text` values enter as their digests |
| `UnitRef` | string | `<unit>`, `<unit>.<item>` or `<unit>/<child unit>` |
| `Feedback` | `text_ref` | Pointer into the local evidence file; never the text in a record |
| | `chars` | Length |
| | `ruling` | bool |
| | `applies_to` | list of `UnitRef`, for a ruling; empty means the unit given at and every later unit |
| `Ruling` | `id`, `feedback`, `given_at` (unit), `by` (`Caller`), `at`, `revoked_at?`, `revoked_by?` (`Caller`) | Kept in state under its own reducer; never cleared by the trip-back reducer |

### 2.13 Callers and supervision

Shared by [PRV](85-caller-provenance.spec.md), [SUP](86-supervision-metrics.spec.md), [SCO](87-supervision-cost.spec.md), [HUM](07-gate-and-human.spec.md), [EVT](30-run-events.spec.md), [CST](34-central-run-stats.spec.md), [FBK](41-feedback-and-judge-reliability.spec.md) and [ORC](45-orchestration.spec.md).

| Type | Field | Meaning |
|---|---|---|
| `CallerKind` | enum | `person`, `agent`, `orchestrator`, `pipeline`, `engine`, `unknown` ([PRV §2.1](85-caller-provenance.spec.md)) |
| `Caller` | `kind`, `confidence` (`attested`, `marked`, `observed`, `declared`, `none`) | Classified by [PRV §2.3](85-caller-provenance.spec.md) |
| | `decided_by` (`CallerKind`), `relay` (`direct`, `turn_named`, `turn_only`, `claimed`, `none`) | For deciding calls ([PRV §2.4](85-caller-provenance.spec.md)); null otherwise |
| | `host`, `host_session`, `caller_app`, `parent`, `trace_id`, `evidence[]`, `call_id` | [PRV §2.5](85-caller-provenance.spec.md); `host_session` is hashed in anything that leaves the machine |
| `TouchClass` | enum | `designed`, `rescue`, `steer`, `engine` ([SUP §2.1](86-supervision-metrics.spec.md)) |
| `SupervisionLevel` | enum | `observer`, `approver`, `consultant`, `collaborator`, `operator` ([SUP §2.3](86-supervision-metrics.spec.md)) |
| `SupervisionRecord` | per [SUP §2.2](86-supervision-metrics.spec.md) | One per thread; the ledger row's `supervision{}` |
| `SupervisionCost` | `marginal`, `turn`, `sessions[]`, `completeness` | [SCO §2.5](87-supervision-cost.spec.md); completeness adds `measured_zero` and `none_known` to the run cost flags |

## 3. Behaviours

**CON-B1 Tolerant read.** Given a run log line with an unknown event kind, when the analyzer reads it, then it skips the line and counts it under `unknown_kinds`.

**CON-B2 Unknown cost.** Given a `SessionResult` whose executor reported tokens but no cost, when it is recorded, then `reported_cost_usd` is null and `estimated_cost_usd` is computed from the price table.

| Executor | Tokens reported | Cost reported | `reported_cost_usd` | `estimated_cost_usd` |
|---|---|---|---|---|
| claude | yes | 0.42 | 0.42 | from table |
| agent-sdk | yes | 0.40 | 0.40 | from table |
| messages-api | yes | — | null | from table |
| antigravity | yes | — | null | from table |
| any | — | — | null | null |

**CON-B3 Alias tiers.** Given a step with model `large` on executor `antigravity`, when the alias is resolved, then the executor's binding table maps `large` to its configured slug and the record shows `alias=large, bound_by=antigravity`.

## 4. Error conditions

| Condition | Where detected | Result |
|---|---|---|
| A field outside the template grammar | Validation | Workflow invalid; exit 2 |
| An alias no executor binds | Preflight | Exit 2 before spend |
| A tool capability the executor's `tool_map` lacks | Preflight | Exit 2 before spend |
| A session option outside `Capabilities.session_options` | Preflight | Exit 2 (`effort` only warns) |
| A document with a newer major schema | Reader | Distinct reader exit, nothing written |

## 5. Design notes

- Neutral tool and model names keep a workflow portable across the four executors; the cost is a mapping table per executor ([ADR-0006](../adr/0006-executors-as-capability-adapters.adr.md), [ADR-0008](../adr/0008-portable-model-aliases.adr.md)).
- `reported_cost_usd` and `estimated_cost_usd` are never summed into one figure ([ADR-0012](../adr/0012-cost-when-executor-reports-tokens-only.adr.md)).
- The exit-code table is the contract for every caller and skill ([ADR-0015](../adr/0015-exit-codes-as-caller-contract.adr.md)).

## 6. Acceptance criteria

- [ ] CON-AC-1 Every type named by two or more specs is defined here and only here.
- [ ] CON-AC-2 A rendered template contains no unrendered field; a missing value renders as the marker and is recorded.
- [ ] CON-AC-3 No persisted document records unknown usage as 0.
- [ ] CON-AC-4 Every persisted document carries a schema version and its readers pass a test with an unknown key and an unknown event kind.
- [ ] CON-AC-5 A workflow that names only neutral aliases and the capabilities `read`, `search`, `list`, `edit`, `write` and `shell` validates against all four executors' binding and tool tables.
- [ ] CON-AC-6 The exit-code table here equals the engine's constants, checked by a generated-table drift test.

## Open questions

| Question | Owner |
|---|---|
| Should `effort` values be normalized further when one executor accepts `xhigh` and another does not? Today the executor maps and records what it applied. | Executor implementer |

## References

