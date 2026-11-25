# Feedback labels and judge reliability

## Purpose

Every signal of the self-improvement loop rests on judges, and a judge is only as good as its agreement with what people and later facts say ([research `self-improving-agent-systems`](../research/self-improving-agent-systems.rsrch.md) F2). This spec turns the ground truth that already arrives after a run (an approval answer, a pull request merged or closed, a re-run, a person sending passed work back, an audit judge that disagreed) into one label record joined to the run, gate and criterion it speaks about. From labels it grades each judge binding `reliable`, `unmeasured` or `unreliable`, which licenses or blocks judge grades in filing ([SIL](self-improvement.spec.md)), the quality lens and trials ([PRP](improvement-proposals.spec.md)), and it watches for a quality shift when an executor, model or brief changes. A grade is per binding because a judge moved to another model is a different judge. Labels are facts the engine already sees; the only new human effort is the optional queue, ordered so the most informative judgements come first (research `self-improving-agent-systems` F6). Thresholds have no data behind them and are recorded as parameters with that provenance ([IMD](improvement-data.spec.md)). The loop, trials, harvest and the monitor depend on these labels and grades.

## Behaviours

### FBK-B8 Label record

WHEN a label is written THE engine SHALL append a `kind: label` row to the state root's `ledger.jsonl` with a deterministic `label_id`, `thread`, `run_id`, `unit`, `attempt`, optional `gate_record` (the gate record's `seq`) and `gate_verdict`, optional `criterion_id`, `label_kind`, `value` (`agree`, `disagree` or `neutral`, relative to the judgement), `source` (`person` only when the answer's `decided_by` is a person, [PRV](caller-provenance.spec.md); `agent` for an agent's own answer and for unknown callers and relays without host evidence, [HUM](gate-and-human.spec.md); `fact` for a derived fact), `origin` (`run` by default, `authoring_trial` for the first trial of an authored workflow, [SCF](blueprint-and-scaffold.spec.md), or `sign_off` for a per-criterion sign-off, [OUT](run-outcome.spec.md)), `at`, `observed_after_s`, `binding` (`executor`, `executor_version`, `alias`, `model_slug`, and `brief_digest` and `criteria_digest` from the gate's `judgement` record), the judgement's `confidence` and `confidence_source`, the improvement-data identifiers and the caller block, metadata only, a person's typed reason staying in the local evidence file referenced by id ([SEC](security.spec.md)).

- GIVEN a label with a typed reason WHEN the ledger row is read THEN it holds the reason's id and not its text

### FBK-B9 Label kinds

WHEN a run exits THE engine SHALL derive, from the run log and the ledger, `approval` (an answer at a final approval pause: accepted `agree` with the last gate, declined or reworked `disagree`), `rerun` (a new run of the same task key within 14 days, `disagree` with the earlier run's last PROCEED), `pushback` (a person's retry or back at the next pause after a PROCEED, a gate escape, `disagree` with it per named criterion), `audit` (an `audit_judge` record: per criterion the same status `agree`, MET against UNMET `disagree`, counted apart and never alone making a judge `reliable`) and `override` (a person's proceed on an ESCALATE whose check ran and passed, `disagree`), a second derivation of one judgement writing nothing; and `explicit` from `label <thread> <unit> --value agree|disagree [--criterion id] [--attempt n]`.

- GIVEN a run derived twice WHEN labels are counted THEN each judgement has one label per kind

### FBK-B1 Labels without a model

WHEN a run whose final approval was answered "reworked" is recorded THE engine SHALL write one `approval` label `disagree` against the last gate, with no model call and no text.

- GIVEN an approval answered "reworked" WHEN recorded THEN one `disagree` label exists and no model was called

### FBK-B10 Label errors

WHEN a label names a gate record that does not exist, or two labels of one kind speak about one judgement THE engine SHALL keep the label with `gate_record` null counted under `orphan_labels` and in no figure, or let the later one win while keeping both.

- GIVEN a label naming a missing gate record WHEN figures are computed THEN it is in `orphan_labels` only

### FBK-B11 Reliability figures

WHEN reliability is computed per gate and binding over a 90-day window from labels with `source` `person` or `fact` only THE engine SHALL compute `n` (labels valued `agree` or `disagree`), `false_pass_rate` (`disagree` on PROCEED judgements over labels on PROCEED), `false_block_rate` (`disagree` on RETRY, BACK or ESCALATE over labels on those), `audit_agreement` (share of criteria with the same status in `audit` labels) and `confidence_bands` (`false_pass_rate` per confidence anchor of [SSN](session-contract.spec.md), judge-sourced values only).

- GIVEN 30 labels on PROCEED of which 3 disagree WHEN computed THEN `false_pass_rate` is 0.10

### FBK-B2 Agent answers do not grade judges

WHEN labels are derived from a pause answered by an agent on its own (declared, or seen by its host marker) THE engine SHALL give the label `source=agent` and exclude it from every reliability figure.

- GIVEN an agent's own answer WHEN figures are computed THEN they are unchanged

### FBK-B12 Grade rule

WHEN a binding is graded THE engine SHALL apply in order: `n` below 20 gives `unmeasured`; `false_pass_rate` above 0.15, or `audit_agreement` below 0.8 with at least 30 audited criteria, gives `unreliable`; no label in the last 30 days, fewer than 5 labelled judgements where the work was known bad (a `disagree` on a PROCEED or an `agree` on a block), or no live score `accepted` or `provisional` on a case set with known-bad cases ([JCL](judge-calibration.spec.md)) gives `unmeasured`; otherwise `reliable`; so a `false_pass_rate` of 0 with no known-bad evidence never grades `reliable` on its own (research `self-improving-agent-systems` F5).

- GIVEN `n` 40, false pass rate 0.0 and no known-bad label WHEN graded THEN it is `unmeasured`

### FBK-B3 Reliability grades

WHEN the report runs over fixture bindings THE engine SHALL give each one grade by FBK-B12.

- GIVEN `n` 12 and false pass rate 0.0 WHEN graded THEN it is `unmeasured`
- GIVEN `n` 40, false pass rate 0.10, audit agreement 0.85 over 60 criteria, 7 known-bad labels and a passing live score WHEN graded THEN it is `reliable`
- GIVEN `n` 40, false pass rate 0.20, audit agreement 0.90 over 60 WHEN graded THEN it is `unreliable`
- GIVEN `n` 40, false pass rate 0.05, audit agreement 0.70 over 45 WHEN graded THEN it is `unreliable`

### FBK-B4 A new model starts unmeasured

WHEN any field of a judge's binding changes, such as its alias rebound to another model slug THE engine SHALL start a new binding with no labels graded `unmeasured`, refuse trials that target that gate's grades until it is measured, and show the old grade beside it as history, never inherited.

- GIVEN a reliable judge rebound to another model WHEN its next judgement is recorded THEN the binding is `unmeasured` and the old grade is shown as history

### FBK-B5 Quality lens unlocks per gate

WHEN the quality lens of [SIL](self-improvement.spec.md) runs THE engine SHALL let only gates whose current binding is `reliable` trigger filing from their scorecard rows, reporting the rows of other gates only.

- GIVEN a gate whose binding is `unmeasured` WHEN the lens runs THEN its rows are reported and file nothing

### FBK-B13 Grades and queue verbs

WHEN `labels grades <workflow>` or `labels queue <workflow>` runs THE engine SHALL print, read-only, the figures and grade per gate and binding, or the gate judgements a person should label in this order (gate escapes without a label, audit disagreements, judge-sourced confidence at or below 0.5, PROCEEDs of an `unmeasured` binding, then a 5 % random sample of PROCEEDs seeded per day), each row carrying the exact `label` command; the monitor may render the queue.

- GIVEN a gate escape and an audit disagreement WHEN the queue is listed THEN the escape comes first with its `label` command

### FBK-B6 Harvest from labels

WHEN `evals harvest` lists candidates ([LIF-B14](lifecycle-and-evals.spec.md)) after a person's `disagree` label on a PROCEED THE engine SHALL list the attempt as a calibration-case candidate with the person's value as the suggested expectation.

- GIVEN a person's `disagree` on a PROCEED WHEN harvest runs THEN the attempt is a candidate expecting `UNMET`

### FBK-B14 Binding-shift watch

WHEN a gate's binding changes (executor version, model slug, brief or criteria digest) THE engine SHALL compare the first 10 judgements of the new binding with the last 30 of the old on pass rate, UNVERIFIABLE rate and mean turns, and record a `binding_shift` finding in the run's `findings.json` when pass rate differs by more than 20 points or UNVERIFIABLE rate by more than 15, attributed to `executor:<name>` when only executor or model fields changed and to `workflow` otherwise, entering the friction lens like any finding and never a route or a pause; labels and shifts an exit adds ride on its `finding_recorded` event ([EVT-B14](run-events.spec.md)).

- GIVEN only the brief digest changed and a 25-point drop WHEN watched THEN `binding_shift` is attributed to `workflow`

### FBK-B7 Binding shift is visible

WHEN the watch runs for a gate on `antigravity` whose pass rate was 70 % over its last 30 judgements and 40 % over the first 10 after a CLI update with no workflow change THE engine SHALL record `binding_shift` against `executor:antigravity` with both versions.

- GIVEN a 30-point drop after a CLI update WHEN watched THEN `binding_shift` names `executor:antigravity` and both versions

### FBK-B15 Review text stays in local evidence

WHEN the loop reads the text of a person's reviews or review comments from a pull request THE loop SHALL keep that text in the run's local evidence, as it keeps a person's feedback ([SEC-B9](security.spec.md)), and carry into every `later[]` entry, finding, label, ledger row, issue and comment only counts and kinds.

- GIVEN a review comment holding a canary WHEN the loop reads the pull request THEN the canary is in the run's local evidence and in no `later[]` entry
- GIVEN that run is an escape WHEN the loop files its finding THEN the canary is in no issue body, issue comment, ledger row, finding or label row
- GIVEN a review with no comment text WHEN it is read THEN its entry holds its counts and the local evidence holds no text for it

## Acceptance criteria

- FBK-AC1 (FBK-B9, FBK-B1): Every derived label kind is produced from a fixture run log with no model call
- FBK-AC2 (FBK-B3, FBK-B11, FBK-B12): Every scenario of FBK-B3 is reproduced by the grading function
- FBK-AC3 (FBK-B8): No label record contains request, output or feedback text, by a canary test
- FBK-AC4 (FBK-B2): Agent-sourced labels change no reliability figure
- FBK-AC5 (FBK-B4): A binding change resets the grade to `unmeasured` in a fixture
- FBK-AC6 (FBK-B5, FBK-B6, FBK-B10, FBK-B13, FBK-B14, FBK-B7): Fixtures cover the per-gate quality lens, harvest from labels, orphan and repeated labels, the queue order and the binding-shift watch
- FBK-AC7 (FBK-B15): Against a fake code host, a canary planted in the text of a review and of a review comment of a fixture run's pull request is in the run's local evidence and in no `later[]` entry, finding, label row, ledger row, issue body or issue comment after the loop has read the pull request and filed the run's escape

## Open questions

- Should the grade also read the offline gold-set calibration state per binding, so that `reliable` needs that state `accepted`? Until answered: JCL's `accepted` or `provisional` on known-bad cases stands in. Owner: owner, with the eval and judge design.
- Should `pr_state` labels (merged `agree`, closed unmerged `disagree`, open after 30 days `neutral`) be read by the shared store's collector for every machine, or only on request? Until answered: not derived as labels; the loop reads a run's recorded pull request on the machine that holds the person's sign-in and keeps its state in `later[]` ([OUT-B24](run-outcome.spec.md)), and the shared store's collector reads no code host. Owner: owner, with the run-monitor design.
