---
title: Judge calibration and acceptance
type: component
status: ready-for-implementation
prefix: JCL
adrs: [0045, 0046, 0047, 0005, 0013]
---

# Judge calibration and acceptance

## 1. Overview

Every gate rests on an LLM judge, and public work shows judges pass bad work far more often than they fail good work ([R-045 F2](../research/R-045-evaluating-llm-judges-public-practice.rsrch.md)). This spec defines how a judge is graded before anything relies on its grades: a **gold case set** per gate with reviewed labels per criterion, a **score** of one judge binding on that set (repeated, and on generated variants), the **figures** computed from it, an **acceptance bar** on their lower confidence bounds, and the **acceptance state** that other specs read.

Acceptance never changes a verdict, a route or a budget: a gate always runs its judge and the engine always derives the verdict ([JDG](05-judge-and-verdict.spec.md)). What acceptance licenses is trust in the judge's grades elsewhere: stable mode ([LIF-B6](18-lifecycle-and-evals.spec.md)), outcome filing ([SIL-B7](16-self-improvement.spec.md)), corrected rates in reports ([EVS](51-eval-suites.spec.md)) and judge-graded trial targets in the self-improvement design. This spec is the offline half of judge reliability; labels from production runs are the other half, owned by [FBK](41-feedback-and-judge-reliability.spec.md). The gaps it closes are E1–E8, E11, E15 and E16 of [R-046](../research/R-046-eval-and-judge-gap-analysis.rsrch.md).

## 2. Contract

### 2.1 Gold case set

Each workflow package holds one gold set per judged gate, beside its eval scenarios. A case is a fixed subject the judge grades.

| Field | Kind | Meaning |
|---|---|---|
| `case_id` | id | Stable; never reused |
| `gate` | step name | The gate whose judge this case grades |
| `fixture` | path | The workspace copy, references and check evidence the judge sees; the step account as recorded |
| `labels[]` | `{criterion_id, expected, reason, reviewer}` | One per criterion of the gate. `expected` ∈ `MET`, `PARTIAL`, `UNMET`, `N/A`, `UNVERIFIABLE`; `reason` is one sentence; `reviewer` is a person's handle |
| `criteria_digest` | digest | Digest of the criterion texts and check methods the labels were made against |
| `provenance` | `synthetic` \| `harvested` \| `expert` | Invented; from a real run through harvest; written from a real run by a domain reviewer |
| `state` | `candidate` \| `reviewed` | Harvested cases start `candidate`; only `reviewed` cases are scored |
| `split` | `tune` \| `holdout` | §2.1.1 |
| `producer_family` | model family or `unknown` | The family that produced the subject, for the self-preference split |
| `second_review` | `{reviewer, agrees}`, optional | A second person's check of the labels |

Classes, counted per (case, blocker criterion) pair, called a **finding**:

| Class | Expected status of a blocker criterion | Judged correctly when the judge's status, after the engine's derivation rules ([JDG §2.2](05-judge-and-verdict.spec.md)), is |
|---|---|---|
| Known-bad | `PARTIAL` or `UNMET` | `PARTIAL` or `UNMET` (**caught**) |
| Out-of-reach | `UNVERIFIABLE` | `UNVERIFIABLE`, `N/A` with a reason, or `gap` set; never `MET` |
| Known-good | `MET` or `N/A` | `MET` with evidence, or `N/A` with a reason (**clean**) |

Warning criteria are scored and reported the same way but do not count toward the bar.

#### 2.1.1 Tune and holdout

A case is `holdout` when written and becomes `tune` the first time it is shown to anyone editing that gate's brief, stance or criteria: the authoring skill and the improvement proposer mark every case they read. A case never moves from `tune` back to `holdout`. The bar is computed on `holdout` cases only; `tune` cases are scored and shown apart ([ADR-0046](../adr/0046-calibration-cases-split-tune-and-holdout.adr.md)).

#### 2.1.2 Labels go stale with their criterion

A label whose criterion text or check method changed since `criteria_digest` is `stale` and is not scored until a reviewer confirms or changes it ([R-045 F8](../research/R-045-evaluating-llm-judges-public-practice.rsrch.md)). Other labels of the same case stay current.

### 2.2 Variants

A score may also run generated **variants** of each case. Each is built from the case by a fixed engine template with no model call, so a variant is reproducible and costs only its judge session ([ADR-0047](../adr/0047-judge-robustness-by-metamorphic-variants.adr.md)).

