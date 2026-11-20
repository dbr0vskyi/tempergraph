---
goal: Build release 1 of tempergraph — author a simple workflow, run it on Claude Code, see everything it did, and trust its result
version: 1
date_created: 2026-11-20
last_updated: 2026-11-20
owner: dbr0vskyi
status: Planned
tags: [release-plan, tempergraph, tempergraph-monitor]
tracker: none
spec: plugins/tempergraph/docs/specs/00-overview.spec.md
spec_commit: 75a81bd
task_id: first-release
---

# Release 1 plan

## 0. Hand-off

| Field | Value |
|---|---|
| Origin | Design session for the owner, 2026-11-20 (thread "Define first release feature set") |
| Research | [R-090 readiness](../research/R-090-implementation-readiness.rsrch.md), [R-011 gaps](../research/R-011-design-gap-review.rsrch.md) |
| Decisions | [ADR-0090 scope](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md), [ADR-0091 executor](../adr/0091-first-release-ships-the-claude-executor-only.adr.md) |
| Spec, read at | [Overview](../specs/00-overview.spec.md) and the specs named in §1, at `52aac24` (re-read after PRs 15 to 17) |
| Tracker | none |

**Problem statement.** The design set is complete on mechanism but had no release boundary, so no plan could start. This plan fixes what release 1 contains, the order it is built in, and what must be true before each part starts.

**Decisions made.**

| Decision | Choice | Rationale |
|---|---|---|
| Scope | Simple trusted workflows, their creation, full local observability, supervision | Owner's ask; accepted ADR-0029 ([ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md)) |
| Executor | `claude` only; stand-ins carry the other three capability sets | [ADR-0091](../adr/0091-first-release-ships-the-claude-executor-only.adr.md) |
| Platforms | macOS and Linux, inside git repositories | R-011 U3, G9 deferred |
| Plan shape | This release plan sets tracks and phases; each track gets its own skeleton and expanded plan (`<track>.plan.md`) when its specs are ready, within the method's 14 KB skeleton budget. This file is over that budget because it lists 53 phases across 12 tracks and the item-by-item feature list (§1.3), and holds no task row | One plan per coding unit, per the method |

**Implementation guidance.** Contracts in [CON](../specs/01-contracts.spec.md) are the only shared types; a component that needs another adds it there first. Every acceptance criterion is a test before it is code (TDD rows in the expanded plans). Every model-calling behaviour is first tested against scripted stand-ins; only track T11 spends money. LangGraph is imported only by the compiler and durability modules (R-011 U4, a source-scan test from T1.1).

**Context for the implementer.** Read the [docs README](../README.md), the overview, the contracts, then the component spec. Truth ranking: acceptance criteria, then specs and decision records, then this plan, then code.

**Status: Planned.** No track has started.

## 1. Requirements analysis

### 1.1 Entry conditions

| Id | Condition | Before | Owner |
|---|---|---|---|
| EC-1 | The owner accepts ADR-0090 and ADR-0091, or edits them | Any code track | Owner |
| EC-2 | A track's specs are `ready-for-implementation`: its first phase turns each open question into a recorded default (R-090 B5) and sets the status | Each track | Implementer, owner may veto |
| EC-3 | P-CC-2, P-CC-5, P-CC-6, P-CC-9 and P-WTR-1 recorded on the pinned Claude Code release (R-090 X6) | T3.4 relied on live; T11 | Owner's machine |
| EC-4 | Specs for the workflow package (D1), the authoring contract (D2) and the run outcome (D3) written | T5.8, T8, T9 | Satisfied by PKG, AUT, OUT, SCF (PR 17); their status pass is EC-2 |
| EC-5 | P-SUP-1, P-SUP-2, P-SUP-3 recorded | T7.6 leaves `projected` | Owner's machine |

### 1.2 Requirements by spec

A spec listed is in scope with all its acceptance criteria except those named; excluded criteria belong to a later release ([ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md)). CON-AC-5, WFM-AC-5, PRM-AC-1, PRA-AC-2 and EXI-AC-9 run against the four declared capability sets as test data, and again when each adapter ships.

