---
title: Supervision metrics
type: component
status: review
prefix: SUP
adrs: [0085, 0086, 0088, 0089]
---

# Supervision metrics

## 1. Overview

How much a run needed someone, and who that was. A workflow you can trust is one that reaches a good result with few touches by anyone, not only with few touches by a person: a run babysat by an agent looks autonomous if only people are counted ([R-085](../research/R-085-callers-supervision-and-babysitting-cost.rsrch.md) D6, B3). This spec defines a **touch**, the per-run **supervision record**, a run's **supervision level**, the per-workflow aggregates, where each figure is written and read, and the supervision criteria for promoting a workflow ([ADR-0041](../adr/0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md), [ADR-0089](../adr/0089-supervision-is-a-promotion-and-improvement-measure.adr.md)).

Every figure is built from records written when the act happened: the `caller` blocks of [PRV](85-caller-provenance.spec.md) and, for the spend of supervising sessions, the supervision journal of [SCO](87-supervision-cost.spec.md). Nothing is classified after the fact by a model. Building and writing them is best effort and never changes a run (contract C2); every reader is model-free (C13).

## 2. Contract

### 2.1 Touches

A **touch** is one accepted call that changes a thread's course or answers it, made by anyone but the thread's own graph. Each has a class, an action and the `caller` block of the call.

| Class | Actions | Meaning |
|---|---|---|
| `designed` | `approve` (approval pause or approval node), `answer` (an ask's `input` pause), `event` (a wait's event value) | The workflow asked for it; part of the job |
| `rescue` | `decide` at an `escalation` or `budget` pause (any cause, `tool_access` and council no-decision included), `apply_deadline` with `escalate` | The workflow could not go on alone |
| `steer` | `rewind`, `rerun` (on the source thread), `stop`, `grant`, `override` (settings changed on a resume), `ruling`, `breakpoint` (the resume of a `--pause-before`), `edit` (an orchestration edit naming the node) | Someone changed the course unasked |
| `engine` | infra re-open, the orchestrator's `reopen_infra`, the self-improvement child | No supervisor; counted apart and never as supervision |

The start of a run is not a touch; it is counted as `starts`. A scheduled start is a `starts` entry of caller `scheduler`; the person's `schedule add` and `edit` are setup counted once per schedule, never per run ([TCK §2.7](84-schedule-ticks-and-unattended-fires.spec.md)). One resume can be several touches (a `decide` that also grants and overrides is one `rescue` and two `steer`). An undesigned touch is a `rescue` or a `steer`.

### 2.2 Supervision record of a run

Built at every `run_exit` for the thread so far, written as the `supervision{}` object of the ledger row ([SIL §2.4](16-self-improvement.spec.md)) and as a `supervision` run-log record ([EVT §2.2](30-run-events.spec.md)). Cost fields are filled later by [SCO §2.5](87-supervision-cost.spec.md) and are null until then.

