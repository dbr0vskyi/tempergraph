# A pause finding is handed on until a loop has dealt with it

## Context

[The record on the findings of earlier pauses](the-loop-judges-the-findings-of-earlier-pauses-at-every-final-exit.adr.md) hands the findings of a thread's earlier pauses to every final exit, once. This record replaces two lines of it: its line that a finding is handed to a loop once, and its consequence that a loop whose judge failed or was skipped by the daily cap has still been handed its findings.

Facts read in the code:

- A pause finding counts as handed when a `loop_started` record of the thread's loop log names its fingerprint at or after the finding was made (`plugins/tempergraph/engine/src/tempergraph/improve/record.py`, `unjudged_pause_findings`, lines 191 to 210). The record is written when a child starts a ticket, before it judges or files (`plugins/tempergraph/engine/src/tempergraph/improve/child.py`, lines 362 to 367), so a ticket held by autonomy `record` (lines 486 to 488), a dry run, the daily cap or a failed judge session uses up the findings it only recorded. When the hold lifts, a thread that finishes hands the loop none of them.
- A waiting or claimed ticket is not read there, and `loop_started` is written by the detached child, so two final exits of a thread before the first child starts hand the same findings twice. `started_for` (lines 163 to 183) already reads waiting and claimed tickets, for lost runners.
- The friction judge is asked about every fault of a ticket whatever answers exist (`child.py`, lines 425 to 443). The answers the filing rules count are the `answers[]` of the workflow's `loop_judged` records ([SIL-B36](../specs/self-improvement.spec.md)), read by fingerprint inside the window (`plugins/tempergraph/engine/src/tempergraph/improve/filing.py`, `recorded_answers`, lines 106 to 133), and the exit's own answer is added to them (`decide`, line 157). A second answer for one fingerprint from one thread would count twice towards the majority of [FFD-B1](../specs/friction-filing-decisions.spec.md).
- An independent review of the earlier record's change measured the effect on one machine's threads: under the filing hold every thread that finished had its pause findings used up (`batch-queue/tasks/i170.review.md`, finding 9, which called it a decision to confirm).

## Decision

We will hand a pause finding to the next final exit of its thread until a loop has dealt with it, count a loop that only recorded the finding as not having dealt with it, and put a fingerprint to the friction judge once for a thread (option A). The rules are [SIL-B28, SIL-B47, SIL-B48 and SIL-B49](../specs/runs-without-a-final-exit.spec.md).

## Options considered

### A. Handed until a loop has dealt with it (chosen)

For: a hold, a failed judge session or the daily cap postpones a finding and does not discard it; the cost of a later exit is one judge session for the findings with no recorded answer. Against: the record of what a loop dealt with has to say more than which fingerprints it named, and a ticket's own state is read as well.

### B. Handed once, when a loop starts (the earlier record's choice)

For: nothing changes, and one record answers it. Against: a thread under a hold, a judge that failed or a capped day loses its pause findings for good, which the review found on real threads.

### C. Handed until filed or commented

For: a finding that the count has not yet met is offered at every exit. Against: every finding below the count is handed and recorded at every exit of the thread, and only a finding that files is ever dealt with, so most would cost a decision each time for nothing.

### D. Handed until dealt with, and judged each time

For: no recorded answer has to be found. Against: a thread that is handed a finding twice adds two answers for one fingerprint, and the majority of [FFD-B1](../specs/friction-filing-decisions.spec.md) counts one thread's opinion twice.

## Consequences

- A thread that is held at one exit and finished at a later one files its pause findings at the later one, and its judge is asked once for each fingerprint.
- A thread whose last final exit is held cannot be recovered by lifting the hold: it has no later exit, and a finished thread starts a new thread only through `rerun`. Its pause findings stay in `findings.json` and in the loop log.
- A claimed ticket whose child was killed leaves its claim file, and the findings it holds stay held while the file exists. This is the state `started_for` already reads for [SIL-B31](../specs/runs-without-a-final-exit.spec.md). Whether a claim left by a dead child should stop holding after a time is not decided here; until it is, such a claim holds.
- The earlier record's other lines stand, among them the session review of earlier pauses at a person's stop only.

## Revisit when

The findings handed on cost more judge sessions than their answers are worth, or a person wants the pause findings of a thread that was last held and has no later exit.