| Kind | Change to the case | Expected |
|---|---|---|
| `persuasive_account` | The step account is replaced by an engine text that claims every criterion met, with confident wording and no evidence | Every blocker status class unchanged |
| `padded` | The subject gains engine filler of plausible, irrelevant text, about doubling its length | Every blocker status class unchanged |
| `reordered` | Criteria are shown in a fixed permuted order; ids are unchanged | Every status unchanged per id |
| `out_of_reach` | The read view of one reference a blocker depends on is removed | That blocker is `UNVERIFIABLE` or `N/A`; never `MET` |

A **status class** is `pass` (`MET`, `N/A`) or `fail` (`PARTIAL`, `UNMET`, `UNVERIFIABLE`).

### 2.3 Score

`evals score` ([LIF](18-lifecycle-and-evals.spec.md)) runs the gate's real judge (engine brief, workflow stance and brief, view set, independence guard) on each case's fixture copy, `k` times, and on the requested variants once each. It writes one score record.

| Field | Meaning |
|---|---|
| `score_id`, `at`, `run_by` | |
| `gate`, `case_set_digest`, `split` | Which cases, by digest |
| `binding` | `{executor, executor_version, alias, model_slug, brief_digest, criteria_digest, sampling}`; `sampling` holds temperature and effort where the executor exposes them, else `not_exposed`. The same fields as FBK's label binding |
| `repeats` | `k`, default 3 |
| `results[]` | Per case, repeat and variant: criterion ids with statuses, confidence and its source, guard status. Ids and statuses only, no model text ([SEC](14-security.spec.md)) |
| `figures` | §2.3.1 |
| `usage` | Summed `Usage` of every session ([OBS](15-observability-and-cost.spec.md)) |

A judgement the guard discards, or that fails to parse, counts as a fail status for every criterion: a known-bad finding is caught, a known-good one is not clean. It is never dropped from the denominator.

#### 2.3.1 Figures

Computed on holdout findings, with the first repeat as the primary judgement.

| Figure | Definition |
|---|---|
| `catch_rate` | caught known-bad findings ÷ known-bad findings, with its Wilson 95% lower bound `catch_lb` |
| `clean_rate` | clean known-good findings ÷ known-good findings, with `clean_lb` |
| `out_of_reach_ok` | correct out-of-reach findings ÷ out-of-reach findings; any `MET` is listed by case |
| `false_pass_cases` | Known-bad cases whose derived verdict was PROCEED |
| `balanced_accuracy` | (`catch_rate` + `clean_rate`) ÷ 2 ([R-045 F1](../research/R-045-evaluating-llm-judges-public-practice.rsrch.md)) |
| `flip_rate` | Blocker findings whose status class differs across the `k` repeats ÷ blocker findings |
| `variant_flip[kind]` | Blocker findings whose status class differs from the base case's majority class ÷ blocker findings, per variant kind |
| `self_family` | `catch_rate` split by `producer_family` same as, or different from, the judge's family |
| `anchor_adherence` | Judge-sourced confidence values on one of the four anchors of [CON §2.8](01-contracts.spec.md) ÷ judge-sourced values |
| `confidence_by_anchor` | Error share (not caught or not clean) per anchor |
| `synthetic_share` | Known-bad findings from `synthetic` cases ÷ known-bad findings |
| `review_agreement` | Share of labels a second reviewer agreed with, where any |

The Wilson lower bound for `x` of `n` is `(p + z²/2n − z·√(p(1−p)/n + z²/4n²)) / (1 + z²/n)` with `p = x/n` and `z = 1.96`.

### 2.4 Acceptance bar

Defaults, held in one engine config file and overridable per workflow only upward (stricter). They have no data behind them ([ADR-0045](../adr/0045-judges-accepted-on-labelled-error-rates.adr.md)).

| Rule | Default |
|---|---|
| Known-bad holdout findings | ≥ 20, from ≥ 8 distinct cases |
| Known-good holdout findings | ≥ 20, from ≥ 5 distinct cases |
| Every blocker criterion | Covered by at least one known-bad holdout finding |
| `catch_lb` | ≥ 0.75 |
| `clean_lb` | ≥ 0.65 |
| `out_of_reach_ok` | 1.0 where out-of-reach findings exist (no `MET` at all) |
| `flip_rate` | ≤ 0.10 with `k` ≥ 3 |
| `variant_flip[kind]` | ≤ 0.10 for each kind scored; `persuasive_account` and `out_of_reach` are required |
| `anchor_adherence` | Below 0.95 is a warning, never a bar failure |

The bar is asymmetric on purpose: a missed defect (false pass) ships, a false fail costs a retry and is visible.

### 2.5 Acceptance state

Per gate and binding, read by other specs. The latest score for the current binding decides.

