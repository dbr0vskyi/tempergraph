---
goal: Build release 3 of tempergraph — a workflow that contains another workflow, runs independent work at once within its cap, asks several sessions for one hard answer, fires on a schedule, and is re-graded in the pull request's pipeline
version: 1
date_created: 2026-11-22
last_updated: 2026-11-22
owner: dbr0vskyi
status: In progress
tags: [release-plan, tempergraph]
tracker: none
spec: plugins/tempergraph/docs/specs/00-overview.spec.md
spec_commit: da5584c
task_id: third-release
---

# Release 3 plan

## 0. Hand-off

| Field | Value |
|---|---|
| Origin | Release 3 preparation for the owner, 2026-11-22 (thread "Verify release two and plan release three") |
| Research | [R-140 readiness and gaps](../research/R-140-release-three-readiness-and-gaps.rsrch.md); R-135 (pull-request gate, in review) |
| Decisions | [ADR-0132 scope](../adr/0132-release-three-is-workflows-that-compose-run-in-parallel-and-grade-in-the-pipeline.adr.md), [ADR-0133 sub-workflows](../adr/0133-a-sub-workflow-runs-inside-its-parents-thread-workspace-and-cap.adr.md); ADR-0130 and ADR-0131 when the pull-request gate is accepted |
| Spec, read at | [Overview](../specs/00-overview.spec.md) and the specs named in §1, at `da5584c` plus this branch |
| Tracker | none |

**Problem statement.** Release 2 makes one workflow measurable, adaptive and movable. The first real workflow now waits for four engine capabilities: a workflow inside a workflow, coding phases in parallel, several answers to a hard choice, and a scheduled audit (R-140 F2). The owner asked for a gate that re-grades a run's result on its pull request. Running release 2 found two defects that parallel work would make worse: a step inside a host session reaches more than it declares, and the cost cap checks only finished spend (R-140 F4, F5).

**Decisions made.**

| Decision | Choice | Rationale |
|---|---|---|
| Scope | What workflows and the owner ask for, release 2's findings, and the items moved from release 2 | [ADR-0132](../adr/0132-release-three-is-workflows-that-compose-run-in-parallel-and-grade-in-the-pipeline.adr.md) |
| Executor | `claude` only; other executors in release 4 | ADR-0132 |
| Orchestration | Release 4 | ADR-0132: needs sub-workflows and the reserving cap first |
| Sub-workflow shape | A subgraph inside the parent's thread, workspace and cap | [ADR-0133](../adr/0133-a-sub-workflow-runs-inside-its-parents-thread-workspace-and-cap.adr.md) |
| Order | Cap and reach first, because every parallel shape relies on them | R-140 F4, F5 |
| Plan shape | Tracks and phases only; each track's expanded plan is written when its specs are ready (EC-2) | As in release 2 |

