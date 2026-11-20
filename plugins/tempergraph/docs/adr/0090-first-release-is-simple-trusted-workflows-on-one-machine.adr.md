# ADR-0090 The first release is simple, trusted workflows on one machine, with their creation and full observability

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — (answers R-011 G4 and U3; keeps accepted [ADR-0029](0029-own-observability-first-export-deferred.adr.md) and [ADR-0040](0040-take-script-steps-attention-and-composition-from-archon.adr.md)) |

## Context

The set designs everything at once: 62 specs, four executors, eleven unit kinds, orchestration, self-improvement, evals, update and upgrade. No document said what the first release holds, so the first plan had no boundary ([R-011 G4](../research/R-011-design-gap-review.rsrch.md)). On 2026-11-20 the owner asked for the feature set "needed for simple workflows and for their creation", including "all the crucial observability, reporting features and others", with "different advanced types of node and orchestration" later. The owner had already accepted that the local store, observer events, detail document, monitor and directory sink with its home fleet copy ship in the first release ([ADR-0029](0029-own-observability-first-export-deferred.adr.md)). Readiness is in [R-090](../research/R-090-implementation-readiness.rsrch.md).

## Decision

We will cut the work into three releases and commit only to the first. **Release 1** is done when a person can **author** a simple workflow through the authoring skill, **run** it on their machine, **see** everything it did, what it cost and who touched it, and **trust** its result because every gate's check, independent judge and engine verdict hold as specified. Releases 2 and 3 are a forecast, reordered freely.

A **simple workflow** is: model steps and script steps in order, routes and switches on step values, trips back, checks with an engine command runner, independent judges, pauses for a person (escalation, spent budget, approval, tool access), retry and resume with feedback and rulings, rewinds and reruns, settings overrides and profiles, and a finalizer.

