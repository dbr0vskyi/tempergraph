# Runs that end without a final exit

## Purpose

Split from [self-improvement](self-improvement.spec.md) by capability, keeping its ids: when a thread that a person stopped at a pause, or whose runner was lost, counts as a final exit for the loop, how that exit is recorded once, and how the findings of the pauses that ended earlier segments of a thread reach the loop at the thread's final exit, what the friction judge is told about the pause that ended each of those segments and what its prompt shows of those segments. That no text of a run reaches the loop's judge or its log is owned by [self-improvement](self-improvement.spec.md).

## Depends on

- `caller-provenance.spec.md`: caller kinds (PRV-B11); decider (PRV-B14)
- `durability-and-resume.spec.md`: cut-off attempt (DUR-B2)
- `friction-filing-decisions.spec.md`: a finding files by the count only on a majority of its recorded answers (FFD-B1); the judge is told that attribution can file by the count (FFD-B6)
- `improvement-data.spec.md`: parameters with provenance (IMD-B23)
- `improvement-proposals.spec.md`: autonomy level (PRP-B11)
- `run-control.spec.md`: not live (RCT-B3)
- `run-detail-document.spec.md`: health (RDD-B14)
- `session-review.spec.md`: review setting (SRV-B13); signals and what they read (SRV-B16)
- `supervision-metrics.spec.md`: touches (SUP-B9)
- `worktree-mode.spec.md`: what a resume compares (WTR-B28)

## Behaviours

### SIL-B27 A stop at a pause is an exit

WHEN a person stops a paused thread, at a gate or before a unit named by `--pause-before`, THE engine SHALL write the records of SIL-B8 for the stop as an exit with exit code 4 and reason `person`.

- GIVEN a thread paused before unit `code` by `--pause-before code` WHEN a person runs `resume --decision stop` THEN the command exits 4, the ledger gains one row with exit code 4 and reason `person` and the run log gains one `finding_recorded` record
- GIVEN a thread paused at a gate WHEN a person stops it THEN the ledger and the run log gain the same row and record

### SIL-B28 A final exit covers the thread's earlier pauses

WHEN a thread reaches a final exit (SIL-B9) THE loop SHALL treat the findings of every earlier segment of the thread that ended in a pause, and that no earlier loop of the thread dealt with (SIL-B47) and no ticket of the thread holds (SIL-B48), as findings of that exit, so that its friction lens judges their faults (SIL-B10, SIL-B49) and, at a person's stop (SIL-B27), its session review is planned from their signals ([SRV-B13, SRV-B16](session-review.spec.md)).

- GIVEN a thread whose first segment paused on `retries_spent` at unit `code` WHEN a person stops it at that pause THEN the ticket's friction lens is on and the loop child's friction judge is asked about the `retries_spent` finding of `code`; in stable mode the session review plan has depth `partial` with the last attempt and the judge of `code` as its targets
- GIVEN a thread whose first segment paused on `gap_escalation` at unit `review`, was resumed with `proceed` and then ended with exit 0, with exit 4 and reason `stopped_by_request`, with exit 4 and reason `attempt_cap` or with exit 5 WHEN its loop child runs THEN the ticket holds the fingerprint of the `gap_escalation` finding of `review` and the friction judge is asked about it
- GIVEN a thread stopped at a pause on `retries_spent` at unit `code`, whose loop child's judge answered for that finding, re-opened with `retry`, paused a second time on `gap_escalation` at unit `review` and stopped a second time WHEN the second stop's loop child runs THEN its friction judge is asked about the `gap_escalation` finding of `review` and not about the `retries_spent` finding of `code`

### SIL-B47 A loop that only recorded a finding has not dealt with it

WHEN a loop child ends THE loop SHALL count each finding handed to it as dealt with, except every finding of a child that autonomy `record` (PRP-B11) or a dry run (SIL-B6) held and each friction finding its judge gave no answer for (SIL-B35).

- GIVEN a thread stopped at a pause on `gap_escalation` while autonomy `record`, or a dry run from the workflow's declaration, held its loop child, then re-opened with `proceed` and finished with the hold lifted (a resume with `--no-dry-run` lifts the dry run), and a judge that attributes the finding at 0.9 WHEN the finished thread's loop child runs THEN its ticket holds the finding, one issue is filed for it and the judge has been asked about it once in all
- GIVEN a thread stopped at a pause whose loop child's judge session failed, then re-opened and finished WHEN the finished thread's loop child runs THEN its ticket holds the finding and its judge is asked about it
- GIVEN a thread whose last final exit was held by autonomy `record` WHEN the hold is lifted THEN no loop is handed its pause findings, the thread having no later final exit, and they stay recorded only

