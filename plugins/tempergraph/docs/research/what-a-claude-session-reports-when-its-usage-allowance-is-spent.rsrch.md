# What does a `claude` session report when its usage allowance is spent, and when does it reset?

## Problem statement

The loop must tell a review that failed on a spent usage allowance from every other failed review, and run it again after the allowance resets (task t-30e1f2509b, gaps G3 and G4). Executors classify failures from structured facts only, never from prose ([EXI-B7](../specs/executor-interface.spec.md)), so the question is whether the `claude` stream carries the fact that the allowance is spent, and the time it resets, as structured fields. The engine reads none of it today, and no note records its shape.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Recorded `claude` 2.1.330 judge stream, line 10 | code | `plugins/tempergraph/engine/tests/fixtures/recorded/claude-2.1.330-judge.jsonl` |
| Recorded `claude` 2.1.330 step stream, line 10 | code | `plugins/tempergraph/engine/tests/fixtures/recorded/claude-2.1.330-step.jsonl` |
| Date of the recordings | code | `plugins/tempergraph/engine/tests/test_recorded_streams.py` line 1 |
| The `claude` line mapper and failure classifier | code | `plugins/tempergraph/engine/src/tempergraph/executors/claude.py` lines 242 to 336 |
| The reviewer call of the session review | code | `plugins/tempergraph/engine/src/tempergraph/improve/review.py` lines 612 to 614 and 662 to 687 |
| Agent SDK TypeScript reference, section `SDKRateLimitEvent` | web | https://code.claude.com/docs/en/agent-sdk/typescript |
| Type comment of the same event in a third-party proxy, `@rynfar/meridian` 1.42.1 | web | https://cdn.jsdelivr.net/npm/@rynfar/meridian@1.42.1/dist/proxy/rateLimitStore.d.ts |
| The overnight run whose reviews all failed | research | `plugins/tempergraph/docs/research/does-the-improvement-loop-find-what-a-reviewer-finds.rsrch.md` F7 |
| Claude Code's own wait on a usage limit | research | `plugins/tempergraph/docs/research/dynamic-workflows-as-orchestration-model.rsrch.md` D13 |

## Key findings

### F1 The stream carries rate limit reports that the engine does not read `confirmed`

Both recorded streams hold, at line 10, a message of type `rate_limit_event` whose `rate_limit_info` has `status` `allowed`, `rateLimitType` `five_hour`, `resetsAt` 1795317000, `overageStatus` `rejected` and `unifiedWindows` with one entry per window (`five_hour` and `seven_day`), each with its own `resetsAt`, `status` and `utilization`. `parse_line` in `claude.py` has a branch for `system` `init`, `api_retry` and `permission_denied`, for `assistant`, `user`, `stream_event` and `result`, and none for this type, so it maps to no event. A search of the engine source for `rate_limit_event`, `rate_limit_info` and `resetsAt` finds nothing.

### F2 The reference documents the fields a spent allowance would use `supported`

The Agent SDK TypeScript reference describes `SDKRateLimitEvent` as "Emitted when the session encounters a rate limit", with `rate_limit_info.status` one of `allowed`, `allowed_warning` and `rejected`, an optional `resetsAt`, an optional `utilization` and an optional `errorCode` of `credits_required`. Of that code it says the rejection is from a claude.ai subscription whose included usage is exhausted and that the session cannot continue until the user buys usage credits; it names Claude Code 2.1.181 as the first version with that code and the two fields that go with it. The recorded streams are from 2.1.330. The third-party declaration lists the same three status values.

### F3 A rejected status means the request was refused for the limit `inferred`

The reference lists `rejected` as a value and defines it nowhere. That it marks a refusal for the limit follows from its name, from the `credits_required` paragraph and from the event being emitted when a session "encounters a rate limit". No source states it outright.

### F4 The recorded `resetsAt` is an epoch in seconds, and a third-party comment says milliseconds `supported`

1795317000 read as seconds is 2026-11-22T03:10:00Z, the day the streams were recorded (2026-11-22, the docstring of `test_recorded_streams.py`); the `seven_day` window of the same event, 1795431600, is 2026-11-23T11:00:00Z. Read as milliseconds the value falls in January 1970. The reference gives no unit for `resetsAt` (it names milliseconds only for `end_time` of a task update), and the third-party declaration comments it "epoch ms".

### F5 No recorded stream holds a rejection `confirmed`

Both recorded events have status `allowed`, and the `allowed` event carries the same fields a rejection would. The shape of a rejected event, and of the `result` that follows it, is therefore read from the reference only.

### F6 Today no class of a failed session names a spent allowance `confirmed`

`classify` gives a stream with an error `result` the class `model` and a stream with no `result` whose last retry category is `rate_limit` or `overloaded` the class `throttled` (`claude.py` lines 313 to 336). In the review, `_ask` re-asks any reviewer session that is not ok once and then returns no block, and `run` writes `review_failed` with the session key and the cost only (`review.py` lines 612 to 614 and 667 to 687). research `does-the-improvement-loop-find-what-a-reviewer-finds` F7 matches: 32 reviewer sessions for 16 targets, all at cost 0, a summary that read `18 recorded, 0 filed`, and nothing that said the reviews had failed.

### F7 Claude Code bounds its own wait for a reset `supported`

research `dynamic-workflows-as-orchestration-model` D13 reads the vendor's documents as: on a usage limit a run pauses and continues by itself after the reset, under narrow conditions (an interactive subscription session, a reset within 24 hours, at most two waits).

## Conclusions

1. The `claude` executor can learn that a session was refused for the allowance, and when it resets, from two structured fields of one stream message, with no reading of prose (F1, F2, F3).
2. A rejection with `errorCode` `credits_required` has no reset to wait for (F2).
3. `resetsAt` is read as epoch seconds until a recorded rejection says otherwise (F4, F5).
4. No existing class can name a spent allowance, so a failed review cannot say why it failed without a new result field (F6).
5. A bounded wait with a limited number of retries is the pattern Claude Code itself follows (F7).

## Open questions

- What a rejected `rate_limit_event`, and the `result` after it, hold in a real stream: no recording exists (F5). The first recorded rejection settles the unit, whether `resetsAt` is present and whether the final `result` is an error.
- Whether the top-level `resetsAt` of a rejection is the reset of the window that rejected (`rateLimitType`) or the earliest of the windows. In the recorded `allowed` event the two agree for `five_hour`.
- Where the text `usage_limit_reached` of research `does-the-improvement-loop-find-what-a-reviewer-finds` F7 came from, the CLI's result text or the API's error body. The engine reads no text, so the design does not depend on it.