| Req | Spec | Criteria in scope | Phase |
|---|---|---|---|
| REQ-1 | CON | all | T1.2 |
| REQ-2 | SEC | all but SEC-AC-4 (tool host) | T1.3 |
| REQ-3 | LOS | all | T1.4, T7.3 |
| REQ-4 | WFM | all | T2.1 |
| REQ-5 | PRM, VAL | all; VAL-B4 item keys later | T2.2 |
| REQ-6 | CMP | AC-1, 2, 4, 5; AC-3 and AC-6 for release-1 primitives and kinds | T2.3 |
| REQ-7 | LIF | AC-2, 4, 6 | T2.4, T8.3, T8.4 |
| REQ-8 | EXI | all | T3.1–T3.3 |
| REQ-9 | ECC | all; judge MCP views later (`judge_mcp = false`) | T3.4 |
| REQ-10 | DUR | all | T4.1, T4.2 |
| REQ-11 | WSP, WTR | WSP AC-1, 2, 4; AC-3 for `in_place` and one engine worktree; WTR for its §5 release-1 slice | T4.3 |
| REQ-12 | RCT | all (POSIX) | T4.4 |
| REQ-13 | OBS | all | T5.1, T7.4 |
| REQ-14 | CHK | all but AC-6 (`self-check`); AC-2 on Linux and macOS | T5.2 |
| REQ-15 | JDG | all but AC-7 (audit judge) | T5.3 |
| REQ-16 | GRD | all; AC-5 on `claude` fixtures | T5.4 |
| REQ-17 | HUM | AC-1, 4; AC-2 for escalation, budget, approval | T5.5 |
| REQ-18 | BUD | all | T5.6 |
| REQ-19 | SCR, FIN | SCR all but AC-4 (cache); FIN all | T5.7 |
| REQ-20 | CLI | all, for the release-1 verbs of ADR-0090 | T6.1, T7.4 |
| REQ-21 | RST | all but rows for orchestration, council, contest and switch-arm keys | T6.2, T6.3 |
| REQ-22 | RRN | all but §2.6 | T6.4 |
| REQ-23 | PRV | all; AC-6 for P-SUP-1 and P-SUP-2 | T6.5 |
| REQ-24 | EVT | all; AC-5 for file observers | T7.1 |
| REQ-25 | RDD | all; AC-1's fixture without a map | T7.2 |
| REQ-26 | SUP, IMD, FBK | SUP all but AC-3's `promote-check` half; IMD R1–R3, R6, R9, R10, R14 and AC-1; FBK-AC-3 (`label`) | T7.5 |
| REQ-27 | SCO, SHL §2.2 | SCO AC-1 to AC-5, AC-6's P-SUP-3 half | T7.6 |
| REQ-28 | UPD, VER | UPD AC-7, AC-8; VER AC-1, 2, 5, 6 | T8.1–T8.3 |
| REQ-29 | AUD, ARC, PRA | AUD AC-2, 4–7 and AC-1 for definition and host rules; ARC same; PRA all | T8.5 |
| REQ-30 | SHL, LSK | SHL all for run driver, authoring, bootstrap, troubleshooter; LSK install skill | T9.1–T9.3 |
| REQ-31 | CST | all, directory sink | T10.1 |
| REQ-32 | Monitor MOV, MDS, MBA, MRV, MDD, MAC, MCF | all but orchestration views | T10.2–T10.4 |
| REQ-33 | PKG | all | T8.1 |
| REQ-34 | OUT | AC-1 to AC-5; AC-6 with the loop (release 3) | T5.8 |
| REQ-35 | AUT | all | T9.2 |
| REQ-36 | SCF | all | T8.6 |

### 1.3 Feature list

Every item release 1 ships, then every item it leaves out with its release. Release 2 and 3 are a forecast ([ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md)); an item not built is refused with `not_in_release`, never ignored.

**Included in release 1**

