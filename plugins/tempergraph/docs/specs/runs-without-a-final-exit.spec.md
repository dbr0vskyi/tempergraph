# Runs that end without a final exit

## Purpose

Split from [self-improvement](self-improvement.spec.md) by capability, keeping its ids: when a thread that a person stopped at a pause, or whose runner was lost, counts as a final exit for the loop, how that exit is recorded once, and how the findings of the pauses that ended earlier segments of a thread reach the loop at the thread's final exit, with what answered each pause. That no text of a run reaches the loop's judge or its log is owned by [self-improvement](self-improvement.spec.md).

## Behaviours

### SIL-B27 A stop at a pause is an exit

WHEN a person stops a paused thread, at a gate or before a unit named by `--pause-before`, THE engine SHALL write the records of SIL-B8 for the stop as an exit with exit code 4 and reason `person`.

- GIVEN a thread paused before unit `code` by `--pause-before code` WHEN a person runs `resume --decision stop` THEN the command exits 4, the ledger gains one row with exit code 4 and reason `person` and the run log gains one `finding_recorded` record
- GIVEN a thread paused at a gate WHEN a person stops it THEN the ledger and the run log gain the same row and record

### SIL-B28 A final exit covers the thread's earlier pauses

WHEN a thread reaches a final exit (SIL-B9) THE loop SHALL treat the findings of every earlier segment of the thread that ended in a pause, and that no earlier loop of the thread was handed, as findings of that exit, so that its friction lens judges their faults (SIL-B10) and, at a person's stop (SIL-B27), its session review is planned from their signals ([SRV-B13, SRV-B16](session-review.spec.md)).

- GIVEN a thread whose first segment paused on `retries_spent` at unit `code` WHEN a person stops it at that pause THEN the ticket's friction lens is on and the loop child's friction judge is asked about the `retries_spent` finding of `code`; in stable mode the session review plan has depth `partial` with the last attempt and the judge of `code` as its targets
- GIVEN a thread whose first segment paused on `gap_escalation` at unit `review`, was resumed with `proceed` and finished with exit 0 WHEN its loop child runs THEN the ticket holds the fingerprint of the `gap_escalation` finding of `review` and the friction judge is asked about it
- GIVEN a thread stopped at a pause on `retries_spent` at unit `code`, re-opened with `retry`, paused a second time on `gap_escalation` at unit `review` and stopped a second time WHEN the second stop's loop child runs THEN its friction judge is asked about the `gap_escalation` finding of `review` and not about the `retries_spent` finding of `code`

### SIL-B37 The friction judge is told what answered a pause