### SIL-B48 A ticket that waits holds its findings

WHEN a thread reaches a final exit while an earlier ticket of the thread waits for its loop child or has been claimed by it THE loop SHALL not hand that exit the pause findings the earlier ticket holds.

- GIVEN a thread that paused on `gap_escalation`, was stopped by request, resumed and finished before the loop child of the stop's ticket has started WHEN the finished thread's ticket is made THEN it holds none of the fingerprints of the stop's ticket and the judge is asked about the finding once in all
- GIVEN the stop's ticket claimed by its loop child, which has written no record yet WHEN the finished thread's ticket is made THEN it holds none of those fingerprints

### SIL-B49 A recorded answer of the friction judge is used

WHEN a loop child is handed a finding for whose fingerprint an earlier loop of its thread recorded an answer of the friction judge (SIL-B36) THE loop child SHALL decide the finding on that answer without asking the judge about it, so that the thread adds one answer for the fingerprint to those FFD-B1 counts.

- GIVEN a thread whose first loop child, held by autonomy `record`, recorded an answer attributed at 0.9 for a pause finding, and that finished with the hold lifted WHEN its loop child runs THEN the judge's prompt holds no row for that fingerprint, one issue is filed and the thread's `loop.jsonl` holds one answer for the fingerprint
- GIVEN that recorded answer not attributed WHEN the finished thread's loop child runs THEN the finding is recorded `not_attributed`, no issue is filed and the judge is not asked
- GIVEN a finding whose earlier loop child's judge gave no answer WHEN a later exit is handed it THEN the judge is asked about it

### SIL-B37 The friction judge is told what answered a pause

WHEN the friction judge is asked about a finding of a segment that ended in a pause THE loop child SHALL tell it, in one row, the pause's reason, the decision word that answered it, the kind of caller that decided (PRV-B11, PRV-B14), whether feedback was given, whether a ruling was given, the class of the decision's touch (SIL-B43), the operator's reason, whether the workspace changed between the pause and the resume (WTR-B28) and the verdict of the paused unit's next gate (SIL-B41).

- GIVEN a thread that paused with reason `unresolved_gap` at unit `review` and was resumed by a person with `proceed`, no feedback and no operator reason, in a worktree nobody changed WHEN the judge is asked about the `gap_escalation` finding of `review` THEN it is told the reason `unresolved_gap`, the decision `proceed`, the caller kind `person`, that no feedback and no ruling were given, that no operator reason was given, that the workspace did not change and that the next gate verdict is `none`
- GIVEN a thread that paused at unit `code` with its retries spent and was resumed by an agent with `retry`, a feedback text and `--reason judge_error`, a person having committed a change in the worktree between the pause and the resume, and the next gate of `code` gave PROCEED WHEN the judge is asked about the `retries_spent` finding of `code` THEN it is told the decision `retry`, the caller kind `agent`, that feedback was given, the operator reason `judge_error`, that the workspace changed and the verdict PROCEED, and the prompt holds no word of the feedback
- GIVEN a thread that runs in place, so that the engine compares no workspace between its segments WHEN the judge is asked about a finding of a paused segment THEN it is told that the workspace change is `not recorded`

### SIL-B39 A finding is told the pause that ended its own segment

WHEN the friction judge is asked about a finding of a segment that ended in a pause THE loop child SHALL tell it the pause that ended that segment, whatever the finding's unit, with the paused unit and item named in the finding's row; a segment that ended in several pauses gives the pause at the finding's unit, else its last pause.

- GIVEN a thread that paused at unit `a`, was resumed with `proceed` and paused at unit `b`, with a finding of unit `a` in that second segment WHEN the judge is asked about that finding THEN its row names unit `b` and the reason of the pause at `b`, and not the pause at `a`
- GIVEN a segment that ended in pauses at the units `a` and `b` of one parallel block, the pause at `b` recorded last WHEN the judge is asked about a finding of `a` and about one of a unit `c` that did not pause THEN the row of the first names the pause at `a` and the row of the second the pause at `b`
- GIVEN a map that paused at its second item WHEN the judge is asked about a finding of the map's unit THEN the row names the unit and that item