| # | Feature | Spec | Phase |
|---|---|---|---|
| I-1 | Workflow package: plugin, Python and docs halves, `tempergraph.json` manifest, loading in isolation | PKG §2.1–2.3 | T8.1 |
| I-2 | Typed Python builders for step, script, route, switch and workflow; prompt and check text kept in files | PKG §2.4 | T8.1 |
| I-3 | Docs half and the `docs-drift` check (warning) | PKG §2.5 | T8.1 |
| I-4 | Package skills and agents on step sessions through `--plugin-dir`, never on judges | PKG §2.6 | T8.1 |
| I-5 | Minimal package | PKG §2.7 | T8.1 |
| I-6 | `outcome.json`: final and intermediate outcomes, one verifier per criterion | OUT §2.1–2.2 | T5.8 |
| I-7 | Scoring scale on every judged criterion | OUT §2.2.1, ADR-0114 | T5.8 |
| I-8 | Trust and coverage; unverified criteria always shown | OUT §2.3 | T5.8 |
| I-9 | Final outcome gate before the finalizer | OUT §2.4 | T5.8 |
| I-10 | Person sign-off criteria in the approval pause | OUT, HUM | T5.8 |
| I-11 | Outcome record, uncorrected measures, `outcome show`, `outcome candidates` | OUT §2.5 | T5.8 |
| I-12 | Outcome revision through revise mode; a weakening needs a person's yes | OUT, AUT §2.7 | T9.2 |
| I-13 | Validation before spend, including `not_in_release` | WFM | T2.1 |
| I-14 | Template grammar, prompt rendering, output contract | CON, PRM | T2.2 |
| I-15 | Value artifacts and template keys (no item keys) | VAL | T2.2 |
| I-16 | Workflow settings and profiles | RST, WFM | T6.2 |
| I-17 | Model tiers and aliases, binding table, ladders | EXI, ECC | T3.1 |
| I-18 | Tool capabilities, including `skill:` and `subagent` on `claude` | ECC | T3.4 |
| I-19 | Command allow-list and resolver | CHK, SEC | T5.2 |
| I-20 | Step and script units; hybrid `before` and `after` scripts (no cache) | SCR | T5.7 |
| I-21 | Order, route, switch with `--arm`, back-edges with loop budgets | CMP | T2.3 |
| I-22 | Finalizer | FIN | T5.7 |
| I-23 | Check contract, findings, facts, mechanical criteria | CHK | T5.2 |
| I-24 | Command runner (timeout, tree kill, reuse) and the check worker | CHK | T5.2 |
| I-25 | Independent judge: one re-ask, verdict by rule, no-change escalation (no audit judge) | JDG | T5.3 |
| I-26 | Derived view sets and the independence guard (no MCP views) | GRD | T5.4 |
| I-27 | Pauses for escalation, budget, approval and tool access; proceed, retry, back, rewind, stop; intervention rows | HUM | T5.5 |
| I-28 | Budgets by cause, infra retries, timeouts, idle watchdog, run cost cap, auto re-open, attempt cap | BUD | T5.6 |
| I-29 | `--strict-permissions` and `--enforce-tools` | SEC, ECC | T3.4 |
| I-30 | Verbs `run`, `run --check`, `resume`, `status`, `wait`, `list`, `validate`, `executors --probe`, `facts`, `graph` | CLI | T6.1 |
| I-31 | SQLite checkpoints, thread states, locks, aliases and labels, cut-off recovery | DUR | T4.1 |
| I-32 | Workspace `in_place` and `auto`; engine worktree (sibling root, head base, ref-safe names, re-attach); executor pinned to it with `EnterWorktree`/`ExitWorktree` disallowed; `worktree list\|path` | WSP, WTR release-1 slice | T4.3 |
| I-33 | `stop --drain\|--now` | RCT | T4.4 |
| I-34 | Settings catalog, layers, files, snapshot, effective record, `config show\|validate\|paths` | RST | T6.2 |
| I-35 | Tool grants: `--grant`, `--allow-command` | RRN, SEC | T6.3 |
| I-36 | Feedback, rulings, revoke, rewind, `rerun` as a linked fork with external-effect consent | RRN | T6.3 |
| I-37 | Caller provenance with `--relayed` (person, Claude Code, pipeline) | PRV | T6.4 |
| I-38 | Executor interface: registry, preflight, launcher, normalized events, conformance suite with four stand-ins | EXI | T3.1–T3.3 |
| I-39 | Claude Code executor | ECC | T3.4 |
| I-40 | Run log with usage; reported vs estimated cost; unmeasured never shown as zero | OBS | T5.1 |
| I-41 | Live progress file, session metrics, time profile, timeout classes | OBS | T7.1 |
| I-42 | `report` and monthly `stats` | OBS | T7.2 |
| I-43 | Observer events, activity journal, `events --follow` (file observers only) | EVT | T7.3 |
| I-44 | `status --detail` | RDD | T7.4 |
| I-45 | Local store: raw session logs, check output, engine code log, `logs`, `store usage\|prune\|export`, retention, capture level | LOS | T1.4, T7.4 |
| I-46 | `attention` (everything waiting on a person) | CLI | T7.2 |
| I-47 | Machine index and `--all-roots` | LOS | T7.4 |
| I-48 | Directory sink, outbox, `stats flush`, fleet copy, `stats --source\|--live\|--projection` | CST | T10.1 |
| I-49 | Monitor plugin: band, alerts, run view, drill-down, prompt-fill actions, cost and fleet views | Monitor set | T10.2–T10.4 |
| I-50 | Supervision record and level, touches, waits, aggregates, `report --supervision` (no §2.7) | SUP | T7.5 |
| I-51 | Supervision cost: host hooks, journal, attribution, `supervision log\|close\|show` | SCO | T7.6 |
| I-52 | Improvement-data fields and the ledger (subset) | IMD | T7.5 |
| I-53 | `label` for gates and the outcome | FBK entry | T7.5 |
| I-54 | Security: constants-only argv, prompt off argv, scrubbing, canary, config cleanup | SEC (no tool-host criterion) | T1.3 |
| I-55 | First install: launcher, home folder, environment, shim, `PATH` | UPD §2.7 | T8.2 |
| I-56 | `workflows list\|register\|unregister\|reinstall` | UPD §2.8 | T8.1 |
| I-57 | Workflow version, content digest, release record; stamp by `upgrade --check --stamp` over an empty changelog | VER, WUP | T8.3 |
| I-58 | Executor compatibility table | VER | T8.3 |
| I-59 | Diagram model and diagram currency | LIF | T2.4 |
| I-60 | Prompt lint and the structural readiness report | LIF | T8.4 |
| I-61 | Deterministic scenarios on stand-ins | LIF | T8.4 |
| I-62 | `audit` definition and host layers, their ARC rules, PRA, ignores, json and sarif, `--fail-on` | AUD, ARC, PRA | T8.5 |
| I-63 | `author start\|intake\|check\|show\|list\|drop`; entry from a solution, sources or a chat; the inventory | AUT §2.1–2.3 | T9.2 |
| I-64 | Backwards interview, verification classification, flag-never-hide, criteria lint, guidance rungs | AUT §2.4–2.6, ADR-0114 | T9.2 |
| I-65 | Authoring record and revise mode | AUT §2.7 | T9.2 |
| I-66 | Blueprint check, draw and compare; literal check; `scaffold` with `--update`; generated tests | SCF | T8.6 |
| I-67 | `author verify` ladder with judge seeds and a capped, consented trial | SCF | T8.6 |
| I-68 | Authoring skill `tempergraph:author` | SHL, AUT | T9.2 |
| I-69 | Run driver skill | SHL | T9.1 |
| I-70 | Project bootstrap skill | SHL | T9.1 |
| I-71 | Troubleshooter skill | SHL | T9.3 |
| I-72 | Install skill | LSK | T9.3 |
| I-73 | Supervision host hooks | SHL §2.2, SCO | T7.6 |
| I-74 | Platforms: macOS and Linux, git repositories only | WSP | all |
| I-75 | Example workflows: the minimal one and a three-step document workflow | PKG, SCF | T11.2 |

