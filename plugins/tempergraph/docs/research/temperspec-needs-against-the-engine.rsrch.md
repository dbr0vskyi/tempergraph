# Temperspec's needs against the engine design

## Problem statement

The owner asked on 2026-11-20 to verify that the engine design holds everything a temperspec workflow will need. temperspec is the spec-driven delivery workflow (task → triage → discovery → plan → expand → phase × N → code → release → draft pull request) that will run on tempergraph as a workflow package. This note answers:

1. What does temperspec require of the engine?
2. For each need, where does the engine design (specs `overview`, `contracts`, `workflow-model`, `compiler-and-flow`, `prompt-rendering`, `judge-and-verdict`, `independence-guard`, `gate-and-human`, `budgets-and-failures`, `durability-and-resume`, `executor-interface`, `executor-claude-code`, `executor-antigravity`, `workspace-and-concurrency`, `security`, `observability-and-cost`, `self-improvement`, `engine-cli`, `lifecycle-and-evals`, `plugin-shell`, `executor-messages-api`, `executor-agent-sdk`, `tool-host`, `run-options`, `lifecycle-hooks`, `session-contract`, `schedule-timing-formats`, `run-events`, `run-detail-document`, `run-control`, `local-observability-store`, `central-run-stats`, `telemetry-export`, `improvement-proposals`, `feedback-and-judge-reliability`, `workflow-lessons`, `improvement-data`, `session-review`, `orchestration`, `orchestrator-skill`, `judge-calibration`, `eval-suites`, `workflow-audit`, `audit-rule-catalog`, `tool-surface-audit`, `prompt-audit`, `engine-update`, `version-metadata`, `state-and-run-migration`, `workflow-upgrade`, `upgrade-workflow`, `lifecycle-skills`, `script-units-and-hybrid-steps`, `council-unit`, `contest-unit`, `ask-unit` and `flow-extensions` on `main`) cover it, and what is missing or only partly covered?
3. Which needs belong to temperspec itself, and which to the parallel thread on configuration overrides and reruns?

