# Eval suites for checks, steps and workflows

## Purpose

Judges are graded by [JCL](judge-calibration.spec.md). This spec covers everything else a workflow is evaluated on: its deterministic checks (do they fail what they should, and only that), its steps (does a step's prompt produce work that passes its gate, and how consistently), and the whole workflow (does a fixed set of real cases keep ending well). It fixes the order in which graders are trusted (code first, then an accepted judge, then a person, [ADR `eval-graders-in-a-fixed-order-of-trust`](../adr/eval-graders-in-a-fixed-order-of-trust.adr.md)), how live suites are run and capped, the split between regression and capability suites, and the rule that a rate graded by a judge is shown with that judge's measured error ([ADR `judge-graded-rates-carry-the-judges-error`](../adr/judge-graded-rates-carry-the-judges-error.adr.md)). It extends the eval tooling of [LIF](lifecycle-and-evals.spec.md) and reuses the case-set format of [PRP](improvement-proposals.spec.md) for workflow cases, so one reviewed case serves both a release check and a paired trial. The gaps it closes are E10, E12 to E14 and E17 of [research `eval-and-judge-gap-analysis`](../research/eval-and-judge-gap-analysis.rsrch.md); notes are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md). Workflow authors, the eval skill and `upgrade-check --stamp` depend on it.

## Depends on

- `caller-provenance.spec.md`: caller provenance
- `executor-interface.spec.md`: executor interface
- `judge-calibration.spec.md`: acceptance state (JCL-B17)
- `lifecycle-and-evals.spec.md`: stamp only when clean (LIF-B2); executor conformance in the eval set (LIF-B4)
- `observability-and-cost.spec.md`: observability and cost
- `supervision-metrics.spec.md`: supervision metrics
- `workspace-and-concurrency.spec.md`: workspace and concurrency

## Behaviours

### EVS-B8 Suites and roles

WHEN a workflow package holds suites THE engine SHALL read each with one kind, `check` (one gate's deterministic check on fixture artifacts, model-free, graded by the expected check result), `judge` (one gate's judge on its gold set, graded by gold labels), `step` (one step session and its gate on a fixed input and workspace) or `workflow` (a whole run on a fixed case as a dry run), the last two graded by the grader order, and one role, `regression` (every case must pass, one failing case failing the suite) or `capability` (tracked as a rate, never failing a suite), listing for graduation a capability case that passed in each of its last three recorded runs on the current binding, for a person to move to `regression` ([research `evaluating-llm-judges-public-practice`](../research/evaluating-llm-judges-public-practice.rsrch.md) F12).

- GIVEN a capability case passing three recorded runs in a row WHEN reported THEN it is listed for graduation

### EVS-B9 Check cases

WHEN check cases are read from `evals/checks/<unit>/must-pass|must-fail/` THE engine SHALL take each fixture's artifacts, workspace state and git facts, expect `PASS`, `MAYBE` or `FAIL` (for `FAIL` the criterion id the evidence must name).

- GIVEN a must-fail case WHEN its check returns `FAIL` naming another criterion THEN the case fails

### EVS-B2 Line endings

WHEN a check suite runs THE engine SHALL run each fixture once with LF and once with CRLF line endings, a different result between the two failing the case.

- GIVEN a check case whose fixture table counts rows WHEN the suite runs THEN it runs with LF and CRLF and a different result fails it

### EVS-B1 Checks are tested both ways

WHEN a workflow whose check has only must-pass cases is validated THE engine SHALL warn `check_without_fail_case` naming the gate.

- GIVEN a check with no must-fail case WHEN validated THEN it warns `check_without_fail_case`

### EVS-B10 Step cases and trials

WHEN step cases are read from `evals/steps/<unit>/<case_id>/case.json` (`role`, `inputs`, `expect`, `covered`, `trials` with `k` 3 by default, and an optional `workspace/`) THE engine SHALL run each trial as the one step as its own workflow in a fresh repository made from the case's workspace, with what earlier units would have produced taken from `inputs`, the step's real prompt and executor, then its check and judge exactly as in a run, and pass it when the gate's derived verdict is PROCEED within the step's retry budget and every `expect` assertion holds.

- GIVEN a step trial whose gate proceeds on attempt 2 within budget WHEN graded THEN it passes

### EVS-B11 Assertions

WHEN an `expect` or `end_state` assertion is read THE engine SHALL accept `{path}` (exists), `{path, absent}`, `{path, pattern}`, `{path, heading}` and `{changed_within: [globs]}`, `covered: true` saying the assertions cover the case so code decides a pass.