**Excluded, release 2**

| # | Feature | Spec |
|---|---|---|
| X2-1 | `agent-sdk` executor and its host profile | EAS, ADR-0091 |
| X2-2 | Promotion to the pipeline: `promote-check`, SUP §2.7 (needs a spec) | ADR-0041, SUP |
| X2-3 | Judge calibration and `evals score\|bar\|label` | JCL |
| X2-4 | Eval suites and `evals run\|report\|grade` | EVS |
| X2-5 | Live scoring, harvest and replay | EVS |
| X2-6 | FBK grades, `labels queue`, binding-shift watch | FBK |
| X2-7 | Corrected outcome rates | OUT, JCL |
| X2-8 | Stable mode | LIF-B6, JCL |
| X2-9 | Eval skill | SHL |
| X2-10 | `update`, rollback, `prune-engines` | UPD |
| X2-11 | Migrations and pins | MIG |
| X2-12 | Changelog, detect rules and transforms | WUP, VER |
| X2-13 | Update skill | LSK |
| X2-14 | Audit history layer and its rules | AUD, ARC |
| X2-15 | Tool-surface audit | TSA |
| X2-16 | Ask unit | ASK |
| X2-17 | Event waits (`wait` unit) | HUM, WFM |
| X2-18 | `--pause-before`, deadlines, fallback target | HUM, BUD |
| X2-19 | Parallel read-only branches | FLX |
| X2-20 | Sequential map and item keys | MAP, VAL |
| X2-21 | Measured switches (shadow mode, per-arm overrides) | SWM |
| X2-22 | Script cache | SCR |
| X2-23 | `self-check` for step sessions | CLI, CHK |
| X2-24 | Audit judge | JDG-B7 |
| X2-25 | Judge MCP views through the filtering proxy | GRD, ECC |
| X2-26 | Lifecycle hooks, in-process observers, wider hook events | EVT |
| X2-27 | Schedules, release-2 slice: once and calendar recur for workflow targets, `catch_up latest\|none`, overlap skip, both caps, all verbs but `export`, portable loop with the host adapter | SCH §5, TCK |
| X2-28 | Worktree extras: `in_repo` and `path:` roots, `default_branch` and `ref:` bases, `cleanup on_finish`, `prune --apply`, foreign-worktree scan, `.worktreeinclude` | WTR |
| X2-29 | State root outside git | WSP (R-011 G9) |
| X2-30 | Windows | R-011 U3 |

