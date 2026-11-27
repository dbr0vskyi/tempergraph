# Friction causes from run records

## Purpose

Which records of a run make which friction cause, with its class, side and fixed remedy, for five causes: a trip back, a stop at the attempt cap, a last stage that delivered nothing, a session the usage limit refused and a pause at an ask unit; and which records give the finding of a pause that an agent decides its class ([the decision record](../adr/a-decision-by-the-caller-that-started-a-run-is-designed.adr.md) holds why the caller that started the run is told apart). Class and side are those of [SIL-B11](self-improvement.spec.md), and a cause is made with no model call from names and numbers of the run's records. How a finding is judged and filed, and the causes of [SIL-B12 to SIL-B15](self-improvement.spec.md), stay with [self-improvement](self-improvement.spec.md); the causes read from session digests stay with [session-review](session-review.spec.md). Workflow owners, the engine's maintainers and the friction judge depend on it.

## Depends on

- `caller-provenance.spec.md`: the caller block (PRV-B16); where the block is written (PRV-B17)
- `compiler-and-flow.spec.md`: attempt cap in nodes (CMP-B5); back-edges (CMP-B12)
- `finalizer-contract.spec.md`: what it returns (FIN-B8)
- `gate-and-human.spec.md`: waits, asks and breakpoints (HUM-B10)
- `self-improvement.spec.md`: agent rescues and supervision (SIL-B15)
- `session-contract.spec.md`: a spent usage allowance (SSN-B11)
- `supervision-metrics.spec.md`: touches (SUP-B9)

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

## Acceptance criteria

- FRC-AC1 (FRC-B1): A fixture run of two units, each with one step session and one judge session, whose second gate routes `BACK` to the first once leaves a finding on the second unit with cause `trip_back:<first unit>`, count 4, class `fault`, side `workflow` and a remedy that names a gate criterion or a check and neither a prompt nor a step; a third unit after them that had not run before the trip back leaves the count at 4, and an attempt cap that stops the invocation after the trip back leaves it at 0
- FRC-AC2 (FRC-B2): A fixture run that reaches its attempt cap after two trips back exits 4 with a finding of cause `attempt_cap` that names no unit, with count 2, class `fault`, side `workflow` and a remedy that names a gate criterion, a check or the attempt cap and neither a prompt nor a step; a fixture run that reaches the cap with no trip back leaves count 0, and one that finishes under the cap leaves no such finding
- FRC-AC3 (FRC-B3): Fixture runs whose finalizer returns `skipped` with manual steps, returns a declared outcome with one manual step, raises, and publishes with no manual step leave `finalizer_undelivered:skipped`, `finalizer_undelivered:` followed by that outcome, `finalizer_undelivered:error` and no such finding, each finding of class `fault` and side `workflow` with a remedy that names the finalizer or its environment and neither a prompt nor a step, and none holding a word of a step or of a reason
- FRC-AC4 (FRC-B4): A fixture run whose step session ends with `usage_limit` true leaves on its unit one finding `usage_limit` of class `infra` and side `host` with a remedy that proposes no change and no other cause from that session, a judge session that ends so leaves the same on the judged unit, and a session that ends not ok with `usage_limit` false and spends the retry budget leaves `retries_spent` and no `usage_limit`
- FRC-AC5 (FRC-B5): A fixture run that pauses at an ask unit leaves a finding `input` of class `designed` on that unit with a remedy that proposes no change and none of class `fault`, and a thread whose only pause was that one and that then finished does not fire the friction lens in dev mode
- FRC-AC6 (FRC-B6): A fixture run started by an agent session and answered at its escalation by that same session leaves on the paused unit a finding `agent_decided:escalation` of class `designed` that the friction judge's prompt does not list and that files nothing, the same run answered from another host session leaves the finding with class `fault`, and a run whose caller blocks record no host session leaves it with class `fault`
