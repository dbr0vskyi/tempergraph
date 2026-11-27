# Friction causes from run records

## Purpose

Which records of a run make which friction cause, with its class, side and fixed remedy, for five causes: a trip back, a stop at the attempt cap, a last stage that delivered nothing, a session the usage limit refused and a pause at an ask unit; which records give the finding of a pause that an agent decides its class ([the decision record](../adr/a-decision-by-the-caller-that-started-a-run-is-designed.adr.md) holds why the caller that started the run is told apart); and which records of a decision that answered a pause make five more causes, of class `fault` whoever decided: an override of a gate, a confirmed upstream claim, a retry that passed unchanged, a retry that paused again and a resume that made no progress. Class and side are those of [SIL-B11](self-improvement.spec.md), and a cause is made with no model call from names and numbers of the run's records. How a finding is judged and filed, and the causes of [SIL-B12 to SIL-B15](self-improvement.spec.md), stay with [self-improvement](self-improvement.spec.md) and [friction-filing-decisions](friction-filing-decisions.spec.md); the causes read from session digests stay with [session-review](session-review.spec.md). Workflow owners, the engine's maintainers and the friction judge depend on it.

## Depends on

- `caller-provenance.spec.md`: the caller block (PRV-B16); where the block is written (PRV-B17)
- `compiler-and-flow.spec.md`: attempt cap in nodes (CMP-B5); back-edges (CMP-B12)
- `engine-cli.spec.md`: the operator reason of a decision (CLI-B24)
- `finalizer-contract.spec.md`: what it returns (FIN-B8)
- `gate-and-human.spec.md`: waits, asks and breakpoints (HUM-B10); what a decision answered (HUM-B19)
- `judge-and-verdict.spec.md`: an upstream claim (JDG-B9)
- `runs-without-a-final-exit.spec.md`: the next gate is the paused unit's own (SIL-B41)
- `self-improvement.spec.md`: agent rescues and supervision (SIL-B15)
- `session-contract.spec.md`: a spent usage allowance (SSN-B11)
- `supervision-metrics.spec.md`: touches (SUP-B9)
- `worktree-mode.spec.md`: what a resume compares (WTR-B28)

## Does not own

- How these findings file and what the records of that decision hold: `friction-filing-decisions.spec.md`
- What an issue for these findings shows: `loop-issues.spec.md`

## Behaviours

### FRC-B1 A trip back is a finding of the gate that sent the run back

WHEN a gate whose verdict is `BACK` routes the run back ([CMP-B12](compiler-and-flow.spec.md)) THE loop SHALL make a finding on that gate's unit with cause `trip_back:<unit>`, the unit the run went to, class `fault`, side `workflow`, a fixed remedy that names a gate criterion or a check, and a count of the sessions started in the visits that the trip back began, up to the next trip back or the end of the invocation.

- GIVEN units `a` and `b`, each with one step session and one judge session, and the gate of `b` routing `BACK` to `a` once WHEN the run then passes both gates THEN the findings of `b` hold `trip_back:a` with count 4
- GIVEN the same units and a unit `c` after `b` that had not run before the trip back WHEN the run then passes `c` as well THEN the count of `trip_back:a` is still 4
- GIVEN the same units and an attempt cap that stops the invocation before any session starts after the trip back WHEN it exits THEN the findings of `b` hold `trip_back:a` with count 0

### FRC-B2 A stop at the attempt cap is a finding that counts the trips back

WHEN an invocation exits with code 4 and reason `attempt_cap` ([CMP-B5](compiler-and-flow.spec.md)) THE loop SHALL make a finding that names no unit with cause `attempt_cap`, class `fault`, side `workflow`, a fixed remedy that names a gate criterion, a check or the run's attempt cap, and a count of the trips back the invocation held, 0 when it held none.

- GIVEN a gate whose verdict is `BACK` twice, each time routing the run back, and an attempt cap that stops the invocation after the second trip back WHEN it exits THEN the findings hold `attempt_cap`, naming no unit, with count 2
- GIVEN a unit retried until the attempt cap stops the invocation, and no gate routing `BACK` WHEN it exits THEN the findings hold `attempt_cap` with count 0
- GIVEN a run that finishes before it reaches the attempt cap WHEN it exits THEN no finding has cause `attempt_cap`

