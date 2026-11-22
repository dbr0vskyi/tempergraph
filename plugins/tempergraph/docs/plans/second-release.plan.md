---
goal: Build release 2 of tempergraph — measure a workflow, route it by complexity, escalate only on trusted evidence, promote it to stable mode, move a paused run between machines, and carry it across engine releases
version: 1
date_created: 2026-11-20
last_updated: 2026-11-21
owner: dbr0vskyi
status: Planned
tags: [release-plan, tempergraph]
tracker: none
spec: plugins/tempergraph/docs/specs/00-overview.spec.md
spec_commit: 26096be
task_id: second-release
---

# Release 2 plan

## 0. Hand-off

| Field | Value |
|---|---|
| Origin | Design session for the owner, 2026-11-20 (thread "Design release two scope and specs") |
| Research | [R-130 readiness and gaps](../research/R-130-release-two-readiness-and-gaps.rsrch.md), [R-120](../research/R-120-effort-ladders-and-one-step-model-escalation.rsrch.md), [R-121](../research/R-121-judge-model-by-risk-and-evidence-for-escalation.rsrch.md), [R-126](../research/R-126-routing-by-complexity-between-decompositions.rsrch.md) |
| Decisions | [ADR-0125 scope](../adr/0125-release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing.adr.md), [ADR-0121](../adr/0121-ladders-climb-only-on-trusted-substantive-evidence.adr.md) to [ADR-0124](../adr/0124-promotion-is-a-model-free-stamp-per-workflow-version.adr.md), [ADR-0091 executor](../adr/0091-first-release-ships-the-claude-executor-only.adr.md) |
| Spec, read at | [Overview](../specs/00-overview.spec.md) and the specs named in §1, at `26096be` plus this branch |
| Tracker | none |

**Problem statement.** Release 1 builds simple trusted workflows on one machine. Release 2 makes them measurable, adaptive and movable: eval suites, judges raised by risk, ladders that climb only on evidence, a choice between a simple and a detailed decomposition by complexity, promotion to stable mode, run state carried on a branch, Windows and non-git folders, and update and upgrade across engine releases. The owner added upgrade, judges and ladders, and complexity branching on 2026-11-20, then moved CI pipelines to a later release with state on a branch meanwhile.

**Decisions made.**

| Decision | Choice | Rationale |
|---|---|---|
| Scope | ADR-0090's release 2 forecast plus upgrade, LAD, JRK, CXR and PRO | Owner's ask ([ADR-0125](../adr/0125-release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing.adr.md)) |
| Executor | `claude` only | [ADR-0091](../adr/0091-first-release-ships-the-claude-executor-only.adr.md) |
| Pipelines | A later release; a paused run moves between machines by its state branch | [ADR-0124](../adr/0124-promotion-is-a-model-free-stamp-per-workflow-version.adr.md), [ADR-0126](../adr/0126-a-run-carries-a-scrubbed-thread-state-on-its-own-branch-and-deletes-it-when-done.adr.md) |
| Platforms | macOS, Linux; folders outside git. Native Windows is release 3 (owner, 2026-11-21) | [ADR-0127](../adr/0127-outside-git-the-state-root-is-found-by-walk-up-and-the-guard-hashes-files.adr.md), [ADR-0128](../adr/0128-windows-is-supported-natively-with-job-objects-and-probes-before-judges.adr.md) |
| Ladders | Evidence-gated effort ladder; one model step, last resort; the release 1 model list retired by a transform | Owner: "I don't want to increase model or efforts on any failure" ([ADR-0121](../adr/0121-ladders-climb-only-on-trusted-substantive-evidence.adr.md)) |
| Order | Switches, maps and ladders first, because CXR, UWF and PRO build on them | R-130 F1 |
| Plan shape | Tracks and phases only; each track's expanded plan is written when its specs pass status (EC-2) | temperspec 3.6 |

**Status: Built; the owner's own live checks pending.** Tracks R2-T1 to R2-T9 are built and pass offline (engine `0.2.0`), and every live check a cloud container can run passed on 2026-11-22 ([R-140](../research/R-140-release-three-readiness-and-gaps.rsrch.md) F1); what each track left open is in its code report under `tasks/` and in the status column of [plans/README.md](README.md). The owner approved this plan on 2026-11-21 with a trim (§1.3): EC-1 is met. The build follows the plan, task-note and test-first rules of the delivery workflow's rule files; each phase has a plan under `plans/r2-*.plan.md` and a report under `tasks/`. Live checks stay pending on the owner's machine and are never faked.

