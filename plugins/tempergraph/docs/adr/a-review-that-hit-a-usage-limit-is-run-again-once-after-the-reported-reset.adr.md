# A review that hit a usage limit is run again once, after the reset its executor reported, within a bound

## Context

[R-160](../research/R-160-does-the-improvement-loop-find-what-a-reviewer-finds.rsrch.md) F7 records an overnight run in which every review failed: 16 targets, 32 reviewer sessions at cost 0, all ended by a usage limit, and a `loop_summary` that read `18 recorded, 0 filed`. A loop that had read nothing looked like a loop that had found nothing. The task asks that the summary and `attention` say so, and that a review that failed on a usage limit run again once the limit has passed, before the loop is called done.

What the code does today. `_ask` in `plugins/tempergraph/engine/src/tempergraph/improve/review.py` re-asks every reviewer session that is not ok once, so a spent allowance costs two sessions per target, and `run` then writes a `review_failed` record with the session key and the cost and no cause. The loop child (`improve/child.py`) writes its `loop_summary` after the review, the proposal and the trial. It claims a ticket by renaming it and holds it until it ends; `drain` handles the tickets of its list one after another. Nothing limits the number of children: every final exit that writes a ticket starts its own through `detach.start`, which has no single-instance guard. A wait therefore holds one claimed ticket and one detached process, and the tickets of other runs go to the children those runs started. With `TEMPERGRAPH_LOOP=inline` the same code runs inside the exit of the run that started it (`plugins/tempergraph/engine/src/tempergraph/run/runner.py`), where a wait would hold the run's own process.

What the executors tell it. A failed session is classified from structured facts only ([EXI-B7](../specs/10-executor-interface.spec.md)). [ECC-B12](../specs/11-executor-claude-code.spec.md) gives an error `result` the class `model` and a stream that ends without `result` after a rate limit retry the class `throttled`; neither says that an allowance is spent. The `claude` stream carries a `rate_limit_event` with a status and a reset instant that the engine does not read, and a rejection is documented but not recorded ([the research note](../research/what-a-claude-session-reports-when-its-usage-allowance-is-spent.rsrch.md)).

Whether a step or judge session of a run should also wait for a reset is a different question. The open question of [BUD](../specs/08-budgets-and-failures.spec.md) on a `throttled` session keeps the standard backoff for runs until it is measured, and this record leaves it alone.

## Decision

We will let an executor report a spent usage allowance, and the instant it resets, as two fields of the session result, end a review on it at once with its error class, and have the loop child run each review that failed that way once more, no earlier than the latest reported reset, when the reset is at most six hours ahead (the parameter `review.retry_wait_hours`). The child writes its summary after that retry. A review whose reset is unknown or further ahead, and any review that ran in the foreground, stays failed and starts no wait, and the summary and `attention` show it. The behaviours are [SSN-B11](../specs/25-session-contract.spec.md), [ECC-B17](../specs/11-executor-claude-code.spec.md), [SRV-B29 and SRV-B30](../specs/44-session-review.spec.md), [SIL-B24, SIL-B25 and SIL-B26](../specs/16-self-improvement.spec.md) and [CLI-B20](../specs/17-engine-cli.spec.md).

## Options considered

### A. Wait in the loop child for the reported reset, within a bound, and retry once (chosen)

For: it is what the task asks. The retry starts when the allowance has come back, a fact the stream reports, so the one retry is likely to succeed. A sleeping process costs no tokens, and reviews lost to a five-hour allowance are read before the loop is called done. Against: the child and its claimed ticket are held for up to the bound; a machine that sleeps or restarts in that time ends the child, as it would any crashed child; the reset rests on one stream message.

### B. Report the failure and never retry

For: nothing waits, and no executor change goes beyond the class. Against: the task's third criterion asks for the retry. A person learns of the failure only by reading `attention`, and must rerun `improve review` by hand after the window. The loop is called done with nothing read.

### C. Retry after a fixed delay, whatever the reset

For: no new field on the result. Against: it is a guess. With a five-hour window a short delay spends the one retry on a limit that has not passed, and a delay long enough for every window is paid by every transient limit. The reset cannot be taken from the message text ([EXI-B7](../specs/10-executor-interface.spec.md)).

### D. Wait for the reset without a bound

For: the simplest rule, and every such review is retried. Against: a weekly allowance can be days away, and the child, its claimed ticket and the loop's summary would be held that long. Claude Code itself limits its own wait ([R-035](../research/R-035-dynamic-workflows-as-orchestration-model.rsrch.md) D13).

### E. Leave a retry for a later ticket

For: no sleeping process. Against: the loop writes its summary first and is called done with its reviews unread. It also needs a new kind of ticket and a start at the reset time, and nothing starts a child then.

## Consequences

- A loop that read nothing says so in its summary and in `attention`, with the class that stopped it. Reviews lost to a five-hour allowance are read when it resets, within the bound, and nothing is retried more than once.
- The bound is a parameter with provenance `default_no_data` ([IMD-B23](../specs/43-improvement-data.spec.md)). Six hours covers the five-hour window and leaves out a weekly one. A wait costs one idle detached process per ticket, for six hours at most.
- A retry is paid like any review, under the money caps ([SRV-B21 and SRV-B25](../specs/44-session-review.spec.md)). A review that failed on the allowance cost nothing, so the caps see the same figures as before.
- A foreground run never waits. `improve review` and an inline loop return at once, and a person reruns the review after the reset ([SRV-B23](../specs/44-session-review.spec.md)).
- Risk: the reset instant is read as epoch seconds from the documents and from two recordings of an `allowed` event, none of a rejection. Limit: a value that is really milliseconds reads as a reset far ahead, so nothing waits and nothing is retried, and the failure stays visible; a reset read as already past would start the retry at once, which fails again as `usage_limit` and is not repeated. The open question of ECC names what settles it.
- Risk: the one retry is spent if the allowance has not returned at the reported instant (a clock that differs, a window that rolled). Limit: it is one retry, the failure stays in the summary, and a person can rerun the review.
- `usage_limit` is an addition to the result of every executor, false and null where an executor reports nothing. Gates, ladders and ledgers do not read it, so the counters of BUD and the classes of ECC-B12 stay as they are.

## Revisit when

A rejected `rate_limit_event` has been recorded (its unit, its `resetsAt` and the `result` that follows), or the first overnight loops that waited show how long resets take and how often the retry succeeds.
