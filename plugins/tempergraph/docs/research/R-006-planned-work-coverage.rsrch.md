# R-006 Planned capabilities against this design

## Problem statement

A workflow engine of this kind needs capabilities that a first design easily leaves out: judge reach and tool scope, live confirmation and unattended runs, cost, judge reliability, self-improvement, run tracking, and the needs of a delivery workflow. A design that ignored them would leave gaps that show only in use. This note checks a list of such planned capabilities against the specs and decision records, and records whether the design covers each, adds it now, defers it with a reason, or does not apply.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| This design | Specs and decision records | [specs](../specs/00-overview.spec.md), [adr](../adr/README.md) |

Read on 2026-11-19. Each classification below is `confirmed`: it comes from reading the planned item and the named spec side by side.

## Key findings

Status words: **covered** (in the design before this check), **added** (written into the named spec by this check), **deferred** (named in the spec or here, not designed, with the reason), **n/a** (code hygiene with no design consequence, or another plugin's work).

### Judge reach, tool scope and security

|---|---|---|---|
| Judges must not reach plugin-registered tools | DESIGNED | covered | [ECC](../specs/11-executor-claude-code.spec.md) `--bare` (P-CC-1), [EAS](../specs/21-executor-agent-sdk.spec.md) P-AS-1, [GRD](../specs/06-independence-guard.spec.md) guard; [EMA](../specs/20-executor-messages-api.spec.md) by construction |
| A command resolver so gates work outside Python | BUILT | added | [WFM](../specs/02-workflow-model.spec.md) `command_resolver`, [CON §2.1](../specs/01-contracts.spec.md) |
| Clear static-scan High findings | n/a | Code hygiene; the rule behind it is [SEC-B5, SEC-B6](../specs/14-security.spec.md) |
| Tools block and prompt-against-tools check | BUILT | covered | [PRM §2.2](../specs/04-prompt-rendering.spec.md), [WFM §2.2](../specs/02-workflow-model.spec.md) |
| Light release lane, drafted fixes, loop-opened pull request | DESIGNED | added (drafted fix); deferred (lane: a team process; loop-opened pull request: waits for drafted-fix data) | [SIL](../specs/16-self-improvement.spec.md) |
| Enforced tool declarations by default; strict permission mode | PARTLY BUILT | added (strict mode, default rule) | [EXI](../specs/10-executor-interface.spec.md), [CLI](../specs/17-engine-cli.spec.md) `--strict-permissions` |
| Remote MCP servers in a step's filtered tool set | DESIGNED | deferred: rests on unrun probe facts | [EXI](../specs/10-executor-interface.spec.md) open question |
| View catalog knows newer tracker and wiki tool names | PLANNED | added (additive names, generic write tiers partial) | [GRD](../specs/06-independence-guard.spec.md) |

### Live confirmation, unattended runs, run time

|---|---|---|---|
| Run fake-only capabilities once on the real binary | BUILT, AWAITING LIVE CHECK | covered | Probe tables in [ECC](../specs/11-executor-claude-code.spec.md), [EAG](../specs/12-executor-antigravity.spec.md), [EAS](../specs/21-executor-agent-sdk.spec.md); readiness flags in the [docs README](../README.md) |
| Open questions only the CLI and gateway settle | PLANNED | covered (subagent model P-CC-4, concurrency, flags); added (resume chains) | [BUD](../specs/08-budgets-and-failures.spec.md) |
| A flag moves to live-proven only with a written result | PLANNED | added | [docs README](../README.md#readiness-flags) |
| Batches end to end in any repository | PARTLY BUILT | added (batch file, event file); deferred (integration, pull-request adapter, shared-resource claims) | [WSP](../specs/13-workspace-and-concurrency.spec.md) |
| Engine from pipelines | DESIGNED | added (the Agent SDK and Messages API executors need no interactive sign-in); deferred (the hosted web service of another team) | [ADR-0018](../adr/0018-add-messages-api-and-agent-sdk-executors.adr.md) |
| Record who answered a pause | DESIGNED | covered; added (callers classified from host markers, relayed decisions backed by a person turn, supervision measures and cost) | [HUM-B6](../specs/07-gate-and-human.spec.md), [PRV](../specs/85-caller-provenance.spec.md), [SUP](../specs/86-supervision-metrics.spec.md), [SCO](../specs/87-supervision-cost.spec.md) |
| Delegation policy for agent answers | DESIGNED | deferred: needs calibrated judges and a C6 amendment | [HUM](../specs/07-gate-and-human.spec.md) |
| Auto mode | DESIGNED (draft) | added (never used: undeclared tools refuse) | [EXI](../specs/10-executor-interface.spec.md), [EAS](../specs/21-executor-agent-sdk.spec.md) |
| Token-free schedule for declared programs | PLANNED | added as a reserved target kind of schedules; declaring programs in a package is deferred | [SCH §5](../specs/83-schedules.spec.md) |
| Self-improvement delivery batch | PLANNED | deferred: waits for batch integration | this note |
| Idle watchdog with its own stalled class | PARTLY BUILT | covered (watchdog); added (stalled class in reports) | [EXI-B4](../specs/10-executor-interface.spec.md), [OBS](../specs/15-observability-and-cost.spec.md) |
| Sort each timeout into hung, slow host or model-silent | PLANNED | added | [OBS](../specs/15-observability-and-cost.spec.md) |
| A running tool's CPU and IO count as activity | DESIGNED | deferred: until timeouts are sorted | [EXI](../specs/10-executor-interface.spec.md) open question |
| Executor-neutral progress stream, loop detector, stop contract | DESIGNED | covered (stream, [ADR-0009](../adr/0009-normalized-session-event-stream.adr.md)); added (record-only loop signal, graceful stop) | [EXI](../specs/10-executor-interface.spec.md), [OBS](../specs/15-observability-and-cost.spec.md) |
| Slow host and "Request timed out" as infrastructure | BUILT | covered | [BUD §2.2](../specs/08-budgets-and-failures.spec.md) |
| Host-speed preflight; loop knows a slow host | PLANNED | added | [EXI](../specs/10-executor-interface.spec.md), [SIL](../specs/16-self-improvement.spec.md) |
| Prompt written before the stdin window closes | DESIGNED | covered (writer first); added (gap measured) | [EXI-B2](../specs/10-executor-interface.spec.md) |

### Cost, judge reliability, self-improvement

|---|---|---|---|
| Switch unit with overrides and a route record | PARTLY BUILT | covered (switch); added (override, record) | [CMP](../specs/03-compiler-and-flow.spec.md) |
| Code mode from plan size; low-effort phase watch | DESIGNED | n/a (temperspec's own routing) | temperspec |
| Route report and per-arm options | DESIGNED | added (per-arm cost); deferred (per-arm options) | [OBS](../specs/15-observability-and-cost.spec.md) |
| Model of each mapped item from the item | PARTLY BUILT | covered | [CON §2.1](../specs/01-contracts.spec.md) item function ref |
| Load only the MCP servers a step needs | BUILT | covered | [ECC §2.3](../specs/11-executor-claude-code.spec.md) |
| Measure each cost fix | PARTLY BUILT | covered | [SIL-B5](../specs/16-self-improvement.spec.md) |
| Cost outlier signal; first-visit and repeat split | DESIGNED | added | [SIL](../specs/16-self-improvement.spec.md), [OBS](../specs/15-observability-and-cost.spec.md) |
| Spend cap for a whole run; child spend in the parent's total | PLANNED | added | [BUD](../specs/08-budgets-and-failures.spec.md), [OBS](../specs/15-observability-and-cost.spec.md) |
| Operator skills as a core plus references | BUILT | covered | [SHL](../specs/19-plugin-shell.spec.md) |
| Double judging and confidence against outcome | PLANNED | added (sampled audit, recorded only) | [JDG](../specs/05-judge-and-verdict.spec.md) |
| Harvest real judge misses into cases | PLANNED | added | [LIF](../specs/18-lifecycle-and-evals.spec.md) |
| Score a judge live on a fixed subject | PLANNED | added | [LIF](../specs/18-lifecycle-and-evals.spec.md) |
| Judge-readiness report and the stable-mode rule | PLANNED | covered | [LIF](../specs/18-lifecycle-and-evals.spec.md) |
| Per-criterion rates, gate escapes, prompt digests | PLANNED | added | [OBS](../specs/15-observability-and-cost.spec.md) |
| Evals shipped with each workflow | PARTLY BUILT | covered | [OVR §2.1](../specs/00-overview.spec.md) layer 2 |
| Replay set of past cases | BUILT | added | [LIF](../specs/18-lifecycle-and-evals.spec.md) |
| Trigger and behaviour evals for skills | PLANNED | covered | [LIF §5](../specs/18-lifecycle-and-evals.spec.md) |
| Prompt lint for model-facing files | PLANNED | added | [LIF](../specs/18-lifecycle-and-evals.spec.md) |
| Confidence floor for filing; confidence scale; engine-made values | PLANNED / BUILT | covered | [SIL](../specs/16-self-improvement.spec.md) open question, [CON §2.8](../specs/01-contracts.spec.md) |
| Data behind the loop's defaults | PLANNED | covered | [SIL §5](../specs/16-self-improvement.spec.md) |
| Git facts in the outcome evidence | PLANNED | added | [SIL](../specs/16-self-improvement.spec.md) |
| File outcome issues only from a scored judge | PLANNED | added | [SIL](../specs/16-self-improvement.spec.md) |
| Quality lens with a scorecard per version | PLANNED | deferred: trustworthy only with judge reliability measured | [SIL](../specs/16-self-improvement.spec.md) |
| Move rule-like branching out of judge prose | PARTLY BUILT | added (design rule) | [JDG](../specs/05-judge-and-verdict.spec.md) |
| A blocked pause whose check ran nothing stays a fault | BUILT | added | [SIL](../specs/16-self-improvement.spec.md) |
| The loop names a cause for retry bursts (temperspec G) | PLANNED | added | [SIL](../specs/16-self-improvement.spec.md) |

### Tracking, run UX, hygiene, workflow-side

|---|---|---|---|
| A read-only facts verb | DESIGNED | added | [CLI](../specs/17-engine-cli.spec.md) `facts` |
| Run lifecycle hooks | DESIGNED | added | [CLI](../specs/17-engine-cli.spec.md) §2.3, [SEC](../specs/14-security.spec.md) |
| Tracker plugin, autonomy, rollout | DESIGNED | n/a: a separate plugin; the engine supplies facts and hooks only | [SHL](../specs/19-plugin-shell.spec.md) |
| Run aliases and origin | PLANNED | added | [DUR §2.2](../specs/09-durability-and-resume.spec.md), [CLI](../specs/17-engine-cli.spec.md) |
| Drill into a run; live tool calls | PLANNED | covered | `status --detail`, [OBS §2.3](../specs/15-observability-and-cost.spec.md) |
| Bootstrap cut to the engine's own setup | PLANNED | covered | [SHL §2](../specs/19-plugin-shell.spec.md) |
| Central per-user run stats with the ticket | PLANNED | added | [OBS](../specs/15-observability-and-cost.spec.md), [CLI](../specs/17-engine-cli.spec.md) `stats` |
| One thing per line in the update output | PLANNED | added (`update --json`) | [LIF](../specs/18-lifecycle-and-evals.spec.md) |
| Tests in a run worktree import the right engine | PLANNED | added (declared import roots) | [WSP](../specs/13-workspace-and-concurrency.spec.md) |
| A test must not depend on LangGraph internals | PLANNED | n/a: test practice of the old code; [CMP-AC-3](../specs/03-compiler-and-flow.spec.md) tests behaviour | — |
| Windows-safe merge renumbering helper | PLANNED | n/a: repository tooling | — |
| Generated tables with a drift test | PARTLY BUILT | covered | [CLI §5](../specs/17-engine-cli.spec.md) |
| Remove legacy code; no environment-variable executor fallback | PLANNED | covered as a rule: no environment variable selects an executor | [EXI §2.1](../specs/10-executor-interface.spec.md) |
| Multi-repository targets | deferred: no approach chosen | this note |
| Tracing with LangSmith or OpenTelemetry | PLANNED | deferred: governance decision | [OBS §5](../specs/15-observability-and-cost.spec.md) |
| A no-change blocker does not spend a retry | PARTLY BUILT | added | [JDG §2.2](../specs/05-judge-and-verdict.spec.md), [CON §2.8](../specs/01-contracts.spec.md) |
| Per-step idle limits | PLANNED | covered | [CON §2.1](../specs/01-contracts.spec.md) `idle_s` |
| Skills and agents resolved by plugin path, not bare name (temperspec D) | BUILT | added | [SHL](../specs/19-plugin-shell.spec.md) |
| Final-stage coverage, reading-set rules, spec cascades, plan checks (temperspec A, B, F, G) | various | n/a: temperspec's own workflow | temperspec |

## Conclusions

1. Of the engine's planned capabilities, the design already covered about a third; this check adds about half into the named specs, and defers the rest with a reason each.
2. Every deferral is one of three kinds: it rests on an unrun probe of a real binary, it needs measured judge reliability first, or it is batch and scheduling work beyond the first release.
3. Nothing planned is contradicted by the design. Two items change shape because tempergraph has more executors: the CI path is an executor choice (Agent SDK or Messages API) rather than a hosted service, and "a judge must not reach plugin tools" holds by construction on the Messages API executor.

## Open questions

| Question | Owner | How to settle |
|---|---|---|
| Is a recurring scheduler (workflow and declared-program ticks) in scope for tempergraph's first release? | Owner | Designed on 2026-11-20 at the owner's request ([SCH](../specs/83-schedules.spec.md), [TCK](../specs/84-schedule-ticks-and-unattended-fires.spec.md)); the recommended slice for the release after the first is in SCH §5. |
| Should batch integration (merge, conflict judge, one pull request) be part of the engine or a workflow? | Owner | Decide with the self-improvement delivery batch, which is its first consumer. |
</content>
</invoke>