## 1. Requirements analysis

### 1.1 Entry conditions

| Id | Condition | Before | Owner |
|---|---|---|---|
| EC-1 | The owner accepts ADR-0125 (and ADR-0121 to ADR-0124), or edits them | Any code track | Owner |
| EC-2 | A track's specs are `ready-for-implementation`: its first phase turns each open question into a recorded default and sets the status (R-130 G5) | Each track | Implementer, owner may veto |
| EC-3 | Release 1's live checks that a track builds on are recorded ([live checks plan](live-checks.plan.md)) | The live half of each track | Owner's machine |
| EC-4 | Satisfied: WSP §2.4 with ADR-0127 and R-131; WIN with ADR-0128 and R-132 | R2-T8 | — |

### 1.2 Feature list

Every item release 2 ships. Items not built are refused with `not_in_release`, never ignored.

| # | Feature | Spec | Track | Was |
|---|---|---|---|---|
| I2-1 | Measured switches: shadow mode, per-arm overrides, re-arming | SWM | R2-T1 | X2-16 |
| I2-2 | Sequential map and item keys | MAP, VAL | R2-T1 | X2-15 |
| I2-3 | Complexity switches: measures, rules file and zones, arm contract, one-way re-arm, exploration, `report --switch` | CXR | R2-T1 | new |
| I2-4 | Effort ladder, climbing evidence, held causes, `xhigh`, `CheckFinding.kind` | LAD, CON, RST | R2-T2 | new |
| I2-5 | One-step model escalation, its stages and offer pause, `resume --escalate`, the escalation record | LAD, HUM, CLI | R2-T2 | new |
| I2-6 | Retirement of the retry-count model list and its transform | LAD §2.8, VER | R2-T2 | new (replaces BUD-B7) |
| I2-7 | Judge model by risk: rule, levels, floor, shadow, `report --risk` | JRK | R2-T3 | new |
| I2-8 | Eval suites and `evals run\|report\|grade`; live scoring, harvest and replay; eval skill | EVS, SHL | R2-T4 | X2-2 to X2-4 |
| I2-9 | Calibration and readiness per judge risk level | JCL, LIF, JRK | R2-T4 | new |
| I2-10 | Stages of a run, `promote-check --to local-stable`, promotion stamp; `--to pipeline` refused `not_in_release` | PRO, SUP §2.7 | R2-T5 | X2-1, pipelines moved later |
| I2-11 | `update`, rollback, `prune-engines`, update skill | UPD, LSK | R2-T6 | X2-5, X2-8 |
| I2-12 | Migrations and pins | MIG | R2-T6 | X2-6 |
| I2-13 | Changelog, detect rules and transforms | VER, WUP | R2-T6 | X2-7 |
| I2-14 | `upgrade` beyond `--check`, the built-in upgrade workflow, the upgrade skill | WUP, UWF, LSK | R2-T6 | X3-13, moved by the owner |
| I2-15 | Moved to release 3 (§1.3) | AUD, ARC, TSA | — | X2-9, X2-10 |
| I2-16 | Ask unit; event waits; `--pause-before`, deadlines, fallback target; parallel read-only branches | ASK, HUM, FLX | R2-T7 | X2-11 to X2-14 |
| I2-17 | `self-check` | CHK | R2-T7 | X2-18; script cache, audit judge and judge MCP views moved to release 3 (§1.3) |
| I2-18 | Lifecycle hooks, wider hook events | CLI, EVT | R2-T7 | X2-21; in-process observers moved to release 3 (§1.3) |
| I2-19 | Moved to release 3 (§1.3) | SCH §5, TCK | — | X2-22 |
| I2-20 | Moved to release 3 (§1.3) | WTR | — | X2-23 |
| I2-21 | State root outside git: walk-up or declared root, `in_place` only, manifest fingerprint, `needs_git` refusals | WSP §2.4 | R2-T8 | X2-24 |
| I2-22 | Moved to release 3 (§1.3) | WIN | — | X2-25 |
| I2-23 | Moved to release 3 (§1.3) | SRV §2.4, §5 | — | X2-26 |
| I2-24 | The loop's alias as a setting (R-130 G4) | RST, SIL | R2-T2 | divergence |
| I2-25 | Run state carried on its own branch: `--carry`, `carry push\|pull\|status\|drop`, lease, deletion at finish | CAR | R2-T5 | new, owner 2026-11-20 |
| I2-26 | Deliverables required per path; a repository-level command declaration; `GitFacts.pushed` set (R-130 G10 to G12) | WFM, CHK | R2-T7 | new, from the first authored workflow |
| I2-27 | Sizing: every step and judge states model, effort and why; `sizing` in the blueprint, `sizing-unassessed` in the audit (owner 2026-11-21) | SCF §2.1.1, ARC | R2-T2 | new |