**Excluded, release 3**

| # | Feature | Spec |
|---|---|---|
| X3-1 | Self-improvement loop | SIL |
| X3-2 | Proposals and the `improve` verbs | PRP |
| X3-3 | Lessons | LSN |
| X3-4 | `report --loop` and improvement-data aggregate queries | OBS, IMD |
| X3-5 | Outcome proposals from the loop | OUT, PRP |
| X3-6 | Orchestrator, its skill, `batch` | ORC, OSK |
| X3-7 | Monitor orchestration views | Monitor set |
| X3-8 | Council unit | CNL |
| X3-9 | Contest unit | CTS |
| X3-10 | Writer branches and slot and item worktrees | FLX, WTR |
| X3-11 | Parallel map | MAP |
| X3-12 | Sub-workflows and mapped sub-workflows | FLX |
| X3-13 | Selective parallel | FLX |
| X3-14 | `messages-api` executor and its tool host | EMA, THS |
| X3-15 | `antigravity` executor | EAG |
| X3-16 | Live cross-executor judging | EXI |
| X3-17 | `upgrade` beyond `--check`, the built-in upgrade workflow and its skill | WUP, UWF, LSK |
| X3-18 | Schedules, the rest: OS adapter, orchestration and program targets, `catch_up all`, queue and parallel overlap, cron, pipeline export | SCH, TCK |

**Unscheduled**

| # | Feature | Source |
|---|---|---|
| XU-1 | OTLP export | TEL |
| XU-2 | Remote MCP | ADR-0090 |
| XU-3 | Step sandbox profile | R-011 G10 |
| XU-4 | Team or managed settings layer | RST |
| XU-5 | Antigravity-native shell and a non-Claude authoring host | SHL |
| XU-6 | Postgres checkpointer | DUR |
| XU-7 | Structured judge output | R-011 G6 |
| XU-8 | Running-cost stop on uncapped executors | R-011 G8 |

## 2. Tracks and phases