| Field | Meaning |
|---|---|
| `touches` | Counts by class × `decided_by` (`person`, `agent`, `unknown`, `pipeline`, `orchestrator`, `scheduler`), and by pause kind for `rescue` |
| `undesigned` | `rescue` + `steer`, every decider |
| `relayed` | Counts by `relay` (`turn_named`, `turn_only`, `claimed`) |
| `agent_own_rescues` | `rescue` touches with `decided_by: agent` |
| `wait_s` | Seconds from each `pause` record (or due approval node) to the touch that answered it, summed per decider; `person_wait_s` is the `person` sum, as in [CST §2.2](34-central-run-stats.spec.md) |
| `latency_s` | Median and maximum of the same per-pause times |
| `observations` | Read-only engine calls about the thread by supervising hosts, from the journal; null with no journal ([SCO §2.4](87-supervision-cost.spec.md)) |
| `supervisors` | Number of distinct host sessions that called about the thread, and their hosts |
| `callers_unknown` | Touches and starts whose caller is `unknown` |
| `supervision_cost` | `{marginal, turn, completeness}` per [SCO §2.5](87-supervision-cost.spec.md) |
| `supervision_share` | Marginal estimated supervision cost ÷ (the run's estimated cost + that), null when either is unmeasured |
| `level`, `level_by` | §2.3 |

A rerun thread has its own record; the rerun is a `steer` touch on its source thread. Reports roll a lineage up to its root on request ([RRN §2.4](81-reruns-and-feedback.spec.md)).

### 2.3 Supervision level of a run

The user's-role scale of Feng, McDonald and Zhang ([R-085](../research/R-085-callers-supervision-and-babysitting-cost.rsrch.md) P4), read from the run's own touches. The first matching row from the top wins.

| Level | Rule |
|---|---|
| `operator` | Undesigned touches on half or more of the units the run reached, or a breakpoint before every unit |
| `collaborator` | At least one `steer` touch |
| `consultant` | At least one `rescue` touch, no `steer` |
| `approver` | `designed` touches only |
| `observer` | No touch after the start |

`level_by` says who made the undesigned touches: `person` (every one `decided_by: person`), `agent` (every one `agent`), `mixed`, or `none` for `observer` and `approver`. An `approver` run whose designed touches were all made by an agent is `approver` with `designed_by: agent` shown beside it, since the workflow asked a person and got an agent.

### 2.4 Workflow aggregates

Read-only, over a window (default 30 days) per workflow and version, from the ledger and the stats rows, local or from the fleet copy ([CST §2.5](34-central-run-stats.spec.md)). A figure over fewer than 5 runs is shown with its count and marked `thin`.

| Figure | Definition |
|---|---|
| Runs, by level and `level_by` | Counts and shares |
| Unattended rate | Share of runs at `observer` or `approver`, with a 95% Wilson interval |
| Undesigned touches per run | Mean, by class and by decider |
| Agent's own rescue share | `agent_own_rescues` ÷ all `rescue` touches |
| Relay quality | Share of agent relays by `relay` value |
| Wait on people | p50 and p90 of `person_wait_s` per run, and per pause kind |
| Supervision cost per run | p50 and p90 of marginal estimated cost; the turn figure beside it ([ADR-0088](../adr/0088-attribute-supervision-spend-by-marginal-tokens-beside-turn-totals.adr.md)) |
| Supervision share | Median and p90 of `supervision_share` |
| Observations per run | Median; and the share of supervision cost spent re-reading after a wake (`rewake`, [SCO §2.4](87-supervision-cost.spec.md)) |
| Data quality | Share of runs with every caller known; share with supervision cost measured |

### 2.5 Where the figures land

| Place | What it holds | Owner of the shape |
|---|---|---|
| Run log | `caller` blocks on every intervention ([PRV §2.5](85-caller-provenance.spec.md)); the `supervision` record at each `run_exit` | [EVT §2.2](30-run-events.spec.md) |
| Ledger row | `supervision{}` (§2.2), cost filled on close | [SIL §2.4](16-self-improvement.spec.md), [IMD-R15](43-improvement-data.spec.md) |
| Stats and sink rows | The `run` row gains `touches_undesigned`, `touches_by_decider`, `agent_own_rescues`, `level`, `level_by`, `callers_unknown`; the `supervision` row carries the cost when it closes; the heartbeat says who a waiting run waits on (`person` or the supervising host) | [CST §2.2](34-central-run-stats.spec.md) |
| Detail document | A `supervision` block: touches in time order with class, action, caller kind, decider, relay and wait; the open supervising sessions; cost so far | [RDD](31-run-detail-document.spec.md) |
| Monitor | Run view: the level and the touch list; cost tab: run cost and supervision cost apart, and the share; fleet tab: level and supervision share per workflow | monitor [MRV](../../../tempergraph-monitor/docs/specs/03-run-view.spec.md), [MCF](../../../tempergraph-monitor/docs/specs/06-cost-and-fleet.spec.md) |
| Reports | `report --supervision [window] [--by workflow\|version\|unit\|host\|level]` prints §2.4; `stats --by level\|decider\|host` | [CLI](17-engine-cli.spec.md), [CST §2.5](34-central-run-stats.spec.md) |
| Orchestration report | Per orchestration: the skill's own supervision cost, the runs' cost and the share, against [OSK-AC-4](46-orchestrator-skill.spec.md)'s 3% | [ORC](45-orchestration.spec.md) |

### 2.6 Audit, evals and the improvement loop

| Place | Use |
|---|---|
| Eval suites ([EVS §2.3](51-eval-suites.spec.md)) | A workflow case's pauses are answered by its recorded `answers[]`, with caller `pipeline` and `caller_app: evals`; eval runs never enter the production aggregates of §2.4. A case may declare `max_level: <level>`; a trial that needed a higher level fails, so an eval asserts autonomy as well as quality, much as an assisted evaluation does ([R-085](../research/R-085-callers-supervision-and-babysitting-cost.rsrch.md) P4) |
| Improvement loop ([SIL §2.4](16-self-improvement.spec.md)) | Each agent's own rescue is a friction finding with cause `agent_decided:<pause cause>`, clustered by (workflow, unit, pause cause) across runs and machines; a cluster whose decisions were mostly `proceed` with no workspace change files a workflow issue whose remedy is a check or an environmental cause, so the pause stops happening. Supervision cost joins the cost lens as its own figure, never summed into run cost |
| Promotion | §2.7 |

### 2.7 Supervision criteria for promotion

`promote-check` ([ADR-0041](../adr/0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md)) reads §2.4 over its window for the workflow version. These rows replace ADR-0041's "person interventions per run" row ([ADR-0089](../adr/0089-supervision-is-a-promotion-and-improvement-measure.adr.md)); its other criteria stand. Defaults, with no data behind them.

| Criterion | To `local-stable` | To `pipeline` |
|---|---|---|
| Undesigned touches per run, every decider | ≤ 1.0 | ≤ 0.3 |
| Unattended rate, lower bound of the interval | ≥ 0.5 | ≥ 0.8 |
| Agent's own rescue share | reported | ≤ 0.05 |
| Supervision share, median | ≤ 0.10 | ≤ 0.03 |
| Runs with every caller known | ≥ 0.8 | ≥ 0.95 |
| Runs with supervision cost measured | reported | ≥ 0.8 |

A criterion whose data is missing on more runs than its row allows is reported `unmeasured`, which is not met. After promotion the same rows are re-read over the sliding window; a failing row shows the workflow `regressed` with the number, and nothing is demoted automatically (ADR-0041).

## 3. Behaviours

**SUP-B1 An agent-babysat run is not autonomous.** Given a run with two escalations, both answered by a Claude Code session with `proceed` and no relay, when the record is built, then `undesigned` is 2, `agent_own_rescues` is 2, the level is `consultant` with `level_by: agent`, and the run counts against the unattended rate.

**SUP-B2 Designed pauses keep a run unattended.** Given a run with one approval answered by a person and nothing else, when the record is built, then the level is `approver`, `undesigned` is 0 and the run counts toward the unattended rate.

| Run | Touches | Level | `level_by` |
|---|---|---|---|
| A | none | observer | none |
| B | approve (person) | approver | none |
| C | decide escalation (agent, relayed `turn_named`) | consultant | person |
| D | decide escalation (agent) + grant (person) | collaborator | mixed |
| E | rewind and decide on 3 of 4 units reached (person) | operator | person |

**SUP-B3 One resume, several touches.** Given a resume of a `tool_access` pause with `--decision retry --grant code=shell --set code.timeout_s=900 --relayed` backed by a named person turn, when the record is built, then it counts one `rescue` and two `steer` touches, each `decided_by: person`, `relay: turn_named`.

**SUP-B4 Waiting time per decider.** Given a pause at 10:00 relayed by an agent at 10:40 with `turn_named`, and a second pause at 11:00 answered by the agent alone at 11:01, when the record is built, then `person_wait_s` is 2400 and the agent wait is 60.

**SUP-B5 Thin and unmeasured figures.** Given a workflow version with 3 runs, when `report --supervision` runs, then every figure shows `n = 3` and `thin`; given 12 runs of which 4 have no supervision journal, then the supervision cost figures show `measured 8 of 12` and the `pipeline` criterion "runs with supervision cost measured" reads 0.67, not met.

**SUP-B6 Eval runs stay apart.** Given a workflow case that declares `max_level: approver` and whose trial needed a recorded answer at an escalation, when the suite runs, then the trial fails with `level consultant above approver`, and the run appears in no production aggregate.

**SUP-B7 Agent rescues feed the loop.** Given seven runs on two machines in which an agent answered the `code` gate's `check_environmental` escalation with `proceed` and no change, and each run then passed, when self-improvement reads them, then the seven `agent_decided:escalation` findings form one cluster and one workflow issue is filed naming the environmental cause as the remedy.

**SUP-B8 Promotion counts agents.** Given 20 runs whose person interventions are 0.1 per run but whose agent's own rescues are 0.9 per run, when `promote-check --to pipeline` runs, then "undesigned touches per run" reads 1.0, not met, and the check names the leading pause cause.

## 4. Error conditions

| Condition | Result |
|---|---|
| A record lacks a `caller` block (written by an older engine) | The touch is counted with caller `unknown`; the data-quality figure shows it |
| The ledger row cannot be written | One failure record; the run's exit code is unchanged (C2) |
| `report --supervision` over a window with no runs | An empty report, exit 0 |
| `max_level` names an unknown level | `validate` refuses the case, exit 2 |

## 5. Design notes

- **Count every decider** ([ADR-0089](../adr/0089-supervision-is-a-promotion-and-improvement-measure.adr.md)). The owner's lifecycle is "less human-in-the-loop, then the pipeline". In the pipeline no agent babysits a run, so a workflow that today needs an agent's rescues is not ready even if no person was touched.
- **Designed touches are the job.** An approval the workflow asks for is not supervision debt; counting it would push authors to remove approvals ([HUM-B5](07-gate-and-human.spec.md)). It is counted, shown, and kept out of the undesigned figures.
- **Levels describe a run, not a workflow.** A workflow's autonomy is the distribution of its runs' levels, which is what public measurement found: autonomy is a property of a deployment ([R-085](../research/R-085-callers-supervision-and-babysitting-cost.rsrch.md) P1).
- **No active time.** How long a person spent reading a pause cannot be measured from records; only waiting time and turn counts are. The design does not estimate it.

- Release 1 build ([T7 plan](../plans/t7-observability.plan.md) T7.5): the record is built by `run/supervision.py` (T5 and T6) and read by the stats row, the sink row, the detail document and `report --supervision` (`observe/supervision_report.py`). Deviations: a run is a thread and its figures are the thread's last record; `--by unit` counts touches from the ledger's intervention rows; waits per pause kind are not shown (`null`), since the record keeps waits per decider; supervision cost, share and observations are joined from SCO's closed ledger lines (T7.6), so a thread counts as not measured until its supervision closes; the share is null while the run has no estimated cost. `promote-check` is not built (AC-3's other half).

