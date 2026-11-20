---
title: Feedback labels and judge reliability
type: component
status: review
prefix: FBK
adrs: [0031, 0033, 0005, 0021]
---

# Feedback labels and judge reliability

## 1. Overview

Every signal of the self-improvement loop rests on judges, and a judge is only as good as its agreement with what people and later facts say ([R-030 F2](../research/R-030-self-improving-agent-systems.rsrch.md)). This spec turns the ground truth that already arrives after a run (an approval answer, a pull request merged or closed, a re-run, a person sending passed work back, an audit judge that disagreed) into one **label** record joined to the run, gate and criterion it speaks about. From labels it grades each judge binding `reliable`, `unmeasured` or `unreliable`, which licenses or blocks judge grades in filing ([SIL](16-self-improvement.spec.md)), the quality lens and trials ([PRP](40-improvement-proposals.spec.md)). It also watches for a quality shift when an executor, model or brief changes.

## 2. Contract

### 2.1 Label

| Field | Kind | Meaning |
|---|---|---|
| `label_id` | id | |
| `thread`, `run_id`, `unit`, `attempt` | | What the label is about |
| `gate_record` | id, optional | The gate judgement it confirms or contradicts |
| `criterion_id` | id, optional | When the label names one criterion |
| `kind` | §2.2 | |
| `value` | `agree` \| `disagree` \| `neutral` | Relative to the judgement: `disagree` means the judge's PROCEED or MET was wrong, or its block was wrong |
| `source` | `person` \| `agent` \| `fact` | From the answer's decider ([PRV §2.4](85-caller-provenance.spec.md)): `person` only when `decided_by` is `person`; `agent` for an agent's own answer, `unknown` callers and relays without host evidence ([HUM](07-gate-and-human.spec.md)) |
| `origin` | `run` (default), `authoring_trial`, `sign_off` | Where the label was given: a production run, the first trial of an authored workflow ([SCF §2.5](91-blueprint-and-scaffold.spec.md)), or a person's per-criterion sign-off ([OUT §2.2](90-run-outcome.spec.md)) |
| `at`, `observed_after_s` | | When, and how long after the gate |
| `binding` | `{executor, executor_version, alias, model_slug, brief_digest, criteria_digest}` | The judge binding that produced the judgement |

Metadata only: no request, output or feedback text ([SEC](14-security.spec.md)). A person's typed reason stays in the local evidence file and is referenced by id.

### 2.2 Label kinds and how each is derived

| Kind | Derived from | `value` |
|---|---|---|
| `approval` | Answer at a final approval pause: accepted / declined / reworked | accepted → `agree` with the last gate; declined or reworked → `disagree` |
| `pr_state` | Pull request merged or closed, read on request or by the shared store | merged → `agree`; closed unmerged → `disagree`; open after 30 days → `neutral` |
| `rerun` | A new run of the same task key within 14 days | `disagree` with the earlier run's last PROCEED |
| `pushback` | A person's retry or back at the next pause after a PROCEED (a gate escape, [OBS](15-observability-and-cost.spec.md)) | `disagree` with that PROCEED, per criterion where the person named one |
| `audit` | An `audit_judge` record (JDG-B7) | per criterion: same status → `agree`, MET against UNMET → `disagree` |
| `explicit` | `label <thread> <gate> [--criterion id] --value agree\|disagree` by a person, or the monitor's equivalent | as given |
| `override` | A person's proceed on an ESCALATE whose check ran and passed | `disagree` with the escalation |

`audit` labels measure judge consistency, not correctness; they are counted apart and never alone make a judge `reliable`.

### 2.3 Reliability per judge binding

Computed per gate and binding over a 90-day window, from labels with `source` `person` or `fact` only.

| Figure | Definition |
|---|---|
| `n` | Labels with value `agree` or `disagree` |
| `false_pass_rate` | `disagree` labels on PROCEED judgements ÷ labels on PROCEED judgements |
| `false_block_rate` | `disagree` labels on RETRY, BACK or ESCALATE ÷ labels on those |
| `audit_agreement` | Share of criteria with the same status in `audit` labels |
| `confidence_bands` | `false_pass_rate` per confidence anchor of [CON §2.8](01-contracts.spec.md), judge-sourced values only |

| Grade | Rule |
|---|---|
| `unmeasured` | `n` < 20; or no label in the last 30 days; or fewer than 5 labelled judgements where the work was known bad (a `disagree` label on a PROCEED, or an `agree` label on a block); or no current live score of the binding on calibration cases that include known-bad cases ([LIF](18-lifecycle-and-evals.spec.md) live judge scoring) |
| `unreliable` | `false_pass_rate` > 0.15, or `audit_agreement` < 0.8 with at least 30 audited criteria |
| `reliable` | otherwise: enough labels, known-bad evidence, a passing live score, and neither `unreliable` rule |

A `false_pass_rate` of 0 with no known-bad evidence says only that people accepted everything; judges are known to be agreeable, so it never grades `reliable` on its own ([R-030 F5](../research/R-030-self-improving-agent-systems.rsrch.md)).

A binding change (any field of `binding`) starts a new binding with no labels; the previous binding's grade is shown beside it, never inherited.

### 2.4 Labelling queue

`labels queue [workflow]` lists gate judgements a person should label, in this order: gate escapes without a label, audit disagreements, judge-sourced confidence at or below 0.5, PROCEEDs of a binding that is `unmeasured`, then a 5% random sample of PROCEEDs. Each row carries the exact `label` command. The queue is a read-only verb; the monitor plugin may render it.