| Track | Component specs | Phases | Depends on | Kind |
|---|---|---|---|---|
| T0 Live probes | ECC §2.7, PRV §5, SCO §5 | T0.1–T0.2 | — | probe |
| T1 Foundations | CON, SEC, LOS | T1.1–T1.4 | EC-1 | code |
| T2 Model and compiler | WFM, PRM, VAL, CMP, LIF | T2.1–T2.4 | T1 | code |
| T3 Executors | EXI, ECC | T3.1–T3.4 | T1; T0.1 for live | code |
| T4 Durability and workspace | DUR, WSP, RCT | T4.1–T4.4 | T1 | code |
| T5 Gate funnel | OBS, CHK, JDG, GRD, HUM, BUD, SCR, FIN, OUT | T5.1–T5.8 | T2, T3, T4 | code |
| T6 Run operations | CLI, RST, RRN, PRV | T6.1–T6.5 | T5 | code |
| T7 Observability and supervision | EVT, RDD, LOS, OBS, SUP, IMD, FBK, SCO | T7.1–T7.6 | T6; T0.2 for T7.6 live | code |
| T8 Packages, install, audit, scaffold | PKG, UPD, VER, LIF, AUD, ARC, PRA, SCF | T8.1–T8.6 | T6 | code |
| T9 Shell skills | SHL, LSK, AUT, OUT | T9.1–T9.3 | T7, T8 | code |
| T10 Stats across machines and monitor | CST, monitor set | T10.1–T10.4 | T7 | code |
| T11 Release | all | T11.1–T11.3 | every track | release |

Milestones: **M1** after T6.1, a two-step workflow defined in Python test code runs end to end on stand-ins and on `claude`. **M2** after T7, every observability verb answers for that run. **M3** after T9, a person authors, registers and runs a workflow from a conversation. **M4** after T11, release 1 is live-proven.

### T0 Live probes

#### T0.1 Executor probes
Goal: record P-CC-1 to P-CC-9 on the pinned Claude Code release in [ECC §2.7](../specs/11-executor-claude-code.spec.md), P-CC-2, 5, 6 and 9 first, and P-WTR-1 in [WTR](../specs/82-worktree-mode.spec.md).
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T0.1 -->

#### T0.2 Host probes
Goal: record P-SUP-1 to P-SUP-3, and check the monitor's mods facts against the current Claude Code release.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T0.2 -->

### T1 Foundations

#### T1.1 Repository skeleton and rules
Goal: the engine package, test runner, linters, type checker and the source-scan harness (EXI-AC-1, WFM-AC-4, LangGraph confinement), with their commands recorded in CLAUDE.md.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T1.1 -->

#### T1.2 Shared types
Goal: every CON type, schema-versioned documents and tolerant readers.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T1.2 -->

#### T1.3 Launch rules and scrubbing
Goal: sanctioned launch sites, constants-only argv, the scrubber and the canary harness every later track reuses.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T1.3 -->

#### T1.4 Store layouts and code log
Goal: state root and home layouts with their manifests, and the engine code log.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T1.4 -->

### T2 Model and compiler

#### T2.1 Validation
Goal: `validate` with every release-1 refusal and `not_in_release`.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T2.1 -->

#### T2.2 Prompt rendering and values
Goal: the one renderer, the output contract and `value` artifacts with template keys.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T2.2 -->

#### T2.3 Compiler
Goal: four nodes per unit, order, route, switch, back-edge and the finalizer node, as a LangGraph graph.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T2.3 -->

#### T2.4 Diagram model
Goal: the diagram model, `graph`, and the diagram-currency test.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T2.4 -->

### T3 Executors

#### T3.1 Registry and preflight
Goal: registry, capability declarations, binding table, every EXI-B1 refusal before spend.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T3.1 -->

#### T3.2 Session launcher
Goal: prompt on stdin, timeout, idle watchdog, process-tree lifetime, stop contract, prompt-gap and host-speed records.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T3.2 -->

#### T3.3 Normalized events and conformance
Goal: the event stream, no-raise results, causes from structure, and the conformance suite with stand-ins for all four capability sets.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T3.3 -->

#### T3.4 Claude Code executor
Goal: step and judge launches, stream mapping and failure classes of ECC, passing the conformance suite.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T3.4 -->

### T4 Durability and workspace

#### T4.1 Checkpoints and resume
Goal: the SQLite checkpointer, thread states, the lock, aliases and the resume table of DUR §2.1.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T4.1 -->

#### T4.2 Status and wait
Goal: the status document, `status` and `wait`, read-only.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T4.2 -->

