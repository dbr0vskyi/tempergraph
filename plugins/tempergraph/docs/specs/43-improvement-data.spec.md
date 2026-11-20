---
title: Improvement data requirements
type: component
status: ready-for-implementation
prefix: IMD
adrs: [0033, 0030, 0034]
---

# Improvement data requirements

## 1. Overview

What the self-improvement loop ([SIL](16-self-improvement.spec.md), [PRP](40-improvement-proposals.spec.md), [FBK](41-feedback-and-judge-reliability.spec.md), [LSN](42-workflow-lessons.spec.md)) needs to read, stated as requirements on the run data store that the run-monitor and observability design owns: the per-repository state under `.tempergraph/` and the cross-machine aggregate. This spec designs no store of its own ([ADR-0033](../adr/0033-improvement-data-is-a-requirement-on-the-run-store.adr.md)). It lists the records and fields the loop reads, which may leave the machine and which may not, the events the loop emits, the parameters whose values must carry provenance, and the figures that measure the loop itself. The analysis behind it is [R-031 F2](../research/R-031-self-improvement-gap-analysis.rsrch.md).

## 2. Contract

### 2.1 Requirements on the store

| # | Requirement | Why |
|---|---|---|
| IMD-R1 | Every record the loop reads carries `run_id`, `thread`, `workflow`, `workflow_version`, `machine` (a stable pseudonymous id, not a host name) and `repo` (a digest of the normalized remote URL) | Joins across runs, machines and repositories |
| IMD-R2 | Every `agent_run` carries the digests of its rendered template, its lessons block and, for a judge, its brief, stance and criteria set | A version comparison splits by what the model saw ([LSN](42-workflow-lessons.spec.md)) |
| IMD-R3 | Every `gate` record keeps the per-criterion list (id, status, `defect_in`, `no_change`), confidence with its source, and the judge binding of [FBK §2.1](41-feedback-and-judge-reliability.spec.md) | Reliability, the quality lens and gate escapes |
| IMD-R4 | Labels ([FBK](41-feedback-and-judge-reliability.spec.md)), clusters, proposals and trials ([PRP](40-improvement-proposals.spec.md)) are stored as their own record kinds with `schema_version` | They outlive the run that produced them |
| IMD-R5 | Issue and pull-request state for every loop-filed issue and every proposal: `filed`, `commented`, `fixed` (closed by a merged change), `noise` (closed as not planned), `stale` (open 60 days), with timestamps | The loop's own metrics (§2.4) |
| IMD-R6 | The local evidence file (request, outputs, feedback text) stays on the machine that made it. Only records of §2.2 cross a machine boundary | C9; the publish boundary of [SEC](14-security.spec.md) |
| IMD-R7 | The aggregate answers the loop's window queries in one call: counts of runs, distinct request digests and machines per cluster in a window; repeat cost per cluster; labels per gate binding | The pattern rule and ranking need all machines (G6 of R-031) |
| IMD-R8 | When no aggregate is configured, or it cannot be reached, every query falls back to the local records and says so in its result (`scope: local`) | The loop works on one laptop and never blocks a run |
| IMD-R9 | Records are append-only; a correction is a new record that names the one it replaces | Trials and grades are reproducible from history |
| IMD-R10 | Retention: metadata records at least 400 days; evidence files 90 days by default, operator-configurable; a deleted evidence file leaves its records readable | Windows of 30 and 90 days, year-on-year comparison |
| IMD-R11 | The store emits the loop events of §2.3 to the engine's event surface (lifecycle hooks of [CLI §2.2](17-engine-cli.spec.md), and whatever event interface the monitor design adds) | The monitor shows the loop; integrations react |
| IMD-R14 | Every tool grant and allowed command is a `grant` run-log record and an entry of the ledger row's `grants[]` (names, classes, `via`, used or not, outcome after; never the session's text), and the aggregate counts grants per (workflow, unit, capability) across runs and machines ([SIL §2.4](16-self-improvement.spec.md), [RST §2.8](80-run-settings-and-overrides.spec.md)) | The loop proposes the declaration a grant keeps standing in for |
| IMD-R13 | Every run line, `agent_run`, ledger and finding record carries `settings_digest` and `overridden_keys`, and a rerun's records carry `rerun_of` ([RST §2.7](80-run-settings-and-overrides.spec.md), [RRN §2.4](81-reruns-and-feedback.spec.md)) | Lenses compare runs with like settings and do not file an operator's override as a workflow fault; a rerun is joined to its source as an outcome signal |
| IMD-R15 | Every intervention record carries its `Caller` ([PRV §2.5](85-caller-provenance.spec.md)); the ledger row carries `supervision{}` ([SUP §2.2](86-supervision-metrics.spec.md)) and, once closed, a `supervision` line with the supervising sessions' cost ([SCO §2.5](87-supervision-cost.spec.md)); the aggregate counts touches by class, decider and pause cause per (workflow, unit) across runs and machines | Agent rescues cluster into workflow issues; promotion and the loop read supervision, not only a person's touches |
| IMD-R12 | A request digest is a keyed hash with a per-installation key, so equal requests match across one team's machines and cannot be looked up from outside | Distinct-request counts without request text |