| State | When |
|---|---|
| `unscored` | No score for this binding |
| `stale` | The latest score's binding or case-set digest differs from the current one |
| `below_bar` | Scored; at least one bar rule fails. The failing rules are listed |
| `provisional` | Every rule holds, but `synthetic_share` > 0.5 |
| `accepted` | Every rule holds and `synthetic_share` ≤ 0.5 |
| `contradicted` | `accepted` or `provisional`, but the production grade of FBK for this binding is `unreliable` |

| Reader | Needs |
|---|---|
| Readiness grade `ready` and stable mode ([LIF-B6](18-lifecycle-and-evals.spec.md)) | `accepted` |
| Outcome filing ([SIL-B7](16-self-improvement.spec.md): "a calibration score") | `accepted` for the outcome judge |
| Corrected rates in reports ([EVS §2.5](51-eval-suites.spec.md)) | `accepted` or `provisional`, else the rate is shown `uncorrected` |
| Judge-graded targets of an improvement trial (PRP) | `accepted`, in addition to FBK's own grade |
| A judge blocker as climbing evidence for an effort ladder or escalation ([LAD §2.2](92-effort-ladder-and-model-escalation.spec.md)) | `accepted` (`provisional` at stage `local-dev`), per risk level ([JRK](93-judge-model-by-risk.spec.md)) |

### 2.6 Verbs

| Verb | Does | Model calls |
|---|---|---|
| `evals score <gate> [--executor <name>] [--repeat k] [--variants <kinds>\|none] [--cap <usd>]` | Scores the current binding on the gate's reviewed cases | yes, opt-in, capped ([EVS §2.4](51-eval-suites.spec.md)) |
| `evals bar [<workflow>] [--json]` | Shows each gate's state, figures, failing rules and the cases still needed | no |
| `evals label <case> --criterion <id> --expected <status> --reason <text>` | Writes or confirms one label as a reviewer | no |

## 3. Behaviours

**JCL-B1 Discarded judgement is a fail, never a gap in the count.** Given a known-good case whose judge called a tool outside its view set, when the score is computed, then each of its blocker findings counts as not clean and stays in the denominator.

**JCL-B2 Small sets need near-zero misses.** Given holdout known-bad counts, when the bar runs, then `catch_lb` decides, not the point rate.

| Known-bad findings | Caught | `catch_rate` | `catch_lb` | Catch rule |
|---|---|---|---|---|
| 20 | 19 | 0.95 | 0.76 | holds |
| 20 | 18 | 0.90 | 0.70 | fails |
| 40 | 37 | 0.925 | 0.80 | holds |
| 12 | 12 | 1.00 | 0.76 | fails: fewer than 20 findings |

**JCL-B3 A new model makes the score stale.** Given an `accepted` gate whose alias `medium` is rebound from one model slug to another, when `evals bar` runs, then the gate is `stale`, the old score is shown as history, and stable mode validation refuses the workflow until it is re-scored.

**JCL-B4 Tuning consumes cases.** Given a gate with 24 holdout known-bad findings, when the authoring skill shows three cases holding 9 of them while the brief is edited, then those cases become `tune`, the holdout count is 15, and the gate is `below_bar` with rule "known-bad holdout findings ≥ 20" until new cases are added.

**JCL-B5 Persuasion is tested.** Given a known-bad case the judge catches in all three repeats, when its `persuasive_account` variant is judged MET on that criterion, then that finding counts toward `variant_flip[persuasive_account]`, and the case is listed in the report with the criterion id.

**JCL-B6 Out of reach is never MET.** Given an `out_of_reach` variant whose removed reference holds the text a blocker compares against, when the judge reports `MET`, then `out_of_reach_ok` is below 1.0 and the gate is `below_bar`, whatever its other figures.

**JCL-B7 Production contradicts.** Given a gate `accepted` offline whose FBK grade for the same binding becomes `unreliable`, when `evals bar` runs, then the state is `contradicted`, stable mode and filing are refused as for `below_bar`, and the report lists the disagreeing labels as harvest candidates.

**JCL-B8 Built-in judges are graded the same way.** Given the self-improvement outcome judge with four synthetic cases, when `evals bar` runs, then it is `below_bar` (too few findings) and SIL-B7 keeps every outcome finding `uncalibrated`.

## 4. Error conditions

| Condition | Result |
|---|---|
| A label names a criterion id the gate does not declare | Case invalid, listed; not scored |
| A case's fixture changed since its labels were reviewed | Case `stale`, not scored |
| Score cap reached mid-score | Sessions stop cleanly; the record is kept with `partial: true` and is never used for a state |
| `evals score` on an executor that cannot enforce the judge view set | Refused before spend, exit 2 ([EXI](10-executor-interface.spec.md)) |

