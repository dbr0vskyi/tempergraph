# The loop's issues

## Purpose

A repository manages its work as issues: one triage queue, one set of labels, and a close reason that says whether a thing was done or declined. The loop files its findings there ([SIL-B18](16-self-improvement.spec.md)); this spec makes a loop issue a member of that queue and lets the owner's triage teach the loop. It states the labels a loop issue carries, the sections of its body and the run context they hold, which issue a finding goes to (one per cause, found from the loop's label list), and what the loop does when a finding returns after its issue was closed: nothing for a while after a close as not planned, and a new issue that links the old one as a possible regression after a close as completed. It sits beside [SIL](16-self-improvement.spec.md), which keeps filing and de-duplication on open issues and is near its size budget, and beside [PRP](40-improvement-proposals.spec.md), which ties proposals and trials to the same issues. The mute period is a parameter record like the loop's other thresholds ([IMD-B23](43-improvement-data.spec.md)); the reasons for its value and for the mapping of close reasons are in [the decision record](../adr/a-closed-loop-issue-mutes-its-fingerprint-or-links-a-regression.adr.md), and those for one issue per cause, the label list and the run context in [the second](../adr/one-loop-issue-per-cause-read-from-the-label-list.adr.md). Maintainers who triage the loop's issues and workflow owners who receive them depend on it.

## Behaviours

### ISS-B1 Triage labels

WHEN the loop opens an issue THE loop SHALL give it the labels of `issue_labels` (default `tempergraph-loop` and `needs-triage`; for a workflow-side finding the list in the workflow's `improvement.issue_labels`, for an engine or executor finding the engine's own list), `tempergraph-loop` when that list omits it, and the finding's side label: `side:engine`, `side:workflow` or `executor:<name>` ([SIL-B11](16-self-improvement.spec.md)).

- GIVEN a workflow that declares no `issue_labels` WHEN a workflow-side finding files THEN the issue carries `tempergraph-loop`, `needs-triage` and `side:workflow`
- GIVEN a workflow that declares `improvement.issue_labels` as `["triage", "bot"]` WHEN a workflow-side finding files THEN the issue carries `triage`, `bot`, `tempergraph-loop` and `side:workflow`, and not `needs-triage`
- GIVEN that workflow WHEN an engine-side finding files THEN the issue carries `tempergraph-loop`, `needs-triage` and `side:engine`
- GIVEN a finding attributed to the executor `claude` WHEN it files THEN the issue carries `tempergraph-loop`, `needs-triage` and `executor:claude`
- GIVEN a workflow whose `improvement.issue_labels` is not a list of names WHEN a workflow-side finding files THEN the issue carries the default labels

### ISS-B2 Body sections

WHEN the loop opens an issue THE loop SHALL write its body as the hidden line of [SIL-B18](16-self-improvement.spec.md), the cause line of ISS-B7 and the hidden lines of any further fingerprints, followed by the sections `## Summary` (the cause, its side, the workflow and every unit), `## Environment`, `## Run`, `## Steps to reproduce` and `## Run log` (ISS-B8, ISS-B10), `## Evidence` (each unit's count, fingerprint and pattern figures, as names and numbers), `## Fingerprint` (the fingerprints and the cause key as text) and `## Suggested remedy` (the cause's drafted remedy), in that order.

- GIVEN a filed workflow-side finding WHEN its issue body is read THEN its first line is the hidden line, its second the cause line, and its headings are `## Summary`, `## Environment`, `## Run`, `## Steps to reproduce`, `## Run log`, `## Evidence`, `## Fingerprint` and `## Suggested remedy` in that order, each with text under it
- GIVEN that body WHEN its `## Fingerprint` section is read THEN it shows the fingerprint of the hidden line, and its `## Suggested remedy` section shows the cause's drafted remedy

### ISS-B3 A close as not planned mutes the fingerprint

WHEN a finding that would file matches no open issue and the matching issue closed most recently was closed as not planned less than `mute.days` (30) days ago THE loop SHALL open no issue and add no comment, and record the finding `muted` with that issue's URL.

- GIVEN an issue of the fingerprint closed as not planned 10 days ago and none open WHEN the finding files THEN no issue and no comment is made, and the finding is recorded `muted` with the closed issue's URL
- GIVEN that issue closed as not planned 31 days ago WHEN the finding files THEN a new issue opens and the finding is not muted
- GIVEN that issue closed 10 days ago and a second issue of the fingerprint open WHEN the finding files THEN the open issue gets one "seen again" comment ([SIL-B2](16-self-improvement.spec.md)) and the finding is not muted
- GIVEN an issue closed as completed 40 days ago and a later issue of the fingerprint closed as not planned 5 days ago WHEN the finding files THEN the finding is recorded `muted`

### ISS-B4 A close as completed links a possible regression