- GIVEN `{path: "docs/x.md", heading: "Plan"}` WHEN the file lacks that heading THEN the assertion fails

### EVS-B12 Workflow cases and trials

WHEN workflow cases are read from the entries of `evals/cases.json` (the case-set fields of PRP plus `role`, `end_state[]`, optional `answers[]`, optional `max_level`, `covered` and `trials`, `k` 1 by default and 3 for regression cases of a workflow declaring `stable`) THE engine SHALL run each trial as a dry-run item that pushes, files and comments nothing ([WSP](workspace-and-concurrency.spec.md)), apply recorded answers per pause in order with caller `pipeline` and `caller_app: evals` ([PRV](caller-provenance.spec.md)), end a trial that stops for a person for any reason other than a spent budget as `paused`, counted in no rate, fail a trial above `max_level` ([SUP](supervision-metrics.spec.md)), keep eval runs out of production supervision figures, list a case whose base commit is missing as invalid while running the rest, and pass a trial when the run ends with exit 0 and every `end_state` assertion holds, with the outcome gate passing too where the workflow declares one.

- GIVEN a case whose base commit is missing WHEN the suite runs THEN it is listed invalid and the rest run

### EVS-B13 Model-free and live suites

WHEN suites run THE engine SHALL run `check` suites, prompt lint, deterministic scenarios and any suite on scripted stand-in executors ([LIF-B4](lifecycle-and-evals.spec.md)) in the test suite and CI, and refuse with exit 2, starting no session, a `judge`, `step` or `workflow` suite on a real executor under the test runner's marker unless `TEMPERGRAPH_LIVE=1` lifts it, so no test starts a live model session.

- GIVEN a live suite under the test marker WHEN started THEN it exits 2 and no session starts

### EVS-B14 Cap, binding and logging

WHEN a live suite runs THE engine SHALL take `--cap <usd>` (default from the operator config, else $20) and start no new session at the cap while running sessions finish and the record is `partial`, refuse a step case whose executor cannot provide the step's tools before spend ([EXI](executor-interface.spec.md)), record each session's binding (executor, version, alias, model slug, prompt and brief digests) so a result whose binding differs from the current one reads `stale`, log and cost every session like a run's ([OBS](observability-and-cost.spec.md)), and write results as rows of `evals/results.jsonl` under the state root holding ids, statuses, counts and digests only; `evals run --kind judge` scores every judged gate and risk level under the one cap.

- GIVEN a result whose judge alias was rebound WHEN reported THEN it reads `stale`

### EVS-B6 Cap stops cleanly

WHEN a workflow suite run with `--cap 20` reaches an estimated $20 after 4 of 7 cases THE engine SHALL start no fifth case, let the fourth finish, and record `partial` with 4 results.

- GIVEN $20 reached after 4 of 7 cases WHEN the cap is reached THEN the record is `partial` with 4 results

### EVS-B15 Judge-graded rates carry the judge's error

WHEN a report shows a rate that counts judge statuses or judge-derived verdicts (per-criterion and gate pass rates of [OBS](observability-and-cost.spec.md), step-suite pass rates, judge-graded trial targets) THE engine SHALL show the raw rate with the judge's state ([JCL-B17](judge-calibration.spec.md)) and, for `accepted` or `provisional`, the corrected rate `θ = (p + c − 1) / (c + g − 1)` clipped to [0, 1] (`p` the raw pass rate, `c` the judge's `catch_rate`, `g` its `clean_rate`) labelled `corrected`; the raw rate only labelled `uncorrectable` when `c + g − 1` is below 0.2; the raw rate only labelled `uncorrected` with the state for `unscored`, `stale`, `below_bar` or `contradicted`; never hiding the raw rate or storing the corrected one in its place ([research `evaluating-llm-judges-public-practice`](../research/evaluating-llm-judges-public-practice.rsrch.md) F4).

- GIVEN a judge with catch 0.55 and clean 0.60 WHEN a rate is shown THEN it is raw only, labelled `uncorrectable`

### EVS-B5 Corrected rate

WHEN the per-criterion report runs for a criterion with a raw pass rate of 0.80 over 50 runs THE engine SHALL show, for an `accepted` judge with `catch_rate` 0.90 and `clean_rate` 0.95, raw 0.80 and corrected (0.80 + 0.90 − 1) / (0.90 + 0.95 − 1) = 0.82 labelled `corrected`, and for a `stale` judge 0.80 labelled `uncorrected (stale)`.

- GIVEN an `accepted` judge with catch 0.90 and clean 0.95 WHEN reported THEN the corrected rate is 0.82
- GIVEN the judge `stale` WHEN reported THEN 0.80 shows labelled `uncorrected (stale)`