### FRC-B3 A last stage that delivered nothing is a finding

WHEN a run exits 0 and the finalizer's recorded result has at least one manual step, or the outcome `skipped`, `error` or `invalid` ([FIN-B8](finalizer-contract.spec.md)), THE loop SHALL make a finding that names no unit with cause `finalizer_undelivered:<outcome>`, the finalizer's outcome, class `fault`, side `workflow` and a fixed remedy that names the finalizer or its environment.

- GIVEN a finalizer that returns `skipped` with two manual steps WHEN the run exits 0 THEN the findings hold `finalizer_undelivered:skipped` with count 1 and no word of the steps or of the reason
- GIVEN a finalizer that raises WHEN the run exits 0 THEN the findings hold `finalizer_undelivered:error`
- GIVEN a finalizer that publishes and returns no manual step WHEN the run exits 0 THEN no finding has cause `finalizer_undelivered`

### FRC-B4 A session the usage limit refused is the host's

WHEN a session of a run ends with `usage_limit` true ([SSN-B11](session-contract.spec.md)) THE loop SHALL make a finding on the session's unit with cause `usage_limit`, class `infra`, side `host`, a fixed remedy that proposes no change and a count of such sessions, and no other cause from the run-log records of those sessions or of the pause that follows them.

- GIVEN a step session that ends with `usage_limit` true, and the pause that follows WHEN the invocation exits THEN the findings of its unit hold `usage_limit` with count 1, no `retries_spent` and no other cause from that session or its pause
- GIVEN a judge session that ends with `usage_limit` true WHEN the invocation exits THEN the findings of the judged unit hold `usage_limit` with count 1
- GIVEN a session that ends not ok with `usage_limit` false and spends the retry budget WHEN the run exits THEN the findings hold `retries_spent` and no `usage_limit`

### FRC-B5 A pause at an ask unit is designed

WHEN a run pauses at an ask unit to take a person's input ([HUM-B10](gate-and-human.spec.md)) THE loop SHALL make a finding on that unit with cause `input`, class `designed`, side `workflow` and a fixed remedy that proposes no change, and no other cause from that pause.

- GIVEN an ask unit that pauses the run for answers WHEN the invocation exits 3 THEN the findings of that unit hold `input` of class `designed` and none of class `fault`
- GIVEN dev mode and a thread whose only pause was an ask unit's, answered, and that then finished WHEN its final exit is recorded THEN the friction lens does not fire

### FRC-B6 A pause that the caller that started the run decides is designed

WHEN the loop makes the finding `agent_decided:<pause cause>` for a pause that an agent decides with a `rescue` touch (SIL-B15, SUP-B9) THE loop SHALL give it class `designed` when the caller recorded with the decision has the same `host` and the same recorded `host_session` as the caller recorded when the run started ([PRV-B16, PRV-B17](caller-provenance.spec.md)), and class `fault` otherwise.

- GIVEN a run started by an agent session that answers its own escalation with `proceed` WHEN the resumed run exits THEN the findings of the paused unit hold `agent_decided:escalation` of class `designed` and none of class `fault` with that cause
- GIVEN that run whose escalation an agent of another host session answers WHEN the resumed run exits THEN the findings of the paused unit hold `agent_decided:escalation` of class `fault`
- GIVEN a run started and answered by agents whose caller blocks record no host session WHEN the resumed run exits THEN the finding is of class `fault`

### FRC-B7 A `proceed` over a failed check, a gap or a spent budget is a finding of what it overrode