#### T4.3 Workspace
Goal: state root from any worktree, `in_place`, one engine worktree with bootstrap and interpreter, plus the release-1 part of [WTR](../specs/82-worktree-mode.spec.md) (`run.workspace`, sibling root, head base, re-attach, `worktree list|path`; ADR-0090).
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T4.3 -->

#### T4.4 Stop
Goal: `stop --drain` and `--now`, resumable.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T4.4 -->

### T5 Gate funnel

#### T5.1 Run log, ledger and cost
Goal: every model call an `agent_run` record with usage, cost rules, live progress file and the ledger writer, all best effort.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T5.1 -->

#### T5.2 Checks and command runs
Goal: check context and results, findings and facts, command resolution and runs, the check worker.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T5.2 -->

#### T5.3 Judge and verdict
Goal: judge prompt, one re-ask, verdict derivation by rule.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T5.3 -->

#### T5.4 Independence guard
Goal: derived view sets and the after-the-fact guard.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T5.4 -->

#### T5.5 Gate and human nodes
Goal: routing tokens, escalation, budget, approval and tool-access pauses, decisions, intervention rows.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T5.5 -->

#### T5.6 Budgets and failures
Goal: cause-to-counter, visit budgets, timeouts, ladders, run cost cap, automatic re-open.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T5.6 -->

#### T5.7 Scripts and finalizer
Goal: script units, `before` and `after` scripts, the finalizer contract.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T5.7 -->

#### T5.8 Run outcome gate
Goal: load `outcome.json`, give each gate its intermediate criteria, the scoring scales, trust and coverage, the final outcome gate, sign-off criteria in the approval pause, the outcome record, `outcome show` and `outcome candidates` ([OUT §2.1–2.5](../specs/90-run-outcome.spec.md)).
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T5.8 -->

### T6 Run operations

#### T6.1 Core verbs
Goal: `run`, `run --check`, `resume`, `list`, `validate`, `executors`, `facts`, exit codes, reserved words (milestone M1).
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T6.1 -->

#### T6.2 Settings
Goal: catalog, layers, files, workflow settings and profiles, snapshot on resume, effective-settings record, `config`.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T6.2 -->

#### T6.3 Tool grants
Goal: `--grant` and `--allow-command`, and the tool-access pause that names them.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T6.3 -->

#### T6.4 Feedback, rulings, rewind, rerun
Goal: feedback at every resume, lasting rulings, `rewind:`, `rerun` as a linked fork.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T6.4 -->

#### T6.5 Caller provenance
Goal: one `caller` block per mutating call, deciders and relay evidence.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T6.5 -->

### T7 Observability and supervision

#### T7.1 Run events
Goal: record envelope, observer kinds, activity journal with input summaries, `events`.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T7.1 -->

#### T7.2 Detail document
Goal: `status --detail`, built on demand, read-only.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T7.2 -->

#### T7.3 Session logs and the store
Goal: `raw.jsonl` per session, `logs`, `store usage|prune|export`, retention, capture level.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T7.3 -->

#### T7.4 Reports and attention
Goal: `report`, monthly `stats`, and `attention`.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T7.4 -->

#### T7.5 Supervision record and improvement data
Goal: touches, the supervision record and level, `report --supervision`, IMD fields, `label`.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T7.5 -->

#### T7.6 Supervision cost
Goal: the host hooks, the supervision journal, attribution and the `supervision` verbs.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T7.6 -->

### T8 Packages, install, audit

#### T8.1 Packages and registry
Goal: load a package per [PKG](../specs/88-workflow-package.spec.md) (layout, manifest, typed builders, docs check, `--plugin-dir` on step sessions, minimal package), the home registry and `workflows list|register|unregister|reinstall`, workflow version and digest.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T8.1 -->

#### T8.2 First install
Goal: the plugin launcher, home folder, first engine environment, shim and `PATH` block, release record.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T8.2 -->

#### T8.3 Stamp and compatibility
Goal: `upgrade --check --stamp` (alias `upgrade-check --stamp`) over an empty changelog, the stamp record, the executor compatibility table.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T8.3 -->

#### T8.4 Scenarios, lint and readiness
Goal: deterministic scenarios with the scripted stand-in, prompt lint in `validate`, the structural readiness report.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T8.4 -->