### SIL-B40 A finding with nothing recorded gets no row

WHEN the run's records hold no pause, no decision and no gate for a finding of a segment that ended in a pause THE loop child SHALL show the friction judge no row for that finding, and no section on what answered each pause when no finding has a row.

- GIVEN the only finding of a segment that ended in a pause, with no pause, decision row or gate recorded for that segment WHEN the judge is asked about it THEN the prompt holds no row for it and no section on what answered each pause
- GIVEN a thread of one pause whose paused segment holds a finding of the paused unit and one of another unit WHEN the judge is asked about them THEN both rows name that pause and neither reads `not recorded` for every fact

### SIL-B41 The next gate is the paused unit's own

WHEN the friction judge is told the verdict of the next gate after a pause THE loop child SHALL take it from the first gate after the pause that is of the paused unit and the paused item, a unit of a child workflow and a unit of its parent that share a name being different units, and tell `none` when no such gate follows.

- GIVEN a map that paused at its first item, was resumed with `proceed` and whose second item's first gate gave RETRY WHEN the judge is asked about the pause's finding THEN the next gate verdict is `none`
- GIVEN that map resumed with `retry` and whose first item then passed its gate with PROCEED WHEN the judge is asked THEN the next gate verdict is PROCEED
- GIVEN a unit with no items that a person stopped at its pause WHEN the judge is asked about the pause's finding THEN the next gate verdict is `none`

### SIL-B42 A ruling is told as a ruling, never as feedback or in words

WHEN a decision that answered a pause was given with a ruling THE loop child SHALL tell the friction judge that a ruling was given and that feedback was not, and tell it no word of the ruling.

- GIVEN a pause resumed with `proceed`, a feedback text and a ruling WHEN the judge is asked about the pause's finding THEN it is told that a ruling was given and that feedback was not given, and the prompt holds no word of the text
- GIVEN a pause resumed with `retry` and a feedback text and no ruling WHEN the judge is asked THEN it is told that feedback was given and that no ruling was given

### SIL-B43 The class of the decision's touch is told

WHEN the friction judge is told what answered a pause THE loop child SHALL tell it the class of each touch the decision made ([SUP-B9](supervision-metrics.spec.md)), each class once, in the order `designed`, `rescue`, `steer`, `engine`, and `not recorded` when the decision's record holds no touch.

- GIVEN an escalation answered with `proceed` WHEN the judge is asked about the pause's finding THEN it is told the touch class `rescue`
- GIVEN an escalation answered with `stop` WHEN the judge is asked THEN it is told the touch classes `rescue` and `steer`
- GIVEN a decision whose record holds no touch WHEN the judge is asked THEN it is told that the touch class is `not recorded`

### SIL-B44 The judge is told what the section on pauses is

WHEN the loop child asks the friction judge about findings THE loop child SHALL tell it in the prompt that the section on what answered each pause gives, for a finding of a segment that ended in a pause, what answered that segment's pause, that a `retry` that then passes with the workspace unchanged points at the judge or the check and not at the step, and that a `proceed` given with a ruling means a person or the caller that started the run overrode the gate.

- GIVEN a ticket with one finding of a segment that ended in a pause WHEN the friction judge's session starts THEN its prompt holds those three sentences and the sentence that an answer `attributed: true` can file a finding by the count whatever its confidence (FFD-B6)

### SIL-B50 The judge is told what an operator reason points at

WHEN the loop child asks the friction judge about findings THE loop child SHALL tell it in the prompt that an operator reason other than `plan` or `request` points away from the workflow's step.

- GIVEN a ticket with one finding of a segment that ended in a pause WHEN the friction judge's session starts THEN its prompt holds that sentence

### SIL-B45 The prompt shows the records of each segment that holds a finding it lists

WHEN the loop child asks the friction judge about findings THE loop child SHALL show in the prompt, for the last segment and for each earlier segment that ended in a pause and holds a finding the prompt lists, a section headed by the segment's exit code and its reason, with the counts of the record kinds of the segment's units and the ids of the criteria that blocked them, and no text of a record.