WHEN a finding that would file matches no open issue and the matching issue closed most recently was closed as completed THE loop SHALL open a new issue whose `## Summary` names the closed issue as a possible regression.

- GIVEN an issue of the fingerprint closed as completed and none open WHEN the finding files THEN a new issue opens with the labels of ISS-B1 and its `## Summary` names the closed issue (`#<n>`) as a possible regression, and the closed issue gets no comment
- GIVEN that issue closed as completed 200 days ago WHEN the finding files THEN a new issue opens with the same link
- GIVEN the new issue is open WHEN the fingerprint recurs THEN the new issue gets one "seen again" comment and no third issue opens

### ISS-B5 A close reason the loop does not read changes nothing

WHEN a finding that would file matches no open issue and the matching issue closed most recently has no close reason, or one other than not planned and completed, THE loop SHALL open a new issue that names no regression and mutes nothing.

- GIVEN an issue of the fingerprint closed as a duplicate and none open WHEN the finding files THEN a new issue opens whose `## Summary` names no regression and the finding is not muted
- GIVEN an issue of the fingerprint closed with no reason WHEN the finding files THEN a new issue opens whose `## Summary` names no regression and the finding is not muted

### ISS-B6 A failed search of closed issues files anyway

WHEN the read of the loop's closed issues (ISS-B9) fails twice THE loop SHALL open the new issue with no link and no mute and record why, as it does when the search for open issues fails ([SIL-B2](16-self-improvement.spec.md)).

- GIVEN a code host whose search of closed issues fails twice WHEN a finding that would file matches no open issue THEN a new issue opens with no link and the result records that the search failed
- GIVEN a code host whose search of closed issues fails once WHEN the same finding files THEN the search is retried and the close reason of the matching issue applies

### ISS-B7 One issue per cause

WHEN findings would file THE loop SHALL send each to the oldest open loop issue whose body holds its fingerprint's hidden line, else to the oldest whose body holds its cause line `<!-- tempergraph:cause=<key> -->` (the key being a digest of side, workflow and cause, without the unit), and SHALL make one issue or one "seen again" comment for all findings of one cause key in one filing, listing every unit; the closed issues of ISS-B3 to ISS-B6 match the same way, and the title names the workflow and the cause, not a unit.

- GIVEN one run whose cause `judge_unread_pass` would file at the units `plan`, `expand` and `phase` WHEN the loop files THEN one issue opens whose Summary names the three units and whose body holds the three fingerprints' hidden lines, and the other two findings are recorded `grouped` with its URL
- GIVEN that issue open WHEN a later run's same cause files at the unit `code` THEN the issue gets one "seen again" comment naming `code` and no issue opens
- GIVEN an open issue filed before this behaviour, with only a fingerprint's hidden line WHEN that fingerprint files THEN it gets the comment
- GIVEN the cause's issue closed as not planned 5 days ago WHEN the cause files at two other units THEN both are recorded `muted`

### ISS-B8 Environment, run and steps to reproduce

WHEN the loop opens an issue or adds a "seen again" comment THE loop SHALL write under `## Environment` the engine version of the run and of the loop, the workflow version, the executors, their CLI versions, the models, aliases and efforts of the units' sessions, the loop's judge executor, the improvement mode, and the Python version, operating system and architecture of the machine; under `## Run` the run's thread, segment start, exit code and reason, run cost, the units' session cost and attempts, the request digest, the run it reran and the machine id; and under `## Steps to reproduce` the `tempergraph status`, `tempergraph logs` and `tempergraph rerun --check` commands for that thread and unit, and where the request and session logs stay; each only as read from the run log and the machine, a value it cannot read being left out.

- GIVEN a run whose log records engine 0.3.0, executor `claude` at CLI 2.1.330 and model `claude-opus-4-5` WHEN its finding files THEN `## Environment` shows each of them and the loop's own engine version
- GIVEN that run, which exited 0 as `finished` at 1.25 USD WHEN its finding files THEN `## Run` shows the thread, the exit code, the reason and the cost, and `## Steps to reproduce` shows `tempergraph status <thread> --detail --unit <unit>`
- GIVEN that issue open WHEN the finding files again THEN the comment holds `## Environment`, `## Run`, `## Steps to reproduce`, `## Run log` and `## Evidence`

### ISS-B9 The loop's issues are read from the label list

WHEN the loop looks for the issues of ISS-B7 THE loop SHALL read the repository's open, and when none matches its closed, issues that carry `tempergraph-loop`, through the code host's list of issues by label (on GitHub the REST issues endpoint, page by page), never its search index, once per repository and state in one filing, and match their hidden lines on the machine.

- GIVEN three findings of three causes in one filing WHEN the loop files THEN the open list and the closed list are each read once
- GIVEN an issue the loop opened in an earlier filing WHEN the same fingerprint files a moment later THEN it is found and commented on
- GIVEN the GitHub code host WHEN it reads the loop's issues THEN it calls the REST issues endpoint with the label and the state, with no search and no GraphQL, and leaves out pull requests

