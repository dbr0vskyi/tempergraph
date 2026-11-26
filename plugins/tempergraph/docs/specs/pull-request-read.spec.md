# Pull request read

## Purpose

Split from [run outcome](run-outcome.spec.md) by capability, keeping its ids: how the loop reads the pull request that a run recorded ([FIN-B11](finalizer-contract.spec.md)) into entries of the run's `later[]` ([OUT-B18](run-outcome.spec.md)), which hold counts and kinds of what a person did there and never text. A person who reviews a delivered pull request finds what every gate let through, and these entries are how the improvement loop hears them: [OUT-B26](run-outcome.spec.md) counts the escapes they show and [SIL-B33](self-improvement.spec.md) records a finding for the units that wrote the files a person changed. The state of a proposal's pull request is read by [PRP-B26](improvement-proposals.spec.md), which this spec does not own. Review text stays in the run's local evidence ([FBK-B15](feedback-and-judge-reliability.spec.md)). Workflow owners, the engine's maintainers and whoever reads the escape rate depend on it.

## Depends on

- `finalizer-contract.spec.md`: a pull request the finalizer publishes is recorded (FIN-B11)
- `improvement-proposals.spec.md`: a proposal's pull request state is read from the code host (PRP-B26); a pull request that cannot be read leaves its proposal as it was (PRP-B28)
- `self-improvement.spec.md`: an escape is a finding on the units that wrote the changed files (SIL-B33)

## Behaviours

### OUT-B23 A recorded pull request is read until it is merged or closed

WHEN a final exit of a workflow is recorded at autonomy `file` or above, outside a dry run, THE loop SHALL read from the code host, as for a proposal's pull request ([PRP-B26, PRP-B28](improvement-proposals.spec.md)), the pull request of each run of the workflow that recorded one ([FIN-B11](finalizer-contract.spec.md)) and that no earlier read found merged or closed.

- GIVEN a recorded pull request that the last read found open WHEN another final exit of the workflow is recorded THEN it is read at that exit
- GIVEN a recorded pull request that a read found merged, or closed without a merge WHEN another final exit is recorded THEN it is not read
- GIVEN a code host that cannot be reached WHEN a final exit is recorded THEN no entry is appended to any run's `later[]` and the exit code of the run and the loop's other work are unchanged

### OUT-B24 A read appends counts and kinds

WHEN the loop has read a recorded pull request THE loop SHALL append to the run's `later[]` one entry of the pull request's state (`open`, `merged` or `closed`) and of counts of a person's work (OUT-B25), never text: reviews in each state (`approved`, `changes_requested`, `commented`, `dismissed`), review comments, follow-up commits (OUT-B27) and the files the run wrote that those commits changed (OUT-B28).

- GIVEN an open pull request with one person's review in state `changes_requested`, two review comments and no follow-up commit WHEN it is read THEN the entry holds `open`, one review in `changes_requested`, two comments, no follow-up commit and no file
- GIVEN a merged pull request with one follow-up commit that changed two files, one of them written by the run WHEN it is read THEN the entry holds `merged`, one follow-up commit and one file

### OUT-B25 Only a person's work is counted

WHEN the loop counts the reviews, review comments and commits of a pull request THE loop SHALL count, and keep the text of, only those of a person: an account the code host gives as an owner, member or collaborator of the repository and does not class as a bot, with review or comment text that does not start with the marker line of the agent comment format of `CONTRIBUTING.md`, and for a commit, one parent.

- GIVEN a review, a review comment and a commit of an account the host gives as a collaborator, with no marker line WHEN they are read THEN each is counted and the text of the review and of the comment is in the run's local evidence
- GIVEN a review, a review comment and a commit of an account the host classes as a bot or does not give as owner, member or collaborator, and a review comment that starts with the marker line WHEN they are read THEN none is counted and no text of them is kept
- GIVEN a commit that has no account and a commit that has two parents WHEN they are read THEN neither is counted

### OUT-B27 Follow-up commits

WHEN the loop counts the follow-up commits of a pull request THE loop SHALL take the commits the pull request holds after the commit recorded as the end of the run's branch ([FIN-B11](finalizer-contract.spec.md)), and none when no end commit was recorded or the pull request does not hold it.

- GIVEN a pull request that holds the run's end commit followed by two commits of a person WHEN it is read THEN the entry counts two follow-up commits
- GIVEN a pull request that does not hold the run's end commit, because its branch was rewritten WHEN it is read THEN the entry counts no follow-up commit and no file
- GIVEN a run whose ledger row records no end commit WHEN its pull request is read THEN the entry counts no follow-up commit and no file

### OUT-B28 The files the run wrote

WHEN the loop counts the files the run wrote that follow-up commits changed THE loop SHALL take as the files the run wrote those that differ between the commit its branch started from and the commit recorded as its end, whatever tool or command changed them, and none when either commit is unknown.