Scope: the engine side only. How temperspec's own steps, prompts, rules, skills and checks are written is temperspec's design, not this set's. A need counts as covered when a workflow package can meet it through declared data and the engine's public interface, with no engine edit (OVR-B10).

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S6 | This design: specs `overview`, `contracts`, `workflow-model`, `compiler-and-flow`, `prompt-rendering`, `judge-and-verdict`, `independence-guard`, `gate-and-human`, `budgets-and-failures`, `durability-and-resume`, `executor-interface`, `executor-claude-code`, `executor-antigravity`, `workspace-and-concurrency`, `security`, `observability-and-cost`, `self-improvement`, `engine-cli`, `lifecycle-and-evals`, `plugin-shell`, `executor-messages-api`, `executor-agent-sdk`, `tool-host`, `run-options`, `lifecycle-hooks`, `session-contract`, `schedule-timing-formats`, `run-events`, `run-detail-document`, `run-control`, `local-observability-store`, `central-run-stats`, `telemetry-export`, `improvement-proposals`, `feedback-and-judge-reliability`, `workflow-lessons`, `improvement-data`, `session-review`, `orchestration`, `orchestrator-skill`, `judge-calibration`, `eval-suites`, `workflow-audit`, `audit-rule-catalog`, `tool-surface-audit`, `prompt-audit`, `engine-update`, `version-metadata`, `state-and-run-migration`, `workflow-upgrade`, `upgrade-workflow`, `lifecycle-skills`, `script-units-and-hybrid-steps`, `council-unit`, `contest-unit`, `ask-unit` and `flow-extensions`, ADRs `standalone-design-assumptions`, `langgraph-graph-runtime`, `workflows-as-data`, `four-nodes-per-unit`, `independent-judge-engine-verdict`, `executors-as-capability-adapters`, `two-first-class-executors`, `portable-model-aliases`, `normalized-session-event-stream`, `judge-isolation-per-executor`, `isolated-config-home-for-antigravity`, `cost-when-executor-reports-tokens-only`, `cross-executor-judging`, `sqlite-checkpointer`, `exit-codes-as-caller-contract`, `portable-authoring-surface`, `artifact-type-suffixes`, `add-messages-api-and-agent-sdk-executors`, `in-process-executors-run-in-a-worker-process`, `engine-owned-tool-loop-for-the-messages-api`, `scope-of-planned-work`, `observers-read-files-not-sockets`, `local-activity-journal-with-tool-input-summaries`, `one-local-store-layout-with-a-manifest`, `cross-machine-stats-through-opt-in-sinks`, `telemetry-export-as-otel-genai-without-content`, `in-process-observers-and-wider-hook-events`, `stop-verb-as-the-only-observer-control`, `own-observability-first-export-deferred`, `improvement-closes-through-measured-proposals`, `steps-and-their-graders-change-apart`, `lessons-are-versioned-workflow-content`, `improvement-data-is-a-requirement-on-the-run-store`, `paired-trial-on-a-fixed-case-set`, `orchestration-is-data-run-by-a-model-free-supervisor`, `orchestration-state-is-a-file-and-an-event-log`, `attention-batched-waking-of-the-orchestrating-session`, `batch-is-a-one-node-orchestration`, `pauses-stay-with-the-person-failures-follow-node-policy`, `take-script-steps-attention-and-composition-from-archon`, `graduate-a-workflow-from-local-to-pipeline-by-measured-criteria`, `judges-accepted-on-labelled-error-rates`, `calibration-cases-split-tune-and-holdout`, `judge-robustness-by-metamorphic-variants`, `judge-graded-rates-carry-the-judges-error`, `eval-graders-in-a-fixed-order-of-trust`, `advisory-read-only-audit-verb-in-three-layers`, `audit-rules-are-a-fixed-catalog-keyed-to-causes`, `tool-audit-compares-grant-need-and-use`, `history-findings-need-a-minimum-sample`, `audit-joins-existing-checks-and-files-nothing`, `side-by-side-engine-environments-switched-atomically`, `threads-move-to-the-new-engine-at-resume-unless-a-release-pins-them`, `typed-version-metadata-on-both-sides`, `upgrade-by-transforms-first-and-a-gated-model-workflow-for-the-rest`, `an-upgrade-is-done-when-model-free-checks-pass`, `registered-workflows-are-reinstalled-and-pinned-never-lost`, `lifecycle-skills-drive-plugin-commands-then-engine-verbs`, `new-node-kinds-keep-the-gated-unit`, `council-is-a-gated-step-with-engine-tallied-outcomes`, `contest-picks-a-candidate-by-the-gates-own-judge`, `ask-unit-takes-a-persons-input-as-an-artifact`, `flow-extensions-for-langgraph-parity` and `cache-only-model-free-script-results-per-thread` | Design set on `main` | [overview](../specs/overview.spec.md) |
| S7 | Earlier gap reviews: research `planned-work-coverage` (planned work), research `design-gap-review` (design gaps, U1 check callables), research `node-types-against-langgraph` (node types) | Research notes | [research `planned-work-coverage`](planned-work-coverage.rsrch.md), [research `design-gap-review`](design-gap-review.rsrch.md), [research `node-types-against-langgraph`](node-types-against-langgraph.rsrch.md) |
| S9 | research `claude-code-cli-headless` F20: a resumed retry carries the whole conversation, so it costs more than a fresh session told the last report | Research note | [research `claude-code-cli-headless`](claude-code-cli-headless.rsrch.md) |

## Key findings

### F1 The shape of temperspec

