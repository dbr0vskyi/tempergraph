# Supervision metrics

## Purpose

How much a run needed someone, and who that was. A workflow you can trust is one that reaches a good result with few touches by anyone, not only with few touches by a person: a run babysat by an agent looks autonomous if only people are counted ([R-085](../research/R-085-callers-supervision-and-babysitting-cost.rsrch.md) D6, B3). This spec defines a touch, the per-run supervision record, a run's supervision level, the per-workflow aggregates, where each figure is written and read, and the supervision criteria for promoting a workflow ([ADR-0041](../adr/0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md), [ADR-0089](../adr/0089-supervision-is-a-promotion-and-improvement-measure.adr.md)). Every figure is built from records written when the act happened: the `caller` blocks of [PRV](caller-provenance.spec.md) and, for the spend of supervising sessions, the supervision journal of [SCO](supervision-cost.spec.md); nothing is classified after the fact by a model. Building and writing them is best effort and never changes a run (OVR-B4); every reader is model-free (C13). Reports, the monitor, audit, eval suites, the improvement loop and the promotion check ([PRO](promotion-check.spec.md)) depend on it; design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### SUP-B1 An agent-babysat run is not autonomous

WHEN a run's escalations are answered by an agent with no relay THE record builder SHALL count them as undesigned agent rescues, give the run level `consultant` with `level_by: agent`, and count the run against the unattended rate.

- GIVEN a run with two escalations both answered by a Claude Code session with `proceed` and no relay WHEN the record is built THEN `undesigned` is 2, `agent_own_rescues` is 2 and the level is `consultant` by `agent`

### SUP-B2 Designed pauses keep a run unattended

WHEN a run's only touches are designed ones THE record builder SHALL give it level `approver` with `undesigned` 0 and count it toward the unattended rate.

- GIVEN no touch WHEN the record is built THEN the level is `observer`, `level_by` `none`
- GIVEN one approval by a person WHEN the record is built THEN the level is `approver`, `level_by` `none`
- GIVEN an escalation decided by an agent relayed `turn_named` WHEN the record is built THEN the level is `consultant`, `level_by` `person`
- GIVEN an escalation decided by an agent and a grant by a person WHEN the record is built THEN the level is `collaborator`, `level_by` `mixed`
- GIVEN a person's rewind and decide on 3 of 4 units reached WHEN the record is built THEN the level is `operator`, `level_by` `person`

### SUP-B3 One resume, several touches

WHEN one resume carries a decision, grants and overrides THE record builder SHALL count each as its own touch with the resume's decider and relay.

- GIVEN a resume of a `tool_access` pause with `--decision retry --grant code=shell --set code.timeout_s=900 --relayed` backed by a named person turn WHEN the record is built THEN it counts one `rescue` and two `steer` touches, each `decided_by: person`, `relay: turn_named`

### SUP-B4 Waiting time per decider

WHEN pauses are answered THE record builder SHALL sum the wait from each pause to its answer per decider.

- GIVEN a pause at 10:00 relayed by an agent at 10:40 with `turn_named` and a pause at 11:00 answered by the agent alone at 11:01 WHEN the record is built THEN `person_wait_s` is 2400 and the agent wait is 60

### SUP-B5 Thin and unmeasured figures

WHEN an aggregate rests on fewer than 5 runs or on runs with missing data THE engine SHALL show it with its count and `thin`, show measured counts beside cost figures, never count an unmeasured cost as zero, and report a promotion criterion with missing data on more runs than its row allows as not met.

- GIVEN a workflow version with 3 runs WHEN `report --supervision` runs THEN every figure shows `n = 3` and `thin`
- GIVEN 12 runs of which 4 have no supervision journal WHEN `report --supervision` runs THEN cost figures show `measured 8 of 12` and the `pipeline` criterion on measured cost reads 0.67, not met

### SUP-B6 Eval runs stay apart

WHEN an eval trial needs a higher level than its case's `max_level` THE engine SHALL fail the trial naming both levels, and keep every eval run out of the production aggregates.

- GIVEN a case declaring `max_level: approver` whose trial needed a recorded answer at an escalation WHEN the suite runs THEN the trial fails with `level consultant above approver` and appears in no production aggregate

### SUP-B7 Agent rescues feed the loop

WHEN self-improvement reads runs in which agents answered the same gate's pause with `proceed` and no change THE engine SHALL cluster the `agent_decided:<pause cause>` findings by workflow, unit and pause cause across runs and machines, and file one workflow issue naming a check or the environmental cause as the remedy.

- GIVEN seven runs on two machines in which an agent answered the `code` gate's `check_environmental` escalation with `proceed` and each run then passed WHEN self-improvement reads them THEN one cluster and one workflow issue result

### SUP-B8 Promotion counts agents

WHEN `promote-check` reads undesigned touches THE engine SHALL count every decider, not only people, and name the leading pause cause of a failing row.

- GIVEN 20 runs with 0.1 person interventions and 0.9 agent's own rescues per run WHEN `promote-check --to pipeline` runs THEN "undesigned touches per run" reads 1.0, not met, naming the leading pause cause