WHEN a segment that a decision `proceed` at a pause started exits THE loop SHALL make a finding on the paused unit with cause `answer_overrode:<kind>`, the first `<kind>` that fits being `check` (the decision's answered facts, [HUM-B19](gate-and-human.spec.md), show a FAIL check that is not environmental), `environment` (a FAIL check that is), `gap` (the gap flag, or the pause reason `unresolved_gap`) or `budget` (the pause kind `budget`), and no finding otherwise.

- GIVEN a unit whose last check result was a FAIL that is not environmental and a pause there answered `proceed` WHEN the resumed segment exits THEN the findings of the unit hold `answer_overrode:check` with count 1
- GIVEN a pause of kind `budget` whose last check result was such a FAIL, answered `proceed` WHEN the resumed segment exits THEN the findings of the unit hold `answer_overrode:check` and no `answer_overrode:budget`
- GIVEN a pause for an unresolved gap answered `retry` WHEN the resumed segment exits THEN no finding has cause `answer_overrode`

### FRC-B8 One finding for a unit and kind says what was overridden

WHEN decisions of one segment make the same `answer_overrode` kind at one unit THE loop SHALL make one finding for them with `count` the number of the decisions, `criteria` each criterion id that their answered facts name as failed or as a blocker with the number of decisions that name it, and `items` the number of distinct items they answered.

- GIVEN one `proceed` over a FAIL check of the criteria `a` and `b` WHEN the segment exits THEN the finding holds count 1, `criteria` with `a` 1 and `b` 1, and `items` 0
- GIVEN a `proceed` at the item `i2` of a map's unit WHEN the segment exits THEN the finding's `items` is 1
- GIVEN `proceed` decisions at one gate in two segments, over a failing criterion `a` in the first and `b` in the second WHEN the thread's findings are read THEN the two findings have one fingerprint

### FRC-B9 A `back` that confirms an upstream claim is a finding on the claimed unit

WHEN a segment that a decision `back:<unit>` at a pause started exits, and the answered facts of the decision ([HUM-B19](gate-and-human.spec.md)) hold the `claim` of an upstream claim ([JDG-B9](judge-and-verdict.spec.md)) that names that unit, THE loop SHALL make a finding on that unit with cause `upstream_confirmed:<unit>` and the paused unit as `from_unit`.

- GIVEN a pause at unit `b` whose last judgement claimed unit `a`, answered `back:a` WHEN the resumed segment exits THEN the findings of `a` hold `upstream_confirmed:a` with `from_unit` `b`
- GIVEN that pause answered `back:c`, an earlier unit it did not claim, WHEN the resumed segment exits THEN no finding has cause `upstream_confirmed`
- GIVEN a pause whose last judgement holds no claim, answered `back:a`, WHEN the resumed segment exits THEN no finding has cause `upstream_confirmed`

### FRC-B10 A retry that passes with nothing changed is a finding of the gate

WHEN a segment that a decision `retry` at a pause started exits, the workspace is recorded unchanged between the pause and the resume ([WTR-B28](worktree-mode.spec.md)) and the next gate of the paused unit and item ([SIL-B41](runs-without-a-final-exit.spec.md)) gave PROCEED, THE loop SHALL make a finding on the paused unit with cause `retry_passed_unchanged:<pause reason>`.

- GIVEN a unit paused with reason `blocked` in its worktree and resumed with `retry`, nothing having changed in the worktree between, and whose next gate gives PROCEED WHEN the segment exits THEN the findings of the unit hold `retry_passed_unchanged:blocked`
- GIVEN the same pause and a person who committed a change in the worktree before the resume WHEN the segment exits THEN no finding has cause `retry_passed_unchanged`
- GIVEN a thread that runs in place, so that no workspace is compared, and a retry that passes WHEN the segment exits THEN no finding has cause `retry_passed_unchanged`

### FRC-B11 A retry followed by the same pause is a finding

WHEN a segment that a decision `retry` at a pause started exits with a pause at the unit and item the decision answered, before any gate of that unit and item gave PROCEED, THE loop SHALL make a finding on that unit with cause `retry_same_failure`, counting each such decision once.

- GIVEN a unit paused with its retries spent and resumed with `retry`, whose segment ends in a pause at the same unit WHEN it exits THEN the findings of the unit hold `retry_same_failure` with count 1
- GIVEN a retry after which the same unit pauses again with another reason WHEN the segment exits THEN the findings of the unit hold `retry_same_failure` with count 1
- GIVEN a retry after which the unit's gate gave PROCEED and a later unit paused WHEN the segment exits THEN no finding has cause `retry_same_failure`

### FRC-B12 A resume that goes nowhere is a finding of the engine

WHEN a segment that a decision other than `stop` at a pause started runs no step (no session starts and no script runs) and ends with exit code 4, or with a pause at the unit, item and reason the decision answered, THE loop SHALL make a finding on the paused unit with cause `resume_no_progress`, counting each such segment once.

- GIVEN a thread paused at unit `a` and resumed with `proceed`, whose segment starts no session and exits with code 4 WHEN it exits THEN the findings of `a` hold `resume_no_progress` with count 1
- GIVEN a thread paused at unit `a` with reason `blocked` and resumed with `retry`, whose segment starts no session and pauses again at `a` with reason `blocked` WHEN it exits THEN the findings of `a` hold `resume_no_progress` with count 1
- GIVEN a thread resumed with `stop` WHEN its segment exits with code 4 THEN no finding has cause `resume_no_progress`

### FRC-B13 A finding says what its decisions gave

WHEN the loop makes a finding of FRC-B7 to FRC-B12 THE loop SHALL give it `decisions`, the number of its decisions by decision word, `reasons`, their number by operator reason ([CLI-B24](engine-cli.spec.md)) with `not given` for a decision that gave none, and `wait_s_median`, the median of the seconds their pauses waited (the mean of the two middle values for an even number), null when none recorded one.

- GIVEN a finding of three `proceed` decisions with the operator reasons `plan`, `plan` and none, whose pauses waited 60, 100 and 400 seconds WHEN it is made THEN `decisions` is `proceed` 3, `reasons` is `plan` 2 and `not given` 1, and `wait_s_median` is 100
- GIVEN a finding of two decisions whose pauses waited 60 and 100 seconds WHEN it is made THEN `wait_s_median` is 80
- GIVEN a finding whose decisions recorded no wait WHEN it is made THEN `wait_s_median` is null

### FRC-B14 These causes are faults whoever decided

WHEN the loop makes a finding of FRC-B7 to FRC-B12 THE loop SHALL give it class `fault`, whoever decided (a person or an agent, the caller that started the run or another), side `workflow` (`engine` for `resume_no_progress`) and a fixed remedy that names a check or a gate criterion (the engine's resume for `resume_no_progress`).

- GIVEN a run started by an agent session that answers its own escalation over a FAIL check with `proceed` WHEN the segment exits THEN the findings of the paused unit hold `agent_decided:escalation` of class `designed` and `answer_overrode:check` of class `fault`, in one findings document
- GIVEN the same pause answered with `proceed` by a person WHEN the segment exits THEN `answer_overrode:check` is of class `fault`
- GIVEN a resumed segment that starts no session and exits with code 4 WHEN it exits THEN `resume_no_progress` is of class `fault` and side `engine`

### FRC-B15 A fact the decision's row lacks makes no finding

WHEN the ledger row of a decision lacks a fact that a cause of FRC-B7 to FRC-B12 needs, or holds it as `not recorded`, THE loop SHALL make no finding of that cause from the decision and fail nothing.

- GIVEN the row of a `proceed` over a FAIL check that holds no `answered` WHEN the segment exits THEN no finding has cause `answer_overrode` and the segment's other findings are made
- GIVEN the row of a `retry` that holds no `item`, followed by a pause at the same unit WHEN the segment exits THEN no finding has cause `retry_same_failure`

## Acceptance criteria

- FRC-AC1 (FRC-B1): A fixture run of two units, each with one step session and one judge session, whose second gate routes `BACK` to the first once leaves a finding on the second unit with cause `trip_back:<first unit>`, count 4, class `fault`, side `workflow` and a remedy that names a gate criterion or a check and neither a prompt nor a step; a third unit after them that had not run before the trip back leaves the count at 4, and an attempt cap that stops the invocation after the trip back leaves it at 0
- FRC-AC2 (FRC-B2): A fixture run that reaches its attempt cap after two trips back exits 4 with a finding of cause `attempt_cap` that names no unit, with count 2, class `fault`, side `workflow` and a remedy that names a gate criterion, a check or the attempt cap and neither a prompt nor a step; a fixture run that reaches the cap with no trip back leaves count 0, and one that finishes under the cap leaves no such finding
- FRC-AC3 (FRC-B3): Fixture runs whose finalizer returns `skipped` with manual steps, returns a declared outcome with one manual step, raises, and publishes with no manual step leave `finalizer_undelivered:skipped`, `finalizer_undelivered:` followed by that outcome, `finalizer_undelivered:error` and no such finding, each finding of class `fault` and side `workflow` with a remedy that names the finalizer or its environment and neither a prompt nor a step, and none holding a word of a step or of a reason
- FRC-AC4 (FRC-B4): A fixture run whose step session ends with `usage_limit` true leaves on its unit one finding `usage_limit` of class `infra` and side `host` with a remedy that proposes no change and no other cause from that session, a judge session that ends so leaves the same on the judged unit, and a session that ends not ok with `usage_limit` false and spends the retry budget leaves `retries_spent` and no `usage_limit`
- FRC-AC5 (FRC-B5): A fixture run that pauses at an ask unit leaves a finding `input` of class `designed` on that unit with a remedy that proposes no change and none of class `fault`, and a thread whose only pause was that one and that then finished does not fire the friction lens in dev mode
- FRC-AC6 (FRC-B6): A fixture run started by an agent session and answered at its escalation by that same session leaves on the paused unit a finding `agent_decided:escalation` of class `designed` that the friction judge's prompt does not list and that files nothing, the same run answered from another host session leaves the finding with class `fault`, and a run whose caller blocks record no host session leaves it with class `fault`
- FRC-AC7 (FRC-B7): Fixture runs whose paused unit holds a FAIL check that is not environmental, a FAIL check that is, a judgement with the gap flag and a spent budget, each answered `proceed`, leave on the unit `answer_overrode:check`, `answer_overrode:environment`, `answer_overrode:gap` and `answer_overrode:budget`; a budget pause whose last check is such a FAIL leaves `answer_overrode:check` and no `answer_overrode:budget`; and the same pauses answered `retry` leave none
- FRC-AC8 (FRC-B8): A fixture `proceed` over a FAIL check of two criteria leaves one finding with count 1 and `criteria` naming each once; one at the item of a map leaves `items` 1 and one at a unit with no items leaves 0; and two such decisions over two criteria of one gate in two segments leave findings of one fingerprint
- FRC-AC9 (FRC-B9): A fixture pause at a unit whose last judgement claimed an earlier unit, answered `back:` to that unit, leaves on that unit `upstream_confirmed:<unit>` with the paused unit in `from_unit`; answered `back:` to another unit, answered `proceed`, or with a judgement that holds no claim, it leaves none
- FRC-AC10 (FRC-B10): A fixture worktree run paused at a unit, resumed with `retry` with nothing changed and passing its next gate leaves `retry_passed_unchanged:<pause reason>` on the unit; the same run with a change committed between the pause and the resume, a run in place, and a retry whose next gate does not give PROCEED leave none
- FRC-AC11 (FRC-B11): A fixture unit that pauses, is resumed with `retry` and pauses again at the same unit and item leaves `retry_same_failure` with count 1, also when the second pause has another reason; three such retries one after another leave three findings of count 1; a retry whose gate passes leaves none
- FRC-AC12 (FRC-B12): A fixture thread resumed with `proceed` whose segment starts no session and exits 4, and one resumed with `retry` whose segment starts no session and pauses again at the same unit, item and reason, each leave `resume_no_progress` with count 1; a thread resumed with `stop`, and a resumed segment that starts a session, leave none
- FRC-AC13 (FRC-B13): A fixture finding made of decisions with known words, operator reasons and waits holds `decisions`, `reasons` with `not given` for a decision that gave none, and `wait_s_median` equal to the middle wait of an odd number of waits, to the mean of the two middle waits of an even number, and null when none was recorded
- FRC-AC14 (FRC-B14): A fixture run started by an agent session and answered by that session at its escalation over a FAIL check leaves in one findings document `agent_decided:escalation` of class `designed` and `answer_overrode:check` of class `fault`; the same pause answered by a person leaves `answer_overrode:check` of class `fault`; a fixture segment that starts no session leaves `resume_no_progress` of class `fault` and side `engine`; each remedy names a check or a gate criterion (the engine's resume for `resume_no_progress`) and neither a prompt nor a step
- FRC-AC15 (FRC-B15): A fixture ledger row with no `answered` over a failed check, a row with no `item` followed by a pause at the same unit, and a row whose `answered` holds `not recorded` for the fact a cause needs each leave no finding of that cause, and the segment's other findings are made