- GIVEN a thread whose first and second segments each ended in a pause and held a finding, and whose third segment ended with exit 0 WHEN the judge is asked about the findings THEN the prompt holds three sections, headed by exit code 3 and the first pause's reason, exit code 3 and the second pause's reason, and exit code 0 and its reason, each with the counts of the record kinds of its own units and the ids of the criteria that blocked them
- GIVEN a paused segment whose findings an earlier loop of the thread dealt with (SIL-B47) WHEN the judge is asked about the last segment's findings THEN the prompt holds the last segment's section and none for that paused segment
- GIVEN a paused segment whose records hold a distinct word in a check's notes and another in a judge's gap WHEN the judge is asked THEN neither word is in any section

### SIL-B51 A finding is bound to the segment it was made in

WHEN the loop child binds a finding to the segment it was made in, for the friction judge's rows and sections (SIL-B39, SIL-B45), THE loop child SHALL take the segment that starts at the segment start the finding records and, for a finding that records none, the segment whose `run_exit` record is the latest at or before the finding's time, both read to the whole second.

- GIVEN a thread whose first and second segments each paused and whose third finished, with a finding of each paused segment made by an engine that recorded no segment start, one of them made 4 seconds after its segment's `run_exit` WHEN the judge is asked about the findings THEN the row of each names the pause that ended its own segment and the prompt holds a section for each paused segment
- GIVEN a finding made in the whole second in which its segment exited, the `run_exit` record being timed 0.7 seconds into that second WHEN it is bound THEN it belongs to that segment and not to the one before
- GIVEN a finding that records no segment start and whose time cannot be read WHEN the judge is asked about it THEN it has no row (SIL-B40)

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
- SIL-AC21 (SIL-B28): A fixture thread stopped at a pause whose loop child's judge answered for the finding, re-opened, paused and stopped again gives a second friction judgement over the findings of the second pause only
- SIL-AC39 (SIL-B28): A fixture thread that pauses on `gap_escalation`, is resumed with `proceed` and ends with exit 0 gives a ticket with the friction lens on that holds the fingerprint of that finding, and its loop child's friction judge is asked about it
- SIL-AC40 (SIL-B28, SIL-B47): A fixture thread stopped at a pause, whose loop child's judge answered for its findings, and then resumed and finished with exit 0 hands the loop at that exit none of the fingerprints the first loop child was handed, and no friction judge is asked about those findings a second time
- SIL-AC41 (SIL-B37): In the fixture of SIL-AC39, whose worktree nobody changes between the pause and the resume, the friction judge's prompt names for the `gap_escalation` finding the reason `unresolved_gap`, the decision `proceed`, the kind of the resume's caller, that no feedback was given, that the workspace did not change and the next gate verdict `none`
- SIL-AC42 (SIL-B37): A fixture thread paused with its retries spent and resumed with `retry` and a feedback text gives a friction judge prompt that names the decision `retry`, that feedback was given and the verdict of the unit's next gate, and that holds no word of the feedback
- SIL-AC43 (SIL-B28, SIL-B2): At the final exit of a fixture thread that paused on `gap_escalation` and was resumed with `proceed`, when a fixture judge attributes the finding at 0.9 and an open issue on a fake code host holds its fingerprint or its cause, one "seen again" comment is added to that issue and no new issue is made
- SIL-AC45 (SIL-B28): The stable-mode fixture of SIL-AC20, resumed with `retry` and finished with exit 0 instead of being stopped, gives a session review plan of depth `none`
- SIL-AC46 (SIL-B37): A fixture thread in a worktree whose step commits before the pause gives a friction judge prompt that names the workspace as unchanged when nothing is done between the pause and the resume and as changed when a person commits between them, and the same thread run in place gives one that names the workspace change as `not recorded`
- SIL-AC48 (SIL-B28): A fixture thread whose first segment paused on `gap_escalation` and whose later segment ends with exit 4 and reason `stopped_by_request`, with exit 4 and reason `attempt_cap` and with exit 5 gives at each of the three exits a ticket with the friction lens on that holds the fingerprint of the pause's finding, and its loop child's friction judge is asked about it
- SIL-AC49 (SIL-B39): A fixture thread that pauses at unit `a`, is resumed and pauses at unit `b` with a finding of `a` in that second segment gives a friction judge prompt whose row for that finding names unit `b` and the reason of the pause at `b`, and a fixture map that pauses at its second item gives a row that names the unit and that item
- SIL-AC50 (SIL-B40): A fixture finding of a paused segment whose run log holds no pause, no decision row and no gate for that segment gets no row in the friction judge's prompt, and a fixture thread of one pause gives rows that name that pause and none that reads `not recorded` for every fact
- SIL-AC51 (SIL-B41): A fixture map that pauses at one item, is resumed with `proceed` and whose next item's first gate gives RETRY gives the row for the pause's finding the next gate verdict `none`, and the same map resumed with `retry` gives the verdict of that item's next gate
- SIL-AC52 (SIL-B42): A fixture decision given with a feedback text and a ruling and no other feedback gives a row that says a ruling was given and feedback was not given, and a canary word in the ruling is in neither the friction judge's prompt nor `loop.jsonl`
- SIL-AC53 (SIL-B43): A fixture escalation answered with `proceed` gives the row the touch class `rescue`, one answered with `stop` gives `rescue` and `steer`, and a fixture ledger row with no touch gives `not recorded`
- SIL-AC54 (SIL-B44): The prompt that a fixture friction judge session receives when a finding of a paused segment is in it holds the three sentences of SIL-B44 and still holds the sentence of FFD-B6
- SIL-AC55 (SIL-B45): A fixture of two paused segments and a final one gives a friction judge prompt with three sections headed by exit code and reason, each with its own record-kind counts and blocking criterion ids, and none holding a canary word placed in the text of a record
- SIL-AC57 (SIL-B47): A fixture thread stopped at a pause under autonomy `record` and finished with the hold lifted hands its second loop child the pause's finding, files one issue for it when its judge attributed it at 0.9, and its judge was asked about it once in all; a fixture thread whose first loop child's judge session failed hands the finding to its next final exit, whose judge is asked about it; a fixture thread whose last final exit was held hands no loop its pause findings when the hold is lifted; a fixture thread of a workflow that declares `loop_dry_run` `true`, stopped at a pause and finished after a resume with `--no-dry-run`, hands its second loop child the pause's finding and files one issue for it when its judge attributed it at 0.9
- SIL-AC58 (SIL-B48): A fixture thread with two final exits before the first ticket's loop child has started, and the same with the first ticket claimed, gives the second ticket none of the fingerprints of the first ticket's pause findings, and the friction judge is asked about each of those findings once
- SIL-AC59 (SIL-B49): A fixture loop child handed a pause finding that an earlier loop child of its thread recorded an answer for puts no row for it in the friction judge's prompt, decides it on that answer and leaves one answer for the fingerprint in the thread's `loop.jsonl`, and a finding with no recorded answer is put to the judge
- SIL-AC60 (SIL-B37): A fixture decision given with `--reason judge_error` gives a friction judge prompt that names the operator reason `judge_error` for the finding of the paused segment, and one given with no reason gives a prompt that says no operator reason was given
- SIL-AC61 (SIL-B50): The prompt that a fixture friction judge session receives when a finding of a paused segment is in it holds the sentence of SIL-B50
- SIL-AC62 (SIL-B51): A fixture thread of two paused segments and a final one, whose paused-segment findings are some with and some without a segment start, gives every one of them its row and each paused segment its section, and a fixture finding made within the second of its segment's `run_exit` is bound to that segment
- SIL-AC22 (SIL-B29): A fixture thread whose process died after a failed check, with no `run_exit`, leaves after `status` one ledger row with exit code 5 and reason `runner_lost`, a `check_fail` finding in `findings.json` and one ticket, and `status --detail` still shows `health.orphaned` true
- SIL-AC23 (SIL-B29): After `attention`, and after `stop` (which exits 2), the same fixture leaves the same records and ticket as after `status`
- SIL-AC24 (SIL-B29): The same fixture with its newest record older than 7 days leaves the state root unchanged after `status`
- SIL-AC25 (SIL-B30): Two runs of `status`, and one `status` with one `attention` at the same moment, on a fixture lost runner leave one `runner_lost` ledger row and one ticket
- SIL-AC26 (SIL-B31): A fixture thread whose lost runner started the loop and that is resumed and lost again leaves a second `runner_lost` ledger row and no second ticket
- SIL-AC27 (SIL-B31): A fixture thread whose lost runner started the loop and that is then resumed and finishes has two tickets in all, one for each end
- SIL-AC28 (SIL-B32): With a ledger that cannot be written, `status` on a fixture lost runner prints its document and exits 0, and `stop` exits 2 with the message of RCT-B3
