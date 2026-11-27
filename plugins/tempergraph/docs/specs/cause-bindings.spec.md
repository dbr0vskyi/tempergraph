# Bindings of a cause to an issue the loop did not open

## Purpose

A person who closes a loop issue as a duplicate says the cause is tracked in another issue; this spec states how the loop learns that issue from the closing comment, keeps it in a record of the state root, and sends the cause's later findings there as bounded comments instead of opening issues. The closed issue of a cause is the loop issue that holds the cause and closed most recently ([ISS-B3](loop-issues.spec.md)); the cause is bound when that issue was closed as a duplicate and a comment of a person on it names the issue the cause is tracked in, the target. A close as a duplicate that names no usable target mutes the cause as ISS-B3 says, and a closed target decides as a closed loop issue does. A binding here links a cause to a target and has nothing to do with the binding table of model aliases. Why the target is read from a comment and why a record is kept are in [the decision record](../adr/a-duplicate-close-binds-a-cause-to-the-issue-its-comment-names.adr.md). Maintainers who close the loop's issues and the people who own the issues they name depend on it.

## Depends on

- `loop-issues.spec.md`: the matching issue, the mute and the regression link (ISS-B3, ISS-B4, ISS-B5), the "seen again" comment (ISS-B7), the run-log excerpt (ISS-B10), the bound of comments a day (ISS-B13)
- `local-observability-store.spec.md`: the state root's top level (LOS-B7)
- `pull-request-read.spec.md`: who counts as a person (OUT-B25)
- `security.spec.md`: sanctioned launch sites of the code host client (SEC-B7)
- `self-improvement.spec.md`: an open issue of the cause takes the comment (SIL-B2); a payload the code host refused waits in the outbox (SIL-B19)
- Outside: the code host's REST interface for issues and their comments

## Does not own

- The mute after a close as not planned or as a duplicate that names no usable target, and the new issue that links a possible regression: `loop-issues.spec.md`
- The sections of a "seen again" comment and the bound of comments a day on an issue: `loop-issues.spec.md`
- Keeping a payload the code host refused and delivering it with the next filing: `self-improvement.spec.md`
- Who counts as a person: `pull-request-read.spec.md`
- The layout, the owner-only modes and the versioning of the state root: `local-observability-store.spec.md`

## Behaviours

### BND-B1 A closing comment names the target

WHEN a finding that would file matches no open issue and its cause's closed issue was closed as a duplicate THE loop SHALL take as the cause's target the first number written as `duplicate of #<n>`, in any letter case, in the newest comment on the closed issue by a person ([OUT-B25](pull-request-read.spec.md)) that holds such a number, and no target when none does.

- GIVEN a closing comment by a collaborator that names two issues after `Closing as a duplicate of` WHEN the cause files THEN its comment goes to the first issue named
- GIVEN an older comment by a person that names one issue and a newer comment by a person that names another WHEN the cause files THEN its comment goes to the issue the newer comment names
- GIVEN a comment that names an issue and an author the host does not give as an owner, member or collaborator WHEN the cause files THEN no target is named and [ISS-B3](loop-issues.spec.md) decides

### BND-B2 A number that cannot be a target binds nothing

WHEN the number taken as a cause's target (BND-B1, BND-B9) is the number of the closed issue itself, of a pull request, or of an issue the code host does not hold THE loop SHALL bind the cause to no issue and try no other number, so that ISS-B3 decides as for a close that names no target.

- GIVEN a closing comment that names the closed issue itself, the close 10 days ago WHEN the cause files THEN no comment is added to any issue and the finding is recorded `muted`
- GIVEN a closing comment that names a pull request and then an open issue WHEN the cause files THEN the open issue gets no comment
- GIVEN a closing comment that names a number the host holds no issue for, the close 31 days ago WHEN the cause files THEN a new issue opens

### BND-B3 A bound cause comments on its open target

WHEN a finding that would file matches no open issue and its cause's closed issue was closed as a duplicate whose target (BND-B1) is open THE loop SHALL open no issue and add one comment to the target within the bound of [ISS-B13](loop-issues.spec.md), whether the close was less or more than `mute.days` days ago.

