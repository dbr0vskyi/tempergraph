# A close as a duplicate mutes a loop issue's cause like a close as not planned

## Context

[The record on how a closed loop issue is read](a-closed-loop-issue-mutes-its-fingerprint-or-links-a-regression.adr.md) maps the close reason of the matching issue to what the loop does: not planned mutes, completed links a possible regression, and "another reason, or none" opens a new issue with no link and no mute (its table and its option A, "read no other reason"). It leaves open whether a close as a duplicate should mute, because the loop cannot see the issue that the closed one duplicates. This record replaces that decision for the reason `duplicate` only; the earlier record is not edited, and what it says of a close with no reason, or with a reason the loop does not read, stands.

A close as a duplicate is a close reason the code host reports. GitHub's REST API lists the values of an issue's `state_reason` as `completed`, `not_planned`, `duplicate`, `reopened` and none (https://docs.github.com/en/rest/issues/issues). The loop reads closed issues through `GET repos/<repo>/issues` and lowercases the reason (`loop_issues` in `plugins/tempergraph/engine/src/tempergraph/improve/codehost.py`, lines 126 to 145), and the engine's fake code host closes with `not_planned`, `completed`, `duplicate` or no reason (the same file, lines 336 to 341). `file` in `plugins/tempergraph/engine/src/tempergraph/improve/filing.py` (lines 400 to 411) mutes on `not_planned` and links on `completed`; a close as a duplicate falls through to a new issue.

An independent review of the loop on one machine's real records (GitHub issue 171, finding 3) found a loop issue that a person had closed as a duplicate filed again at the next exit: the person had said the cause is tracked in another issue, and the loop opened one more. The acceptance criterion written for that finding answers the question the earlier record left open: a close as a duplicate mutes as a close as not planned does.

## Decision

We will treat a close as a duplicate as the loop treats a close as not planned (option A). When no matching issue is open and the matching issue closed most recently was closed as a duplicate less than `mute.days` (30) days ago, the loop opens no issue and adds no comment, and records the finding `muted` with the closed issue's URL ([ISS-B3](../specs/loop-issues.spec.md)). A close with no reason, or with a reason the loop does not read, still opens a new issue ([ISS-B5](../specs/loop-issues.spec.md)).

## Options considered

### A. Mute after a duplicate like after not planned (chosen)

For: a person who closes a loop issue as a duplicate says the cause is already tracked, so a new issue at the next exit asks the person to close the same thing again; the same period and the same parameter, `mute.days`, apply and no new vocabulary is needed; reopening the issue ends the mute at once, as it does for not planned. Against: the loop cannot see the issue that this one duplicates, so a cause whose tracked issue is later fixed stays muted until the period ends, and a cause that is muted by a duplicate close is not commented on the issue that tracks it.

### B. Read no other reason (the earlier record's option A)

For: no change, and no assumption about what a duplicate means. Against: a cause that a person has closed as a duplicate opens a new issue at every exit after the first, so the person closes the same cause again and again.

### C. Treat a duplicate like a close as completed

For: the closed issue stays in view as a link. Against: a close as a duplicate says the cause is tracked elsewhere, not that it was fixed, so a "possible regression" link names a fault that was never declared fixed.

### D. Follow the duplicate to the issue it names

For: the loop could comment on the tracking issue and mute only while that issue is open. Against: it needs a further read of the code host for each matching issue, only some hosts report the target, the target can be in another repository, and the loop's reads of issues are bounded to its own label list ([ISS-B9](../specs/loop-issues.spec.md)).

## Consequences

- The behaviours are [ISS-B3 and ISS-B5](../specs/loop-issues.spec.md), which hold no open question on a duplicate close, and the guide `plugins/tempergraph/docs/guides/improving-workflows.guide.md` says that a close as not planned or as a duplicate mutes a cause.
- The finding is still recorded on every run and listed by `improve backlog`, so a muted cause stays visible to a person.
- Risk: a duplicate close whose target is itself declined or forgotten hides a real fault for up to `mute.days`; reopening the issue ends the mute at once.
- Risk: the host may report a duplicate close for an issue closed by mistake; the same reopening ends it.

## Revisit when

The owner finds that a duplicate close should follow its target, or the host reports the target in the listing the loop already reads.
