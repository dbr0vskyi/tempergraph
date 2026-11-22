# Judge and verdict

## Purpose

Every model step is graded by a fresh, read-only judge session that reports a finding per criterion; the engine, never the judge, derives the verdict by rule. A deterministic check runs first and can end the attempt with no model call, and a judging failure never passes. This spec owns contract C4, which prompt rendering ([PRM](04-prompt-rendering.spec.md)) and the independence guard ([GRD](06-independence-guard.spec.md)) uphold ([ADR-0005](../adr/0005-independent-judge-engine-verdict.adr.md)). Gates, budgets ([BUD](08-budgets-and-failures.spec.md)), pauses ([HUM](07-gate-and-human.spec.md)), calibration ([JCL](50-judge-calibration.spec.md)) and the outcome gate ([OUT](90-run-outcome.spec.md)) depend on it; design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### JDG-B1 Check first

WHEN a step ended with a `BLOCKED:` line, failed, or its check returned FAIL THE judge node SHALL start no judge session and set the outcome from the check or the step: FAIL as RETRY, blocked as ESCALATE with confidence placeholder 1.0, source `engine_placeholder`.

- GIVEN a step whose check returned FAIL WHEN the judge node runs THEN no judge session starts and the verdict is RETRY

### JDG-B2 One re-ask

WHEN a judge answer has no parsable judgement block or a criterion id that does not match its number THE judge node SHALL run exactly one second session for the block only, logged with kind `judge_reask` and fed the last 8,000 chars of the first answer, and if it also fails record an unparsed judgement: an unresolved gap with confidence 0.0, source `engine_placeholder`.

- GIVEN two answers with no judgement block WHEN the judge node continues THEN the verdict is ESCALATE with confidence 0.0

### JDG-B3 Judge on its own executor and model

WHEN a judge resolves THE engine SHALL choose its executor by [EXI-B24](10-executor-interface.spec.md) and its model by the judge order ([CON-B3](01-contracts.spec.md)), so producer and judge may differ in both, and refuse at preflight with exit 2 a judge executor that cannot be bound, never falling back at run time.

- GIVEN a `claude` step on `medium` WHEN the judge resolves THEN it runs on `claude` with the step's model
- GIVEN an `antigravity` step on `medium` and no judge settings WHEN the judge resolves THEN it runs cross-executor on `claude` at tier `medium`
- GIVEN an `antigravity` step on `large` with gate judge `antigravity:gemini-pro` WHEN the judge resolves THEN it runs on `antigravity` once its restriction is confirmed
- GIVEN an `agent-sdk` step on `medium` or a `messages-api` step on `small` WHEN the judge resolves THEN it runs on the same executor with the step's model

### JDG-B4 Own timeout

WHEN a judge runs THE engine SHALL give it the judge timeout, not the step's, and treat a judge timeout as an unparsed judgement that escalates, with a timeout row in its record.

- GIVEN a judge timeout of 600 s and a step timeout of 1800 s WHEN the judge runs THEN it gets 600 s

### JDG-B5 Judge infra failure

WHEN a judge session fails with an `infra_cause` THE judge node SHALL rerun the judge inside the node with backoff (10, 20, 40 s) up to the infra cap, never pausing and never passing, and end the run as an infra failure when the cap is spent.

- GIVEN a judge that fails with `rate_limited` three times WHEN the cap is spent THEN the run ends as an infra failure and no PROCEED is recorded

### JDG-B6 Mechanical criteria

WHEN a criterion's requirement is a file, heading, git fact or test result THE engine SHALL expect it in the deterministic check, the judge reading the check's evidence rather than the step's claim, and SHALL warn at validation on rule-like branching written into a judge brief ("if the diff touches X, require Y"), which belongs in the check or a route.

- GIVEN a judge brief that says "if the diff touches `src/`, require a test" WHEN the workflow validates THEN it warns

### JDG-B7 Sampled audit judge

WHEN a gate's judge has produced a judgement and an operator audit rate is set THE engine SHALL with that probability run a second judge on the same subject, on the audit executor if set, record its per-criterion agreement as an `audit_judge` record, log its cost like any judge, and never change the verdict, the route or a budget.

- GIVEN an audit rate of 1.0 WHEN a fixture run passes its gates THEN every verdict, route and counter equals the run without audit

### JDG-B8 No-change blocker escalates

WHEN every failing blocker is marked `no_change` and the criterion's `no_change_policy` is `escalate` THE engine SHALL derive ESCALATE, leave the retry budget unchanged and show the blocker in the pause payload.

- GIVEN a RETRY whose only blocker is UNMET with `no_change = true` ("the ticket names no acceptance test") WHEN the verdict is derived THEN it is ESCALATE with the budget unchanged

### JDG-B9 An upstream claim is judged on its own

