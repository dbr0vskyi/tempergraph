# tempergraph system overview

## Purpose

tempergraph ("tempered rails for AI workflows") is an opinionated Python framework on LangGraph. A team's repeated process is written as a workflow: declarative data of steps, gates and flow. The engine validates it, compiles it into a durable state graph and runs it. Every step is a fresh headless agent session; after every step a gate runs a deterministic check and then an independent judge in a fresh read-only session; the engine, never the judge, derives the verdict and routes: proceed, retry, go back, ask a person, or stop. Every model call is costed, every run is recorded, and a built-in self-improvement workflow reads finished runs and files issues where the fault lives.

The engine starts sessions through executors. Four are designed: the Claude Code CLI and the Antigravity CLI ([ADR `two-first-class-executors`](../adr/two-first-class-executors.adr.md)), the Claude Agent SDK and Anthropic's Messages API ([ADR `add-messages-api-and-agent-sdk-executors`](../adr/add-messages-api-and-agent-sdk-executors.adr.md)); releases 1 and 2 ship the first, `claude` ([ADR `first-release-ships-the-claude-executor-only`](../adr/first-release-ships-the-claude-executor-only.adr.md)), and what each release holds is [ADR `first-release-is-simple-trusted-workflows-on-one-machine`](../adr/first-release-is-simple-trusted-workflows-on-one-machine.adr.md). A workflow names engine-neutral model aliases and tool capabilities, so the same workflow can run its steps on any executor that declares what the step needs, and its judges on whichever executor can enforce a read-only view.

The system has four layers, each depending only on the one below: the engine (registry, compiler, graph runtime, gate funnel, executors, tool host, checkpoint, run log, analyzer, workspace and the built-in self-improvement workflow, on LangGraph, SQLite, the two CLIs as child processes and the Agent SDK and Anthropic client library inside engine worker processes); workflows as data (one package per workflow, using the engine's public interface only); the authoring surface (agents, skills and rules a workflow's prompts invoke inside a step session); and the shell (skills that drive the engine CLI from a conversation, and the read-only `tempergraph-monitor` plugin, which reads only the status document, the detail document and the observer events).

The system's goals, each owned by the specs named:

- G1 Start from a stated good outcome: a run-level outcome with final and intermediate criteria, each verified by a check, a judge or a person or shown as unverified, graded at every step gate and at a final outcome gate (OUT, WFM, JDG).
- G2 Deterministic checks first, an independent judge second, a verdict by rule (JDG, GRD).
- G3 Retries, trips back and pauses are graph edges driven by verdicts, each bounded by a budget (CMP, BUD, HUM, RST).
- G4 Durable, resumable runs that survive days at a pause, and reruns from any unit with a person's feedback (DUR, RRN).
- G5 The same workflow on any of the four executors, with refusal before spend when an executor cannot enforce what is asked (EXI, ECC, EAG, EAS, EMA).
- G6 Every model call costed; unmeasured is never zero (OBS).
- G7 A closed improvement loop that files scrubbed, de-duplicated issues, drafts measured changes and hands them to a person (SIL, PRP, FBK, LSN, IMD, SRV).
- G8 Non-experts author good workflows from an existing solution, references or a conversation, through a guided skill that works backwards from the good outcome, a scaffold that writes a Claude plugin with a Python part and its own docs, and checks up to a first trial (AUT, SCF, PKG, SHL, WFM, AUD).
- G9 Many runs planned as a graph of runs, validated before spend and supervised without a model, with every pause left to a person (ORC, OSK).
- G10 The engine and each workflow move between releases without losing a run (UPD, VER, MIG, WUP, UWF, LSK).
- G11 Every graph shape LangGraph can build, except the self-routing forms [research `node-types-against-langgraph`](../research/node-types-against-langgraph.rsrch.md) excludes, is declarable as workflow data, and higher-level units keep every outcome engine-derived and judged (SCR, CNL, CTS, ASK, FLX, SWF).
- G12 A delivery workflow is expressible through the public interface alone: checks that run commands and record facts, step values, per-item maps, measured switches and a finalizer that can never fail a passed run (CHK, VAL, MAP, FIN, SWM).
- G13 Every call and intervention on a run is attributed to a person, an agent, the orchestrator, a pipeline or the engine, and every run reports how much supervision it needed and what supervising it cost (PRV, SUP, SCO).
- G14 A person or a script schedules a workflow or an orchestration once or on a recurrence, model-free, and the run fires on any OS with no terminal open, capped, attested as scheduled and still answered by a person at every pause (SCH, TCK).

