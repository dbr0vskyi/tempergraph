# Loop summary and review retries

## Purpose

Split from [self-improvement](self-improvement.spec.md) by capability, keeping its ids: what the loop child does when a session review it ran failed on a usage limit (a retry once the limit has passed, and no wait for a limit that will not pass soon), and the one `loop_summary` record it writes when it ends, with the findings it left, the filings it made, the observations it kept and the reviews that ended failed. Operators who read `attention` and the run's detail document depend on it. How a review is planned, run and classed is not owned here: that is [session review](session-review.spec.md).

## Depends on

- `improvement-data.spec.md`: parameters with provenance (IMD-B23)
- `session-review.spec.md`: budget (SRV-B21); targets in priority order (SRV-B24); each review is paid for from what was reported (SRV-B25); a failed review names its error class (SRV-B29)

## Behaviours

### SIL-B25 A review that hit a usage limit is run again once the limit has passed

WHEN the loop child's session review has ended with reviews failed as `usage_limit` whose `resets_at` falls at most `review.retry_wait_hours` after that moment (6, provenance `default_no_data`, [IMD-B23](improvement-data.spec.md)) THE loop child SHALL run each of those reviews once more, in plan order ([SRV-B24](session-review.spec.md)) and within the money caps ([SRV-B21, SRV-B25](session-review.spec.md)), starting no earlier than the latest of those reset times and marking every record of a retry `retry` true ([the decision record](../adr/a-review-that-hit-a-usage-limit-is-run-again-once.adr.md)).

- GIVEN 16 reviews failed as `usage_limit` with `resets_at` 2 hours ahead WHEN the session review has ended THEN the child starts no retry before that instant, then runs the 16 once more in plan order, and every record of a retry has `retry` true
- GIVEN reviews failed as `usage_limit` with `resets_at` 1 hour and 2 hours ahead WHEN the session review has ended THEN every retry starts no earlier than the later instant
- GIVEN a retry that fails as `usage_limit` again WHEN it ends THEN its `review_failed` has `retry` true and the review is not run a third time
- GIVEN a retry whose estimate passes a money cap WHEN it is decided THEN it and every later retry are `review_skipped` with reason `budget` and stay failed

### SIL-B26 A usage limit that will not pass soon is not waited for

WHEN a review failed as `usage_limit` with no `resets_at` or one later than `review.retry_wait_hours` after its session review ended, or ran in the foreground (a person's `improve review`, or the loop run inline with `TEMPERGRAPH_LOOP=inline`), THE engine SHALL leave it failed and start no wait for it.

- GIVEN a review failed as `usage_limit` with `resets_at` 40 hours ahead WHEN the session review has ended THEN the child starts no wait and no retry, and its summary counts the review under `usage_limit`
- GIVEN a review failed as `usage_limit` with no `resets_at` WHEN the session review has ended THEN the child starts no wait and no retry
- GIVEN reviews failed as `usage_limit` with `resets_at` 2 hours and 40 hours ahead WHEN the session review has ended THEN the first is retried after its reset and the second stays failed
- GIVEN `improve review` run by a person whose reviews fail as `usage_limit` WHEN it ends THEN it returns at once with `review_failed` records of that class and no retry
- GIVEN `TEMPERGRAPH_LOOP=inline` and reviews failed as `usage_limit` with `resets_at` 2 hours ahead WHEN the run exits THEN the loop starts no wait and returns

### SIL-B22 The loop's summary

WHEN the loop child ends THE loop child SHALL write one `loop_summary` record to the thread's `loop.jsonl` with `recorded` (the findings the thread holds), `filed` (the issues this child opened or commented on) and `top[]`, at most three kept review observations of the thread, the highest `confidence` first and ties in plan order ([SRV-B24](session-review.spec.md)), each with `category`, `unit` and `confidence` and no note text.

- GIVEN a child that leaves 14 findings, files none and keeps five observations with confidence 0.7, 0.7, 0.55, 0.5 and 0.45 WHEN it ends THEN `loop_summary` has `recorded` 14, `filed` 0 and `top[]` of the first three, each with category, unit and confidence and none with a note
- GIVEN a child that keeps no observation WHEN it ends THEN `loop_summary` has an empty `top[]`

### SIL-B24 The summary counts the reviews that failed

WHEN the loop child ends, which is after the last retry of SIL-B25, THE loop child SHALL write in its `loop_summary` record `review_failed`, the number of reviews that ended failed counted by `error_class` ([SRV-B29](session-review.spec.md)) and empty when none did, a review having ended failed when the latest `review_done` or `review_failed` record of its reviewed session is `review_failed`, and a `review_failed` record that names no session counting as one review.

- GIVEN a child that finds nothing and whose 16 reviews all end `review_failed` as `usage_limit` WHEN it ends THEN `loop_summary` has `review_failed` with `usage_limit` 16, `recorded` as the thread holds and an empty `top[]`
- GIVEN two reviews failed as `unparsed` and one as `timed_out` WHEN the child ends THEN `review_failed` holds `unparsed` 2 and `timed_out` 1
- GIVEN a review that failed as `usage_limit` and ended `review_done` on its retry WHEN the child ends THEN `loop_summary` does not count it
- GIVEN a child whose review raised before any session ended WHEN it ends THEN `review_failed` holds `error` 1
- GIVEN a child none of whose reviews failed WHEN it ends THEN `review_failed` is empty

## Acceptance criteria

- SIL-AC14 (SIL-B22): A fixture loop child leaves one `loop_summary` record with the counts of findings recorded and filed and at most three kept observations by confidence, each with category, unit and confidence and none with note text
- SIL-AC16 (SIL-B24): A fixture loop child that finds nothing and whose reviews all end `review_failed` as `usage_limit` leaves a `loop_summary` with `review_failed` holding `usage_limit` and their number, a review that failed and then ended `review_done` on its retry is not counted, and a child with no failed review has an empty `review_failed`
- SIL-AC17 (SIL-B25, SIL-B26): A fixture loop child on a fake clock whose reviews all return `usage_limit` true with `resets_at` 2 hours ahead starts no retry before that instant, runs each review once more in plan order with `retry` true on every record of a retry, never a third time, and writes its summary after the last retry; with `resets_at` 40 hours ahead or none, from `improve review`, or inline, it starts no wait and no retry