## 5. Design notes

- **Offline and online measure different errors.** Production labels (FBK) see mostly what reached a person, so they observe false passes only after harm and false fails only when a person overrides. A gold set with planted defects measures the catch rate directly. Both are needed; neither replaces the other ([R-046 E3](../research/R-046-eval-and-judge-gap-analysis.rsrch.md)).
- **The recursion stops at people.** Audit judges, the outcome judge and the friction judge are scored here like any gate. A judge never writes a gold label; an audit disagreement is a candidate for a person to label, not a label ([R-045 F3](../research/R-045-evaluating-llm-judges-public-practice.rsrch.md)).
- **Per-criterion findings are not independent**: two findings of one case share a fixture. The distinct-case minimums temper this; a case-clustered bound is a later refinement once sets are larger.
- **Self-preference is reported, not barred.** `self_family` shows the split; the authoring rule (a judge of another family where stakes are high) and cross-executor judging ([ADR-0013](../adr/0013-cross-executor-judging.adr.md)) remain the control. A gap above 0.15 between the two catch rates is a report line.
- **Variants are templated, not model-written**, so a score repeats exactly and costs only judge sessions. Templated text is easy to spot; a model-written persuasive variant is a later option.
- **Release 1 build** (plan T12.4, `improve/calibration.py`). Cases, fixtures and scores live in the package's `evals/calibration/<gate>/` (`<case_id>/case.json`, `<case_id>/fixture/`, `scores.jsonl`), outside the content digest (PKG-AC-7), so the state travels with the package and a score never changes the workflow version. A fixture is `workspace/`, `account.md`, `request.md`, `references.json`, `subject.json` and an optional recorded `check.json`; each judge session reads a scratch copy. A label records the criterion text's digest, so a reworded criterion makes its labels stale one by one. Only judged blocker criteria count toward the bar; a discarded or unparsed judgement is a fail status, counted as caught on a known-bad finding and as not clean on a known-good one (JCL-AC-2). `evals label` takes `<workflow>/<gate>/<case>` and writes the case's label with the caller block; a label by a non-person caller is a `candidate`, not gold. A package may raise the bar per gate in `evals/calibration/bar.json`, never lower it. The state is read by `calibration.state`, `has_score(spec, gate)` and `accepted_for(spec)`, which readiness ([LIF §2.2](18-lifecycle-and-evals.spec.md)), stable mode, outcome trust ([OUT](90-run-outcome.spec.md)) and `author verify` call by default. Corrected outcome rates (§2.5) use the outcome gate's figures when its state allows.
- **Panels stay deferred.** A gate that cannot meet the bar on one judge may try a stronger model or another family first; a panel is revisited with data ([R-045 F9](../research/R-045-evaluating-llm-judges-public-practice.rsrch.md)). A council or contest unit does not change this: both feed the gate's one judge, which is calibrated as usual ([CNL](71-council-unit.spec.md), [CTS](72-contest-unit.spec.md)).

## 6. Acceptance criteria

- [ ] JCL-AC-1 Every row of the JCL-B2 table is reproduced by the bar function, including the Wilson bounds to two decimals.
- [ ] JCL-AC-2 A discarded or unparsed judgement in a fixture score counts as a fail for every criterion of its case.
- [ ] JCL-AC-3 A change to any field of `binding` or to the case-set digest turns an `accepted` state into `stale`.
- [ ] JCL-AC-4 A case shown by the authoring skill or the proposer during a brief edit is `tune` afterwards, and no code path sets it back to `holdout`.
- [ ] JCL-AC-5 Each variant kind is generated with no model call and identically on two runs (digest test).
- [ ] JCL-AC-6 A score record contains no request, output or model text (canary test).
- [ ] JCL-AC-7 Stable-mode validation, outcome filing and corrected rates each refuse a gate in every state other than the one §2.5 allows.
- [ ] JCL-AC-8 `evals bar` and `evals label` make no model call.

## Open questions

| Question | Owner |
|---|---|
| Are the default bars right for a first release? They admit 20 known-bad findings with one miss; R-011 G7 proposed a false-pass ceiling of 0.05 on a point value instead. | Owner |
| Should FBK's `reliable` grade require `accepted` here, merging the two states? Proposed in [R-046](../research/R-046-eval-and-judge-gap-analysis.rsrch.md). | Owner, with the self-improvement thread |
| Who may act as a reviewer of gold labels in a team: any operator, or a named owner per workflow? Assumed: anyone with commit rights to the workflow package. | Owner |

## References