It is not a replacement for pull-request review (a finalizer opens a draft at most), not deterministic output, not a production-workload orchestrator, not a general chat agent, has no executor beyond the four, and is not a general tool harness: its own tool host serves only the Messages API executor ([THS](tool-host.spec.md)). Planned work is in scope only where [ADR `scope-of-planned-work`](../adr/scope-of-planned-work.adr.md) says so.

The component specs, each owning what follows its name:

- [contracts.spec.md](contracts.spec.md) CON: every shared type.
- [workflow-model.spec.md](workflow-model.spec.md) WFM: what a workflow declares; what is refused before a run.
- [compiler-and-flow.spec.md](compiler-and-flow.spec.md) CMP: four nodes per unit, edges, flow primitives.
- [prompt-rendering.spec.md](prompt-rendering.spec.md) PRM: what a step is told and must emit.
- [judge-and-verdict.spec.md](judge-and-verdict.spec.md) JDG: judge session, judgement block, verdict derivation.
- [independence-guard.spec.md](independence-guard.spec.md) GRD: view sets, the catalog, the after-the-fact guard.
- [gate-and-human.spec.md](gate-and-human.spec.md) HUM: routing, pauses, approvals, event waits, decisions.
- [budgets-and-failures.spec.md](budgets-and-failures.spec.md) BUD: counters, failure causes, loop-backs, limits.
- [durability-and-resume.spec.md](durability-and-resume.spec.md) DUR: checkpoints, thread states, resume, status, wait.
- [executor-interface.spec.md](executor-interface.spec.md) EXI: protocol, capabilities, preflight, binding, lifetime, conformance.
- [executor-claude-code.spec.md](executor-claude-code.spec.md) ECC: the `claude -p` mapping.
- [executor-antigravity.spec.md](executor-antigravity.spec.md) EAG: the `agy` mapping.
- [workspace-and-concurrency.spec.md](workspace-and-concurrency.spec.md) WSP: state root, shapes of parallel work, writers, batches.
- [security.spec.md](security.spec.md) SEC: launch rules, scrubbing, publish boundary.
- [observability-and-cost.spec.md](observability-and-cost.spec.md) OBS: run log, live progress, cost, reports.
- [self-improvement.spec.md](self-improvement.spec.md) SIL: lenses, filing, calibration feedback.
- [engine-cli.spec.md](engine-cli.spec.md) CLI: verbs, options, catalog.
- [lifecycle-and-evals.spec.md](lifecycle-and-evals.spec.md) LIF: install, compatibility, diagrams, evals.
- [plugin-shell.spec.md](plugin-shell.spec.md) SHL: the skills the engine plugin ships.
- [executor-messages-api.spec.md](executor-messages-api.spec.md) EMA: the engine-owned loop on the Messages API.
- [executor-agent-sdk.spec.md](executor-agent-sdk.spec.md) EAS: the `claude-agent-sdk` mapping.
- [tool-host.spec.md](tool-host.spec.md) THS: the engine's client tools for the Messages API.
- [run-options.spec.md](run-options.spec.md) ROP: run options.
- [lifecycle-hooks.spec.md](lifecycle-hooks.spec.md) HOK: lifecycle hooks.
- [session-contract.spec.md](session-contract.spec.md) SSN: the session contract.
- [schedule-timing-formats.spec.md](schedule-timing-formats.spec.md) STM: the exact timing formats of a schedule (`--at`, `--rrule`, `--every`, `--cron`) and their refusals, split from SCH.
- [run-events.spec.md](run-events.spec.md) EVT: record envelope, observer record kinds, activity journal, `events`, hook events.
- [run-detail-document.spec.md](run-detail-document.spec.md) RDD: one thread in full, for the monitor and people.
- [run-control.spec.md](run-control.spec.md) RCT: the `stop` verb.
- [local-observability-store.spec.md](local-observability-store.spec.md) LOS: state-root and home layouts, session and engine logs, retention.
- [central-run-stats.spec.md](central-run-stats.spec.md) CST: machine index, sinks, cross-machine stats.
- [telemetry-export.spec.md](telemetry-export.spec.md) TEL: OTLP export with the GenAI conventions, deferred ([ADR `own-observability-first-export-deferred`](../adr/own-observability-first-export-deferred.adr.md)).
- [improvement-proposals.spec.md](improvement-proposals.spec.md) PRP: clusters, proposals, change classes, case sets, trials.
- [proposal-text-growth.spec.md](proposal-text-growth.spec.md) PTG: the proposer may replace text, its judge weighs growth, measures per changed file, character budgets.
- [feedback-and-judge-reliability.spec.md](feedback-and-judge-reliability.spec.md) FBK: labels, reliability grades, labelling queue, binding-shift watch.
- [workflow-lessons.spec.md](workflow-lessons.spec.md) LSN: per-step lessons files and how they render and change.
- [improvement-data.spec.md](improvement-data.spec.md) IMD: the loop's requirements on the shared run store.
- [session-review.spec.md](session-review.spec.md) SRV: the model-free session digest, review plans and the tool-less reviewer.
- [orchestration.spec.md](orchestration.spec.md) ORC: orchestration file, supervisor, node states, `orchestrate` verbs, orchestration status.
- [orchestrator-skill.spec.md](orchestrator-skill.spec.md) OSK: the skill that plans, starts and walks a person through an orchestration.
- [judge-calibration.spec.md](judge-calibration.spec.md) JCL: gold case sets, judge scores and figures, the acceptance bar and state.
- [eval-suites.spec.md](eval-suites.spec.md) EVS: suite kinds and roles, grader order, live-suite caps, corrected rates.
- [workflow-audit.spec.md](workflow-audit.spec.md) AUD: the `audit` verb, its layers, report, views and ignores.
- [audit-rule-catalog.spec.md](audit-rule-catalog.spec.md) ARC: the audit's rules outside tools, keyed to ranked causes.
- [tool-surface-audit.spec.md](tool-surface-audit.spec.md) TSA: grant, need and use of each step and judge session.
- [prompt-audit.spec.md](prompt-audit.spec.md) PRA: model-facing text, its names, agreement with declarations and size.
- [decision-revisit.spec.md](decision-revisit.spec.md) DRV: decision records whose revisit trigger has fired.
- [engine-update.spec.md](engine-update.spec.md) UPD: the `install` and `update` verbs and the workflow registry.
- [version-metadata.spec.md](version-metadata.spec.md) VER: release record, changelog, transforms, stamps, compatibility states.
- [state-and-run-migration.spec.md](state-and-run-migration.spec.md) MIG: store layout migration and threads across releases.
- [workflow-upgrade.spec.md](workflow-upgrade.spec.md) WUP: the `upgrade` verb from baseline to stamp.
- [upgrade-workflow.spec.md](upgrade-workflow.spec.md) UWF: the gated workflow that makes model-assisted upgrade edits.
- [lifecycle-skills.spec.md](lifecycle-skills.spec.md) LSK: the install, update and upgrade skills.
- [script-units-and-hybrid-steps.spec.md](script-units-and-hybrid-steps.spec.md) SCR: script units, `before` and `after` scripts, the script cache.
- [council-unit.spec.md](council-unit.spec.md) CNL: members, modes, rounds, anonymity, the engine tally.
- [contest-unit.spec.md](contest-unit.spec.md) CTS: candidate slots, per-candidate judging, the pick rule.
- [ask-unit.spec.md](ask-unit.spec.md) ASK: questions, typed answers, the `input` pause.
- [flow-extensions.spec.md](flow-extensions.spec.md) FLX: selective parallel, mapped sub-workflows, deadlines, fallback, breakpoints.
- [check-contract-and-command-runs.spec.md](check-contract-and-command-runs.spec.md) CHK: the check contract, findings, facts, command runs, the check preview.
- [visit-session-record.spec.md](visit-session-record.spec.md) VSR: the calls of every session of a unit's visit, given to a check beside its attempt's own record.
- [step-values-and-template-keys.spec.md](step-values-and-template-keys.spec.md) VAL: the `value` artifact and the keys a template may name.
- [map-unit.spec.md](map-unit.spec.md) MAP: map declaration, fan-out, per-item gates and budgets, the join.
- [finalizer-contract.spec.md](finalizer-contract.spec.md) FIN: finalizer context, outcomes, once-only and exit-code rule.
- [measured-switches.spec.md](measured-switches.spec.md) SWM: shadow mode, per-arm overrides, re-arming.
- [run-settings-and-overrides.spec.md](run-settings-and-overrides.spec.md) RST: the settings catalog, layers, files, profiles and the `config` verb.
- [reruns-and-feedback.spec.md](reruns-and-feedback.spec.md) RRN: every way to run again, feedback, rulings, `rewind`, `rerun`.
- [worktree-mode.spec.md](worktree-mode.spec.md) WTR: `run.workspace`, worktree roots and lifecycle, the `worktree` verb.
- [schedules.spec.md](schedules.spec.md) SCH: the When grammar, zones, schedule entries, policies, the `schedule` verbs.
- [schedule-ticks-and-unattended-fires.spec.md](schedule-ticks-and-unattended-fires.spec.md) TCK: the OS-agnostic tick, fire token, scheduled-run ledger, unattended credentials.
- [caller-provenance.spec.md](caller-provenance.spec.md) PRV: caller kinds, signals, deciders and relay evidence, host profiles.
- [supervision-metrics.spec.md](supervision-metrics.spec.md) SUP: touches, the supervision record and level, aggregates.
- [supervision-cost.spec.md](supervision-cost.spec.md) SCO: the supervision journal, usage sources, attribution, the `supervision` verbs.
- [workflow-package.spec.md](workflow-package.spec.md) PKG: the plugin layout, engine manifest, builders, loading, the minimal package.
- [workflow-authoring.spec.md](workflow-authoring.spec.md) AUT: entry paths, intake, the backwards interview, verification search, revise mode.
- [run-outcome.spec.md](run-outcome.spec.md) OUT: the outcome file, verifier classes, trust, the outcome gate and record.
- [blueprint-and-scaffold.spec.md](blueprint-and-scaffold.spec.md) SCF: the blueprint, the literal check, the scaffold, `author verify`.
- [effort-ladder-and-model-escalation.spec.md](effort-ladder-and-model-escalation.spec.md) LAD: evidence and escalation.
- [judge-model-by-risk.spec.md](judge-model-by-risk.spec.md) JRK: risk levels and the judge floor.
- [complexity-routing.spec.md](complexity-routing.spec.md) CXR: complexity zones and re-arming.
- [promotion-check.spec.md](promotion-check.spec.md) PRO: workflow stages and the stamp.
- [run-state-on-a-branch.spec.md](run-state-on-a-branch.spec.md) CAR: run state carried on a branch.
- [windows-support.spec.md](windows-support.spec.md) WIN: platform rules.
- [subworkflow-unit.spec.md](subworkflow-unit.spec.md) SWF: a child workflow as a unit.
- [test-suite.spec.md](test-suite.spec.md) TST: the engine's own test run: workers, one-process runs, folders no test shares.
- [loop-issues.spec.md](loop-issues.spec.md) ISS: the labels and body of the loop's issues, and what a closed issue changes.
- [cause-bindings.spec.md](cause-bindings.spec.md) BND: a loop issue closed as a duplicate that names another issue binds its cause to it: how the target is read from the closing comment and kept in a record, the comments sent there instead of new issues, and what a closed target decides.
- [judge-read-share.spec.md](judge-read-share.spec.md) SRV (split from 44): the finding for a judge that read too small a share of the change.
- [runs-without-a-final-exit.spec.md](runs-without-a-final-exit.spec.md) SIL (split from 16): a stop at a pause and a lost runner as final exits for the loop, recorded once.
- [pull-request-read.spec.md](pull-request-read.spec.md) OUT (split from run-outcome): how the loop reads the pull request a run recorded into `later[]` entries: which are read, who counts as a person, the follow-up commits, the files the run wrote, the cost of a read, what a pull request that cannot be read leaves and the finding an escape owes.
- [review-repeats.spec.md](review-repeats.spec.md) SRV (split from 44): a review category kept in several sessions of a run or in several runs of a workflow, recorded as a finding for the proposer that files no issue alone.
- [loop-summary-and-review-retries.spec.md](loop-summary-and-review-retries.spec.md) SIL (split from self-improvement): the retry of session reviews that stopped at a usage limit, and the summary the loop child writes when it ends.
- [friction-causes.spec.md](friction-causes.spec.md) FRC: the friction causes the loop makes from a run's records for a trip back, a stop at the attempt cap, a last stage that delivered nothing, a session the usage limit refused and a pause at an ask unit.
- [friction-filing-decisions.spec.md](friction-filing-decisions.spec.md) FFD: how the answers recorded for a friction finding's fingerprint attribute it, the one reason a finding that is not filed carries, the numbers and the reason that the loop's records hold, and what the friction judge is told about attribution.