#### T8.5 Audit
Goal: `audit` definition and host layers, their rules, the prompt audit, ignores, formats and `--fail-on`.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T8.5 -->

#### T8.6 Blueprint and scaffold
Goal: blueprint check, draw and compare, the literal check, `scaffold` and `scaffold --update`, generated tests, the `author verify` ladder with judge seeds and a capped trial ([SCF](../specs/91-blueprint-and-scaffold.spec.md)).
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T8.6 -->

### T9 Shell skills

#### T9.1 Run driver and project bootstrap
Goal: start, report by exit code, walk the person through pauses with `--relayed`; add the state-root ignore rule.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T9.1 -->

#### T9.2 Authoring
Goal: the `author` verbs and the `tempergraph:author` skill per [AUT](../specs/89-workflow-authoring.spec.md): entry paths, inventory, backwards interview, verification classification, criteria lint, guidance rungs, authoring record and revise mode, ending in a registered, audited, stamped workflow.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T9.2 -->

#### T9.3 Troubleshooter and install
Goal: read-only diagnosis from logs, detail and audit; the install skill.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T9.3 -->

### T10 Stats across machines and monitor

#### T10.1 Machine index, directory sink, fleet copy
Goal: rows, outbox, `stats flush`, the fleet copy, `stats --source|--live|--projection`, `--all-roots`.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T10.1 -->

#### T10.2 Monitor sources, band and alerts
Goal: MDS and MBA.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T10.2 -->

#### T10.3 Monitor run view and drill-down
Goal: MRV and MDD.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T10.3 -->

#### T10.4 Monitor actions, cost and fleet
Goal: MAC and MCF.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T10.4 -->

### T11 Release

#### T11.1 Example workflows
Goal: the minimal one-step workflow, and a three-step document workflow using a script, a route on a value, a trip back, an approval and a finalizer, both authored through T9.2.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T11.1 -->

#### T11.2 Live acceptance
Goal: the end-to-end story of §3 A6 on the owner's machine under a spend cap, with readiness flags moved per the [docs README](../README.md#readiness-flags).
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T11.2 -->

#### T11.3 Release
Goal: plugin manifests and marketplace entries, `release.json`, the empty changelog, docs and CLAUDE.md current.
| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
<!-- expand: T11.3 -->

## 3. Architecture decisions

| # | Decision | Why |
|---|---|---|
| A1 | The engine is one Python 3.11+ package `tempergraph` under `plugins/tempergraph/engine/` (source layout); skills under `plugins/tempergraph/skills/`, the launcher under `plugins/tempergraph/bin/`; the monitor under `plugins/tempergraph-monitor/`. | The plugin ships the engine and its shim (ADR-0001 A8, UPD §2.7) |
| A2 | Module boundaries follow the spec index; LangGraph is imported only by the compiler and durability modules; concrete executors only by the executor package (source-scan tests). | R-011 U4, EXI-AC-1, ADR-0002's mitigation |
| A3 | Scripted stand-ins are test code: a recorded stream of `claude` and four capability sets. They are never registered in a shipped engine. | ADR-0091 |
| A4 | Tooling is chosen in T1.1 (proposed: `uv`, `pytest`, `ruff`, `pyright`) and recorded in CLAUDE.md, which states no command until then. | CLAUDE.md rule |
| A5 | Live spend happens only in T0 and T11, each under a stated cap (T11: proposed $25 for the whole acceptance set). | R-011 U7 |
| A6 | Release 1 is accepted when, on `claude`: a person authors a workflow with the authoring skill; `audit` is clean; `run` pauses at an approval; `attention` lists it; `resume` with a ruling passes; `status --detail`, `events`, `logs`, `report`, `report --supervision` and the monitor show the run, its cost and its deciders; `rerun --from` with `--set` makes a linked thread; `stop --drain` and `resume` finish it. | The owner's "author, run, see, trust" |

## 4. Dependencies and imports
<!-- expand: dependencies -->

## 5. File modifications
<!-- expand: files -->

## 6. Code verification
<!-- expand: verification -->

## 7. Code assumptions
<!-- expand: assumptions -->