WHEN the friction judge is asked about a finding of a segment that ended in a pause (at the finding's unit when more than one unit paused) THE loop child SHALL tell it the pause's reason, the decision word that answered the pause, the kind of caller that decided ([PRV-B11, PRV-B14](caller-provenance.spec.md)), whether feedback was given, whether the workspace changed between the pause and the resume ([WTR-B22](worktree-mode.spec.md)), and the verdict of the paused unit's next gate.

- GIVEN a thread that paused with reason `unresolved_gap` at unit `review` and was resumed by a person with `proceed` and no feedback, in a worktree nobody changed WHEN the judge is asked about the `gap_escalation` finding of `review` THEN it is told the reason `unresolved_gap`, the decision `proceed`, the caller kind `person`, that no feedback was given, that the workspace did not change and that the next gate verdict is `none`
- GIVEN a thread that paused at unit `code` with its retries spent and was resumed by an agent with `retry` and a feedback text, a person having committed a change in the worktree, and the next gate of `code` gave PROCEED WHEN the judge is asked about the `retries_spent` finding of `code` THEN it is told the decision `retry`, the caller kind `agent`, that feedback was given, that the workspace changed and the verdict PROCEED, and the prompt holds no word of the feedback
- GIVEN a thread that runs in place, so that the engine compares no workspace between its segments WHEN the judge is asked about a finding of a paused segment THEN it is told that the workspace change is `not recorded`

### SIL-B29 A lost runner is a final exit

WHEN `status`, `stop` or `attention` reads a thread whose runner is gone without an exit, that is whose lock is not held and whose newest segment started and wrote no `run_exit` (a process killed, crashed or cut off by its caller's timeout, which the engine cannot tell apart, [RDD-B14](run-detail-document.spec.md)), and whose newest record is at most `lost_runner.window_days` (7) days old ([IMD-B23](improvement-data.spec.md)), THE engine SHALL treat that segment as a final exit with exit code 5 and reason `runner_lost`, writing the records of SIL-B8 and starting the loop under SIL-B1, SIL-B10 and SIL-B31.

- GIVEN a dev-mode run whose process was killed in unit `code` after its check failed once WHEN `status` runs THEN one ledger row with exit code 5 and reason `runner_lost`, a `check_fail:code` finding in `findings.json` and a hand-off ticket exist, and `status --detail` still shows `health.orphaned` true and the thread resumable ([DUR-B2](durability-and-resume.spec.md))
- GIVEN that thread WHEN `attention` runs, or `stop` names it, THEN the same records and ticket exist, and `stop` exits 2 as [RCT-B3](run-control.spec.md) says
- GIVEN a thread whose newest record is 8 days old WHEN `status` runs THEN nothing is written

### SIL-B30 A lost runner is recorded once

WHEN `status`, `stop` or `attention` reads a lost runner whose segment is already recorded as an exit, or reads it at the same moment as another of them, THE engine SHALL write no second ledger row, no second findings entry and no second ticket for that segment.

- GIVEN a lost runner WHEN `status` runs twice THEN the ledger holds one `runner_lost` row for it, one ticket was written and, after the loop child ends, `loop.jsonl` holds one `loop_started`
- GIVEN a lost runner WHEN `status` and `attention` run at the same moment THEN the ledger holds one `runner_lost` row for it and one ticket was written

### SIL-B31 Once per thread

WHEN a lost runner has started the loop for a thread THE engine SHALL start no second loop for a lost runner of that thread, however often the thread is resumed.

- GIVEN a thread whose lost runner started the loop WHEN it is resumed, lost again and read by `status` THEN the later segment has its own ledger row with exit code 5 and reason `runner_lost` and no second ticket is written
- GIVEN a thread whose lost runner started the loop WHEN it is resumed and finishes THEN its final exit starts the loop under SIL-B1 as any final exit does

### SIL-B32 The finding verbs keep their results

WHEN `status`, `stop` or `attention` hands a lost runner to the loop THE engine SHALL print the document or message and exit with the code it would without the hand-off, even when the hand-off fails, and start no session of its own.

- GIVEN a lost runner and a ledger that cannot be written WHEN `status` runs THEN it prints its document and exits 0
- GIVEN a lost runner WHEN `stop` names it THEN it exits 2 with the message of [RCT-B3](run-control.spec.md)

## Acceptance criteria

- SIL-AC18 (SIL-B27): A fixture thread paused before a unit by `--pause-before` and stopped with `resume --decision stop` gains one ledger row with exit code 4 and reason `person` and one `finding_recorded` record, as a fixture thread stopped at a gate does
- SIL-AC19 (SIL-B28): A fixture thread whose first segment paused on `retries_spent` and that a person then stops gives a ticket with the friction lens on, and its loop child's friction judge is asked about that finding
- SIL-AC20 (SIL-B28): The same fixture in stable mode gives a session review plan of depth `partial` whose targets are the last attempt and the judge of the unit that paused
- SIL-AC21 (SIL-B28): A fixture thread stopped at a pause, re-opened, paused and stopped again gives a second friction judgement over the findings of the second pause only
- SIL-AC39 (SIL-B28): A fixture thread that pauses on `gap_escalation`, is resumed with `proceed` and ends with exit 0 gives a ticket with the friction lens on that holds the fingerprint of that finding, and its loop child's friction judge is asked about it
- SIL-AC40 (SIL-B28): A fixture thread stopped at a pause, whose loop child has run, and then resumed and finished with exit 0 hands the loop at that exit none of the fingerprints the first loop child was handed, and no friction judge is asked about those findings a second time
- SIL-AC41 (SIL-B37): In the fixture of SIL-AC39, whose worktree nobody changes between the pause and the resume, the friction judge's prompt names for the `gap_escalation` finding the reason `unresolved_gap`, the decision `proceed`, the kind of the resume's caller, that no feedback was given, that the workspace did not change and the next gate verdict `none`
- SIL-AC42 (SIL-B37): A fixture thread paused with its retries spent and resumed with `retry` and a feedback text gives a friction judge prompt that names the decision `retry`, that feedback was given and the verdict of the unit's next gate, and that holds no word of the feedback
- SIL-AC43 (SIL-B28, SIL-B2): At the final exit of a fixture thread that paused on `gap_escalation` and was resumed with `proceed`, when a fixture judge attributes the finding at 0.9 and an open issue on a fake code host holds its fingerprint or its cause, one "seen again" comment is added to that issue and no new issue is made
- SIL-AC45 (SIL-B28): The stable-mode fixture of SIL-AC20, resumed with `retry` and finished with exit 0 instead of being stopped, gives a session review plan of depth `none`
- SIL-AC46 (SIL-B37): A fixture thread in a worktree to which a person committed between its pause and its resume gives a friction judge prompt that names the workspace as changed, and the same thread run in place gives one that names the workspace change as `not recorded`
- SIL-AC22 (SIL-B29): A fixture thread whose process died after a failed check, with no `run_exit`, leaves after `status` one ledger row with exit code 5 and reason `runner_lost`, a `check_fail` finding in `findings.json` and one ticket, and `status --detail` still shows `health.orphaned` true
- SIL-AC23 (SIL-B29): After `attention`, and after `stop` (which exits 2), the same fixture leaves the same records and ticket as after `status`
- SIL-AC24 (SIL-B29): The same fixture with its newest record older than 7 days leaves the state root unchanged after `status`
- SIL-AC25 (SIL-B30): Two runs of `status`, and one `status` with one `attention` at the same moment, on a fixture lost runner leave one `runner_lost` ledger row and one ticket
- SIL-AC26 (SIL-B31): A fixture thread whose lost runner started the loop and that is resumed and lost again leaves a second `runner_lost` ledger row and no second ticket
- SIL-AC27 (SIL-B31): A fixture thread whose lost runner started the loop and that is then resumed and finishes has two tickets in all, one for each end
- SIL-AC28 (SIL-B32): With a ledger that cannot be written, `status` on a fixture lost runner prints its document and exits 0, and `stop` exits 2 with the message of RCT-B3