The monitor's own design set is [plugins/tempergraph-monitor/docs](../../../tempergraph-monitor/docs/specs/overview.spec.md). Assumptions made while the owner was unavailable are in [ADR `standalone-design-assumptions`](../adr/standalone-design-assumptions.adr.md); design notes and the origin of each spec block are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### OVR-B1 A run end to end

WHEN an operator starts a run of a registered workflow THE engine SHALL resolve the input read-only ([CLI](engine-cli.spec.md)), preflight every executor, alias and tool ([EXI](executor-interface.spec.md)), classify the thread, take the lock and prepare the workspace ([DUR](durability-and-resume.spec.md), [WSP](workspace-and-concurrency.spec.md)), compile the graph ([CMP](compiler-and-flow.spec.md)) and drive its units, each running its step session, its check, its judge session and its gate ([PRM](prompt-rendering.spec.md), [JDG](judge-and-verdict.spec.md), [HUM](gate-and-human.spec.md)); spend model calls only on steps, judges and the detached self-improvement child ([SIL](self-improvement.spec.md)); exit 3 at a pause; and after the last gate run the finalizer and the recording ([OBS](observability-and-cost.spec.md)) and exit with a code from [CON](contracts.spec.md).

- GIVEN a two-unit workflow whose units both pass WHEN it runs THEN four model sessions ran (two steps, two judges), the finalizer ran once and the exit code is 0