### SUP-B9 Touches

WHEN an accepted call changes a thread's course or answers it, made by anyone but the thread's own graph THE engine SHALL count it as a touch with a class, an action and the call's `caller` block, the classes being `designed` (`approve` at an approval pause or node, `answer` to an ask's `input` pause, `event` for a wait's event value), `rescue` (`decide` at an `escalation` or `budget` pause of any cause, `tool_access` and council no-decision included, and `apply_deadline` with `escalate`), `steer` (`rewind`, `rerun` on the source thread, `stop`, `grant`, `override` of settings on a resume, `ruling`, `breakpoint` for the resume of a `--pause-before`, `edit` of an orchestration naming the node) and `engine` (infra re-open, the orchestrator's `reopen_infra`, the self-improvement child, counted apart and never as supervision); count a run's start as `starts`, a scheduled start as a `starts` entry of caller `scheduler`, the person's `schedule add` and `edit` once per schedule as setup ([TCK-B24](schedule-ticks-and-unattended-fires.spec.md)); and count a record with no `caller` block (an older engine) with caller `unknown`, shown in data quality.

- GIVEN a ledger row written by an older engine with no caller WHEN touches are counted THEN the touch is `unknown` and the data-quality figure shows it

### SUP-B10 Supervision record of a run

WHEN a run exits THE engine SHALL build the thread's record so far and write it as the `supervision{}` object of the ledger row ([SIL](self-improvement.spec.md)) and a `supervision` run-log record ([EVT](run-events.spec.md)), with `touches` (by class and `decided_by` of `person`, `agent`, `unknown`, `pipeline`, `orchestrator`, `scheduler`, and by pause kind for `rescue`); `undesigned` (`rescue` plus `steer`, every decider); `relayed` (by `relay`); `agent_own_rescues`; `wait_s` per decider from each `pause` record or due approval node to its touch, `person_wait_s` the person sum ([CST](central-run-stats.spec.md)); `latency_s` median and maximum; `observations` from the journal, null without one ([SCO](supervision-cost.spec.md)); `supervisors` (distinct host sessions and their hosts); `callers_unknown`; `supervision_cost` `{marginal, turn, completeness}` filled when SCO closes it, null until then; `supervision_share` (marginal estimated supervision cost over the run's estimated cost plus that, null when either is unmeasured); and `level` and `level_by`; a rerun thread having its own record, its rerun a `steer` on the source thread, reports rolling a lineage to its root on request ([RRN](reruns-and-feedback.spec.md)); an unwritable ledger row giving one failure record with the run's exit code unchanged (C2).

- GIVEN an unwritable ledger WHEN a run exits THEN one failure record is written and the exit code is unchanged

### SUP-B11 Supervision level

WHEN a run's level is read from its own touches ([R-085](../research/R-085-callers-supervision-and-babysitting-cost.rsrch.md) P4) THE engine SHALL take the first matching of `operator` (undesigned touches on half or more of the units reached, or a breakpoint before every unit), `collaborator` (at least one `steer`), `consultant` (at least one `rescue`, no `steer`), `approver` (`designed` touches only) and `observer` (no touch after the start); set `level_by` to `person` or `agent` when every undesigned touch had that decider, `mixed` otherwise, and `none` for `observer` and `approver`; and show `designed_by: agent` beside an `approver` run whose designed touches were all an agent's.

- GIVEN an approval answered by an agent WHEN the level is read THEN it is `approver` with `designed_by: agent`

### SUP-B12 Workflow aggregates

WHEN aggregates are read for a workflow and version over a window (default 30 days) from the ledger and the stats rows, local or from the fleet copy ([CST](central-run-stats.spec.md)) THE engine SHALL give runs by level and `level_by`; the unattended rate (share at `observer` or `approver`) with a 95% Wilson interval; undesigned touches per run by class and decider; the agent's own rescue share; relay quality by `relay` value; p50 and p90 of `person_wait_s` per run and per pause kind; p50 and p90 of marginal estimated supervision cost with the turn figure beside it ([ADR-0088](../adr/0088-attribute-supervision-spend-by-marginal-tokens-beside-turn-totals.adr.md)); median and p90 of `supervision_share`; median observations per run and the share of supervision cost spent on `rewake`; and data quality (share of runs with every caller known, share with supervision cost measured); read-only, `report --supervision` and `promote-check` reading the same function, an empty window giving an empty report with exit 0.

- GIVEN a window with no runs WHEN `report --supervision` runs THEN it prints an empty report and exits 0

### SUP-B13 Where the figures land

