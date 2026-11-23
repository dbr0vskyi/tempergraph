# R-075 temperspec's needs against the engine design

## Problem statement

The owner asked on 2026-11-20 to verify that the engine design holds everything a temperspec workflow will need. temperspec is the spec-driven delivery workflow (task → triage → discovery → plan → expand → phase × N → code → release → draft pull request) that will run on tempergraph as a workflow package. This note answers:

1. What does temperspec require of the engine?
2. For each need, where does the engine design (specs 00 to 74 on `main`) cover it, and what is missing or only partly covered?
3. Which needs belong to temperspec itself, and which to the parallel thread on configuration overrides and reruns?

Scope: the engine side only. How temperspec's own steps, prompts, rules, skills and checks are written is temperspec's design, not this set's. A need counts as covered when a workflow package can meet it through declared data and the engine's public interface, with no engine edit (OVR-B10).

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S6 | This design: specs 00 to 74, ADR-0001 to ADR-0067 | Design set on `main` | [overview](../specs/00-overview.spec.md) |
| S7 | Earlier gap reviews: R-006 (planned work), R-011 (design gaps, U1 check callables), R-060 (node types) | Research notes | [R-006](R-006-planned-work-coverage.rsrch.md), [R-011](R-011-design-gap-review.rsrch.md), [R-060](R-060-node-types-against-langgraph.rsrch.md) |
| S9 | R-001 F20: a resumed retry measured +24% cost against a fresh session told the last report | Research note | [R-001](R-001-claude-code-cli-headless.rsrch.md) |

## Key findings

### F1 The shape of temperspec

