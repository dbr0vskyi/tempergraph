# The loop's issues

## Purpose

A repository manages its work as issues: one triage queue, one set of labels, and a close reason that says whether a thing was done or declined. The loop files its findings there ([SIL-B18](16-self-improvement.spec.md)); this spec makes a loop issue a member of that queue and lets the owner's triage teach the loop. It states the labels a loop issue carries, the sections of its body, and what the loop does when a finding returns after its issue was closed: nothing for a while after a close as not planned, and a new issue that links the old one as a possible regression after a close as completed. It sits beside [SIL](16-self-improvement.spec.md), which keeps filing and de-duplication on open issues and is near its size budget, and beside [PRP](40-improvement-proposals.spec.md), which ties proposals and trials to the same issues. The mute period is a parameter record like the loop's other thresholds ([IMD-B23](43-improvement-data.spec.md)); the reasons for its value and for the mapping of close reasons are in [the decision record](../adr/a-closed-loop-issue-mutes-its-fingerprint-or-links-a-regression.adr.md). Maintainers who triage the loop's issues and workflow owners who receive them depend on it.

## Behaviours

### ISS-B1 Triage labels

WHEN the loop opens an issue THE loop SHALL give it the labels of `issue_labels` (default `tempergraph-loop` and `needs-triage`; for a workflow-side finding the list in the workflow's `improvement.issue_labels`, for an engine or executor finding the engine's own list), `tempergraph-loop` when that list omits it, and the finding's side label: `side:engine`, `side:workflow` or `executor:<name>` ([SIL-B11](16-self-improvement.spec.md)).

- GIVEN a workflow that declares no `issue_labels` WHEN a workflow-side finding files THEN the issue carries `tempergraph-loop`, `needs-triage` and `side:workflow`
- GIVEN a workflow that declares `improvement.issue_labels` as `["triage", "bot"]` WHEN a workflow-side finding files THEN the issue carries `triage`, `bot`, `tempergraph-loop` and `side:workflow`, and not `needs-triage`
- GIVEN that workflow WHEN an engine-side finding files THEN the issue carries `tempergraph-loop`, `needs-triage` and `side:engine`
- GIVEN a finding attributed to the executor `claude` WHEN it files THEN the issue carries `tempergraph-loop`, `needs-triage` and `executor:claude`
- GIVEN a workflow whose `improvement.issue_labels` is not a list of names WHEN a workflow-side finding files THEN the issue carries the default labels

### ISS-B2 Body sections

WHEN the loop opens an issue THE loop SHALL write its body as the hidden line of [SIL-B18](16-self-improvement.spec.md) followed by the sections `## Summary` (the cause, its side, the workflow and the unit), `## Evidence` (counts, versions and pattern figures, as names and numbers), `## Fingerprint` (the fingerprint as text) and `## Suggested remedy` (the cause's drafted remedy), in that order.

- GIVEN a filed workflow-side finding WHEN its issue body is read THEN its first line is the hidden line and its headings are `## Summary`, `## Evidence`, `## Fingerprint` and `## Suggested remedy` in that order, each with text under it
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

WHEN the search for a fingerprint's closed issues fails twice THE loop SHALL open the new issue with no link and no mute and record why, as it does when the search for open issues fails ([SIL-B2](16-self-improvement.spec.md)).

- GIVEN a code host whose search of closed issues fails twice WHEN a finding that would file matches no open issue THEN a new issue opens with no link and the result records that the search failed
- GIVEN a code host whose search of closed issues fails once WHEN the same finding files THEN the search is retried and the close reason of the matching issue applies

## Acceptance criteria

- ISS-AC1 (ISS-B1): Against a fake code host, a workflow-side, an engine-side and an executor-side finding each open an issue with the default labels and their side label, a workflow's declared `issue_labels` replaces the default list for its workflow-side findings only, and a declared value that is not a list of names leaves the default labels
- ISS-AC2 (ISS-B2): Against a fake code host, the body of a filed issue starts with the hidden line and holds `## Summary`, `## Evidence`, `## Fingerprint` and `## Suggested remedy` in that order, with the fingerprint under the third and the cause's drafted remedy under the fourth
- ISS-AC3 (ISS-B3): Against a fake code host that holds an issue closed as not planned, a finding of its fingerprint opens no issue, adds no comment and is recorded `muted` when the close was 10 days ago, opens a new issue when the close was 31 days ago, comments on a second, open issue of the fingerprint instead of muting, and is muted by a later close as not planned over an earlier close as completed
- ISS-AC4 (ISS-B4): Against a fake code host that holds an issue closed as completed, a finding of its fingerprint opens one new issue whose `## Summary` names the closed issue as a possible regression, on any close date, and the next occurrence comments on that new issue and opens no third
- ISS-AC5 (ISS-B5): Against a fake code host that holds an issue closed as a duplicate, or closed with no reason, a finding of its fingerprint opens a new issue that names no regression and is not muted
- ISS-AC6 (ISS-B6): Against a fake code host whose search of closed issues fails twice, a finding opens a new issue with no link and records that the search failed, and with one failure it retries and applies the close reason

## Open questions

- Is 30 days the right mute period (`mute.days`)? Until answered: 30, a parameter record with provenance `default_no_data`, the length of the pattern rule's window ([SIL-B3](16-self-improvement.spec.md)), so that a new issue after a mute rests on runs made after the close. Owner: owner.
- Should a close as a duplicate mute like a close as not planned? Until answered: no, the reason is not read (ISS-B5), because the loop cannot see the issue it duplicates. Owner: owner.
- Should a recurrence after a close as completed also record `regressed_after_release` on the merged proposal whose pull request closed the issue ([PRP-B9](40-improvement-proposals.spec.md))? Until answered: no, ISS-B4 only links, and PRP-B9 records it from its own comparison, which waits on the merge being seen. Owner: engine owner.
- Should an operator set `issue_labels` per machine, as a run setting ([RST-B20](80-run-settings-and-overrides.spec.md))? Until answered: no, only a workflow's `improvement.issue_labels` and the engine's own list set it. Owner: owner.