| Capability (owner spec) | Release | Reason |
|---|---|---|
| Workflow model and validation, contracts, prompt rendering, step values ([WFM](../specs/02-workflow-model.spec.md), [CON](../specs/01-contracts.spec.md), [PRM](../specs/04-prompt-rendering.spec.md), [VAL](../specs/76-step-values-and-template-keys.spec.md)) | 1 | The definition every other part reads |
| Compiler: four nodes per unit, order, route, switch, back-edge, finalizer ([CMP](../specs/03-compiler-and-flow.spec.md)) | 1 | "Lightly branching" needs no more |
| Check contract and command runner ([CHK](../specs/75-check-contract-and-command-runs.spec.md)), judge and verdict ([JDG](../specs/05-judge-and-verdict.spec.md)), independence guard ([GRD](../specs/06-independence-guard.spec.md)) | 1 | The product's core: deterministic first, independent judge second, verdict by rule |
| Gate and human node: escalation, budget, approval and tool-access pauses ([HUM](../specs/07-gate-and-human.spec.md)); budgets and failures ([BUD](../specs/08-budgets-and-failures.spec.md)) | 1 | Bounded retries, trips back and pauses are the trust model |
| Script units and hybrid `before`/`after` scripts ([SCR](../specs/70-script-units-and-hybrid-steps.spec.md)); finalizer ([FIN](../specs/78-finalizer-contract.spec.md)) | 1 | Accepted in ADR-0040; non-model work belongs in scripts |
| Durability, resume, status, wait, alias ([DUR](../specs/09-durability-and-resume.spec.md)); workspace in place and one engine worktree ([WSP](../specs/13-workspace-and-concurrency.spec.md)); security ([SEC](../specs/14-security.spec.md)) | 1 | Runs that survive pauses, on a safe launch surface |
| Worktree mode, release-1 part of spec 82 WTR (open in PR 15, its §5 split): `run.workspace` `auto`/`worktree`/`in_place`, sibling root, head base, ref-safe names, start, resume and re-attach, executor pointing with `EnterWorktree`/`ExitWorktree` disallowed, `worktree list` and `worktree path` | 1 | One engine worktree per run is the simple-workflow default for code changes |
| Worktree mode, rest of WTR: `in_repo` and `path:` roots, `default_branch` and `ref:` bases, cleanup `on_finish`, `prune --apply`, the foreign-worktree scan, `.worktreeinclude`; writer, slot and item worktrees with the units that need them | 2 (writer, slot, item: 3) | Housekeeping and variants on top of the release-1 worktree |
| Executor interface, launcher, preflight, conformance suite; the `claude` executor ([EXI](../specs/10-executor-interface.spec.md), [ECC](../specs/11-executor-claude-code.spec.md)) | 1 | One executor, [ADR-0091](0091-first-release-ships-the-claude-executor-only.adr.md) |
| Run settings, layers, files, profiles, tool grants, `config` ([RST](../specs/80-run-settings-and-overrides.spec.md)); feedback, rulings, rewind, rerun ([RRN](../specs/81-reruns-and-feedback.spec.md)) | 1 | Asked for by the owner in PR 11; resume with feedback is a simple-workflow need |
| Run log, cost, live progress, reports, monthly stats ([OBS](../specs/15-observability-and-cost.spec.md)); run events, activity journal, `events` ([EVT](../specs/30-run-events.spec.md)); detail document ([RDD](../specs/31-run-detail-document.spec.md)); `stop` ([RCT](../specs/32-run-control.spec.md)); local store and `logs`, `store` ([LOS](../specs/33-local-observability-store.spec.md)); `attention` ([CLI-B6](../specs/17-engine-cli.spec.md)) | 1 | "See what happened": the crucial observability and reporting |
| Machine index, directory sink, home fleet copy, `stats --source/--live/--projection` ([CST](../specs/34-central-run-stats.spec.md)); the monitor plugin ([monitor set](../../../tempergraph-monitor/docs/specs/00-overview.spec.md)) without orchestration views | 1 | Accepted for the first release in ADR-0029; built last in the release, on settled documents |
| Caller provenance ([PRV](../specs/85-caller-provenance.spec.md)), supervision record and level, `report --supervision` ([SUP](../specs/86-supervision-metrics.spec.md) but §2.7), supervision cost with the Claude Code host hooks ([SCO](../specs/87-supervision-cost.spec.md)) | 1 | Contract C17 is cheapest built in; "who decided" is part of trusting a result |
| Run-store fields the improvement loop needs ([IMD](../specs/43-improvement-data.spec.md)); the ledger writer; the `label` verb ([FBK](../specs/41-feedback-and-judge-reliability.spec.md) entry only) | 1 | Data recorded from the first run, so later releases learn from release 1's runs |
| First install, shim, workflow registry ([UPD §2.7, §2.8](../specs/60-engine-update.spec.md)); workflow version, digest, release record and stamp ([VER](../specs/61-version-metadata.spec.md), stamp by `upgrade-check --stamp` over an empty changelog) | 1 | A workflow must install, register and be stamped |
| Diagram model and `graph`, deterministic scenarios, prompt lint, structural judge readiness report, executor compatibility table ([LIF](../specs/18-lifecycle-and-evals.spec.md)) | 1 | The creation path's verify step |
| `audit` definition and host layers ([AUD](../specs/55-workflow-audit.spec.md), their rules in [ARC](../specs/56-audit-rule-catalog.spec.md)), prompt audit ([PRA](../specs/58-prompt-audit.spec.md)) | 1 | The authoring skill runs them before the first run |
| Skills: run driver, authoring, project bootstrap, troubleshooter, install ([SHL](../specs/19-plugin-shell.spec.md), [LSK](../specs/65-lifecycle-skills.spec.md) install part) | 1 | "Their creation" and driving runs from a conversation |
| Workflow package format, authoring contract (blueprint, scaffold, comparison, literal check, minimal workflow) and a run-level outcome | 1, after design | Unspecified ([R-090 D1 to D3](../research/R-090-implementation-readiness.rsrch.md)); written before their tracks start |
| Judge calibration ([JCL](../specs/50-judge-calibration.spec.md)), eval suites ([EVS](../specs/51-eval-suites.spec.md)), judge reliability grades and labelling queue ([FBK](../specs/41-feedback-and-judge-reliability.spec.md)), live scoring, harvest and replay, the eval skill | 2 | Needs release 1's runs and labels; a precondition of stable mode and promotion |
| Promotion from local to pipeline ([ADR-0041](0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md), [SUP §2.7](../specs/86-supervision-metrics.spec.md), `promote-check`, still unspecified) and the `agent-sdk` executor ([EAS](../specs/21-executor-agent-sdk.spec.md)) | 2 | The pipeline is where a calibrated workflow goes; the SDK is its CI executor |
| `update`, rollback, run and store migration, changelog and transforms, the update skill ([UPD](../specs/60-engine-update.spec.md), [MIG](../specs/62-state-and-run-migration.spec.md), [VER](../specs/61-version-metadata.spec.md), [LSK](../specs/65-lifecycle-skills.spec.md)) | 2 | First needed when a second release exists; release 1 already writes the layout and format versions they read |
| Audit history layer, history rules and tool surface audit ([AUD](../specs/55-workflow-audit.spec.md), [ARC](../specs/56-audit-rule-catalog.spec.md), [TSA](../specs/57-tool-surface-audit.spec.md)) | 2 | Need a run history to be worth reading |
| Ask unit, event waits, breakpoints, deadlines, fallback target ([ASK](../specs/73-ask-unit.spec.md), [HUM](../specs/07-gate-and-human.spec.md), [FLX](../specs/74-flow-extensions.spec.md)); parallel read-only branches; sequential map ([MAP](../specs/77-map-unit.spec.md)); measured switches ([SWM](../specs/79-measured-switches.spec.md)); script cache; `self-check` ([CHK §2.5](../specs/75-check-contract-and-command-runs.spec.md)); sampled audit judge (JDG-B7); judge MCP views through the filtering proxy | 2 | Additive on the four-node unit; a release 1 workflow is expressible without them (a declared input on resume replaces an ask) |
| Lifecycle hooks, in-process observers and the wider hook events ([CLI §2.2](../specs/17-engine-cli.spec.md), [EVT §2.6](../specs/30-run-events.spec.md)) | 2 | Integration points for notifiers and trackers; the monitor covers the person in release 1 |
| State root outside git (R-011 G9); Windows | 2 | Release 1 is git repositories on macOS and Linux |
| Scheduled runs, the slice named in spec 83 SCH §5 (open in PR 16, with spec 84 TCK and contract C18): once and calendar recurrences for workflow targets, catch-up latest or none, overlap skip, run and period caps, every `schedule` verb except export, the OS trigger | 2 | Unattended runs need required cost caps, `attention` and caller provenance live first, and the `scheduler` caller kind builds on PRV |
| Scheduling, rest of SCH: orchestration and program targets, queue and parallel overlap, cron input, pipeline export | 3 | Follow orchestration and the pipeline |
| Self-improvement loop, proposals, trials, lessons ([SIL](../specs/16-self-improvement.spec.md), [PRP](../specs/40-improvement-proposals.spec.md), [LSN](../specs/42-workflow-lessons.spec.md), [IMD](../specs/43-improvement-data.spec.md) analyses) | 3 | Needs calibrated judges and a corpus of runs; it files issues outside the project, so it waits for measured trust |
| Orchestration, orchestrator skill, batch ([ORC](../specs/45-orchestration.spec.md), [OSK](../specs/46-orchestrator-skill.spec.md)) | 3 | The owner's "orchestration later" |
| Council, contest, writer branches, parallel map, sub-workflows and mapped sub-workflows, selective parallel ([CNL](../specs/71-council-unit.spec.md), [CTS](../specs/72-contest-unit.spec.md), [FLX](../specs/74-flow-extensions.spec.md)) | 3 | The owner's "advanced node types later" |
| `messages-api` with the tool host, `antigravity` ([EMA](../specs/20-executor-messages-api.spec.md), [THS](../specs/22-tool-host.spec.md), [EAG](../specs/12-executor-antigravity.spec.md)) | 3 | [ADR-0091](0091-first-release-ships-the-claude-executor-only.adr.md) |
| Workflow upgrade and the built-in upgrade workflow, upgrade skill ([WUP](../specs/63-workflow-upgrade.spec.md), [UWF](../specs/64-upgrade-workflow.spec.md)) | 3 | Needed at the first breaking release; until then pins keep workflows working |
| OTLP export ([TEL](../specs/35-telemetry-export.spec.md)); remote MCP in steps; a step sandbox profile (R-011 G10); a committed team settings layer | unscheduled | Deferred by ADR-0029 and ADR-0021, or not yet designed |