- GIVEN a closed issue closed as a duplicate 10 days ago, or 31 days ago, whose comment names an open issue that carries no loop label WHEN the cause files THEN that issue gets one comment, no issue opens and the `issue_commented` record holds that issue's number
- GIVEN that closed issue reopened WHEN the cause files THEN it gets the "seen again" comment ([SIL-B2](self-improvement.spec.md)) and the target gets none
- GIVEN two causes bound to one target and an exit of each in one UTC day WHEN both file THEN the target gets one comment and the second cause leaves one `loop_result` record with op `comment_capped` that holds the target's number and no text

### BND-B4 A comment on a target says where it comes from

WHEN the loop adds a comment to a target THE loop SHALL write it as a "seen again" comment ([ISS-B7](loop-issues.spec.md)) that begins with one sentence saying it comes from tempergraph's improvement loop, naming the cause, the workflow, the units and the closed issue (`#<n>`) whose close as a duplicate sent it, and saying that reopening that issue ends the comments there, and that holds no free text of the run ([ISS-B10](loop-issues.spec.md)).

- GIVEN a bound cause with findings at two units WHEN its comment on the target is read THEN its first sentence says the comment comes from the improvement loop, names the cause, the workflow, both units and the closed issue's number, and says that reopening that issue ends the comments, and the sections of a "seen again" comment follow
- GIVEN a run whose records hold a canary in free text WHEN the comment is made THEN the canary is not in it

### BND-B5 A closed target decides as a closed issue does

WHEN a finding that would file matches no open issue and the target of its cause is closed THE loop SHALL decide as [ISS-B3, ISS-B4 and ISS-B5](loop-issues.spec.md) do, with the target in the place of the matching issue closed most recently, and read no comment of the target.

- GIVEN a target closed as completed, however long ago WHEN the cause files THEN one new issue opens whose `## Summary` names the target as a possible regression, the target gets no comment and the next finding of the cause comments on the new issue
- GIVEN a target closed as not planned, or as a duplicate of a third issue, 10 days ago WHEN the cause files THEN no issue opens, no comment is added and each finding is recorded `muted` with the target's URL
- GIVEN that target closed 31 days ago WHEN the cause files THEN a new issue opens that names no regression

### BND-B6 A binding that cannot be read stops the filing of its cause

WHEN the read of the comments of a cause's closed issue, or of the target they name, fails twice for a reason other than that the code host holds no such issue THE loop SHALL open no issue, add no comment and write one `loop_result` record with op `binding_unreadable` that holds the cause key and no text.

- GIVEN a code host whose read of the comments fails twice WHEN the cause files THEN no issue opens, no comment is added and one `binding_unreadable` record holds the cause key and no text
- GIVEN a code host whose read of the target fails twice WHEN the cause files THEN no issue opens, no comment is added and one `binding_unreadable` record is written
- GIVEN a code host whose read of the target fails once WHEN the cause files THEN the read is retried and the comment is added

### BND-B7 A learned binding is recorded

WHEN the loop learns a cause's target from the code host THE loop SHALL write one `loop_result` record with op `bound` that holds the cause key, the number of the closed issue and the number of the target, and no text.

- GIVEN a cause whose closed issue holds a person's comment that names an issue, and no record WHEN the cause files THEN one `bound` record holds the cause key and the two numbers and no text
- GIVEN that cause filing at the next exit with its record usable (BND-B9) WHEN it files THEN no second `bound` record is written
- GIVEN a newer comment by a person that names another issue WHEN the cause files THEN one `bound` record holds the new target

### BND-B8 A binding is kept in a record of the state root

WHEN the loop learns a cause's target from the code host THE loop SHALL keep it in `filing-bindings.json` at the top level of the state root ([LOS-B7](local-observability-store.spec.md)), owner-only, in a record keyed by repository and cause key that holds the numbers of the closed issue and of the target, times the host gave and no text.