### 2.2 What may leave the machine

| Record | Crosses to the aggregate | Never crosses |
|---|---|---|
| Run line, `agent_run`, `gate` | Names, enums, counts, costs, durations, digests, criterion ids and statuses | Evidence text, tool inputs, paths outside the workflow package |
| Caller blocks, supervision records | Kinds, deciders, relay values, touch counts, levels, token counts and costs, hashed host sessions | Host session ids in the clear, prompt text, commands |
| Findings, clusters | Cause codes, counts, sides | Rationale text of the friction judge |
| Labels | All fields | The person's typed reason (stays in evidence, referenced by id) |
| Proposals | Ids, classes, side, state, the rule sentence, patch digest | The patch itself (it lives on its branch in the workflow's repository) |
| Trials | Pairs as values and outcomes, metrics, spend, decision | Case requests |
| Parameters | All fields | |

### 2.3 Loop events

| Event | Emitted when | Payload (ids and enums only) |
|---|---|---|
| `finding_recorded` | SIL writes findings at an exit | run, causes, sides |
| `issue_filed`, `issue_commented` | SIL files or comments | cluster, issue URL, side |
| `label_recorded` | A label is derived or entered | gate record, kind, value, source |
| `proposal_state` | A proposal changes state | proposal, state, classes |
| `trial_progress` | A trial case pair finishes, and at the end | trial, pairs done, spend, decision when final |
| `binding_shift` | FBK records a shift | gate, old and new binding |

Release 1 emits `finding_recorded`, `issue_filed` and `issue_commented`; the labels and binding shifts an exit adds ride on it (`labels`), and the other loop events are read from their records (ledger rows, `findings.json`, proposal and trial records) until a release adds them.

### 2.4 Loop metrics

Read-only figures over a window, per workflow and for the engine side, printed by `report --loop` and readable by the monitor.

| Figure | Definition |
|---|---|
| Funnel | Findings → clusters → issues filed → proposals → trials → `shown_better` → merged → held after release |
| Issue precision | `fixed` ÷ (`fixed` + `noise`) over issues closed in the window |
| Time to fix | Median days from first finding of a cluster to the merge that closed it |
| Held after release | Share of merged proposals with no `regressed_after_release` |
| Loop spend | Self-improvement children, proposer runs and trials, reported and estimated apart |
| Estimated saving | Repeat cost per run of the cluster before and after the merge, times runs since; shown with the run counts it rests on, never as a single headline figure |
| Label coverage | Share of gates whose current binding is `reliable`, `unmeasured`, `unreliable` |

### 2.5 Parameters with provenance

Every threshold of the loop is a named parameter record, not a constant in prose.

| Field | Meaning |
|---|---|
| `name` | e.g. `pattern_rule.min_distinct_requests`, `fbk.false_pass_max`, `trial.guard.run_cost_pct` |
| `value` | |
| `provenance` | `default_no_data`, `fitted`, `owner_decision` |
| `fitted_on` | `{window, n, query digest}` when fitted |
| `set_at`, `set_by` | |

Reports print a parameter's provenance beside any figure it decides. Changing a parameter is a workflow or engine configuration change reviewed like any other; the loop never changes its own parameters.

## 3. Behaviours

**IMD-B1 Pattern across machines.** Given an outcome gap seen once each on three machines with three distinct request digests in 30 days, when the pattern rule runs with the aggregate reachable, then it counts three runs, three requests, three machines and files; with the aggregate unreachable it counts one and records `scope: local`.

**IMD-B2 Evidence stays home.** Given a run on machine A, when its records reach the aggregate, then the canary string planted in its request appears in no aggregated record.

**IMD-B3 Loop precision is computed.** Given 10 loop issues closed in a window, 6 by a merged change and 4 as not planned, when `report --loop` runs, then issue precision is 0.6 and the report names both counts.

**IMD-B4 Provenance printed.** Given a report row decided by `trial.guard.run_cost_pct = 15` with provenance `default_no_data`, when printed, then the row shows the parameter and its provenance.

## 4. Error conditions

| Condition | Result |
|---|---|
| A record without `machine` or `repo` | Read locally; excluded from aggregate queries and counted under `unkeyed` |
| Two installations with different digest keys in one aggregate | Distinct-request counts are per key and the report warns `mixed_digest_keys` |
| A store write fails | The run and its exit code are unchanged (C2); the loop reads what exists |

## 5. Design notes

- These requirements are additive to what the observability design already records ([OBS](15-observability-and-cost.spec.md)); where it names a field differently, its name wins and this table is updated.
- Pseudonymous machine ids and keyed request digests are the smallest identity that makes cross-machine pattern counting work without sending text; anything more is a governance decision the owner makes with the aggregate's design.
- Release 1 build ([T7 plan](../plans/t7-observability.plan.md) T7.5, [T10 plan](../plans/t10-monitor.plan.md) T10.1): the aggregate is the directory sink of [CST](34-central-run-stats.spec.md). Sink `run` rows carry `machine_id`, `repo_id` (keyed with the sink key), `thread_hash`, `workflow` and `workflow_version`; `label` rows (IMD-R4) carry `run_id` (`<thread>#<segment>`), `thread`, `workflow`, `workflow_version`, `machine` and `repo`, the same join keys as the ledger's `run_segment` and `intervention` rows (`tempergraph/identity.py`: the machine id, and the first 16 hex of the SHA-256 of the normalized origin URL, null without an origin; unkeyed, since the ledger stays local in release 1). IMD-AC-1 is tested over the sink, the fleet copy, the outbox and label rows. Labels do not cross to a sink in release 1.

## 6. Acceptance criteria

- [ ] IMD-AC-1 Every record kind of §2.2 passes the canary test: no planted request, output or feedback text crosses to the aggregate.
- [ ] IMD-AC-2 Every loop query returns `scope: local` or `scope: aggregate`, and IMD-B1 holds in both.
- [ ] IMD-AC-3 Every threshold named in SIL, PRP, FBK and LSN exists as a parameter record with a provenance.
- [ ] IMD-AC-4 `report --loop` reproduces a hand-computed fixture of every §2.4 figure.

## Open questions

| Question | Owner | Release 1 default |
|---|---|---|
| Who reads pull-request and issue state for IMD-R5 on a team: each machine, or the aggregate's collector once? Assumed the collector, to avoid N reads of the code host. | Owner, with the run-monitor design | The collector |

## References

[OBS](15-observability-and-cost.spec.md) · [SEC](14-security.spec.md) · [WSP](13-workspace-and-concurrency.spec.md) · [SIL](16-self-improvement.spec.md) · [PRP](40-improvement-proposals.spec.md) · [FBK](41-feedback-and-judge-reliability.spec.md) · [R-031](../research/R-031-self-improvement-gap-analysis.rsrch.md)