### OVR-B2 Mixed executors

WHEN a run is preflighted and a step's executor cannot restrict judge tools THE engine SHALL bind that step's judge to an executor that declares `restricts_judge_tools`, or refuse the start with exit 2 ([ADR `cross-executor-judging`](../adr/cross-executor-judging.adr.md)).

- GIVEN steps on Antigravity and no bound executor that restricts judge tools WHEN the run is preflighted THEN the start is refused with exit 2 before any spend

### OVR-B3 Every model call is an executor run

WHEN any model call is made THE engine SHALL make it as an executor run logged with its usage, and finalizers and routes SHALL call no model ([OBS](observability-and-cost.spec.md)).

- GIVEN a run log WHEN its model calls are counted THEN each is an `agent_run` record with usage and none comes from a finalizer or a route

### OVR-B4 Observability never changes a run

WHEN logging, a report or self-improvement fails THE engine SHALL treat it as best effort and leave the run and its exit code unchanged ([OBS](observability-and-cost.spec.md)).

- GIVEN a ledger write that fails WHEN the run ends THEN its exit code is the one it would have had

### OVR-B5 Executors behave the same everywhere

WHEN any executor launches a session THE engine SHALL use one renderer, keep the prompt off argv, build argv from constants only, never raise, and tie children to the engine ([EXI](executor-interface.spec.md)).