**Status: In progress.** R3-T1.1, R3-T1.2, R3-T8.1 to R3-T8.3 and I3-15 are built (2026-11-22). R3-T2.3 and with it track R3-T2 are built (2026-11-22). R3-T3.1 and R3-T3.2 are built (2026-11-23), and with them track R3-T3. R3-T4.1 and R3-T4.2 are built (2026-11-23), and with them track R3-T4. R3-T5.1 and R3-T5.2 are built (2026-11-23), and with them track R3-T5. EC-1 is met: the owner accepted ADR-0132 and ADR-0133 on 2026-11-22. Each track starts when its specs are ready (EC-2). What is left is tracked as GitHub issues labelled `release: 3` (2026-11-23): R3-T0 probes [#99](https://github.com/dbr0vskyi/tempergraph/issues/99), [#104](https://github.com/dbr0vskyi/tempergraph/issues/104), [#106](https://github.com/dbr0vskyi/tempergraph/issues/106), [#107](https://github.com/dbr0vskyi/tempergraph/issues/107); R3-T6 [#67](https://github.com/dbr0vskyi/tempergraph/issues/67); R3-T7 [#68](https://github.com/dbr0vskyi/tempergraph/issues/68) and [#69](https://github.com/dbr0vskyi/tempergraph/issues/69); R3-T9 [#70](https://github.com/dbr0vskyi/tempergraph/issues/70); R3-T10 [#71](https://github.com/dbr0vskyi/tempergraph/issues/71) and [#72](https://github.com/dbr0vskyi/tempergraph/issues/72); known gaps of built tracks [#73](https://github.com/dbr0vskyi/tempergraph/issues/73) to [#80](https://github.com/dbr0vskyi/tempergraph/issues/80).

## 1. Requirements analysis

### 1.1 Entry conditions

| Id | Condition | Before | Owner |
|---|---|---|---|
| EC-1 | The owner accepts ADR-0132 and ADR-0133, or edits them | Any code track | Owner |
| EC-2 | A track's specs are ready: its first phase gives each open question of its specs an `Until answered:` default (R-140 F6; specs carry no status since the spec migration) | Each track | Implementer, owner may veto |
| EC-3 | The owner answers R-135's questions; ADR-0130 and ADR-0131 are accepted and spec 98 is written | R3-T7 | Owner |
| EC-4 | P-WIN-1 to P-WIN-3 have run on a Windows machine | R3-T9 | Owner's machine |

### 1.2 Feature list

Every item release 3 ships. Items not built are refused with `not_in_release`, never ignored.

| # | Feature | Spec | Track | Was |
|---|---|---|---|---|
| I3-1 | A session reserves its cap or its projection before it starts; a reservation over the cap waits or drains | BUD-B12, CST | R3-T1 | new (R-140 F5) |
| I3-2 | A step reaches only what it declares inside a host session: host variables dropped, `--tools` always sent, no added directories; probes P-CC-10, P-CC-11 | ECC-B14 | R3-T1 | new (R-140 F4) |
| I3-3 | Sub-workflow units: declaration, version record, inputs and `produces`, child records, pauses, upstream defects, child outcome, findings | SWF, CMP, MIG, OUT | R3-T2 | CMP-B10 to CMP-B16 row |
| I3-4 | Writer branches with their own worktrees and the merge after | FLX, WTR | R3-T3 | ADR-0090 release 3 |
| I3-5 | The concurrent map mode, with item worktrees for a writing map; a read-only concurrent map for parallel reading over a list | MAP | R3-T3 | ADR-0090 release 3 |
| I3-6 | Council and contest units | CNL, CTS | R3-T4 | ADR-0090 release 3 |
| I3-7 | Schedules and unattended fires, the release 2 slice and the rest | SCH, TCK | R3-T5 | moved from release 2 |
| I3-8 | CI pipelines: the `pipeline` stage, `promote-check --to pipeline`, the regressed watch, P-PRO-1 | PRO, SUP-B17 | R3-T6 | moved from release 2 |
| I3-9 | The pull-request gate: `pr-gate run\|init\|doctor`, GitHub Actions, `report` mode first | spec 98 (to write), SEC-B8 to SEC-B11 | R3-T7 | new, owner's ask |
| I3-10 | Script cache, sampled audit judge, judge MCP views | SCR, JDG-B7, GRD | R3-T8 | moved from release 2 |
| I3-11 | In-process observers; worktree extras; session review in stable mode | EVT, WTR, SRV | R3-T8 | moved from release 2 |
| I3-12 | The audit history layer and the tool surface audit | AUD, ARC, TSA | R3-T8 | moved from release 2 |
| I3-13 | Native Windows | WIN | R3-T9 | moved from release 2 |
| I3-14 | A complexity switch in an example workflow | CXR | R3-T10 | moved from R2-T9.1 |
| I3-15 | `on_deadline: defaults` for ask units: each unanswered question takes its default and the unit proceeds with a complete `answers` artifact | FLX-B8, ASK | R3-T8 | new, asked by the first real workflow. Status: built. FLX-B8, FLX-B11 and ASK-B10 to ASK-B13, proved by FLX-AC5 to FLX-AC7 and ASK-AC5 to ASK-AC8 in `plugins/tempergraph/engine/tests/test_ask_wait.py` |

### 1.3 Excluded

| # | Item | Goes to | Why |
|---|---|---|---|
| X3-1 | Antigravity, Messages API and Agent SDK executors | Release 4 | ADR-0132: no asker, no probe run |
| X3-2 | Orchestration of runs and the orchestrator skill | Release 4 | ADR-0132: builds on I3-1 and I3-3 |
| X3-3 | A child workflow's finalizer | Not planned | SWF-B8: the parent's finalizer owns side effects |
| X3-4 | Pull-request gate: GitLab, `block` mode, judge reasons | Later in R3-T7, or release 4 | R-135: after the first slice, and only with the owner's answers |

## 2. Tracks and phases

| Track | Component specs | Phases | Depends on | Kind |
|---|---|---|---|---|
| R3-T0 Live probes | ECC (P-CC-10, P-CC-11), PRO (P-PRO-1), WIN | R3-T0.1 | — | probe |
| R3-T1 Cap and reach | BUD, CST, ECC | R3-T1.1–R3-T1.2 | EC-1 | code |
| R3-T2 Sub-workflows | SWF, CMP, MIG, OUT, OBS | R3-T2.1–R3-T2.3 | R3-T1.1 | code |
| R3-T3 Writer branches and the concurrent map | FLX, MAP, WTR | R3-T3.1–R3-T3.2 | R3-T1 | code |
| R3-T4 Council and contest | CNL, CTS | R3-T4.1–R3-T4.2 | R3-T1.1 | code |
| R3-T5 Schedules | SCH, TCK | R3-T5.1–R3-T5.2 | EC-1 | code |
| R3-T6 Pipelines | PRO, SUP | R3-T6.1 | R3-T5.2 (unattended credentials) | code |
| R3-T7 Pull-request gate | spec 98, SEC | R3-T7.1–R3-T7.2 | EC-3 | code |
| R3-T8 Moved from release 2 | SCR, JDG, GRD, EVT, WTR, SRV, AUD, ARC, TSA | R3-T8.1–R3-T8.3 | EC-1 | code |
| R3-T9 Windows | WIN | R3-T9.1 | EC-4 | code |
| R3-T10 Release | all | R3-T10.1–R3-T10.2 | every track | release |

Milestones: **N1** after R3-T1, two parallel branches started just under the cap leave the run under it, and a step started from inside a host session lists only its declared tools. **N2** after R3-T2, a fixture parent runs a fixture child, pauses inside it, and resumes on a second state root (SWF-AC3). **N3** after R3-T3 and R3-T4, a writing map runs its items at once in their own worktrees and merges them, and a contest picks one of three answers within the cap. **N4** after R3-T5 to R3-T7, a scheduled fire runs a workflow unattended, and the pull-request gate posts a report on a fixture pull request.

### R3-T0 Live probes

| Probe | Command, on a machine with a signed-in `claude` | Pass |
|---|---|---|
| P-CC-10 | From inside a Claude Code session, launch a step with `--tools Read` and the host's variables dropped; read `system/init`, then try a read outside the workspace | `system/init` lists only `Read`; the outside read is refused |
| P-CC-11 | `claude -p --bare` with a user-scope plugin installed; read `system/init` | The plugin's tools are absent, or the row stays `isolates_user_config: false` |
| P-PRO-1 | As in PRO | As in PRO |
| P-WIN-1 to P-WIN-3 | On Windows, as in WIN | As in WIN |

### R3-T1 Cap and reach

#### R3-T1.1 Reservations
Goal: BUD-B12 for parallel read-only branches (the only concurrent shape release 2 has), with a test that two branches started under the cap never end above it by more than the reservation's error.

Status: built. BUD-B12 to BUD-B15 for parallel read-only branches, proved by BUD-AC2, BUD-AC5, BUD-AC6 and BUD-AC7 in `plugins/tempergraph/engine/tests/test_reservations.py`; the per-unit projection tier remains.

#### R3-T1.2 Step reach
Goal: ECC-B14, tested by argv and environment scans; the live half is P-CC-10.

Status: built. ECC-B14 for a step, a retry and a judge launch (host names dropped from the child's environment, `--tools` on every step launch, no `--add-dir`), proved by ECC-AC6 in `plugins/tempergraph/engine/tests/test_claude_executor.py`; the live half, P-CC-10 and P-CC-11, is left.

### R3-T2 Sub-workflows

#### R3-T2.1 Declaration and validation
Goal: SWF-B7, SWF-B6, SWF-B8, SWF-B6.

Status: built. SWF-B6, SWF-B7 and SWF-B12 (a declared sub-workflow unit, every refusal of a bad child before spend, and `{<unit>.<key>}` in a template), proved by SWF-AC1 and SWF-AC5 in `plugins/tempergraph/engine/tests/test_subworkflow_validate.py`, `test_subworkflow_inputs.py` and `test_subworkflow_template.py`.

#### R3-T2.2 Running a child
Goal: SWF-B8, SWF-B2, SWF-B5, SWF-B1 to B5, SWF-AC1 and AC-2.

Status: built. SWF-B1 to SWF-B5, SWF-B8 and SWF-B10 (a child run as one unit in the parent's workspace, thread and cap; its pause, its changed or removed version under a paused parent, its spend, its upstream defect and its verdict at the unit's gate; its records, version and outcome record in the parent's; its finalizer never run and its outcome gate always run, with the `subworkflow-finalizer-skipped` warning), proved by SWF-AC1 and SWF-AC2 in `plugins/tempergraph/engine/tests/test_subworkflow_run.py`, `test_subworkflow_record.py`, `test_subworkflow_pause.py`, `test_subworkflow_cap.py` and `test_subworkflow_gate.py`.

#### R3-T2.3 Measures and carrying
Goal: SWF-B9, SWF-AC3.

Status: built. SWF-B9 (a child's judges on its own bindings and calibration cases, its findings filed to the child workflow with the parent named, its outcome record counted in its measures with `origin: subworkflow:<parent>` and kept out of its promotion window, and a parent's `upgrade` reading its change notes) and SWF-B8's carrying (a carried parent paused inside its child resumes on a second state root and finishes), proved by SWF-AC1 and SWF-AC3 in `plugins/tempergraph/engine/tests/test_subworkflow_judges.py`, `test_subworkflow_findings.py`, `test_subworkflow_measures.py`, `test_subworkflow_upgrade.py` and `test_subworkflow_carry.py`.

### R3-T3 Writer branches and the concurrent map

#### R3-T3.1 Writer branches
Goal: FLX's writer branch rows, each with its worktree and the merge after.

Status: built. WSP-B11, WSP-B12 and WSP-B19 with WTR-B20 to WTR-B27 for a parallel branch that declares `write` or `edit` (it validates, resolves the run to a worktree, runs in its own sibling worktree cut after a checkpoint commit, and is merged without fast-forward at the join, a conflict resetting the run branch and blocking the join), proved by WFM-AC7, WSP-AC5, WSP-AC10 to WSP-AC15, WTR-AC1, WTR-AC5 and WTR-AC8 to WTR-AC11 in `plugins/tempergraph/engine/tests/test_writer_branches.py`, `test_parallel.py`, `test_workspace.py` and `test_outside_git.py`; the item worktrees of a writing map came with R3-T3.2.

#### R3-T3.2 Concurrent map
Goal: MAP's concurrent mode, the item worktrees of a writing map, and verification after the merge.

Status: built. MAP-B7, MAP-B9, MAP-B10, MAP-B6, MAP-B11, MAP-B12 and MAP-B13 for a map with `mode: concurrent` (it validates with `concurrency` 1 to 10 and is refused for a writing step in an `in_place` workflow; up to `concurrency` items run at once, read-only in the run's worktree or, for a writing step, each in its own sibling worktree cut after a checkpoint commit; the items are merged without fast-forward in list order, a conflict resetting the run branch and blocking the map; the gate's check runs once on the merged result; a spent item pauses addressed by unit and item; items take reservations from the one ledger), proved by MAP-AC2, MAP-AC5 to MAP-AC9, WSP-AC16 to WSP-AC20, WTR-AC12 and BUD-AC9 in `plugins/tempergraph/engine/tests/test_map.py`, `test_map_concurrent.py`, `test_map_concurrent_writers.py`, `test_map_concurrent_pauses.py` and `test_reservations.py`.

### R3-T4 Council and contest

#### R3-T4.1 Council
Goal: CNL acceptance criteria within the reserving cap.
Status: built. The `council` unit (CNL-B1 to CNL-B16: it validates and each refusal of CNL-B16 has a finding code of its own; members answer blind and later rounds are anonymized; the outcome of a `synthesize`, `vote` or `rank` council is derived by rule, a no decision pauses, retries or stops; the step node is a subgraph of member sessions, a round barrier, a pure tally and the chair, each member session kept on its own so a crash resumes only the unfinished ones; the judge grades `decision` with `positions` among its references; a mixed-executor council is checked at preflight; `retry_scope: chair` reruns only the chair; the council's `cost_cap_usd` and the run's cost cap, through the reservations of every member and chair session, stop it; the run detail shows its rounds and tally; `council-one-family` and `council-even-majority` run), proved by CNL-AC1 to CNL-AC7, BUD-AC12 to BUD-AC14, WFM-B13 and ARC-B15 in `plugins/tempergraph/engine/tests/test_council_declaration.py`, `test_council_prompts.py`, `test_council_answer.py`, `test_council_tally.py`, `test_council_run.py`, `test_council_no_decision.py`, `test_council_diagram.py`, `test_council_judge.py`, `test_council_caps.py`, `test_council_detail.py`, `test_council_docs.py`, `test_preflight.py` and `test_audit_history_rules_more.py`. Left out, as the code report says: the member, chair and slot setting scopes and RST-B3, and the member count on the diagram (CMP-AC6).

#### R3-T4.2 Contest
Goal: CTS acceptance criteria; `concurrency` and `attempt_cost_cap_usd` settable.

Status: built. CTS-B1 to CTS-B10 for a `contest` unit (it validates, each refusal of CTS-B10 with a finding code of its own; up to `concurrency` slots run at once, each in its own state, each slot's check before its judge, one judge session per slot holding that slot's artifacts only, the winner picked by a fixed rule with no model call; a retry re-runs the winner's slot alone or every slot by `retry_scope`; a `writes: true` contest runs each slot in its own sibling worktree and merges only the winner; the run detail shows every slot and marks the winner; slots take reservations from the one ledger; `concurrency` and `attempt_cost_cap_usd` are settable), proved by CTS-AC1 to CTS-AC6, RDD-AC9, RDD-AC10, BUD-AC11, RST-AC1 and ARC-AC2 in `plugins/tempergraph/engine/tests/test_contest_validate.py`, `test_contest_pick.py`, `test_contest_run.py`, `test_contest_retry.py`, `test_contest_failures.py`, `test_contest_writers.py`, `test_contest_concurrent.py`, `test_contest_cap.py`, `test_contest_settings.py`, `test_detail.py` and `test_reservations.py`. With R3-T4.1, track R3-T4 is built.

### R3-T5 Schedules

#### R3-T5.1 The schedule command
Goal: R-150 SCH's slice, then the rest of SCH; P-SCH-1 and P-SCH-2.

Status: built. The exact formats (`--at`, `--rrule`, `--every`, `--cron`), the word grammar, the canonical form and echo, slots with daylight saving, the entry and its fire log, the verbs `parse`, `add` for a workflow target, `list`, `show`, `history`, `edit`, `pause`, `resume`, `skip` and `remove`, and the catch-up, overlap, failure, budget and fire-identity rules as pure functions, proved by SCH-AC1 to SCH-AC6 and SCH-AC8 to SCH-AC12 in `plugins/tempergraph/engine/tests/test_schedule_*.py`; the tick, `fire`, `loop`, `trigger`, `runs`, `export`, the credential check, the fire token, the ledger and SCH-AC7 are R3-T5.2, and P-SCH-1 and P-SCH-2 are left.

#### R3-T5.2 Ticks and unattended fires
Goal: TCK, with unattended credentials.

Status: built. The tick (`schedule tick`: the lock, the heartbeat, settling, the decisions of R3-T5.1, at most 4 runs and 20 s, the hand-off ticket and `deferred`), `schedule fire`, `schedule runs` and the machine-wide ledger, the fire token and caller kind `scheduler`, the credential check at `add`, `edit` and each fire, the refusal of a caller that is not a person, `origin: schedule` in the run's records, `report --by schedule`, the attention items and `trigger_stale`, the `schedule_paused` hook event, the portable loop with the `host` and `os` adapters, `schedule export` and the `tempergraph:schedule` skill, proved by TCK-AC1 to TCK-AC7, SCH-AC5 and SCH-AC7 in `plugins/tempergraph/engine/tests/test_schedule_*.py`; orchestration targets wait for release 4 (ADR-0132) and P-SCH-1 to P-SCH-4 are left (`live-checks.plan.md`).

### R3-T6 Pipelines

#### R3-T6.1 The pipeline stage
Issue: [#67](https://github.com/dbr0vskyi/tempergraph/issues/67). Goal: `promote-check --to pipeline`, the regressed watch, PRO's pipeline rows.

### R3-T7 Pull-request gate

#### R3-T7.1 First slice
Issue: [#68](https://github.com/dbr0vskyi/tempergraph/issues/68). Goal: GitHub Actions, `report` mode, statuses and `path:line` evidence, the receipt in the pull request's body, the generated file and `doctor` (R-135 recommendation).

#### R3-T7.2 After the owner's answers
Issue: [#69](https://github.com/dbr0vskyi/tempergraph/issues/69). Goal: whichever of `block`, judge reasons and GitLab the owner accepts.

### R3-T8 Moved from release 2

#### R3-T8.1 Script cache, audit judge, judge MCP views

Status: built. SCR-B9 and SCR-B3 (the script cache for a script unit and a step's `before` and `after` script), proved by SCR-AC4 in `plugins/tempergraph/engine/tests/test_script_cache.py`; JDG-B7 (the sampled audit judge, `audit_rate` and `audit_executor`), proved by JDG-AC7 and ROP-AC1 in `plugins/tempergraph/engine/tests/test_audit_judge.py`; ECC-B3, ECC-B10 and ECC-B15 (the judge view catalog, the filtering proxy with its private configuration, and deferral of a view with no working proxy), proved by GRD-AC6, ECC-AC7, ECC-AC8 and ECC-AC9 in `plugins/tempergraph/engine/tests/test_view_catalog.py`, `test_mcp_proxy.py` and `test_judge_mcp_deferral.py`; the live check of the proxy against the pinned CLI is left (the owner's row in `live-checks.plan.md`).

#### R3-T8.2 Observers, worktree extras, session review in stable mode
Goal: EVT-B23 observers with a preflight warning for a missing one, the `in_repo` and `path:` worktree roots, the `default_branch` base, `cleanup: on_finish`, `worktree prune` and foreign-worktree scans (spec 82), and `signals` review plans with saturation and the stable caps (spec 44), with no model call in any test.

Status: built. EVT-AC5 in `plugins/tempergraph/engine/tests/test_events.py`, `test_run_log.py` and `test_preflight.py`; WTR-AC1, WTR-AC3, WTR-AC5 and WTR-AC6 in `test_workspace.py`, `test_worktree_cleanup.py`, `test_worktree_prune.py`, `test_rerun.py`, `test_carry.py`, `test_cli.py` and `test_run.py`; SRV-AC2 and SRV-AC9 in `test_session_review.py`, `test_review_budget.py` and `test_improve.py`, all under `plugins/tempergraph/engine/tests/`; writer, slot and item worktrees, probes P-WTR-1 to P-WTR-4, and corroborated filing (spec 44's Not built yet line) remain.

#### R3-T8.3 Audit history and tool surface audit
Status: built. The `history` layer and `audit tools` (AUD-B1, AUD-B3, AUD-B5, AUD-B10 to AUD-B12; ARC-B7, ARC-B9 to ARC-B15; TSA-B1 to TSA-B13; PRA-B11 `changed`), proved by AUD-AC1 to AUD-AC3, ARC-AC1, ARC-AC4, ARC-AC5, TSA-AC1 to TSA-AC6, PRA-AC3 and PRA-AC5 in `plugins/tempergraph/engine/tests/test_audit_history.py`, `test_audit_history_rules.py`, `test_audit_history_rules_more.py`, `test_audit_surface.py`, `test_audit_tools.py`, `test_audit_tools_verb.py` and `test_audit.py`; the post-release watch that `prompt-change-moved-gate` renders and the host probe that lists plugin tools for `judge-ambient-tool` are left.

### R3-T9 Windows

#### R3-T9.1 Windows
Issue: [#70](https://github.com/dbr0vskyi/tempergraph/issues/70) (probes [#107](https://github.com/dbr0vskyi/tempergraph/issues/107)). Goal: WIN's acceptance criteria, after EC-4.

### R3-T10 Release

#### R3-T10.1 Examples and docs
Issue: [#71](https://github.com/dbr0vskyi/tempergraph/issues/71). Goal: one example workflow gains a complexity switch; the guides cover sub-workflows, parallel work, schedules and the pull-request gate.

#### R3-T10.2 Release files
Issue: [#72](https://github.com/dbr0vskyi/tempergraph/issues/72). Goal: the release record, the changelog, the version bump.

## 3. Risks

| Risk | Mitigation |
|---|---|
| Release 3 too large | R3-T8 and R3-T9 move to release 4 first; R3-T7 does not wait on the other tracks |
| Reservations from projections are wrong on a new workflow | With no stats, a session reserves its per-session cap or the run's remaining cap divided by the width |
| A child changes under a paused parent | MIG-B15's rules apply per child (SWF-B3) |
| The pull-request gate leaks local text into a public pull request | Statuses and evidence pointers only until ADR-0131 is accepted |