### ISS-B10 A run-log excerpt with no free text

WHEN the loop writes `## Run log` THE loop SHALL show the last segment's run-log records of the findings' units and the run's start and exit, one line each, at most 40 (saying how many earlier records were left out), each line holding only its time, kind, unit and the values of a fixed list of keys whose value is a number, a boolean, or an id, enum, version or model name of at most 64 characters with no space or slash, or a list or map of those; changed paths show only as their number.

- GIVEN a run log whose records hold a canary in the request, a check's notes, a judge's gap, a session's transcript path and a changed path WHEN its finding files THEN the canary is in no issue or comment
- GIVEN 55 records of the unit WHEN the excerpt is written THEN it holds the last 40 and says 16 were left out
- GIVEN a record of another unit WHEN the excerpt is written THEN it is not shown

## Acceptance criteria

- ISS-AC1 (ISS-B1): Against a fake code host, a workflow-side, an engine-side and an executor-side finding each open an issue with the default labels and their side label, a workflow's declared `issue_labels` replaces the default list for its workflow-side findings only, and a declared value that is not a list of names leaves the default labels
- ISS-AC2 (ISS-B2): Against a fake code host, the body of a filed issue starts with the hidden line and the cause line and holds `## Summary`, `## Environment`, `## Run`, `## Steps to reproduce`, `## Run log`, `## Evidence`, `## Fingerprint` and `## Suggested remedy` in that order, with the fingerprint under `## Fingerprint` and the cause's drafted remedy under the last
- ISS-AC3 (ISS-B3): Against a fake code host that holds an issue closed as not planned, a finding of its fingerprint opens no issue, adds no comment and is recorded `muted` when the close was 10 days ago, opens a new issue when the close was 31 days ago, comments on a second, open issue of the fingerprint instead of muting, and is muted by a later close as not planned over an earlier close as completed
- ISS-AC4 (ISS-B4): Against a fake code host that holds an issue closed as completed, a finding of its fingerprint opens one new issue whose `## Summary` names the closed issue as a possible regression, on any close date, and the next occurrence comments on that new issue and opens no third
- ISS-AC5 (ISS-B5): Against a fake code host that holds an issue closed as a duplicate, or closed with no reason, a finding of its fingerprint opens a new issue that names no regression and is not muted
- ISS-AC6 (ISS-B6): Against a fake code host whose search of closed issues fails twice, a finding opens a new issue with no link and records that the search failed, and with one failure it retries and applies the close reason
- ISS-AC7 (ISS-B7): Against a fake code host, one cause at three units in one filing opens one issue naming the three units with their three hidden lines, a later unit of the cause comments on it, an issue with only a fingerprint line takes that fingerprint's comments, another cause opens its own issue, and a cause closed as not planned 5 days ago is muted at other units
- ISS-AC8 (ISS-B8): Against a fake code host and a fixture run log, an issue shows the run's and the loop's engine versions, the workflow version, executor, CLI version, model, alias, mode, Python and OS, the thread, exit code, reason and cost, and the status, logs and rerun commands of its thread and unit, and a "seen again" comment holds the same sections; end to end, a loop child's issue shows the engine version, the thread and run-log lines
- ISS-AC9 (ISS-B9): Against a fake code host, one filing of three causes reads the open and the closed list once each, and an issue opened by one filing is commented on by the next; the GitHub client calls the REST issues endpoint with the loop's label and state, no search, and leaves out pull requests
- ISS-AC10 (ISS-B10): A canary placed in a fixture run log's request, notes, evidence, gap, transcript, changed paths and in free-text values of listed keys reaches no issue or comment, the excerpt keeps the last 40 lines and counts the rest, and another unit's records are not shown

## Open questions

- Is 30 days the right mute period (`mute.days`)? Until answered: 30, a parameter record with provenance `default_no_data`, the length of the pattern rule's window ([SIL-B3](16-self-improvement.spec.md)), so that a new issue after a mute rests on runs made after the close. Owner: owner.
- Should a close as a duplicate mute like a close as not planned? Until answered: no, the reason is not read (ISS-B5), because the loop cannot see the issue it duplicates. Owner: owner.
- Should a recurrence after a close as completed also record `regressed_after_release` on the merged proposal whose pull request closed the issue ([PRP-B9](40-improvement-proposals.spec.md))? Until answered: no, ISS-B4 only links, and PRP-B9 records it from its own comparison. Owner: engine owner.
- Should an operator set `issue_labels` per machine, as a run setting ([RST-B20](80-run-settings-and-overrides.spec.md))? Until answered: no, only a workflow's `improvement.issue_labels` and the engine's own list set it. Owner: owner.