### 2.5 Binding-shift watch

| Trigger | Comparison | Finding |
|---|---|---|
| A gate's binding changes (executor version, model slug, brief or criteria digest) | The first 10 judgements of the new binding against the last 30 of the old: pass rate, UNVERIFIABLE rate, mean turns | A difference above 20 points in pass rate, or 15 points in UNVERIFIABLE rate, is finding `binding_shift`, attributed to `executor:<name>` when only executor or model fields changed, otherwise to `workflow` |

The finding is recorded and enters the friction lens like any finding; it is never a route or a pause.

## 3. Behaviours

**FBK-B1 Labels without a model.** Given a run whose final approval was answered "reworked", when the run is recorded, then one `approval` label `disagree` is written against the last gate, with no model call and no text.

**FBK-B2 Agent answers do not grade judges.** Given a pause answered by an agent on its own (declared, or seen by its host marker), when labels are derived, then the label has `source=agent` and is excluded from every §2.3 figure.

**FBK-B3 Reliability grades.** Given four bindings, when the report runs, then each gets one grade.

| n | false_pass_rate | audit_agreement (criteria) | Grade |
|---|---|---|---|
| 12 | 0.0 | — | `unmeasured` |
| 40 | 0.10 | 0.85 (60) | `reliable` (7 known-bad labels, live score passing) |
| 40 | 0.0 | 0.95 (60) | `unmeasured` (every result accepted: no known-bad evidence) |
| 40 | 0.20 | 0.90 (60) | `unreliable` |
| 40 | 0.05 | 0.70 (45) | `unreliable` |

**FBK-B4 A new model starts unmeasured.** Given a reliable judge whose alias is rebound to another model slug, when the next judgement is recorded, then its binding is new and graded `unmeasured`; trials that target that gate's grades are refused until it is measured, and the old grade is shown as history.

**FBK-B5 Quality lens unlocks per gate.** Given a gate whose current binding is `reliable`, when the quality lens of [SIL](16-self-improvement.spec.md) runs, then that gate's scorecard rows may trigger filing; rows of other gates are reported only.

**FBK-B6 Harvest from labels.** Given a `disagree` label from a person on a PROCEED, when `evals harvest` lists candidates ([LIF](18-lifecycle-and-evals.spec.md)), then the attempt appears as a calibration-case candidate with the person's value as the suggested expectation.

**FBK-B7 Binding shift is visible.** Given a gate on `antigravity` whose pass rate was 70% over its last 30 judgements and 40% over the first 10 after a CLI update with no workflow change, when the watch runs, then finding `binding_shift` is recorded against `executor:antigravity` with both versions.

## 4. Error conditions

| Condition | Result |
|---|---|
| A label names a gate record that does not exist | Label kept with `gate_record` null and counted under `orphan_labels`; never in a figure |
| The code host cannot be read for `pr_state` | No label; retried at the next read |
| Two labels of the same kind for one judgement | The later one wins; both kept |

## 5. Design notes

- Labels are cheap facts the engine already sees; the only new human effort is the optional queue, ordered so the most informative judgements come first ([R-030 F6](../research/R-030-self-improving-agent-systems.rsrch.md)).
- The thresholds (20 labels, 0.15, 0.8, 90 days, the shift margins) have no data behind them and are recorded as parameters with that provenance ([IMD](43-improvement-data.spec.md)).
- Confidence is studied here, against labels, rather than used as a filing floor; the open question on the 0.75 floor in SIL is answered from `confidence_bands` once labels exist.
- Release 1 build ([T7 plan](../plans/t7-observability.plan.md) T7.5): only the `explicit` kind, through `label <thread> <unit> --value agree|disagree [--criterion id] [--attempt n]`. The row goes to the state root's `ledger.jsonl` as `kind: label` (the label's own kind is the field `label_kind`, since `kind` names the ledger row's kind) with `gate_record` (the gate record's `seq`), `gate_verdict`, the IMD-R1 fields and the caller block; `source` is `person` only when the caller's decider is a person. `brief_digest` and `criteria_digest` of the binding are null until `agent_run` carries them (IMD-R2). The derived kinds, `labels queue`, grading and the `label_recorded` event are T12.3.

## 6. Acceptance criteria

- [ ] FBK-AC-1 Every row of the §2.2 table is derived from a fixture run log with no model call.
- [ ] FBK-AC-2 Every row of the FBK-B3 table is reproduced by the grading function.
- [ ] FBK-AC-3 No label record contains request, output or feedback text (canary test).
- [ ] FBK-AC-4 Agent-sourced labels change no reliability figure.
- [ ] FBK-AC-5 A binding change resets the grade to `unmeasured` in a fixture.

## Open questions

| Question | Owner |
|---|---|
| Should the grade also read the offline gold-set calibration state per binding being designed in the eval and judge work (spec 50), so that `reliable` needs that state to be `accepted`? Assumed yes once that spec lands; until then the live score above stands in. | Owner, with the eval and judge design |

## References

[JDG](05-judge-and-verdict.spec.md) · [HUM](07-gate-and-human.spec.md) · [OBS](15-observability-and-cost.spec.md) · [SIL](16-self-improvement.spec.md) · [LIF](18-lifecycle-and-evals.spec.md) · [PRP](40-improvement-proposals.spec.md) · [IMD](43-improvement-data.spec.md)