WHEN supervision figures are written and shown THE engine SHALL put `caller` blocks on every intervention and the `supervision` record at each `run_exit` in the run log ([PRV-B17](caller-provenance.spec.md)); `supervision{}` in the ledger row, cost filled on close ([IMD](improvement-data.spec.md)); `touches_undesigned`, `touches_by_decider`, `agent_own_rescues`, `level`, `level_by` and `callers_unknown` in the `run` stats and sink row, the cost in the `supervision` row when it closes, and who a waiting run waits on in the heartbeat ([CST](central-run-stats.spec.md)); a `supervision` block in the detail document with touches in time order (class, action, caller kind, decider, relay, wait), the open supervising sessions and cost so far ([RDD](run-detail-document.spec.md)); the level, touch list, run and supervision cost apart and the share in the monitor (monitor [MRV](../../../tempergraph-monitor/docs/specs/run-view.spec.md), [MCF](../../../tempergraph-monitor/docs/specs/cost-and-fleet.spec.md)); `report --supervision [window] [--by workflow|version|unit|host|level]` and `stats --by level|decider|host` ([CLI](engine-cli.spec.md)); and per orchestration the skill's own supervision cost, the runs' cost and the share against [OSK](orchestrator-skill.spec.md)'s 3% ([ORC](orchestration.spec.md)).

- GIVEN a run WHEN its ledger, stats and sink rows are compared THEN they carry the same touch figures from one builder

### SUP-B14 Audit rules on supervision

WHEN audit history rules run ([ARC](audit-rule-catalog.spec.md)) THE engine SHALL count undesigned touches by every decider in `interventions-per-run`; fire `agent-rescues-alone` when agents made 30% or more of a gate's rescue decisions (`min_n` 5 rescues); fire `supervision-cost-share` when the median share exceeds 10% (`min_n` 5 measured runs); fire `polling-supervisor` when observations per run exceed 20 or `rewake` exceeds half the supervision cost; and fire `callers-unknown` (info) when more than 20% of touches have an unknown caller.

- GIVEN six rescues of one gate, two by agents WHEN audit runs THEN `agent-rescues-alone` fires

### SUP-B15 Eval cases and levels

WHEN an eval suite runs a workflow case ([EVS](eval-suites.spec.md)) THE engine SHALL answer its pauses from the case's recorded `answers[]` with caller `pipeline` and `caller_app: evals`, keep eval runs out of every production aggregate, honour a case's optional `max_level` (SUP-B6) so an eval asserts autonomy as well as quality, and refuse a case whose `max_level` names an unknown level in `validate` with exit 2.

- GIVEN a case with `max_level: pilot` WHEN `validate` runs THEN it exits 2

### SUP-B16 Supervision in the improvement loop

WHEN the improvement loop reads supervision ([SIL](self-improvement.spec.md)) THE engine SHALL make each agent's own rescue a friction finding with cause `agent_decided:<pause cause>` clustered as SUP-B7, and join supervision cost to the cost lens as its own figure, never summed into run cost.

- GIVEN a run with $0.40 run cost and $0.10 supervision cost WHEN the cost lens reads it THEN it shows the two figures apart

### SUP-B17 Supervision criteria for promotion

WHEN `promote-check` ([PRO](promotion-check.spec.md), [ADR-0041](../adr/0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md)) reads the aggregates over its window for a workflow version THE engine SHALL use these rows in place of ADR-0041's "person interventions per run" ([ADR-0089](../adr/0089-supervision-is-a-promotion-and-improvement-measure.adr.md)), its other criteria standing: undesigned touches per run, every decider, at most 1.0 to `local-stable` and 0.3 to `pipeline`; the unattended rate's lower bound at least 0.5 and 0.8; the agent's own rescue share reported and at most 0.05; median supervision share at most 0.10 and 0.03; runs with every caller known at least 0.8 and 0.95; runs with supervision cost measured reported and at least 0.8; a criterion with too much missing data `unmeasured`, which is not met; and after promotion the same rows re-read over the sliding window, a failing row showing the workflow `regressed` with the number, nothing demoted automatically.

- GIVEN a promoted workflow whose unattended rate falls below its bound WHEN the window is re-read THEN it shows `regressed` with the number and stays promoted

## Acceptance criteria

- SUP-AC1 (SUP-B1, SUP-B2, SUP-B3, SUP-B4, SUP-B9, SUP-B10, SUP-B11): Every level case of SUP-B2 is reproduced from a fixture run log by the record builder
- SUP-AC2 (SUP-B13): The ledger row, the stats row and the sink row of a run carry the same touch figures (one builder, as [CST](central-run-stats.spec.md) requires of cost)
- SUP-AC3 (SUP-B8, SUP-B12, SUP-B17): `report --supervision` and `promote-check` read the same aggregate function, and both leave the state root unchanged (hash test)
- SUP-AC4 (SUP-B6, SUP-B15): Eval-origin runs are absent from every aggregate (fixture test)
- SUP-AC5 (SUP-B5, SUP-B7, SUP-B14, SUP-B16): No supervision figure counts an unmeasured cost as zero, and each audit rule and the `agent_decided` cluster have a fixture

## Open questions

- Are the promotion thresholds and the audit thresholds right? Until answered: the stated defaults, revisited after the first 20 runs of one workflow version. Owner: owner.
- Should an `approver` run whose approvals an agent gave count as unattended? Until answered: yes for the rate, flagged by `designed_by: agent`. Owner: owner.
- Not built yet: an eval case's `max_level` (SUP-B6, SUP-B15). Owner: engine owner.