### 1.3 Trim of 2026-11-21

The owner approved moving to release 3 every item that neither an owner ask nor the first authored workflow uses: native Windows, the schedules slice, worktree extras, the audit history layer and tool surface audit, the script cache, the sampled audit judge, judge MCP views, in-process observers and session review in stable mode. Their specs stay as designed; their fields and verbs are refused with `not_in_release`.

## 2. Tracks and phases

| Track | Component specs | Phases | Depends on | Kind |
|---|---|---|---|---|
| R2-T0 Live probes | LAD, PRO, and release 1's pending probes | R2-T0.1 | — | probe |
| R2-T1 Switches, maps and complexity | SWM, MAP, VAL, CXR | R2-T1.1–R2-T1.3 | EC-1 | code |
| R2-T2 Ladders | LAD, CON, RST, BUD, HUM, VER | R2-T2.1–R2-T2.3 | R2-T1.1 (arm overrides) | code |
| R2-T3 Judge by risk | JRK, JDG, JCL | R2-T3.1–R2-T3.2 | R2-T2.2 (floor) | code |
| R2-T4 Evals | EVS, JCL, LIF, SHL | R2-T4.1–R2-T4.3 | R2-T3 | code |
| R2-T5 Promotion and carried state | PRO, SUP, CAR | R2-T5.1–R2-T5.2 | R2-T2, R2-T3, R2-T4, R2-T1.3 | code |
| R2-T6 Update and upgrade | UPD, MIG, VER, WUP, UWF, LSK | R2-T6.1–R2-T6.4 | R2-T1.2 (UWF maps), R2-T4 (fixtures) | code |
| R2-T7 Node features and hooks | ASK, HUM, FLX, CHK, WFM, CLI, EVT | R2-T7.1–R2-T7.4 | EC-1 | code |
| R2-T8 Outside git | WSP | R2-T8.1 | — | code |
| R2-T9 Release | all | R2-T9.1–R2-T9.2 | every track | release |

Milestones: **N1** after R2-T1 and R2-T2, a workflow with a complexity switch and an effort ladder runs on stand-ins, and its report shows arms, zones and rungs. **N2** after R2-T4, `evals bar` grades every risk level and `evals run` passes on the examples. **N3** after R2-T5, the example workflow is stamped for `local-stable` on fixture data, and a carried run pauses on one state root and finishes on another, leaving no state branch. **N4** after R2-T6, a release 1 workflow with a model list is upgraded by `upgrade` and passes V1 to V7.

### R2-T0 Live probes

| Probe | Command, on the owner's machine | Pass |
|---|---|---|
| P-LAD-1 | For each alias of the binding table: `claude -p --model <alias> --effort xhigh` and `--effort max` on a one-line prompt, reading `applied_options` from the stream | Each effort is applied, or the CLI names it unsupported for that alias; recorded per alias in ECC §2.7 |
| P-WIN-1 to P-WIN-3 | Release 3, with Windows | — |
| P-PRO-1 | Moved to the pipeline release with `--to pipeline` | — |

### R2-T1 Switches, maps and complexity

#### R2-T1.1 Measured switches
Goal: SWM-AC-1 to AC-3, with `effort_ladder` and `escalation` accepted in `arm_overrides` (validated, applied in R2-T2).