## 6. Acceptance criteria

- [ ] SUP-AC-1 Every row of the SUP-B2 table is reproduced from a fixture run log by the record builder.
- [ ] SUP-AC-2 The ledger row, the stats row and the sink row of a run carry the same touch figures (one builder, as [CST §2.2](34-central-run-stats.spec.md) requires of cost).
- [ ] SUP-AC-3 `report --supervision` and `promote-check` read the same function for §2.4, and both leave the state root unchanged (hash test).
- [ ] SUP-AC-4 Eval-origin runs are absent from every §2.4 figure (fixture test).
- [ ] SUP-AC-5 No supervision figure counts an unmeasured cost as zero.

## Open questions

| Question | Owner |
|---|---|
| Are the §2.7 thresholds and the audit thresholds of §2.6 right? Defaults, revisited after the first 20 runs of one workflow version. | Owner |
| Should an `approver` run whose approvals an agent gave count as unattended? Assumed yes for the rate, flagged by `designed_by: agent`. | Owner |

## References

[PRV](85-caller-provenance.spec.md) · [SCO](87-supervision-cost.spec.md) · [HUM](07-gate-and-human.spec.md) · [SIL](16-self-improvement.spec.md) · [CST](34-central-run-stats.spec.md) · [ARC](56-audit-rule-catalog.spec.md) · [EVS](51-eval-suites.spec.md) · [ADR-0041](../adr/0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md) · [R-085](../research/R-085-callers-supervision-and-babysitting-cost.rsrch.md)