| # | Finding | Confidence |
|---|---|---|
| F1.1 | temperspec is seven model steps in a line, each followed by a deterministic check and an independent read-only judge, two routes that skip a step (discovery, release), one sequential map over plan phases with a join, five back-edges allowed once each, and a model-free final stage that pushes and opens a draft pull request. | confirmed |
| F1.2 | Its gates do more than read files: the code gate runs the plan's verification commands itself under a time budget, with process-tree kill, output to file, reuse on an unchanged tree and "not finished" exits that make the check MAYBE, and the judge reads that run as evidence. | confirmed |
| F1.3 | Steps hand four single-line values to the run (gap list, route, story line, task detail); routes and checks read such values (route, release-track value, tests-passed value), and one gate records a fact a later gate measures from (the code gate's commit for the release gate). | confirmed |
| F1.4 | Steps declare skills as tools (spec authoring, decision records, test fixing) and use a cheaper survey subagent. | confirmed |
| F1.5 | Three engine limits bear on temperspec: an upstream claim or a judge's attribution is offered only to a step that ran, so a spec defect after a skipped discovery spends a budget or blocks; an expand attempt that fails its check costs a whole new attempt; and the code-mode router needs a generic conditional route in the engine with per-arm session options, a shadow mode and escalation from one arm to the other. | confirmed |

### F2 Coverage map

Status: **covered** (the design meets it today), **gap** (missing or partial; the closing document is named), **temperspec** (the workflow's own design, nothing needed from the engine), **settings thread** (handled by the parallel design of configuration overrides and reruns, which takes specs `run-settings-and-overrides`, `reruns-and-feedback`, `worktree-mode`, `schedules` and `schedule-ticks-and-unattended-fires` and ADRs `one-catalog-of-run-settings-over-fixed-layers`, `overrides-never-change-what-verifies-the-work`, `threads-snapshot-settings-and-reapply-them-on-resume`, `rewind-on-the-thread-rerun-as-a-linked-fork` and `feedback-can-be-a-lasting-ruling`), **open** (left open, with its owner).

#### Packaging, start and workspace

| # | temperspec need | Engine design | Status |
|---|---|---|---|
| T1 | Depends on the engine only; registers once; validated with routing metadata | [WFM](../specs/workflow-model.spec.md), [UPD-B20 to UPD-B24](../specs/engine-update.spec.md), C8 | covered |
| T2 | Declared interface: three start examples, prerequisites, a compatibility stamp | [CON-B9](../specs/contracts.spec.md), [VER](../specs/version-metadata.spec.md) | covered |
| T3 | A diagram generated from the definition, with a currency test | [CMP-B6](../specs/compiler-and-flow.spec.md), [LIF](../specs/lifecycle-and-evals.spec.md) | covered |
| T4 | Skills and agents loaded by plugin path, never bare name | [SHL-B7, SHL-B8, SHL-B11](../specs/plugin-shell.spec.md) | covered |
| T5 | The engine's repository setup adds only its state-root ignore rule; the SDD scaffold is the workflow's bootstrap | [SHL](../specs/plugin-shell.spec.md) project bootstrap, [LOS-B4](../specs/local-observability-store.spec.md) | covered; the bootstrap skill is temperspec |
| T6 | Start from a tracker key, a task file, or a label and a request; a check-only start that spends nothing | [CON-B9](../specs/contracts.spec.md) resolver, [CLI](../specs/engine-cli.spec.md) `run --check` | covered |
| T7 | One run, one worktree, one branch named by the task id and the workflow; an in-place mode | [WSP](../specs/workspace-and-concurrency.spec.md), [CON-B12, CON-B13](../specs/contracts.spec.md) | covered |
| T8 | Models on Claude Code headless through a cloud provider, by tier | Binding tables per executor, `provider` for library executors ([EXI](../specs/executor-interface.spec.md)) | covered |

#### Steps and prompts

| # | temperspec need | Engine design | Status |
|---|---|---|---|
| T9 | A fresh headless session per step; files hand over, not memory | [CMP](../specs/compiler-and-flow.spec.md), [PRM-B14](../specs/prompt-rendering.spec.md) | covered |
| T10 | A step declares tools and the engine grants exactly those in its worktree | [EXI](../specs/executor-interface.spec.md), [ECC-B7](../specs/executor-claude-code.spec.md) | covered |
| T11 | A step declares a **skill** as a tool | No skill capability in [CON-B11](../specs/contracts.spec.md) | **gap** → [ADR `skills-are-a-declared-tool-capability`](../adr/skills-are-a-declared-tool-capability.adr.md), CON-B11, executor tool maps |
| T12 | A survey subagent on a cheaper model | `subagent` capability covered; its model | settings thread (`subagent_model`) |
| T13 | Template fields for the task id, the item and the path of an earlier artifact (the code step finds the plan) | The template grammar allows "engine keys" but no spec lists them, and no field can name an upstream artifact | **gap** → [VAL](../specs/step-values-and-template-keys.spec.md) |
| T14 | A step hands single-line values to the run; a route, a check and the finalizer read them | Artifact kinds are `file`, `url`, `wiki_page`, `tracker_issue`, `pull_request` only | **gap** → [VAL](../specs/step-values-and-template-keys.spec.md) (`value` kind) |
| T15 | Every placeholder renders; a missing value is visible | [CON-B8](../specs/contracts.spec.md), [PRA](../specs/prompt-audit.spec.md) | covered |
| T16 | `BLOCKED` ends the step and asks a person, no judge | [PRM-B11](../specs/prompt-rendering.spec.md), [JDG-B1](../specs/judge-and-verdict.spec.md) | covered |
| T17 | An upstream claim against an earlier step | [PRM-B11](../specs/prompt-rendering.spec.md) for a unit that ran | **gap** for a route-skipped unit → [ADR `claims-may-target-a-route-skipped-back-target`](../adr/claims-may-target-a-route-skipped-back-target.adr.md) |
| T18 | Warnings pass as notes to the next step | [PRM-B6](../specs/prompt-rendering.spec.md), [JDG-B13](../specs/judge-and-verdict.spec.md) | covered |
| T19 | A check failure names the criterion, the place and the change, and the retry is told so | [PRM-B5](../specs/prompt-rendering.spec.md) does it for judge blockers; a check gives one evidence text | **gap** → [CHK](../specs/check-contract-and-command-runs.spec.md) findings |
| T20 | A prompt checked against its declared tools before a run | [WFM-B12](../specs/workflow-model.spec.md), [TSA](../specs/tool-surface-audit.spec.md), [PRA](../specs/prompt-audit.spec.md) | covered |
| T21 | Effort per step (low effort on phase) | `SessionOptions.effort` | covered |
| T22 | Long documents written as a skeleton then one edit per part; self-contained prompts; headless wording | — | temperspec |

#### Gates

| # | temperspec need | Engine design | Status |
|---|---|---|---|
| T23 | Check first; FAIL retries with no judge call; MAYBE leaves it to the judge | [JDG-B1](../specs/judge-and-verdict.spec.md), `CheckResult` | covered |
| T24 | What a check receives (artifacts, values, facts, workspace, git facts), what it may do, and its time limit | Unspecified since research `design-gap-review` U1 | **gap** → [CHK](../specs/check-contract-and-command-runs.spec.md), [ADR `checks-get-a-context-and-an-engine-command-runner`](../adr/checks-get-a-context-and-an-engine-command-runner.adr.md) |
| T25 | A check runs commands: list argv, no shell, declared prefixes or documented commands through one lookup the plan check shares | `command_resolver` ([WFM-B6](../specs/workflow-model.spec.md)); no runner for checks | **gap** → CHK `ctx.resolve`, `ctx.run` |
| T26 | A command run has a time budget, process-tree kill, output to a file, "not finished" exits, trimmed and path-scrubbed evidence, and reuse on an unchanged tree | Scripts have a timeout, group kill and a cache ([SCR](../specs/script-units-and-hybrid-steps.spec.md)); checks have none | **gap** → CHK-B12, CHK-B13 |
| T27 | The code gate's own test budget, set by the operator | — | settings thread (workflow settings); CHK reads it |
| T28 | An environment mark asks a person at once | `CheckResult.environmental`, [BUD-B1, BUD-B11](../specs/budgets-and-failures.spec.md) | covered |
| T29 | A gate records a fact a later gate reads (the code gate's commit) | — | **gap** → CHK facts |
| T30 | Mechanical criteria: the judge takes the check's evidence as given | [JDG-B6](../specs/judge-and-verdict.spec.md) in prose | **gap** (partial) → CHK `Criterion.mechanical` |
| T31 | A rule that cannot apply in the repository passes as not applicable | — | **gap** → CHK finding status `n_a` |
| T32 | An independent read-only judge on its own model with references and a stance | [JDG](../specs/judge-and-verdict.spec.md), [GRD](../specs/independence-guard.spec.md) | covered |
| T33 | The judge reads the gate's test run as evidence, not the step's claim | [JDG-B11, JDG-B12](../specs/judge-and-verdict.spec.md) subject | covered |
| T34 | Blocker and warning severity; criterion keys; check text hidden from the step | `Criterion`, [PRM-B2](../specs/prompt-rendering.spec.md) | covered |
| T35 | Defect attribution sends the run back to the step that wrote it | [JDG-B13](../specs/judge-and-verdict.spec.md) | covered; a skipped target → ADR `claims-may-target-a-route-skipped-back-target` |
| T36 | A blocker that needs no change or a person's ruling escalates, spending no retry | `no_change_policy` | covered |
| T37 | The judge reads the tracker on a remote server, else marks the quote unverifiable | `judge_mcp`, `UNVERIFIABLE`, `unverified_system` | covered; probes pending in ECC |
| T38 | An expand attempt checks its own plan inside the attempt | [PRM-B5](../specs/prompt-rendering.spec.md): a retry is fresh, never resumed | **gap** → [ADR `a-step-previews-its-own-check-in-the-attempt`](../adr/a-step-previews-its-own-check-in-the-attempt.adr.md), CHK-B17 |
| T39 | Calibration sets per gate, offline replay, live scoring, a judge moved to a stronger model | [JCL](../specs/judge-calibration.spec.md), [EVS](../specs/eval-suites.spec.md) | covered |
| T40 | Judges kept aligned with the review skills | — | temperspec (its own test) |

#### Flow

| # | temperspec need | Engine design | Status |
|---|---|---|---|
| T41 | Routes that skip discovery and release, with the longer path on a fault | Switch default arm ([CMP-B10 to CMP-B16](../specs/compiler-and-flow.spec.md)) | covered; the value it reads → VAL |
| T42 | Back-edges once per edge; a trip back rewrites in place and resets no worktree | [CMP](../specs/compiler-and-flow.spec.md), [BUD-B4](../specs/budgets-and-failures.spec.md) | covered |
| T43 | A sequential map over plan phases: items from the expand step, at most 20, one item when there is no phase heading, a check and narrow judge per item, a failed item retried alone, a passed item never rerun, a person asked per item, no back-edge from an item, the join as the next unit, every item rerun after a trip back to plan | One row in [CMP-B10 to CMP-B16](../specs/compiler-and-flow.spec.md); no `MapSpec` | **gap** → [MAP](../specs/map-unit.spec.md) |
| T44 | Resume one plan phase by instance with retry, proceed or stop | [HUM-B3](../specs/gate-and-human.spec.md) | covered |
| T45 | A single-session code mode picked by the operator | `--arm` ([CMP-B7](../specs/compiler-and-flow.spec.md)) | covered |
| T46 | A code-mode router: shadow mode that logs signals and the would-be arm, per-arm session options, escalation from single to per-phase, every choice recorded | Switch with a `route` record; no shadow, no arm overrides, no re-arming | **gap** → [SWM](../specs/measured-switches.spec.md), [ADR `switches-are-measured-before-they-route`](../adr/switches-are-measured-before-they-route.adr.md) |
| T47 | An approval pause after a chosen step; resume with retry and feedback | `--approve`, [HUM-B12](../specs/gate-and-human.spec.md) | covered |
| T48 | Three attempts per step; spent → stop on triage and discovery, ask on the rest | `retry_budget`, `on_budget_spent` | covered |
| T49 | A person's feedback copied as a ruling and shown to every later judge | Feedback reaches the next step and judge once | settings thread (persistent rulings) |
| T50 | An iteration budget across phase attempts; a drained run resumes at the pending item | Attempt cap ([BUD](../specs/budgets-and-failures.spec.md)) | covered; its override is the settings thread |

#### Finishing, operating, measuring

| # | temperspec need | Engine design | Status |
|---|---|---|---|
| T51 | A final stage that calls no model, never raises, ends exit 0 when it cannot publish, and reports opened, reused, pushed or skipped with a reason and the commands to run by hand | `finalizer` is a callable ref with no contract | **gap** → [FIN](../specs/finalizer-contract.spec.md) |
| T52 | The final stage reads the task, the plan's goal, the code report as a claim and the count of open warnings, never judge text | [SEC-B8 to SEC-B11](../specs/security.spec.md) publish boundary | **gap** (partial) → FIN context |
| T53 | The pull request's URL on the run log's final event, for the loop to read merged or closed | [FBK](../specs/feedback-and-judge-reliability.spec.md) `pr_state` reads it; nothing writes it | **gap** → FIN result |
| T54 | Publishing switches: no pull request, base branch, dry run, all recorded at start | `--dry-run` covers filing only | settings thread (workflow settings); FIN reads them |
| T55 | Step overrides per run for models, judges, timeouts, idle limits; auto-resume of a timeout stop | [ROP-B1 to ROP-B13](../specs/run-options.spec.md), [BUD-B6](../specs/budgets-and-failures.spec.md) | covered; layering is the settings thread |
| T56 | An idle limit per step, with a running tool counted as activity | `idle_s`; tool activity is an open question of [EXI](../specs/executor-interface.spec.md) | open (EXI owner) |
| T57 | Every session, gate and decision recorded; cost by step and criterion | [OBS](../specs/observability-and-cost.spec.md), [SIL](../specs/self-improvement.spec.md) | covered |
| T58 | Self-improvement: development mode, issue repository, filing switch, lens cadence, two sides, fingerprints, a cause for retry bursts | [SIL](../specs/self-improvement.spec.md) | covered |
| T59 | A literals check on prompt changes | [LIF](../specs/lifecycle-and-evals.spec.md), [PRP-B3](../specs/improvement-proposals.spec.md) | covered |
| T60 | Offline flow tests with scripted steps and judges on a scratch repository | [LIF-B4](../specs/lifecycle-and-evals.spec.md), [EVS](../specs/eval-suites.spec.md) | covered |
| T61 | Interpreter resolution and the right engine imported in a worktree's tests, visible as environment evidence | — | covered by CHK (`command_resolver` gets the main checkout; runs record the resolved program); the choice of interpreter is temperspec |
| T62 | Run tracking in the work tracker | A separate plugin ([research `planned-work-coverage`](planned-work-coverage.rsrch.md)) | covered by facts and hooks |
| T63 | Placeholder decision-record numbers, merge-time renumbering, spec cascades, reading-set lint, story template | — | temperspec |

## Conclusions

1. Of 63 needs, 38 are covered by the design on `main` (for T50 and T55 the override layering is left to the settings thread), 3 are temperspec's own, 4 belong to the settings thread (T12, T27, T49, T54), 1 is left open with its owner (T56), and **17 rows are gaps** that come down to **eight pieces of work**: the check contract, the in-attempt check preview, run values and template keys, the map, the finalizer, measured switches, the skill capability, and claims against a skipped target.
2. The largest gap is the **check**. temperspec's most valuable gate (the code gate) runs commands, records facts, marks criteria not applicable and hands findings to the retry, but the design never defined what a check receives or how it runs a command (research `design-gap-review` U1 was not closed). [CHK](../specs/check-contract-and-command-runs.spec.md) and [ADR `checks-get-a-context-and-an-engine-command-runner`](../adr/checks-get-a-context-and-an-engine-command-runner.adr.md) close T19, T24 to T26, T29 to T31 and T38.
3. **Run values** (T13, T14): a step can hand over files and links but not a one-line value, and a template can name no engine key or earlier artifact because neither is listed. [VAL](../specs/step-values-and-template-keys.spec.md) adds the `value` kind and the key list.
4. **The map** (T43) is one table row; temperspec's per-phase code depends on a dozen behaviours it leaves implicit. [MAP](../specs/map-unit.spec.md) states them.
5. **The finalizer** (T51 to T53) has no contract, though temperspec's whole review rests on it and the loop's `pr_state` signal needs its URL. [FIN](../specs/finalizer-contract.spec.md) gives it one.
6. The three engine limits of F1.5 are closed by decisions: claims and attributions may target a route-skipped back target ([ADR `claims-may-target-a-route-skipped-back-target`](../adr/claims-may-target-a-route-skipped-back-target.adr.md)); a step may run its own gate's check inside its attempt, without a resumed session, which research `claude-code-cli-headless` F20 shows to be dearer ([ADR `a-step-previews-its-own-check-in-the-attempt`](../adr/a-step-previews-its-own-check-in-the-attempt.adr.md)); and switches can run in shadow, carry per-arm overrides and re-arm on a spent budget ([ADR `switches-are-measured-before-they-route`](../adr/switches-are-measured-before-they-route.adr.md), [SWM](../specs/measured-switches.spec.md)).
7. Skills become a declared tool capability ([ADR `skills-are-a-declared-tool-capability`](../adr/skills-are-a-declared-tool-capability.adr.md)), so the steps that declare a skill keep the "grant exactly what is declared" rule.
8. Nothing found requires the engine to name temperspec (C8), and nothing found conflicts with the four-node unit (ADR `four-nodes-per-unit`, ADR `new-node-kinds-keep-the-gated-unit`).

## Open questions

| Question | Owner |
|---|---|
| Does Claude Code's headless permission layer accept a per-skill allow rule (`Skill(<plugin>:<name>)`), or only the bare `Skill` tool? Probe P-CC-8 in [ECC](../specs/executor-claude-code.spec.md). | Engine implementer |
| What is Antigravity's skill tool name and does its permission engine scope it? Probe P-AG-9 in [EAG](../specs/executor-antigravity.spec.md); until it answers, `skill:` is not in its tool map. | Engine implementer |
| Should a running tool count as activity for the idle watchdog (T56)? | Engine owner ([EXI](../specs/executor-interface.spec.md)) |

## References

[research `design-gap-review`](design-gap-review.rsrch.md) · [research `planned-work-coverage`](planned-work-coverage.rsrch.md) · [research `node-types-against-langgraph`](node-types-against-langgraph.rsrch.md)
