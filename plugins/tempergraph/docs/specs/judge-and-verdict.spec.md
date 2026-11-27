# Judge and verdict

## Purpose

Every model step is graded by a fresh, read-only judge session that reports a finding per criterion; the engine, never the judge, derives the verdict by rule. A deterministic check runs first and can end the attempt with no model call, and a judging failure never passes. This spec owns OVR-B6, which prompt rendering ([PRM](prompt-rendering.spec.md)) and the independence guard ([GRD](independence-guard.spec.md)) uphold ([ADR `independent-judge-engine-verdict`](../adr/independent-judge-engine-verdict.adr.md)). Gates, budgets ([BUD](budgets-and-failures.spec.md)), pauses ([HUM](gate-and-human.spec.md)), calibration ([JCL](judge-calibration.spec.md)) and the outcome gate ([OUT](run-outcome.spec.md)) depend on it; design notes are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Depends on

- `budgets-and-failures.spec.md`: a usage limit spends no counter (BUD-B17)
- `check-contract-and-command-runs.spec.md`: what a check returns (CHK-B14)
- `contracts.spec.md`: model aliases and their resolution (CON-B3)
- `executor-interface.spec.md`: judge executor selection (EXI-B24)
- `independence-guard.spec.md`: independence guard and judge views
- `reruns-and-feedback.spec.md`: feedback (RRN-B14)
- `run-outcome.spec.md`: the scoring scale (OUT-B11)
- `session-contract.spec.md`: judgement block (SSN-B8)

## Behaviours

### JDG-B1 Check first

WHEN a step ended with a `BLOCKED:` line, failed, or its check returned FAIL THE judge node SHALL start no judge session and set the outcome from the check or the step: FAIL as RETRY, blocked as ESCALATE with confidence placeholder 1.0, source `engine_placeholder`.

- GIVEN a step whose check returned FAIL WHEN the judge node runs THEN no judge session starts and the verdict is RETRY

### JDG-B2 One re-ask

WHEN a judge answer has no parsable judgement block or a criterion id that does not match its number THE judge node SHALL run exactly one second session for the block only, logged with kind `judge_reask` and fed the last 8,000 chars of the first answer, and if it also fails record an unparsed judgement: an unresolved gap with confidence 0.0, source `engine_placeholder`.

- GIVEN two answers with no judgement block WHEN the judge node continues THEN the verdict is ESCALATE with confidence 0.0

### JDG-B3 Judge on its own executor and model

WHEN a judge resolves THE engine SHALL choose its executor by [EXI-B24](executor-interface.spec.md) and its model by the judge order ([CON-B3](contracts.spec.md)), so producer and judge may differ in both, and refuse at preflight with exit 2 a judge executor that cannot be bound, never falling back at run time.

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

WHEN a step ends with `UPSTREAM <unit>: <defect>` on a gate that has a judge THE judge node SHALL run no check and one judge session grading the single engine criterion `upstream-claim` (the defect is in that unit's output as claimed and the step could not work around it) with that unit's artifacts and values as the subject and the claim labelled as a claim; MET sending the run BACK to that unit with the claim as the visit reason inside the loop budget ([BUD](budgets-and-failures.spec.md)), PARTIAL or UNMET retrying the claiming step told the claim was not confirmed, and UNVERIFIABLE, a gap or an unparsed answer asking a person, as a gate with no judge does.

- GIVEN `UPSTREAM draft: <defect>` WHEN the judge finds the claim MET THEN the run goes back to `draft` with no pause

### JDG-B10 Judge node

WHEN a judged gate runs THE engine SHALL call `judge_node(unit, state) -> JudgeOutcome` with `verdict`, `judgement` or null, `blockers`, `gap`, `confidence`, `confidence_source` and `judge_executor`, and `derive(judgement, gate, check) -> Verdict`, every judge record naming its executor, alias, alias source and confidence source.

- GIVEN any judged attempt WHEN its record is read THEN it names executor, alias, alias source and confidence source

### JDG-B11 Engine brief and facts

WHEN a judge prompt is rendered THE engine SHALL open it with an engine-owned brief that names no workflow and states the reviewer's role and three fixed rules (the step's account is a claim to verify; only the tools given may be called, a call to any other tool voiding the whole review, [GRD](independence-guard.spec.md); each criterion is graded on its own, so what could not be confirmed for one does not lower another), then the workflow's stance and brief; and add the workspace facts (branch, base, changed files, diff stat, computed by the engine); the references (the request whole up to 32,000 chars, else head and tail around an exact marker with the omitted count, criteria in the cut part being UNVERIFIABLE, never failed, and the earlier artifacts); and the subject (the artifacts graded and the check's evidence and findings, [CHK-B14](check-contract-and-command-runs.spec.md), the evidence labelled as the engine's run of the deterministic check, to be taken as given and not counted as out of reach, which is how a workflow hands a read-only judge what its tools cannot fetch, such as a git log).

