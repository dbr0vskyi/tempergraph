# A thread that ends without a final exit is handed to the loop when it is found

## Context

The loop starts at a final exit, an exit that is not a pause ([SIL-B1, SIL-B9](../specs/self-improvement.spec.md)). The run's own exit path writes the exit's records and the hand-off ticket, in `plugins/tempergraph/engine/src/tempergraph/run/runner.py` (lines 445 to 538). [research `does-the-improvement-loop-find-what-a-reviewer-finds`](../research/does-the-improvement-loop-find-what-a-reviewer-finds.rsrch.md) F7 found that four of eleven overnight runs had no loop, "left paused at a gate, or the runner was killed after a timeout", and that those four held most of the defects found by hand.

Three ends have no working loop today, each for its own reason in the code:

- A person's stop of a thread paused before a unit (`--pause-before`) writes `exit.json` and one `human` record and returns (`runner.py`, lines 949 to 957). It writes no findings, ledger row or ticket, though the command exits 4.
- A person's stop at a gate is a final exit ([HUM-B12](../specs/gate-and-human.spec.md)), so a loop starts, but it reads only the stop's own segment. The ticket carries the fingerprints of that segment (`plugins/tempergraph/engine/src/tempergraph/improve/child.py`, lines 89 to 92 and 226), the friction lens needs a fault in it (`plugins/tempergraph/engine/src/tempergraph/improve/record.py`, lines 218 to 228), and it holds only the designed `person_stop` (`plugins/tempergraph/engine/src/tempergraph/improve/causes.py`, lines 191 to 198). The findings of the earlier segments that paused were recorded at each pause ([SIL-B8](../specs/self-improvement.spec.md)) and are judged only when the same fingerprint comes back. In stable mode the session review plan reads the signals of the same ticket (`plugins/tempergraph/engine/src/tempergraph/improve/review.py`, lines 407 to 412), so it reads nothing.
- A runner killed, crashed or cut off by its caller's timeout writes no `run_exit`, no ledger row, no findings and no digests. Its lock is released by the operating system, its thread stays resumable ([DUR-B2](../specs/durability-and-resume.spec.md)) and `status --detail` shows `health.orphaned` ([RDD-B5, RDD-B14](../specs/run-detail-document.spec.md); `plugins/tempergraph/engine/src/tempergraph/observe/detail.py`, line 662).

The engine cannot tell why a runner is gone. A timeout belongs to the caller (research `does-the-improvement-loop-find-what-a-reviewer-finds` F7), and every way a process can die leaves the same traces: the lock is free, the newest segment started and wrote no `run_exit`.

The task's acceptance criteria say that a killed runner found by `status` gets its loop and that each trigger starts the loop once per thread, and its summary names `status`, `stop` and `attention` as the places that find such runs. These verbs write nothing today ([DUR-B4](../specs/durability-and-resume.spec.md), [CLI-B6, CLI-B8](../specs/engine-cli.spec.md), [OVR-B15](../specs/overview.spec.md), [RCT-B3](../specs/run-control.spec.md)). The acceptance criteria rank above the specs, so those five behaviours take one exception. The owner was away, so each choice below that the criteria do not settle is an assumption, listed as an open question in the self-improvement spec and in the hand-off.

## Decision

We will hand every end of a thread that no runner reported as a final exit to the loop at the moment the engine finds it, and hand each such end over once (option A; the behaviours are [SIL-B27 to SIL-B32](../specs/self-improvement.spec.md)).

- A person's stop of a paused thread is written as an exit with code 4 and reason `person` in both forms, and the loop of the stop treats the findings of the thread's earlier pauses that no loop judged as its own.
- A runner gone without an exit is written as an exit with code 5 and reason `runner_lost` the first time `status`, `stop` or `attention` reads it, at most 7 days after its newest record, with no grace period. Killed, crashed and timed out are one case.
- That trigger starts the loop once per thread. A resume does not reset it and does not cancel it. A later segment of the thread that is lost again is recorded and starts no loop, and a later final exit starts its loop as every final exit does.
- The three verbs write only that hand-off, print what they printed and exit as before. The engine writes no `run_exit` for the lost segment, so `health.orphaned` keeps saying that the process died.

## Options considered

### A. Hand the end over when it is found, once per thread (chosen)

For: it reaches every end F7 lists, with no clock and no background process, and it is what the criteria ask. The cost stays bounded: once per thread, the 7-day window, the review caps of [SRV-B21](../specs/session-review.spec.md), the daily cap of stable mode ([SIL-B20](../specs/self-improvement.spec.md)) and `TEMPERGRAPH_LOOP=off`. Against: three verbs that were free of writes write once, and a monitor's poll can start a paid loop.

### B. Wait for a grace period before a lost runner counts as ended

For: a person who resumes within minutes would not have a loop started on a half-run. Against: only a clock-driven process sees a period pass, and none runs by default. The loop reads records that are complete at the kill, and a resume starts a new segment whose own exit gets its own loop, so waiting saves nothing.

### C. Hand over only when `resume` starts, a verb that already writes

For: no read-only verb writes. Against: a thread nobody resumes never gets its loop, which is F7's case, and the criteria name `status`, `stop` and `attention`.

### D. A background sweep by the schedule loop

For: no verb writes. Against: it needs the schedule trigger installed, which is optional, so a fresh install keeps F7.

### E. Once per end instead of once per thread

For: every lost segment gets a loop. Against: a thread killed again after a resume, often by the same timeout, would start another loop whose plan reads every session of the thread again, and the criterion says once per thread. A person's `improve review` reaches any later segment ([SRV-B23](../specs/session-review.spec.md)).

## Consequences

- A killed run gets its findings, digests, ledger row and loop. A paused thread that is stopped has its earlier faults judged and its sessions reviewed, in dev and in stable mode.
- Five behaviours carry the exception, each one clause long. The `tempergraph-monitor` polls `status` every few seconds, so its first poll after a runner dies hands it to the loop. Its own record `plugins/tempergraph-monitor/docs/adr/poll-files-and-read-only-verbs.adr.md` calls `status` read-only. It is not edited here, and the monitor's owner should read this record.
- Risk: a flood of loops for old dead threads after an upgrade. The window of 7 days limits it, and `lost_runner.window_days` is a parameter with provenance `default_no_data`.
- Risk: a thread lost twice has no loop for its second loss, though its findings reach `improve backlog` and a person can run `improve review`. The alternative is option E.
- In stable mode a lost runner is not a signal of its own ([SRV-B4](../specs/session-review.spec.md)), so it starts the loop only when its segment holds one.
- The catch-up of a paused segment's findings is made at a stop only. A thread resumed with `proceed` after a pause and then finished is unchanged, since no criterion asks for more.
- A thread resumed before `status`, `stop` or `attention` looked at it is not handed over, since `resume` is not one of the finding verbs.

## Revisit when

Real runs show how often a lost runner holds no signal in stable mode, a thread lost twice holds defects its first loop missed, or a person is surprised by a loop that a watching monitor started.
