# The loop judges the findings of earlier pauses at every final exit

## Context

[The record on a thread that ends without a final exit](a-thread-that-ends-without-a-final-exit-is-handed-to-the-loop.adr.md) gave the loop of a person's stop of a paused thread the findings of the thread's earlier pauses, and left a thread that is resumed after a pause and then finished unchanged, "since no criterion asks for more". This record replaces that last choice.

Facts read in the code:

- Every segment writes its findings when it ends, whatever its exit, and marks each with the segment's exit code (`plugins/tempergraph/engine/src/tempergraph/improve/record.py`, `record_exit`, lines 268 to 278).
- The loop starts only at a final exit ([SIL-B9](../specs/self-improvement.spec.md)), so a segment that ended in a pause has no loop of its own.
- `record_exit` reads the findings of earlier pause segments that no loop of the thread was handed (`unjudged_pause_findings`, lines 191 to 209) only when the exit is a person's stop (lines 276 and 277). The ticket of an exit 0 or an exit 5 names the fingerprints of its own segment only (`plugins/tempergraph/engine/src/tempergraph/improve/child.py`, lines 135 and 299).
- The friction judge's prompt holds finding metadata and the record kinds of the last segment (`child.py`, lines 222 to 239), so a pause finding that reached it would come without what answered the pause.
- The session review plan takes its signals from the findings that the ticket's fingerprints name (`plugins/tempergraph/engine/src/tempergraph/improve/review.py`, lines 434 to 439), and for a spent-retries or gap signal it reads the unit's last attempt and its judge (lines 212 to 214). Findings added to an exit's fingerprints therefore steer its review too, and after a resume with `retry` the unit's last attempt is a later one than the attempt that paused.

The task (`batch-queue/tasks/i170.md`) counts the runs of one day: five threads paused 14 times, 40 distinct findings of those segments were named by no `loop_started` record so no friction judge was asked about them, and an open issue whose fingerprint two of those segments recorded got no "seen again" comment. It leaves the session review of the paused segments' sessions out of scope.

## Decision

We will treat the findings of a thread's earlier pause segments that no loop of the thread was handed as findings of every final exit of the thread, and tell the friction judge, for each, what answered its pause (option A; [SIL-B28 and SIL-B37](../specs/runs-without-a-final-exit.spec.md)).

- A finding is handed to a loop once. The record of which findings a loop was handed is the one that already holds for a stop, so a later final exit of the thread leaves them out.
- The session review keeps its rule for the earlier pauses: its plan reads their signals at a person's stop and at no other final exit ([SIL-B28](../specs/runs-without-a-final-exit.spec.md)). At another final exit the findings turn the friction lens on and are judged, and the plan is made from the exit's own findings.
- A pause finding is filed, commented or only recorded by the rules every finding follows ([SIL-B2, SIL-B18](../specs/self-improvement.spec.md)); this record adds no filing rule.
- The judge sees no feedback text, no content of the run's outputs and no content of a workspace file ([SIL-B38](../specs/self-improvement.spec.md)); it is told only that feedback was given.

## Options considered

### A. Every final exit, once per thread (chosen)

For: it reaches the thread that is resumed after a pause and then finishes; it adds no process and no clock, and the record of what a loop was handed, which a stop already reads, serves every exit. Against: the ticket of an exit that follows a pause names more fingerprints, so the judge costs more there.

### B. A person's stop only (the earlier record's choice)

For: nothing changes. Against: the findings of a pause answered with `proceed` or `retry` are judged only if the same fingerprint comes back in a later segment, so the causes of such pauses stay unjudged, as the task's count shows.

### C. At each pause

For: the finding is judged while the pause is fresh. Against: a pause is not a final exit, and starting a loop there would break [SIL-B9](../specs/self-improvement.spec.md). The pause is also unanswered at that moment, so the judge could not be told what answered it, and a thread that pauses again and again would start a loop each time.

### D. Every final exit, with no once rule

For: no record of what a loop was handed is read. Against: every later exit of a thread would judge and pay for the same pause findings again.

### E. Every final exit, for the friction lens and for the session review

For: one rule for both lenses, and the simplest change, since a finding added to the exit's fingerprints steers both. Against: it adds a model-session review to each stable-mode exit that follows a pause, which the task leaves out, and after a `retry` the plan would read a later attempt than the one that paused.

## Consequences

- The causes of pauses reach the friction judge, and through it the filing rules and the "seen again" comment of an open issue, even when the pause was answered with `proceed`.
- A final exit that follows a pause whose fault findings no loop was handed can start a loop when those findings turn the friction lens on ([SIL-B10](../specs/self-improvement.spec.md)), which costs a judge session even when the exit's own segment was clean. The daily cap of stable mode ([SIL-B20](../specs/self-improvement.spec.md)), the once-per-finding rule and `TEMPERGRAPH_LOOP=off` limit it.
- A final exit that is not a stop plans no session review from the signals of earlier pauses, so the ticket has to keep those findings apart from the fingerprints the review plan reads. The review of a stop is unchanged ([SIL-AC20](../specs/runs-without-a-final-exit.spec.md)), and [SIL-AC45](../specs/runs-without-a-final-exit.spec.md) pins the other exits.
- A loop whose judge failed or was skipped by the daily cap has still been handed its findings, so they are recorded `not_judged` ([SIL-B35](../specs/self-improvement.spec.md)) and not handed again. No test pins this.
- Whether the workspace changed between a pause and its resume is recorded only for a run in a worktree ([WTR-B22](../specs/worktree-mode.spec.md)); for a run in place the judge is told `not recorded`, never "no change".
- The consequence of the earlier record that says the catch-up is made at a stop only no longer holds; its other lines stand.

## Revisit when

The extra judge sessions of exits that follow a pause cost more than their answers are worth, the friction judge's confidence on pause findings stays below the filing floor, so that none of them files, or a person asks for the session review of earlier pauses at every final exit.