WHEN a step ends with `UPSTREAM <unit>: <defect>` on a gate that has a judge THE judge node SHALL run no check and one judge session grading the single engine criterion `upstream-claim` (the defect is in that unit's output as claimed and the step could not work around it) with that unit's artifacts and values as the subject and the claim labelled as a claim; MET sending the run BACK to that unit with the claim as the visit reason inside the loop budget ([BUD](08-budgets-and-failures.spec.md)), PARTIAL or UNMET retrying the claiming step told the claim was not confirmed, and UNVERIFIABLE, a gap or an unparsed answer asking a person, as a gate with no judge does.

- GIVEN `UPSTREAM draft: <defect>` WHEN the judge finds the claim MET THEN the run goes back to `draft` with no pause

### JDG-B10 Judge node

WHEN a judged gate runs THE engine SHALL call `judge_node(unit, state) -> JudgeOutcome` with `verdict`, `judgement` or null, `blockers`, `gap`, `confidence`, `confidence_source` and `judge_executor`, and `derive(judgement, gate, check) -> Verdict`, every judge record naming its executor, alias, alias source and confidence source.

- GIVEN any judged attempt WHEN its record is read THEN it names executor, alias, alias source and confidence source

### JDG-B11 Engine brief and facts

WHEN a judge prompt is rendered THE engine SHALL open it with an engine-owned brief that names no workflow and states the reviewer's role and three fixed rules (the step's account is a claim to verify; only the tools given may be called, a call to any other tool voiding the whole review, [GRD](06-independence-guard.spec.md); each criterion is graded on its own, so what could not be confirmed for one does not lower another), then the workflow's stance and brief; and add the workspace facts (branch, base, changed files, diff stat, computed by the engine); the references (the request whole up to 32,000 chars, else head and tail around an exact marker with the omitted count, criteria in the cut part being UNVERIFIABLE, never failed, and the earlier artifacts); and the subject (the artifacts graded and the check's evidence and findings, [CHK-B14](75-check-contract-and-command-runs.spec.md), the evidence labelled as the engine's run of the deterministic check, to be taken as given and not counted as out of reach, which is how a workflow hands a read-only judge what its tools cannot fetch, such as a git log).

- GIVEN a 40,000-character request WHEN the judge prompt is rendered THEN it holds the head and tail around a marker naming the omitted count

### JDG-B12 Claims, feedback and criteria in the prompt

WHEN a judge prompt is rendered THE engine SHALL add the step's final text up to 8,000 chars labelled "claims to verify, not facts"; a person's one-time feedback and every active ruling that applies to the unit as direction that wins over a reference, each ruling adding one engine blocker that the output follows it ([RRN-B14](81-reruns-and-feedback.spec.md)); the criteria numbered with id, text, check method, severity and, for an outcome criterion, its scale and the evidence `met` needs ([OUT-B11](90-run-outcome.spec.md)), a `mechanical` criterion with the check's finding and a fixed sentence that its evidence is given, and a criterion the check found `n_a` with the check's reason; never a criterion verified by `person` or `none`, unless a gate's every criterion is such; previous blockers to re-check first while the full rubric is still graded; on a visit sent back one engine blocker "every point of the reason is addressed"; for each artifact whose read view is absent a fixed sentence telling the judge to report UNVERIFIABLE and not accept the step's word; and the answer format of the judgement block ([SSN-B8](25-session-contract.spec.md)) with the four-anchor confidence scale and an example line that is deliberately not valid JSON.

- GIVEN a gate with a `person` criterion and a `judge` criterion WHEN its judge prompt is rendered THEN only the `judge` criterion is listed

### JDG-B13 Verdict derivation

WHEN a verdict is derived THE engine SHALL treat MET without evidence as PARTIAL; a criterion not reported, or N/A without a reason (a check's `n_a` message counting as the reason), as UNMET; a blocker UNVERIFIABLE or `gap` true as an unresolved gap, ESCALATE; failing blockers that all name in `defect_in` an allowed back target (listed, and run or skipped by a route on this path) as BACK to the earliest such target; failing blockers as JDG-B8 when they all carry `no_change` under `escalate`; other failing blockers as RETRY, budget permitting; and no failing blocker as PROCEED, unmet warnings passing once to the next step as notes; ignoring a verdict the judge writes itself and only logging a mismatch; never letting confidence decide; and never yielding PROCEED on a timeout, a parse failure, a guard discard (an unresolved gap with confidence 0.0) or an infra failure.

- GIVEN a blocker UNMET whose `defect_in` names an allowed back target WHEN the verdict is derived THEN it is BACK to that target
- GIVEN a judgement discarded by the guard WHEN the verdict is derived THEN it is ESCALATE with confidence 0.0

## Acceptance criteria

- JDG-AC1 (JDG-B8, JDG-B10, JDG-B13): Every derivation rule has a test with a scripted judge answer
- JDG-AC2 (JDG-B1): A failed step, a blocked step and a failed check start no judge session
- JDG-AC3 (JDG-B2): A missing block yields exactly one re-ask, logged as its own call with kind `judge_reask`
- JDG-AC4 (JDG-B3, JDG-B4, JDG-B5, JDG-B13): No judging failure (timeout, parse failure, discard, infra) ever yields PROCEED
- JDG-AC5 (JDG-B3, JDG-B10): Every judge record names its executor, alias, alias source and confidence source
- JDG-AC6 (JDG-B6, JDG-B11, JDG-B12): No shipped judge brief contains a sentence telling the judge to accept a step's claim (scan test)
- JDG-AC7 (JDG-B7): An audit judge at any rate leaves every verdict, route and counter of a fixture run unchanged
- JDG-AC8 (JDG-B9): A confirmed upstream claim goes back with no pause, a refuted one retries the step, and an undecided one pauses (three scripted runs)