- GIVEN a planted canary in a prompt WHEN any executor launches THEN the canary is not in argv

### OVR-B6 A step never grades itself

WHEN a step's work is assessed THE engine SHALL have an independent judge assess it and derive the verdict itself ([JDG](judge-and-verdict.spec.md)).

- GIVEN a step that writes "PASS" in its own output WHEN the gate decides THEN the verdict comes from the judge's judgement and the engine's rule, not from the step

### OVR-B7 Pure nodes run safely again

WHEN a gate, route or join is re-run THE engine SHALL produce the same result without side effects, and run the judge and the gate once per attempt ([CMP](compiler-and-flow.spec.md)).

- GIVEN a resume that replays a route node WHEN it runs again THEN it picks the same target and starts no session

### OVR-B8 One interrupt per gate

WHEN a gate pauses THE engine SHALL raise exactly one interrupt and accept a decision on it only from a person ([HUM](gate-and-human.spec.md)).

- GIVEN a paused gate WHEN an agent with no relayed person answers THEN the pause stays open

### OVR-B9 State merged under a stable thread

WHEN state changes THE engine SHALL keep it as JSON merged by reducers under a stable thread id, and never merge a fresh run into an existing thread ([DUR](durability-and-resume.spec.md)).

- GIVEN a finished thread WHEN a fresh run starts with the same request THEN it gets a new thread id

### OVR-B10 The engine names no workflow

WHEN a workflow needs an engine change THE engine core SHALL take it only as a capability any workflow can use and never name a workflow ([WFM](workflow-model.spec.md), [ADR `the-engine-names-no-workflow`](../adr/the-engine-names-no-workflow.adr.md)).

- GIVEN the engine's source, skills and tests WHEN they are scanned for workflow package names THEN none is found

### OVR-B11 Secrets scrubbed

WHEN anything is recorded or published THE engine SHALL scrub secrets and publish metadata only ([SEC](security.spec.md)).

- GIVEN a step output holding an API key WHEN its log line is written THEN the key is replaced by the scrub marker

### OVR-B12 Paths inside the workspace