| # | Finding | Confidence |
|---|---|---|
| F1.1 | temperspec is seven model steps in a line, each followed by a deterministic check and an independent read-only judge (43 criteria), two routes that skip a step (discovery, release), one sequential map over plan phases with a join, five back-edges allowed once each, and a model-free final stage that pushes and opens a draft pull request (S1, S4). | confirmed |
| F1.2 | Its gates do more than read files: the code gate runs the plan's verification commands itself under a time budget, with process-tree kill, output to file, reuse on an unchanged tree and "not finished" exits that make the check MAYBE, and the judge reads that run as evidence (S4 §9). | confirmed |
| F1.3 | Steps hand four single-line values to the run (gap list, route, story line, task detail); routes and checks read such values (route, release-track value, tests-passed value), and one gate records a fact a later gate measures from (the code gate's commit for the release gate) (S2 3.2, 3.9, 3.10). | confirmed |
| F1.4 | Steps declare skills as tools (spec authoring, decision records, test fixing) and use a cheaper survey subagent (S3 §4, §5). | confirmed |
| F1.5 | temperspec names three engine limits it lives with: an upstream claim or a judge's attribution is offered only to a step that ran, so a spec defect after a skipped discovery spends a budget or blocks (S4 7.4, S5 §11); an expand attempt that fails its check costs a whole new attempt (S5 14 B); and the code-mode router needs "a generic conditional route in the engine with per-arm session options", a shadow mode and escalation from one arm to the other (S5 14 B, 14 G). | confirmed |

### F2 Coverage map

Status: **covered** (the design meets it today), **gap** (missing or partial; the closing document is named), **temperspec** (the workflow's own design, nothing needed from the engine), **settings thread** (handled by the parallel design of configuration overrides and reruns, which takes specs 80 to 84 and ADR-0070 to ADR-0074), **open** (left open, with its owner).

#### Packaging, start and workspace

| # | temperspec need | Source | Engine design | Status |
|---|---|---|---|---|
| T1 | Depends on the engine only; registers once; validated with routing metadata | 12 | [WFM](../specs/02-workflow-model.spec.md), [UPD-B20 to UPD-B24](../specs/60-engine-update.spec.md), C8 | covered |
| T2 | Declared interface: three start examples, prerequisites, a compatibility stamp | 11, 12 | [CON-B9](../specs/01-contracts.spec.md), [VER](../specs/61-version-metadata.spec.md) | covered |
| T3 | A diagram generated from the definition, with a currency test | 7, 12 | [CMP-B6](../specs/03-compiler-and-flow.spec.md), [LIF](../specs/18-lifecycle-and-evals.spec.md) | covered |
| T4 | Skills and agents loaded by plugin path, never bare name | 4, 14 D | [SHL-B7, SHL-B8, SHL-B11](../specs/19-plugin-shell.spec.md) | covered |
| T5 | The engine's repository setup adds only its state-root ignore rule; the SDD scaffold is the workflow's bootstrap | 3.12, 14 F | [SHL](../specs/19-plugin-shell.spec.md) project bootstrap, [LOS-B4](../specs/33-local-observability-store.spec.md) | covered; the bootstrap skill is temperspec |
| T6 | Start from a tracker key, a task file, or a label and a request; a check-only start that spends nothing | 1, 11 | [CON-B9](../specs/01-contracts.spec.md) resolver, [CLI](../specs/17-engine-cli.spec.md) `run --check` | covered |
| T7 | One run, one worktree, one branch named by the task id and the workflow; an in-place mode | 2, 3.11 | [WSP](../specs/13-workspace-and-concurrency.spec.md), [CON-B12, CON-B13](../specs/01-contracts.spec.md) | covered |
| T8 | Models on Claude Code headless through a cloud provider, by tier | 0, 13 | Binding tables per executor, `provider` for library executors ([EXI](../specs/10-executor-interface.spec.md)) | covered |

#### Steps and prompts

| # | temperspec need | Source | Engine design | Status |
|---|---|---|---|---|
| T9 | A fresh headless session per step; files hand over, not memory | 0, 2 | [CMP](../specs/03-compiler-and-flow.spec.md), [PRM-B14](../specs/04-prompt-rendering.spec.md) | covered |
| T10 | A step declares tools and the engine grants exactly those in its worktree | 13 | [EXI](../specs/10-executor-interface.spec.md), [ECC-B7](../specs/11-executor-claude-code.spec.md) | covered |
| T11 | A step declares a **skill** as a tool | 4, 5 | No skill capability in [CON-B11](../specs/01-contracts.spec.md) | **gap** → [ADR-0078](../adr/0078-skills-are-a-declared-tool-capability.adr.md), CON-B11, executor tool maps |
| T12 | A survey subagent on a cheaper model | 5, 11 | `subagent` capability covered; its model | settings thread (`subagent_model`) |
| T13 | Template fields for the task id, the item and the path of an earlier artifact (the code step finds the plan) | 3.6, 3.8 | The template grammar allows "engine keys" but no spec lists them, and no field can name an upstream artifact | **gap** → [VAL](../specs/76-step-values-and-template-keys.spec.md) |
| T14 | A step hands single-line values to the run; a route, a check and the finalizer read them | 3.2, 3.9, 3.10 | Artifact kinds are `file`, `url`, `wiki_page`, `tracker_issue`, `pull_request` only | **gap** → [VAL](../specs/76-step-values-and-template-keys.spec.md) (`value` kind) |
| T15 | Every placeholder renders; a missing value is visible | 12 | [CON-B8](../specs/01-contracts.spec.md), [PRA](../specs/58-prompt-audit.spec.md) | covered |
| T16 | `BLOCKED` ends the step and asks a person, no judge | 3.6, 7.5 | [PRM-B11](../specs/04-prompt-rendering.spec.md), [JDG-B1](../specs/05-judge-and-verdict.spec.md) | covered |
| T17 | An upstream claim against an earlier step | 7.6 | [PRM-B11](../specs/04-prompt-rendering.spec.md) for a unit that ran | **gap** for a route-skipped unit → [ADR-0076](../adr/0076-claims-may-target-a-route-skipped-back-target.adr.md) |
| T18 | Warnings pass as notes to the next step | 8 | [PRM-B6](../specs/04-prompt-rendering.spec.md), [JDG-B13](../specs/05-judge-and-verdict.spec.md) | covered |
| T19 | A check failure names the criterion, the place and the change, and the retry is told so | 0, 8 | [PRM-B5](../specs/04-prompt-rendering.spec.md) does it for judge blockers; a check gives one evidence text | **gap** → [CHK](../specs/75-check-contract-and-command-runs.spec.md) findings |
| T20 | A prompt checked against its declared tools before a run | 14 D | [WFM-B12](../specs/02-workflow-model.spec.md), [TSA](../specs/57-tool-surface-audit.spec.md), [PRA](../specs/58-prompt-audit.spec.md) | covered |
| T21 | Effort per step (low effort on phase) | 3.8 | `SessionOptions.effort` | covered |
| T22 | Long documents written as a skeleton then one edit per part; self-contained prompts; headless wording | 3.6, 13 | — | temperspec |

#### Gates

| # | temperspec need | Source | Engine design | Status |
|---|---|---|---|---|
| T23 | Check first; FAIL retries with no judge call; MAYBE leaves it to the judge | 8 | [JDG-B1](../specs/05-judge-and-verdict.spec.md), `CheckResult` | covered |
| T24 | What a check receives (artifacts, values, facts, workspace, git facts), what it may do, and its time limit | 8, 9 | Unspecified since R-011 U1 | **gap** → [CHK](../specs/75-check-contract-and-command-runs.spec.md), [ADR-0075](../adr/0075-checks-get-a-context-and-an-engine-command-runner.adr.md) |
| T25 | A check runs commands: list argv, no shell, declared prefixes or documented commands through one lookup the plan check shares | 9, 14 A | `command_resolver` ([WFM-B6](../specs/02-workflow-model.spec.md)); no runner for checks | **gap** → CHK `ctx.resolve`, `ctx.run` |
| T26 | A command run has a time budget, process-tree kill, output to a file, "not finished" exits, trimmed and path-scrubbed evidence, and reuse on an unchanged tree | 9 | Scripts have a timeout, group kill and a cache ([SCR](../specs/70-script-units-and-hybrid-steps.spec.md)); checks have none | **gap** → CHK-B12, CHK-B13 |
| T27 | The code gate's own test budget, set by the operator | 9, 11 | — | settings thread (workflow settings); CHK reads it |
| T28 | An environment mark asks a person at once | 8, 9 | `CheckResult.environmental`, [BUD-B1, BUD-B11](../specs/08-budgets-and-failures.spec.md) | covered |
| T29 | A gate records a fact a later gate reads (the code gate's commit) | 3.10, 8 | — | **gap** → CHK facts |
| T30 | Mechanical criteria: the judge takes the check's evidence as given | 8 | [JDG-B6](../specs/05-judge-and-verdict.spec.md) in prose | **gap** (partial) → CHK `Criterion.mechanical` |
| T31 | A rule that cannot apply in the repository passes as not applicable | 8 | — | **gap** → CHK finding status `n_a` |
| T32 | An independent read-only judge on its own model with references and a stance | 8 | [JDG](../specs/05-judge-and-verdict.spec.md), [GRD](../specs/06-independence-guard.spec.md) | covered |
| T33 | The judge reads the gate's test run as evidence, not the step's claim | 3.9, 9 | [JDG-B11, JDG-B12](../specs/05-judge-and-verdict.spec.md) subject | covered |
| T34 | Blocker and warning severity; criterion keys; check text hidden from the step | 8 | `Criterion`, [PRM-B2](../specs/04-prompt-rendering.spec.md) | covered |
| T35 | Defect attribution sends the run back to the step that wrote it | 7.6 | [JDG-B13](../specs/05-judge-and-verdict.spec.md) | covered; a skipped target → ADR-0076 |
| T36 | A blocker that needs no change or a person's ruling escalates, spending no retry | 8, 14 C | `no_change_policy` | covered |
| T37 | The judge reads the tracker on a remote server, else marks the quote unverifiable | 8, 14 C | `judge_mcp`, `UNVERIFIABLE`, `unverified_system` | covered; probes pending in ECC |
| T38 | An expand attempt checks its own plan inside the attempt | 14 B | [PRM-B5](../specs/04-prompt-rendering.spec.md): a retry is fresh, never resumed | **gap** → [ADR-0077](../adr/0077-a-step-previews-its-own-check-in-the-attempt.adr.md), CHK-B17 |
| T39 | Calibration sets per gate, offline replay, live scoring, a judge moved to a stronger model | 8, 14 C | [JCL](../specs/50-judge-calibration.spec.md), [EVS](../specs/51-eval-suites.spec.md) | covered |
| T40 | Judges kept aligned with the review skills | 12 | — | temperspec (its own test) |

#### Flow

| # | temperspec need | Source | Engine design | Status |
|---|---|---|---|---|
| T41 | Routes that skip discovery and release, with the longer path on a fault | 7.4 | Switch default arm ([CMP-B10 to CMP-B16](../specs/03-compiler-and-flow.spec.md)) | covered; the value it reads → VAL |
| T42 | Back-edges once per edge; a trip back rewrites in place and resets no worktree | 7.6 | [CMP](../specs/03-compiler-and-flow.spec.md), [BUD-B4](../specs/08-budgets-and-failures.spec.md) | covered |
| T43 | A sequential map over plan phases: items from the expand step, at most 20, one item when there is no phase heading, a check and narrow judge per item, a failed item retried alone, a passed item never rerun, a person asked per item, no back-edge from an item, the join as the next unit, every item rerun after a trip back to plan | 3.8, 7.3 | One row in [CMP-B10 to CMP-B16](../specs/03-compiler-and-flow.spec.md); no `MapSpec` | **gap** → [MAP](../specs/77-map-unit.spec.md) |
| T44 | Resume one plan phase by instance with retry, proceed or stop | 11 | [HUM-B3](../specs/07-gate-and-human.spec.md) | covered |
| T45 | A single-session code mode picked by the operator | 11 | `--arm` ([CMP-B7](../specs/03-compiler-and-flow.spec.md)) | covered |
| T46 | A code-mode router: shadow mode that logs signals and the would-be arm, per-arm session options, escalation from single to per-phase, every choice recorded | 14 B, 14 G | Switch with a `route` record; no shadow, no arm overrides, no re-arming | **gap** → [SWM](../specs/79-measured-switches.spec.md), [ADR-0079](../adr/0079-switches-are-measured-before-they-route.adr.md) |
| T47 | An approval pause after a chosen step; resume with retry and feedback | 11 | `--approve`, [HUM-B12](../specs/07-gate-and-human.spec.md) | covered |
| T48 | Three attempts per step; spent → stop on triage and discovery, ask on the rest | 7.5 | `retry_budget`, `on_budget_spent` | covered |
| T49 | A person's feedback copied as a ruling and shown to every later judge | 7.5, 14 C | Feedback reaches the next step and judge once | settings thread (persistent rulings) |
| T50 | An iteration budget across phase attempts; a drained run resumes at the pending item | 11 | Attempt cap ([BUD](../specs/08-budgets-and-failures.spec.md)) | covered; its override is the settings thread |

#### Finishing, operating, measuring

| # | temperspec need | Source | Engine design | Status |
|---|---|---|---|---|
| T51 | A final stage that calls no model, never raises, ends exit 0 when it cannot publish, and reports opened, reused, pushed or skipped with a reason and the commands to run by hand | 3.11, 10 | `finalizer` is a callable ref with no contract | **gap** → [FIN](../specs/78-finalizer-contract.spec.md) |
| T52 | The final stage reads the task, the plan's goal, the code report as a claim and the count of open warnings, never judge text | 10 | [SEC-B8 to SEC-B11](../specs/14-security.spec.md) publish boundary | **gap** (partial) → FIN context |
| T53 | The pull request's URL on the run log's final event, for the loop to read merged or closed | 10, 11 | [FBK](../specs/41-feedback-and-judge-reliability.spec.md) `pr_state` reads it; nothing writes it | **gap** → FIN result |
| T54 | Publishing switches: no pull request, base branch, dry run, all recorded at start | 10, 11 | `--dry-run` covers filing only | settings thread (workflow settings); FIN reads them |
| T55 | Step overrides per run for models, judges, timeouts, idle limits; auto-resume of a timeout stop | 11 | [ROP-B1 to ROP-B13](../specs/23-run-options.spec.md), [BUD-B6](../specs/08-budgets-and-failures.spec.md) | covered; layering is the settings thread |
| T56 | An idle limit per step, with a running tool counted as activity | 14 E | `idle_s`; tool activity is an open question of [EXI](../specs/10-executor-interface.spec.md) | open (EXI owner) |
| T57 | Every session, gate and decision recorded; cost by step and criterion | 1, 13 | [OBS](../specs/15-observability-and-cost.spec.md), [SIL](../specs/16-self-improvement.spec.md) | covered |
| T58 | Self-improvement: development mode, issue repository, filing switch, lens cadence, two sides, fingerprints, a cause for retry bursts | 11, 14 G | [SIL](../specs/16-self-improvement.spec.md) | covered |
| T59 | A literals check on prompt changes | 11 | [LIF](../specs/18-lifecycle-and-evals.spec.md), [PRP-B3](../specs/40-improvement-proposals.spec.md) | covered |
| T60 | Offline flow tests with scripted steps and judges on a scratch repository | 12 | [LIF-B4](../specs/18-lifecycle-and-evals.spec.md), [EVS](../specs/51-eval-suites.spec.md) | covered |
| T61 | Interpreter resolution and the right engine imported in a worktree's tests, visible as environment evidence | 9, 14 E | — | covered by CHK (`command_resolver` gets the main checkout; runs record the resolved program); the choice of interpreter is temperspec |
| T62 | Run tracking in the work tracker | 14 G | A separate plugin ([R-006](R-006-planned-work-coverage.rsrch.md)) | covered by facts and hooks |
| T63 | Placeholder decision-record numbers, merge-time renumbering, spec cascades, reading-set lint, story template | 3.4, 3.5, 3.7, 14 F | — | temperspec |

## Conclusions

1. Of 63 needs, 38 are covered by the design on `main` (for T50 and T55 the override layering is left to the settings thread), 3 are temperspec's own, 4 belong to the settings thread (T12, T27, T49, T54), 1 is left open with its owner (T56), and **17 rows are gaps** that come down to **eight pieces of work**: the check contract, the in-attempt check preview, run values and template keys, the map, the finalizer, measured switches, the skill capability, and claims against a skipped target.
2. The largest gap is the **check**. temperspec's most valuable gate (the code gate) runs commands, records facts, marks criteria not applicable and hands findings to the retry, but the design never defined what a check receives or how it runs a command (R-011 U1 was not closed). [CHK](../specs/75-check-contract-and-command-runs.spec.md) and [ADR-0075](../adr/0075-checks-get-a-context-and-an-engine-command-runner.adr.md) close T19, T24 to T26, T29 to T31 and T38.
3. **Run values** (T13, T14): a step can hand over files and links but not a one-line value, and a template can name no engine key or earlier artifact because neither is listed. [VAL](../specs/76-step-values-and-template-keys.spec.md) adds the `value` kind and the key list.
4. **The map** (T43) is one table row; temperspec's per-phase code depends on a dozen behaviours it leaves implicit. [MAP](../specs/77-map-unit.spec.md) states them.
5. **The finalizer** (T51 to T53) has no contract, though temperspec's whole review rests on it and the loop's `pr_state` signal needs its URL. [FIN](../specs/78-finalizer-contract.spec.md) gives it one.
6. Three engine limits temperspec documents are closed by decisions: claims and attributions may target a route-skipped back target ([ADR-0076](../adr/0076-claims-may-target-a-route-skipped-back-target.adr.md)); a step may run its own gate's check inside its attempt, without a resumed session, which R-001 F20 measured as dearer ([ADR-0077](../adr/0077-a-step-previews-its-own-check-in-the-attempt.adr.md)); and switches can run in shadow, carry per-arm overrides and re-arm on a spent budget ([ADR-0079](../adr/0079-switches-are-measured-before-they-route.adr.md), [SWM](../specs/79-measured-switches.spec.md)).
7. Skills become a declared tool capability ([ADR-0078](../adr/0078-skills-are-a-declared-tool-capability.adr.md)), so the steps that declare a skill keep the "grant exactly what is declared" rule.
8. Nothing found requires the engine to name temperspec (C8), and nothing found conflicts with the four-node unit (ADR-0004, ADR-0062).

## Open questions

| Question | Owner |
|---|---|
| Does Claude Code's headless permission layer accept a per-skill allow rule (`Skill(<plugin>:<name>)`), or only the bare `Skill` tool? Probe P-CC-8 in [ECC](../specs/11-executor-claude-code.spec.md). | Engine implementer |
| What is Antigravity's skill tool name and does its permission engine scope it? Probe P-AG-9 in [EAG](../specs/12-executor-antigravity.spec.md); until it answers, `skill:` is not in its tool map. | Engine implementer |
| Should a running tool count as activity for the idle watchdog (T56)? | Engine owner ([EXI](../specs/10-executor-interface.spec.md)) |

## References

[R-011](R-011-design-gap-review.rsrch.md) · [R-006](R-006-planned-work-coverage.rsrch.md) · [R-060](R-060-node-types-against-langgraph.rsrch.md)