#### R2-T1.2 Sequential map and item keys
Goal: MAP-AC-1 to AC-4 for the sequential form; VAL item keys; concurrent mode stays `not_in_release`.

#### R2-T1.3 Complexity switches
Goal: CXR-AC-1 to AC-5: stock measures, the rules file and its repository override, zones, arm contract at validation, one-way re-arm on LAD evidence (stand-in evidence until R2-T2.1), exploration, `report --switch`.

### R2-T2 Ladders

#### R2-T2.1 Effort ladder
Goal: LAD-AC-1, AC-2, AC-4: `xhigh`, `CheckFinding.kind`, climbing evidence, every held cause, resets, preflight of each rung, the `ladder` record and `ladder_decision`.

#### R2-T2.2 Escalation
Goal: LAD-AC-3, AC-5: E1 to E9, stages from PRO §2.1 (stand-in until R2-T5), the offer pause and `resume --escalate` with PRV relay rules, the escalation record, rung-0 figures in `report`.

#### R2-T2.3 Model list retirement
Goal: LAD-AC-6: `model-ladder-retired`, the changelog entry and the `model_list_to_escalation` transform; the loop alias setting (I2-24).

### R2-T3 Judge by risk

#### R2-T3.1 Rule, levels and resolution
Goal: JRK-AC-1 to AC-3: `RiskContext`, stock rules, levels, fault and floor, shadow mode, the `judge_risk` record.

#### R2-T3.2 Calibration per level
Goal: JRK-AC-4: scores, states and `evals bar` per level; LIF-B6 per level.

### R2-T4 Evals

#### R2-T4.1 Suites and grading
Goal: EVS suite kinds, grader order, `evals run|report|grade`.

#### R2-T4.2 Live scoring, harvest and replay
Goal: EVS live caps and replay; JCL harvest of `contradicted` labels.

#### R2-T4.3 Eval skill
Goal: the eval skill of SHL.

### R2-T5 Promotion

#### R2-T5.1 Stages and the check
Goal: PRO-AC-1 to AC-4 and AC-6, to `local-stable`: stage of a run, window, P1 to P12, `promotion.json`, voiding.

#### R2-T5.2 Carried state
Goal: CAR-AC-1 to AC-4 with two state roots and a bare remote; `--carry`, the four `carry` verbs, the lease and deletion at finish. PRO §2.5 and §2.6 wait for the pipeline release.

### R2-T6 Update and upgrade

#### R2-T6.1 Update and rollback
Goal: UPD's release 2 part, the registry reinstall and pins, the update skill.

#### R2-T6.2 Migrations
Goal: MIG layouts, threads across releases, workflow change under a paused thread.

#### R2-T6.3 Changelog and transforms
Goal: VER-AC-3 (task 8.3.6 of the T8 plan), every transform of VER §2.3.4 with fixtures.

#### R2-T6.4 Upgrade, the upgrade workflow and skill
Goal: WUP phases 4 to 7, UWF, the upgrade skill of LSK; N4 on the retired model list.

### R2-T7 Node features and hooks

#### R2-T7.1 Ask, waits, breakpoints, deadlines, fallback
#### R2-T7.2 Parallel read-only branches, `self-check`
#### R2-T7.3 Deliverables per path, repository command declaration, `GitFacts.pushed` (I2-26)
#### R2-T7.4 Lifecycle hooks
Goal for each: the acceptance criteria of the specs named in §1.2 for its items.

### R2-T8 Outside git

#### R2-T8.1 State root outside git
Goal: WSP-AC-5 and every row of WSP §2.4.

### R2-T9 Release

#### R2-T9.1 Examples and docs
Goal: the example workflows gain a complexity switch and an effort ladder where they fit, the guides cover ladders, risk, routing and promotion, and the engine's suite runs them.

#### R2-T9.2 Release files
Goal: the release record, the changelog with the model-list entry, the version bump.

## 3. Risks

| Risk | Mitigation |
|---|---|
| Ladders rarely climb because few judges are `accepted` | By design; the offer in `local-dev` gathers labelled evidence |
| Calibration cost grows with judge levels | Levels are 2 or 3; shadow mode before route mode |
| Release 2 too large | R2-T8.3 moves to release 3 first, then the rest of R2-T8 |