- GIVEN a bound cause WHEN the state root is read THEN `filing-bindings.json` holds one record for the repository and the cause key with the two numbers and times and no word of any comment, and on POSIX the file is 0600
- GIVEN the same cause key bound in two repositories WHEN the file is read THEN it holds one record for each repository

### BND-B9 A usable record saves the read of the comments

WHEN the record of a cause names its closed issue, holds the close time the host gives for that issue and was made after the issue's newest comment THE loop SHALL take the target from the record and read no comment of the closed issue.

- GIVEN a record made at the last exit and a closed issue unchanged since WHEN the cause files THEN the comments of the closed issue are not read and the comment goes to the record's target
- GIVEN a comment by a person on the closed issue after the record was made WHEN the cause files THEN the record is not taken and BND-B10 applies

### BND-B10 A record that is not usable is replaced from the host

WHEN the record of a cause is missing, cannot be read or does not meet the conditions of BND-B9 THE loop SHALL learn the target from the comments of the cause's closed issue as BND-B1 says, write the record and go on with the filing.

- GIVEN a cause bound on one machine and a second state root with no record WHEN the cause files there THEN the same issue gets the comment and the same record is written
- GIVEN a record whose closed issue was reopened and closed anew, or that has a newer comment by a person that names another issue WHEN the cause files THEN the newer target gets the comment and the record names it
- GIVEN a record file that cannot be read WHEN the cause files THEN the filing goes on, the target is learned from the host and the file is rebuilt

### BND-B11 A waiting create of a bound cause goes to the target

WHEN the loop delivers an entry of the outbox ([SIL-B19](self-improvement.spec.md)) that would open an issue, no open loop issue holds its fingerprint lines or its cause line, and its cause is bound to an open target THE loop SHALL deliver it as one comment on the target within the bound of ISS-B13 and open no issue, whether the closed issue closed less or more than `mute.days` days ago.

- GIVEN an entry queued before its cause's loop issue was closed as a duplicate that names an open issue WHEN the next filing delivers it 31 days after the close THEN that issue gets one comment, no issue opens and the entry has left the outbox
- GIVEN that target with its comment of the UTC day made WHEN the next filing delivers the entry THEN no comment is added, one `loop_result` record with op `comment_capped` holds the target's number and no text, and the entry has left the outbox

### BND-B12 The comments of one issue are read with their authors' kinds

WHEN the loop reads the comments of one issue THE loop SHALL read every page of them through the code host's REST interface, whatever labels the issue carries, with no search and no GraphQL request, and class each comment's author as a person (OUT-B25), as a bot when the host classes the account as one, and as other in every other case.

- GIVEN an issue that carries no loop label and has comments on three pages WHEN its comments are read THEN every page is read, no search and no GraphQL request is made and each comment comes back with its text and its author's kind
- GIVEN a comment by an owner whose account the host classes as a bot, and one by a contributor WHEN the comments are read THEN the first is a bot and the second is other
- GIVEN a repository that is not `owner/name`, or an issue number that is not a whole number WHEN the comments are read THEN no request is made and the read fails ([SEC-B7](security.spec.md))

### BND-B13 One issue is read by its number

WHEN the loop reads one issue by its number THE loop SHALL read it through the code host's REST interface, whatever labels it carries, with no search and no GraphQL request, learn its state, close reason, close time, address and whether it is a pull request, and tell an issue the host does not hold (`HTTP 404`) from a read that failed.

- GIVEN a closed issue that carries no loop label, and a pull request WHEN each is read by its number THEN the first comes back with its state, close reason, close time and address and is not a pull request, and the second is reported as a pull request
- GIVEN a number the host holds no issue for WHEN it is read THEN the answer is that no such issue exists, and a read that fails for another reason is an error
- GIVEN a repository that is not `owner/name`, or a number that is not a whole number WHEN an issue is read THEN no request is made and the read fails (SEC-B7)

## Acceptance criteria