- GIVEN a 40,000-character request WHEN the judge prompt is rendered THEN it holds the head and tail around a marker naming the omitted count

### JDG-B12 Claims, feedback and criteria in the prompt

WHEN a judge prompt is rendered THE engine SHALL add the step's final text up to 8,000 chars labelled "claims to verify, not facts"; a person's one-time feedback and every active ruling that applies to the unit as direction that wins over a reference, each ruling adding one engine blocker that the output follows it ([RRN-B14](reruns-and-feedback.spec.md)); the criteria numbered with id, text, check method, severity and, for an outcome criterion, its scale and the evidence `met` needs ([OUT-B11](run-outcome.spec.md)), a `mechanical` criterion with the check's finding and a fixed sentence that its evidence is given, and a criterion the check found `n_a` with the check's reason; never a criterion verified by `person` or `none`, unless a gate's every criterion is such; previous blockers to re-check first while the full rubric is still graded; on a visit sent back one engine blocker "every point of the reason is addressed"; for each artifact whose read view is absent a fixed sentence telling the judge to report UNVERIFIABLE and not accept the step's word; and the answer format of the judgement block ([SSN-B8](session-contract.spec.md)) with the four-anchor confidence scale and an example line that is deliberately not valid JSON.

- GIVEN a gate with a `person` criterion and a `judge` criterion WHEN its judge prompt is rendered THEN only the `judge` criterion is listed

### JDG-B13 Verdict derivation

