---
title: Eval suites for checks, steps and workflows
type: component
status: review
prefix: EVS
adrs: [0048, 0049, 0045]
---

# Eval suites for checks, steps and workflows

## 1. Overview

Judges are graded by [JCL](50-judge-calibration.spec.md). This spec covers everything else a workflow is evaluated on: its **deterministic checks** (do they fail what they should, and only that), its **steps** (does a step's prompt produce work that passes its gate, and how consistently), and the **whole workflow** (does a fixed set of real cases keep ending well). It fixes the order in which graders are trusted, how live suites are run and capped, the split between regression and capability suites, and the rule that a rate graded by a judge is shown with that judge's measured error. The gaps it closes are E10, E12–E14 and E17 of [R-046](../research/R-046-eval-and-judge-gap-analysis.rsrch.md).

It extends the eval tooling of [LIF](18-lifecycle-and-evals.spec.md) (deterministic and rubric scenarios, replay of judges) and reuses the case-set format of [PRP](40-improvement-proposals.spec.md) for workflow cases, so one reviewed case serves both a release check and a paired trial.

## 2. Contract

### 2.1 Suites

A workflow package holds suites beside its scenarios. Each suite has one kind and one role.

| Kind | Subject | Spends model calls | Graded by |
|---|---|---|---|
| `check` | One gate's deterministic check on fixture artifacts | no | code: the expected `CheckResult` |
| `judge` | One gate's judge on its gold set | yes | gold labels ([JCL](50-judge-calibration.spec.md)) |
| `step` | One step session and its gate on a fixed input and workspace | yes | the grader ladder of §2.6 |
| `workflow` | A whole run on a fixed case, as a dry run | yes | the grader ladder of §2.6 |

| Role | Meaning | Expected pass level |
|---|---|---|
| `regression` | Behaviour a change must keep | Every case passes; one failing case is a failed suite |
| `capability` | Behaviour the workflow is working toward | Tracked as a rate; never fails a suite |

A capability case that passed in each of its last three recorded runs on the current binding is listed for **graduation**; a person moves it to `regression` ([R-045 F12](../research/R-045-evaluating-llm-judges-public-practice.rsrch.md)).

### 2.2 Check and step cases

| Field | `check` case | `step` case |
|---|---|---|
| `case_id` | stable id | stable id |
| `fixture` | artifacts, workspace state, git facts | input values, workspace at a base, references |
| `expect` | `PASS`, `MAYBE` or `FAIL`, and for `FAIL` the criterion id the evidence must name | deterministic assertions over the produced artifacts (paths, headings, patterns, test results), optional |
| `trials` | — | `k`, default 3 |

Every check has at least one must-fail and one must-pass case; validation warns for a check without both. A check case that fails on one line-ending convention and passes on the other is a failed case: each fixture runs with LF and CRLF.

A step trial runs in a fresh worktree at the case's base, with the step's real prompt and executor, then its check and its judge, exactly as in a run. It **passes** when the gate's derived verdict is PROCEED within the step's retry budget and every `expect` assertion holds.

### 2.3 Workflow cases

A workflow case is a PRP case-set entry (case id, base commit, request, expected scope) plus:

| Field | Meaning |
|---|---|
| `role` | `regression` or `capability` |
| `end_state[]` | Deterministic assertions on the finished branch: paths changed inside the expected scope only, tests passing, artifacts present |
| `answers[]`, optional | Recorded answers per pause, applied in order with caller `pipeline` and `caller_app: evals` ([PRV](85-caller-provenance.spec.md)); a pause with no recorded answer ends the trial as `paused` |
| `max_level`, optional | The highest supervision level a trial may need ([SUP §2.3](86-supervision-metrics.spec.md)); a trial above it fails. Eval runs never enter production supervision figures |
| `trials` | `k`, default 1; 3 for regression cases of a workflow that declares `stable` |

A trial runs as a dry-run batch item ([WSP](13-workspace-and-concurrency.spec.md)): nothing is pushed, filed or commented. It **passes** when the run ends with exit 0 and every `end_state` assertion holds, or, where the workflow declares an outcome gate, when that gate passes too.

### 2.4 Running and cost

| Rule | Detail |
|---|---|
| Model-free suites | `check` suites, prompt lint, deterministic scenarios and any suite run on scripted stand-in executors ([LIF-B4](18-lifecycle-and-evals.spec.md)) run in the test suite and in CI |
| Live suites | `judge`, `step` and `workflow` suites on a real executor are opt-in verbs, never part of the test suite or CI: no test starts a live model session |
| Cap | Every live suite run takes `--cap <usd>` (default from the operator config, else $20); at the cap no new session starts, running sessions finish, and the record is `partial` |
| Binding | Every result records the binding of each session (executor, version, alias, model slug, prompt and brief digests); a result whose binding differs from the current one reads `stale` |
| Logging | Every session is logged and costed like a run's ([OBS](15-observability-and-cost.spec.md)); results are ids, statuses, counts and digests only |

### 2.5 Judge-graded rates carry the judge's error

Any rate in a report that counts judge statuses or judge-derived verdicts (per-criterion pass rates and gate pass rates in [OBS §2.4](15-observability-and-cost.spec.md), step-suite pass rates, judge-graded trial targets) is shown with the judge's state and, where the state allows, a corrected estimate ([ADR-0048](../adr/0048-judge-graded-rates-carry-the-judges-error.adr.md), [R-045 F4](../research/R-045-evaluating-llm-judges-public-practice.rsrch.md)).

| Judge state ([JCL §2.5](50-judge-calibration.spec.md)) | Shown |
|---|---|
| `accepted`, `provisional` | Raw rate, corrected rate `θ = (p + c − 1) / (c + g − 1)` clipped to [0, 1], where `p` is the raw pass rate, `c` the judge's `catch_rate` and `g` its `clean_rate`; and the label `corrected` |
| any state with `c + g − 1 < 0.2` | Raw rate only, labelled `uncorrectable` (the judge separates too little) |
| `unscored`, `stale`, `below_bar`, `contradicted` | Raw rate only, labelled `uncorrected` with the state |

The raw rate is never hidden and the corrected rate is never stored in place of it.

### 2.6 Grader order

A step or workflow case is graded by the first grader that can decide it, in this order ([ADR-0049](../adr/0049-eval-graders-in-a-fixed-order-of-trust.adr.md)):

| Order | Grader | Decides when |
|---|---|---|
| 1 | Code: `expect`, `end_state`, the gate's check | The assertion or check fails, or the case is fully covered by assertions |
| 2 | The gate's judge or the outcome judge | Its state is `accepted` |
| 3 | A person | Otherwise: the trial result is `needs_person`, listed with the command to record a grade |

A trial graded `needs_person` counts in no rate until a person records a grade. In a `regression` suite a `needs_person` case leaves the suite `incomplete`, never `passed`.

### 2.7 Figures and verbs

| Figure | Definition |
|---|---|
| `pass_at_1` | Passing trials ÷ trials |
| `pass_hat_k` | Cases whose `k` trials all passed ÷ cases ([R-045 F11](../research/R-045-evaluating-llm-judges-public-practice.rsrch.md)) |
| `first_attempt_pass` | Trials whose gate passed on attempt 1 ÷ trials |
| `mean_attempts` | Attempts to PROCEED, over passing trials |
| `cost_per_pass` | Estimated cost of all trials ÷ passing trials |
| `never_passed` | Cases with 0 passing trials over at least 5 trials: listed as "check the case first", since such a case is most often broken ([R-045 F13](../research/R-045-evaluating-llm-judges-public-practice.rsrch.md)) |

| Verb | Does | Model calls |
|---|---|---|
| `evals run <workflow> --kind <kind> [--role <role>] [--trials k] [--executor <name>] [--cap <usd>]` | Runs suites, records results | only for live kinds |
| `evals report <workflow> [--json]` | Figures per suite and case, graduation list, stale and `needs_person` results | no |
| `evals grade <result> --pass\|--fail --reason <text>` | Records a person's grade for a `needs_person` trial | no |

## 3. Behaviours

**EVS-B1 Checks are tested both ways.** Given a check with only must-pass cases, when the workflow is validated, then validation warns `check_without_fail_case` naming the gate.

**EVS-B2 Line endings.** Given a check case whose fixture table counts rows, when the suite runs, then it runs once with LF and once with CRLF line endings, and a different result between the two fails the case.

**EVS-B3 Consistency over a lucky pass.** Given a step suite of 6 cases at `k` = 3, when results come in, then `pass_hat_k` counts only cases with all three trials passing.

| Case | Trials passed | Counts for `pass_at_1` | Counts for `pass_hat_k` |
|---|---|---|---|
| a | 3 of 3 | 3 | yes |
| b | 2 of 3 | 2 | no |
| c | 3 of 3 | 3 | yes |
| d | 0 of 3 | 0 | no |
| e | 3 of 3 | 3 | yes |
| f | 1 of 3 | 1 | no |
| **Suite** | | 12 / 18 = 0.67 | 3 / 6 = 0.50 |

**EVS-B4 Unaccepted judge defers to a person.** Given a step case with no `expect` assertions whose gate judge is `below_bar`, when the trial ends with PROCEED, then the result is `needs_person`, not `passed`, and a regression suite holding it reads `incomplete`.

**EVS-B5 Corrected rate.** Given a criterion with a raw pass rate of 0.80 over 50 runs and an `accepted` judge with `catch_rate` 0.90 and `clean_rate` 0.95, when the per-criterion report runs, then it shows raw 0.80 and corrected (0.80 + 0.90 − 1) / (0.90 + 0.95 − 1) = 0.82, labelled `corrected`. With the judge `stale`, it shows 0.80 labelled `uncorrected (stale)`.

**EVS-B6 Cap stops cleanly.** Given a workflow suite run with `--cap 20` whose estimated spend reaches $20 after 4 of 7 cases, when the cap is reached, then no fifth case starts, the fourth finishes, and the record is `partial` with 4 results.

**EVS-B7 Stamp needs green model-free regression suites.** Given a workflow whose `check` regression suite has one failing case, when `upgrade-check --stamp` runs, then no stamp is written and the failing case is printed ([LIF-B2](18-lifecycle-and-evals.spec.md)).

## 4. Error conditions

| Condition | Result |
|---|---|
| A live suite started from the test suite or CI (detected by the engine's test marker) | Refused, exit 2, no session |
| A workflow case whose base commit is missing | Case invalid, listed; the suite runs the rest |
| A step case whose executor cannot provide the step's tools | Refused before spend for that case ([EXI](10-executor-interface.spec.md)) |

## 5. Design notes

- **As built (R2-T4).** `improve/suites.py` holds the suites and `improve/harvest.py` harvest and replay. Check cases are the fixtures of `evals/checks/<unit>/must-pass|must-fail/`; step cases are `evals/steps/<unit>/<case_id>/case.json` (`role`, `inputs`, `expect`, `covered`, `trials`) with an optional `workspace/`; workflow cases are the entries of `evals/cases.json` with `role`, `end_state`, `answers`, `covered` and `trials`. An assertion is `{path}` (exists), `{path, absent}`, `{path, pattern}`, `{path, heading}` or `{changed_within: [globs]}`; `covered: true` says the assertions cover the case, so code decides a pass. A step trial runs the one step as its own workflow in a fresh repository made from the case's workspace, and what earlier units would have produced comes from the case's `inputs`. Results are rows of `evals/results.jsonl` under the state root; a person's grade is a row beside them. A trial that stops for a person for a reason other than a spent budget is `paused` and counts in no rate. `evals run --kind judge` scores every judged gate and risk level under the one cap. The test marker is the test runner's environment variable, lifted only by `TEMPERGRAPH_LIVE=1`. Open: `max_level` of a workflow case is not enforced, a test-result assertion is not built, and the per-criterion pass rates of `report` do not yet carry the judge's state (the step suite's rate does), so EVS-AC-2 stays open.
- **pass^k for gates.** A gate that passes once in three is not a working gate. `pass_hat_k` exposes it where `pass_at_1` averages it away.
- **One case, two uses.** Workflow cases are PRP case-set entries so a reviewed case is written once and serves both a release check here and a version trial there.
- **Corrected, never replaced.** The raw rate stays the record; the corrected rate is an estimate whose error bars depend on a small gold set, so it is a reading aid. An interval that carries the gold set's own uncertainty is a later refinement.

## 6. Acceptance criteria

- [x] EVS-AC-1 Every row of the EVS-B3 table is reproduced by the figures function.
- [ ] EVS-AC-2 The corrected rate of EVS-B5 is reproduced, and every label of the §2.5 table appears for its states in a fixture report.
- [x] EVS-AC-3 No live suite can start under the test marker.
- [x] EVS-AC-4 A `needs_person` result counts in no rate and leaves a regression suite `incomplete`.
- [x] EVS-AC-5 A live suite record contains no request, output or model text (canary test).
- [x] EVS-AC-6 `evals report` and `evals grade` make no model call.

## Open questions

| Question | Owner |
|---|---|
| Should a workflow declaring `stable` also need a live regression suite result on its current binding, not only green model-free suites? Assumed not for the first release, because live suites cost money and need the owner's run. | Owner |

## References