- BND-AC1 (BND-B1, BND-B3): Against a fake code host that holds a person's issue with no loop label and a loop issue of a cause closed as a duplicate by a comment of a collaborator that names that issue, a finding of the cause opens no issue and adds one comment to the person's issue when the close was 10 days ago and when it was 31 days ago, and a reopened loop issue takes the comment itself
- BND-AC2 (BND-B1): Against a fake code host, a comment that names two issues binds the cause to the first, a newer comment by a person that names another issue replaces the target, a newer comment by a person that names none changes nothing, and a comment by an author the host does not give as an owner, member or collaborator, or classes as a bot, binds nothing
- BND-AC3 (BND-B2): Against a fake code host, a closing comment whose first number is the closed issue itself, a pull request or a number the host holds no issue for binds nothing, also when the number comes from a record, so the finding is recorded `muted` while the close is under `mute.days` old and a new issue opens after it, and a second number in that comment is not tried
- BND-AC4 (BND-B6): Against a fake code host whose read of the comments, or of the target, fails twice, a finding of the cause opens no issue, adds no comment and leaves one `loop_result` record with op `binding_unreadable` that holds the cause key and no text, and with one failure the read is retried and the comment is added
- BND-AC5 (BND-B4): The comment on a target begins with one sentence that names the improvement loop, the cause, the workflow, the units and the closed issue's number and says that reopening that issue ends the comments, the sections of a "seen again" comment follow it, and a canary placed in a fixture run's free text is not in it
- BND-AC6 (BND-B3): A fixture of two causes bound to one target and two exits on one UTC day leaves one comment on the target and one `comment_capped` record that holds its number and no text for the other, and an exit on the next UTC day adds a second comment
- BND-AC7 (BND-B3, BND-B5): Against a fake code host, a target closed as completed gives one new issue whose `## Summary` names it as a possible regression and the next finding comments on that issue; a target closed as not planned or as a duplicate of a third issue 10 days ago mutes the cause, with the third issue not read, and a new issue that names no regression opens when the close was 31 days ago; a target closed with no reason or another reason gives a new issue that names no regression; a reopened target takes the comments
- BND-AC8 (BND-B7, BND-B8): The first filing of a bound cause leaves one `loop_result` record with op `bound` that holds the cause key and the two numbers and no text, and one record in `filing-bindings.json`, owner-only and keyed by repository and cause key, that holds numbers and times and no text, and a later filing with a usable record leaves no second `bound` record
- BND-AC9 (BND-B9, BND-B10): A second state root with no record and the same fake host comments on the same target and writes the same record, a record whose closed issue was reopened and closed anew is not used, a newer comment by a person that names another issue replaces the target in the record, a record file that cannot be read is rebuilt from the host with the filing going on, and a usable record leaves the comments of the closed issue unread
- BND-AC10 (BND-B11): Against a fake code host, an outbox entry that would open an issue, queued before its cause's loop issue was closed as a duplicate that names an open issue and delivered 31 days after the close, is delivered as one comment on that issue and opens no issue; with that issue's comment of the UTC day made it leaves one `comment_capped` record and no comment; the entry has left the outbox in each case
- BND-AC11 (BND-B12, BND-B13): A GitHub client with a replaced `gh` reads the comments of an issue with no loop label, and an issue by its number, through read-only REST requests, makes no search and no GraphQL request, refuses a repository that is not `owner/name` and a number that is not a whole number before any request, classes comment authors as a person, a bot or other, and tells `HTTP 404` from another failure; the fake code host answers the same two reads
- BND-AC12 (BND-B1, BND-B3): Through the loop child with a scripted judge and a fake code host, three causes that each have a person's issue with no loop label and a loop issue closed as a duplicate 31 days earlier by a comment of one of three shapes (one number, two numbers in one sentence, two numbers of which the first is also the target of another cause), a fourth cause whose loop issue was closed as a duplicate 10 days earlier with no comment and a fifth cause with no issue leave, over five exits on two UTC days, no new issue for the first four causes, at most one comment a day on each target, the fourth cause recorded `muted`, and one issue for the fifth at the exit where the pattern rule of [SIL-B3](self-improvement.spec.md) is met