WHEN a verdict is derived THE engine SHALL treat MET without evidence as PARTIAL; a criterion not reported, or N/A without a reason (a check's `n_a` message counting as the reason), as UNMET; a blocker UNVERIFIABLE or `gap` true as an unresolved gap, ESCALATE; failing blockers that all name in `defect_in` an allowed back target (listed, and run or skipped by a route on this path) as BACK to the earliest such target; failing blockers as JDG-B8 when they all carry `no_change` under `escalate`; other failing blockers as RETRY, budget permitting; and no failing blocker as PROCEED, unmet warnings passing once to the next step as notes; ignoring a verdict the judge writes itself and only logging a mismatch; never letting confidence decide; and never yielding PROCEED on a timeout, a parse failure, a guard discard (an unresolved gap with confidence 0.0) or an infra failure.

- GIVEN a blocker UNMET whose `defect_in` names an allowed back target WHEN the verdict is derived THEN it is BACK to that target
- GIVEN a judgement discarded by the guard WHEN the verdict is derived THEN it is ESCALATE with confidence 0.0
- GIVEN a blocker graded PARTIAL with evidence WHEN the verdict is derived THEN it is RETRY, and ESCALATE when the judgement also sets `gap`

### JDG-B14 A session ended by the usage limit yields no verdict

WHEN a step session of an attempt, or the judge session grading it or a re-ask or re-read of that session (JDG-B2, JDG-B17), ends not ok with `usage_limit` true ([BUD-B17](budgets-and-failures.spec.md)), whatever its `infra_cause`, THE judge node SHALL derive no verdict from it: no judge session, re-ask or re-read starts after it, no `judgement` record is written and the gate gets an ESCALATE verdict with confidence 1.0 and source `engine_placeholder`.

- GIVEN a step session that ends not ok with `usage_limit` true WHEN the judge node runs THEN no judge session starts and the gate gets ESCALATE, not RETRY
- GIVEN a judge session, or the re-read of a marked judgement, that ends not ok with `usage_limit` true and `infra_cause` `throttled` WHEN the judge node ends THEN it is not rerun with a backoff, no `judge_reask` or `judge_reread` session starts after it and no `judgement` record is written
- GIVEN a judge answer with no parsable block and `usage_limit` false WHEN the judge node continues THEN one re-ask runs as JDG-B2 says

### JDG-B15 A judge marks a grade that rests on a place it did not open

WHEN the engine reads a judgement THE engine SHALL read a finding's `unread`, and the block's `gap_unread`, as the judge's mark that the grade, or the gap, rests on a place the judge itself did not open, count a finding's mark only on a blocker whose grade as JDG-B13 reads it is PARTIAL or UNVERIFIABLE, and read an absent or false field as not marked.

- GIVEN a judgement whose findings carry no `unread` and whose block carries no `gap_unread` WHEN it is read THEN no criterion and no gap is marked
- GIVEN a blocker graded PARTIAL with `unread` true and a `fix` that names a file and its lines WHEN the judgement is read THEN the blocker is marked
- GIVEN a blocker graded UNMET with `unread` true, and a criterion graded MET with `unread` true WHEN the judgement is read THEN neither is marked

### JDG-B16 The answer format asks for the marks

WHEN a judge prompt is rendered THE engine SHALL tell the judge in its answer format to set `unread` on a PARTIAL or UNVERIFIABLE grade, and `gap_unread` beside `gap`, when the grade or the gap rests on a place its own tools can open and it did not, to give the path and lines to open in the `fix` of the finding concerned, or in the `summary` for a gap that no finding carries, and never to mark a place out of its reach.

- GIVEN any judged gate WHEN its prompt is rendered THEN the answer format carries that instruction and every row of its template holds `unread` false

### JDG-B17 One re-read before a verdict

WHEN a judgement has a failing blocker or a `gap`, none of its failing blockers is unmarked and its `gap`, if set, is marked THE judge node SHALL run one more judge session for the attempt, logged with kind `judge_reread`, before it derives a verdict.

- GIVEN a judgement with a marked `gap` and no failing blocker WHEN the judge node continues THEN one `judge_reread` session runs before any verdict is derived
- GIVEN a judgement with a marked PARTIAL blocker and an UNMET blocker WHEN the judge node continues THEN no re-read runs and the verdict is derived from that judgement
- GIVEN a judgement with a marked PARTIAL blocker and a `gap` that is not marked WHEN the judge node continues THEN no re-read runs

### JDG-B18 The re-read is the same judge, told what to open

WHEN the judge node runs a re-read THE judge node SHALL run it on the executor, model, effort and views of the attempt's first judge session and on the same subject, with a prompt that holds the first judgement's `summary` and the `fix` of each marked criterion, tells the judge to open those places and then grade every criterion of the gate, and carries the answer format.

- GIVEN a first judgement that marks a criterion with the `fix` "open `a.py` lines 10 to 20" WHEN the re-read prompt is rendered THEN it holds that line, tells the judge to open it and to grade every criterion, and carries the answer format
- GIVEN a gate whose risk rule raised the judge's model for the attempt WHEN the re-read starts THEN it runs on the raised model with the same views

### JDG-B19 The verdict comes from the re-read alone

WHEN a re-read ends with a judgement THE judge node SHALL derive the attempt's verdict from that judgement alone as JDG-B13 says, so that no status, blocker, gap or confidence of the first judgement reaches the verdict.

- GIVEN a first judgement with a marked PARTIAL blocker and a re-read whose every blocker is MET WHEN the verdict is derived THEN it is PROCEED, with no pause, no retry of the step and no retry spent
- GIVEN a first judgement with a marked PARTIAL blocker and a re-read that grades another blocker UNMET WHEN the verdict is derived THEN it is RETRY naming that blocker alone

### JDG-B20 A judge is re-read once for an attempt

WHEN the judgement of a re-read meets the condition of JDG-B17 THE judge node SHALL start no further re-read for the attempt and derive the verdict as JDG-B13 says: an unresolved gap escalates and a failing PARTIAL blocker retries the step.

- GIVEN a re-read whose judgement marks its `gap` WHEN the verdict is derived THEN it is ESCALATE, two judge sessions ran for the attempt and no third started
- GIVEN a re-read whose judgement marks a PARTIAL blocker and sets no `gap` WHEN the verdict is derived THEN it is RETRY and two judge sessions ran for the attempt

### JDG-B21 A re-read that gives no judgement ends in an unparsed judgement

WHEN a re-read times out, is discarded by the independence guard ([GRD-B2](independence-guard.spec.md) to GRD-B4) or has no parsable block after the re-ask of JDG-B2 THE judge node SHALL derive the verdict as for an unparsed judgement, ESCALATE as an unresolved gap with confidence 0.0 and source `engine_placeholder`, never from the first judgement.

- GIVEN a re-read that times out WHEN the judge node ends THEN the verdict is ESCALATE with confidence 0.0, though the first judgement marked only a PARTIAL blocker
- GIVEN a re-read that calls a tool outside the judge's view set WHEN the judge node ends THEN its judgement is discarded and the verdict is ESCALATE with confidence 0.0
- GIVEN a re-read whose answer has no parsable block WHEN the judge node continues THEN one re-ask runs as JDG-B2 says, and a second failure gives ESCALATE with confidence 0.0

### JDG-B22 A re-read is a session of its own kind

WHEN a re-read runs THE engine SHALL record it as a session with kind `judge_reread`, with a session folder and an `agent_run` record of its own, and count its usage in the run's cost with the attempt's other sessions.

- GIVEN an attempt whose judge was re-read WHEN the run ends THEN the log holds one `agent_run` record of kind `judge_reread` with its own usage, and the run's cost includes that usage

### JDG-B23 The judgement record says that a re-read ran

WHEN a re-read has run THE engine SHALL write the attempt's `judgement` record with `reread` holding `criteria`, the ids of the criteria the first judgement marked (a criterion's number when it has no id), and `gap`, true when it marked its gap, and with the re-read's judgement in the record's other fields; an attempt with no re-read has no `reread` field.