A unit kind, flow primitive or field the running release does not build is refused at validation with finding `not_in_release` ([WFM §2.1](../specs/02-workflow-model.spec.md)), never ignored, so a workflow written for a later release fails before spend.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| R-011's three cuts (cut 1: `claude`, step and route, pauses, check and judge, SQLite, run log, cost, five verbs) | Smallest first build | Leaves out settings, reruns, supervision, the monitor and the creation path the owner now asks for; contradicts accepted ADR-0029 |
| **Simple trusted workflows plus creation plus full local observability (chosen)** | Matches the owner's ask and ADR-0029; one coherent end-to-end story; data for later releases recorded from day one | A larger first release; the monitor and sinks are the first to move if it must shrink |
| Build everything designed | No scoping | No boundary, the failure R-011 G4 named; unmeasured judges behind self-improvement and orchestration |

## Decision rationale

| Criterion | R-011 cut 1 | Chosen | Everything |
|---|---|---|---|
| Owner's ask (simple workflows, creation, crucial observability) | partly | yes | yes |
| Agrees with accepted ADR-0029 and ADR-0040 | no | yes | yes |
| Buildable end to end, then provable live | yes | yes | no |
| Records the data later releases need from the first run | no | yes | yes |
| Puts unmeasured judges in charge of autonomous work | no | no | yes |

## Consequences

- Positive: one story to prove live (author, run, see, trust); every later release adds kinds, executors or loops to a core that does not change shape.
- Negative: no orchestration, self-improvement or second executor for a while; the "four executors" requirement is met at release 3 ([ADR-0091](0091-first-release-ships-the-claude-executor-only.adr.md)).
- Risk: release 1 is still large. Mitigation: the plan orders tracks so the core is usable before the monitor and sinks are built; if the release must shrink, those two move to release 2, which is the owner's call because ADR-0029 is accepted.
- Risk: the creation path rests on three specs not yet written. Mitigation: they are the plan's track D, written while the core is coded.

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| S1 | "Simple workflows" are linear or lightly branching runs of model and script steps as defined above; "advanced node types" are council, contest, map, parallel, sub-workflow and the flow extensions. | The sort table |
| S2 | "Crucial observability" covers everything ADR-0029 names plus supervision; long-range analytics stay in `stats` and `report`. | Release 1 rows |
| S3 | The first release targets git repositories on macOS and Linux (R-011 U3). | WSP, RCT, CHK-AC-2's Windows half |

## Revisit when

The owner trims or widens release 1, or release 1 is live-proven and release 2 is planned.