### EVS-B16 Grader order

WHEN a step or workflow case is graded THE engine SHALL take the first grader that can decide it: code (`expect`, `end_state`, the gate's check) when an assertion or check fails or the case is `covered`; then the gate's judge or the outcome judge when its state is `accepted`; otherwise a person, the result being `needs_person` listed with the command to record a grade, counted in no rate until a grade is recorded, and leaving a regression suite `incomplete`, never `passed`.

- GIVEN a failing assertion WHEN graded THEN code decides and no judge is read

### EVS-B4 Unaccepted judge defers to a person

WHEN a trial of a step case with no `expect` assertions whose gate judge is `below_bar` ends with PROCEED THE engine SHALL record `needs_person`, not `passed`, and read a regression suite holding it `incomplete`.

- GIVEN a `below_bar` judge and PROCEED WHEN graded THEN the result is `needs_person`

### EVS-B17 Figures

WHEN suite figures are computed THE engine SHALL compute `pass_at_1` (passing trials over trials), `pass_hat_k` (cases whose `k` trials all passed over cases, [research `evaluating-llm-judges-public-practice`](../research/evaluating-llm-judges-public-practice.rsrch.md) F11), `first_attempt_pass` (trials whose gate passed on attempt 1), `mean_attempts` (attempts to PROCEED over passing trials), `cost_per_pass` (estimated cost of all trials over passing trials) and `never_passed` (cases with 0 passing trials over at least 5, listed as "check the case first", F13).

- GIVEN a case with 0 of 6 trials passing WHEN reported THEN it is listed under `never_passed`

### EVS-B3 Consistency over a lucky pass

WHEN results come in for a step suite of 6 cases at `k` = 3 with trials passed 3, 2, 3, 0, 3 and 1 THE engine SHALL compute `pass_at_1` 12 / 18 = 0.67 and `pass_hat_k` 3 / 6 = 0.50, counting for `pass_hat_k` only the cases with all three trials passing.

- GIVEN those trials WHEN computed THEN `pass_at_1` is 0.67 and `pass_hat_k` is 0.50

### EVS-B18 Eval verbs

WHEN `evals run <workflow> --kind <kind> [--role <role>] [--trials k] [--executor <name>] [--cap <usd>]`, `evals report <workflow> [--json]` or `evals grade <result> --pass|--fail --reason <text>` runs THE engine SHALL run suites and record results, calling a model only for live kinds; print figures per suite and case, the graduation list, and stale and `needs_person` results with no model call; or record a person's grade for a `needs_person` trial as a row beside the results with no model call.

- GIVEN `evals report` WHEN run THEN no model is called

### EVS-B7 Stamp needs green model-free regression suites

WHEN `upgrade-check --stamp` runs for a workflow whose `check` regression suite has one failing case THE engine SHALL write no stamp and print the failing case ([LIF-B2](lifecycle-and-evals.spec.md)).

- GIVEN one failing check regression case WHEN `upgrade-check --stamp` runs THEN no stamp is written

## Acceptance criteria

- EVS-AC1 (EVS-B3, EVS-B17): Every scenario of EVS-B3 is reproduced by the figures function
- EVS-AC2 (EVS-B5, EVS-B15): The corrected rate of EVS-B5 is reproduced, and every label of EVS-B15 appears for its states in a fixture report
- EVS-AC3 (EVS-B13): No live suite can start under the test marker
- EVS-AC4 (EVS-B16, EVS-B4): A `needs_person` result counts in no rate and leaves a regression suite `incomplete`
- EVS-AC5 (EVS-B14): A live suite record contains no request, output or model text, by a canary test
- EVS-AC6 (EVS-B18): `evals report` and `evals grade` make no model call
- EVS-AC7 (EVS-B1, EVS-B2, EVS-B6, EVS-B7, EVS-B8, EVS-B9, EVS-B10, EVS-B11, EVS-B12): Fixtures cover a check without a fail case, both line endings, step and workflow trials, each assertion form, graduation, the cap and the stamp refusal

## Open questions

- Should a workflow declaring `stable` also need a live regression suite result on its current binding, not only green model-free suites? Until answered: not in the first release, because live suites cost money and need the owner's run. Owner: owner.
- The default cap of $20 per live suite run is low: a full replay of a workflow's cases costs far more, and workflow suites will usually need a higher cap set by the operator. Owner: owner.
- Not built yet: `max_level` of a workflow case is not enforced, a test-result assertion does not exist, and the per-criterion pass rates of `report` do not yet carry the judge's state (the step suite's rate does), so EVS-AC2 is not met. Owner: engine owner.