WHEN a path is resolved THE engine SHALL resolve it inside the workspace, with the state root in the main checkout ([WSP](workspace-and-concurrency.spec.md)).

- GIVEN an artifact path `../outside.md` WHEN it is resolved THEN it is refused

### OVR-B13 One graph per process

WHEN a process runs a graph THE engine SHALL run only that one graph in it ([WSP](workspace-and-concurrency.spec.md)).

- GIVEN a process running a thread WHEN a second run is asked of it THEN it starts in its own process

### OVR-B14 Versioned schemas, tolerant readers

WHEN a persisted document is written or read THE engine SHALL carry its schema version and read it tolerantly ([CON](contracts.spec.md)).

- GIVEN a document with an unknown key WHEN it is read THEN the key is skipped

### OVR-B15 Read-only verbs call no model

WHEN input resolution or a read-only verb runs THE engine SHALL call no model and create nothing but the hand-off of a lost runner ([CLI](engine-cli.spec.md), [SIL-B29](runs-without-a-final-exit.spec.md)).

- GIVEN `status` on a state root with no lost runner WHEN it runs THEN no session starts and no file is created

### OVR-B16 Measurement never writes code

WHEN a measurement call runs THE engine SHALL let it write no code ([SIL](self-improvement.spec.md)).

- GIVEN a self-improvement measurement session WHEN it ends THEN no file in the repository changed

### OVR-B17 Refusal before spend

WHEN a workflow asks for a capability its executor does not declare THE engine SHALL refuse before spend, never downgrade silently ([EXI](executor-interface.spec.md)).

- GIVEN a step needing `web` on an executor that does not declare it WHEN preflighted THEN the start is refused with no session started

### OVR-B18 The supervisor calls no model

WHEN the orchestration supervisor acts THE engine SHALL let it call no model and answer no gate, and start, resume and stop runs only through the engine's own verbs ([ORC](orchestration.spec.md)).

- GIVEN an orchestration node paused at a gate WHEN the supervisor ticks THEN the pause stays for a person

### OVR-B19 Every intervention is attributed

WHEN anyone intervenes on a run THE engine SHALL record the caller and decider with the evidence for them, and never infer a person from a caller's word alone ([PRV](caller-provenance.spec.md)).

- GIVEN an agent that says it relays a person and carries no evidence WHEN it resumes a run THEN the decider is recorded as the agent

### OVR-B20 The schedule tick calls no model

WHEN the schedule tick runs THE engine SHALL let it call no model and answer no gate, start runs and orchestrations only through the engine's own verbs, and start a slot at most once ([TCK](schedule-ticks-and-unattended-fires.spec.md)).

- GIVEN two ticks racing on one due slot WHEN both run THEN exactly one run starts

### OVR-B21 One owner for each requirement

WHEN a spec names a requirement another spec owns, or a component needs a type not in [CON](contracts.spec.md) THE set SHALL remove the duplicate as a review finding, and add the type to CON first.

- GIVEN two specs that both define one record WHEN reviewed THEN one keeps it and the other links to it

## Acceptance criteria

- OVR-AC1 (OVR-B1, OVR-B21): Every goal G1 to G14 is owned by at least one component spec, and every contract behaviour OVR-B3 to OVR-B20 names exactly one owner spec
- OVR-AC2 (OVR-B21): Every spec in Purpose exists, follows the spec rule and stays within 400 lines and 30 KB
- OVR-AC3 (OVR-B21): Every link between specs, decision records and research notes resolves
- OVR-AC4 (OVR-B14, OVR-B21): No component spec defines a type that [CON](contracts.spec.md) also defines
- OVR-AC5 (OVR-B2, OVR-B3, OVR-B4, OVR-B5, OVR-B6, OVR-B7, OVR-B8, OVR-B9, OVR-B10, OVR-B11, OVR-B12, OVR-B13, OVR-B15, OVR-B16, OVR-B17, OVR-B18, OVR-B19, OVR-B20): Each contract holds by its owner spec's acceptance criteria

## Open questions

- Is account-based (consumer) Antigravity use permitted as a child process for the operator's account type? Until answered: the Antigravity executor is not shipped ([research `antigravity-cli-headless`](../research/antigravity-cli-headless.rsrch.md)). Owner: owner.
- May the Agent SDK executor run on an operator's subscription sign-in, or only on API and cloud credentials? Until answered: API and cloud credentials only ([research `claude-agent-sdk-executor`](../research/claude-agent-sdk-executor.rsrch.md)). Owner: owner.