- GIVEN a first judgement that marked criteria `a` and `b` and its gap WHEN the re-read has run THEN the `judgement` record holds `reread` with `criteria` `a` and `b` and `gap` true, and the statuses of the re-read's judgement
- GIVEN an attempt with no re-read WHEN its `judgement` record is read THEN it has no `reread` field

### JDG-B24 A re-read counts with the judge's sessions

WHEN the run report counts judges against steps, or the run detail document lists an attempt's judge sessions, THE engine SHALL include every re-ask and re-read of the judge among the judge's sessions.

- GIVEN a run with one re-read WHEN the run report is built THEN the re-read's cost is in the judges' figure and not in the steps'
- GIVEN an attempt whose judge was re-read WHEN the run detail document is built THEN the attempt's judge sessions list the judge session and the re-read, and its step sessions list neither

## Acceptance criteria

- JDG-AC1 (JDG-B8, JDG-B10, JDG-B13): Every derivation rule has a test with a scripted judge answer
- JDG-AC2 (JDG-B1): A failed step, a blocked step and a failed check start no judge session
- JDG-AC3 (JDG-B2): A missing block yields exactly one re-ask, logged as its own call with kind `judge_reask`
- JDG-AC4 (JDG-B3, JDG-B4, JDG-B5, JDG-B13): No judging failure (timeout, parse failure, discard, infra) ever yields PROCEED
- JDG-AC5 (JDG-B3, JDG-B10): Every judge record names its executor, alias, alias source and confidence source
- JDG-AC6 (JDG-B6, JDG-B11, JDG-B12): No shipped judge brief contains a sentence telling the judge to accept a step's claim (scan test)
- JDG-AC7 (JDG-B7): An audit judge at any rate leaves every verdict, route and counter of a fixture run unchanged
- JDG-AC8 (JDG-B9): A confirmed upstream claim goes back with no pause, a refuted one retries the step, and an undecided one pauses (three scripted runs)
- JDG-AC9 (JDG-B14): A fixture whose step session ends not ok with `usage_limit` true starts no judge session, a fixture whose judge session ends not ok with `usage_limit` true starts no `judge_reask` session and writes no `judgement` record, a fixture whose re-read ends not ok with `usage_limit` true writes no `judgement` record, all three give the gate an ESCALATE verdict with source `engine_placeholder`, and a fixture whose judge answers with no parsable block and `usage_limit` false gets its one re-ask
- JDG-AC10 (JDG-B15, JDG-B16): A judgement without `unread` or `gap_unread` is read as not marked and gets the verdict it gets without the fields, a mark on a blocker graded UNMET or MET marks nothing, and the prompt of every judged gate tells the judge to set the marks and to name the places to open in `fix`
- JDG-AC11 (JDG-B17): A fixture judge whose first answer marks its `gap`, and one whose first answer marks its only failing blocker, each get exactly one `judge_reread` session before any verdict is derived; a fixture with one marked and one unmarked failing blocker, and one with a marked blocker and an unmarked `gap`, get none and are derived as before
- JDG-AC12 (JDG-B18, JDG-B19): The prompt of a re-read holds the first judgement's `fix` lines for the marked criteria and the instruction to open them and grade every criterion, the re-read runs on the first session's executor, model, effort and views, and a fixture whose first answer marks its `gap` and whose second answer sets no `gap` and has no failing blocker goes on with no pause, no retry of the step and no retry spent
- JDG-AC13 (JDG-B19, JDG-B20): A fixture whose second answer grades a blocker UNMET is derived from that answer alone as RETRY, and a fixture whose second answer marks its `gap`, and one whose second answer marks a PARTIAL blocker, each run two judge sessions and no third and are derived as ESCALATE and as RETRY
- JDG-AC14 (JDG-B21): A fixture whose re-read times out, one whose re-read calls a tool outside the judge's view set and one whose re-read has no parsable block after its re-ask each give ESCALATE with confidence 0.0 and source `engine_placeholder`, never PROCEED, though the first judgement marked only a PARTIAL blocker
- JDG-AC15 (JDG-B22, JDG-B23, JDG-B24): In a fixture run with a re-read, the log holds a `judge_reread` session with an `agent_run` record of its own whose usage is in the run's cost, the attempt's `judgement` record holds `reread` with the marked criteria and an attempt with no re-read holds none, and the run report and the run detail document count the re-read with the judge's sessions