- GIVEN a step that changed a file through a shell command and committed it, and a person's follow-up commit that changed that file WHEN the pull request is read THEN the entry counts one file
- GIVEN a file that one step changed and a later step restored, and a person's follow-up commit that changed it WHEN the pull request is read THEN the entry counts no file
- GIVEN a run whose branch start is unknown WHEN its pull request is read THEN the entry counts no file

### OUT-B29 The host is asked for the files of follow-up commits only

WHEN the loop reads a recorded pull request THE loop SHALL ask the code host for the changed files of the commits after the commit recorded as the end of the run's branch and of no other commit.

- GIVEN a pull request of five commits whose third is the run's end commit WHEN it is read THEN the host is asked for the files of the fourth and the fifth commit and of no other
- GIVEN a pull request that does not hold the run's end commit, or a run that recorded none WHEN it is read THEN the host is asked for the files of no commit

### OUT-B30 One entry for one state

WHEN a read of a pull request gives the state and counts of the run's last entry THE loop SHALL append no entry, whether that entry came from an earlier read or from a read of the same pull request that ran at the same time.

- GIVEN a read whose state and counts equal the run's last entry WHEN the loop has read it THEN nothing is appended
- GIVEN two reads of the same pull request that run at the same time and give the same state and counts WHEN both end THEN the run's `later[]` holds one entry for them

### OUT-B31 A pull request that cannot be read is skipped with one record

WHEN a recorded pull request cannot be read, whatever the cause, THE loop SHALL skip it with one `loop_skipped` record in the `loop.jsonl` of the exit's thread, holding the run's thread id, the pull request's number and the type name of the error, and no text.

- GIVEN two recorded pull requests and a code host that fails for the first WHEN a final exit is recorded THEN one `loop_skipped` record holds the first run's thread id, its pull request's number and the error's type name, no entry is appended for it, the second is read and the exit code of the run is unchanged
- GIVEN a code host whose error message holds a canary WHEN a pull request is skipped THEN the record holds the error's type name and not the canary

### OUT-B32 A finding that is owed is recorded at the next read

WHEN a read of a pull request ends THE loop SHALL record each finding of [SIL-B33](self-improvement.spec.md) that its run is owed and does not hold, whether or not this read appended an entry, so that a finding that could not be written is recorded at the next read and reads of one pull request that run at the same time leave one finding for each unit.

- GIVEN a read that appended the run's entry and could not write its finding WHEN the next read of the pull request ends with an entry equal to the last THEN the run holds the finding
- GIVEN two reads of one pull request that run at the same time and show an escape WHEN both end THEN the run holds one finding for each unit that wrote a changed file

## Acceptance criteria

- OUT-AC7 (OUT-B23): Against a fake code host, a final exit of a workflow reads the recorded pull request of each run of the workflow that no earlier read found merged or closed and of no other, reads none at autonomy `record` or in a dry run, and with a code host that cannot be reached appends no entry and leaves the exit code of the run as it was
- OUT-AC8 (OUT-B24): Against a fake code host, a pull request with one review in state `changes_requested`, two review comments and a follow-up commit that changed two files, one of them written by the run, gives one entry holding its state, one review in `changes_requested`, two comments, one follow-up commit, one file and no text
- OUT-AC9 (OUT-B25): Against a fake code host, the reviews, review comments and commits of a bot account and of an author the host does not give as owner, member or collaborator, a review comment that starts with the marker line of the agent comment format, a commit with no account and a commit with two parents are in no count of an entry and leave no text in the run's local evidence, and those of a collaborator are counted
- OUT-AC11 (OUT-B27, OUT-B29): Against a fake code host that counts its calls, a pull request that holds the run's end commit followed by two commits is read with the files asked for those two commits and no other, and one that does not hold the end commit, or whose run recorded none, is read with the files of no commit asked and gives no follow-up commit
- OUT-AC12 (OUT-B28): A run of a fixture package whose steps commit, one of them through a shell command, and whose finalizer returns the url of a pull request, read against a fake code host that shows a person's follow-up commit on the file that step wrote and another on a file no step wrote, gets one `later[]` entry holding one file
- OUT-AC13 (OUT-B30): Two reads of one pull request that run at the same time against a fake code host leave one entry in the run's `later[]`, and a read that gives the state and counts of the last entry appends none
- OUT-AC14 (OUT-B31): Against a fake code host that fails for one of two recorded pull requests with an error message holding a canary, a final exit leaves one `loop_skipped` record holding the failed run's thread id, the pull request's number and the error's type name and not the canary, appends the other pull request's entry and leaves the exit code of the run unchanged
- OUT-AC15 (OUT-B32): Against a fake code host, a read that could not write the finding of an escape leaves it to the next read of the same pull request, which appends no entry, and two reads of one pull request that run at the same time leave one finding for each unit
