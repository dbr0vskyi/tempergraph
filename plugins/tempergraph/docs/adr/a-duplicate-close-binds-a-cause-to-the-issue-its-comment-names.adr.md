# A close as a duplicate binds a loop issue's cause to the issue its closing comment names

## Context

[The record on a close as a duplicate](a-close-as-a-duplicate-mutes-a-loop-issues-cause.adr.md) makes that close mute the loop issue's cause because the loop could not see the issue the closed one duplicates; its `Revisit when` names the day the target becomes readable. This record extends it without editing it: a duplicate close that names no usable target still mutes, and one that names a target sends later sightings there as comments. A replay over one machine's records found 11 to 13 of 25 issues the loop would open repeating an issue a person had filed, three of them closed as duplicates with the target only in the closing comment. The decision is how the loop learns that target and where it keeps it.

## Current state

- A close as not planned or as a duplicate mutes the cause for `mute.days` and files nothing: ISS-B3, ISS-B17 and `plugins/tempergraph/engine/src/tempergraph/improve/filing.py` lines 537-540 and 615-620.
- The loop reads issues from the label list only, never a comment, and one issue by number for its state alone: ISS-B9 and `plugins/tempergraph/engine/src/tempergraph/improve/codehost.py` lines 126-145 and 157-164.
- The host's issue object and timeline name no target of a duplicate close, and the closing comment does: `batch-queue/tasks/i196.md` (the paragraph on what the code host gives without GraphQL).
- The client classes the author of a pull request's review as a person only for an owner, member or collaborator not classed as a bot: OUT-B25 and `codehost.py` lines 58-69.
- A person's issue joins a cause only with the loop's label and the cause line: ISS-B7 and `filing.py` lines 447-454.
- Comments are bounded per issue per day from the `issue_commented` records: ISS-B13 and `filing.py` lines 457-480.
- Code host reads are REST calls by list argv with a checked repository: SEC-B7 and `codehost.py` lines 96-99.
- The state root's top level lists the loop's `ledger.jsonl` and `filing-outbox.jsonl`: LOS-B7.

## Forces

- C1 (constraint): reads are REST by list argv, with no search and no GraphQL. Source: SEC-B7, ISS-B9
- C2 (constraint): only a person with standing (an owner, member or collaborator, not a bot) steers the loop. Source: OUT-B25 and the owner's design in `batch-queue/tasks/i196.md`
- C3 (constraint): the other close reasons, and a duplicate with no usable target, keep their results. Source: ISS-B3, ISS-B4, ISS-B5
- C4 (constraint): a record or a comment holds ids, numbers and times, no text of a run or of a person. Source: ISS-B10 and the sixth criterion in `batch-queue/tasks/i196.md`
- C5 (constraint): a target gets at most `seen_again.max_per_issue_per_day` comments a day, and reopening the closed issue ends the binding. Source: ISS-B13 and `a-close-as-a-duplicate-mutes-a-loop-issues-cause.adr.md`
- F1: the person names the target in words already written, so the closes made so far bind as they are.
- F2: a machine that never saw the loop issue binds the cause the same way.
- F3: fewer host reads at each filing.
- F4: a wrong binding is easy to see and to end.
- F5: no new file in the state root and no stale copy.

## Options considered

### A. Read the closing comment by REST and keep a record (chosen)

How it works: read the comments of the closed issue, take the first `duplicate of #<n>` of the newest comment by a person with standing, read that issue by number, and keep both numbers and the close time in a record of the state root, learned anew when the closed issue changes.
For: F1, F2, F3, F4. Against: F5.

### B. A hidden marker line a person pastes

How it works: the person pastes a hidden line naming the cause and the target into the closing comment, and the loop reads that line.
For: no prose to misread (F4). Against: F1, since the line sits in the loop issue's source, which the page hides, and the closes made so far carry none.

### C. The host's duplicate-of relation through GraphQL

How it works: ask GraphQL for the duplicate event of the closed issue and take the target from it.
For: no prose to misread (F4). Against: breaks C1, and the closes made so far leave no such event (F1).

### D. Read the comment at every filing, keep no record

How it works: as A without the record, reading the comments and the target at every filing.
For: F5. Against: F3, and F4 since no first learning exists to record.

## Decision

We will read the target of a close as a duplicate from the closing comment by REST and keep it in a record of the state root (option A): the first `duplicate of #<n>`, in any letter case, of the newest comment by an owner, member or collaborator on the closed issue. Later sightings comment there, at most one a day, and a close with no usable target mutes as before. The behaviours are in `cause-bindings.spec.md`.

## Decision rationale

- C1: met, both reads are REST by list argv.
- C2: met, only an author classed as a person (OUT-B25) names a target.
- C3: met, a duplicate with no usable target keeps ISS-B3 and the other reasons keep ISS-B4 and ISS-B5.
- C4: met, the text is read for a number and never kept.
- C5: met, comments on a target are within the bound of ISS-B13 and a reopened closed issue takes the comment itself.
- F1: met, the comment form of the closes made so far binds as written.
- F2: met, a machine with no record reads the host.
- F3: met in part, a usable record saves the comments read, and the target is still read at each filing because its state decides.
- F4: met in part, a `bound` result names the target and each comment names its source and how to end it, but a wrong number binds until the closed issue is reopened or a newer comment replaces it.
- F5: given up, one more top-level file and a record that can go stale, which the record behaviours of the spec check against the host.

## Consequences

- A duplicate close with a comment that names the other issue ends new issues for that cause, and later sightings reach that issue, at most one comment a day.
- The client gains two reads, the memory host gains issues without the loop's label and comments with an author kind, the state root gains `filing-bindings.json`, and the loop's results gain `bound` and `binding_unreadable`.
- A duplicate close with no such comment mutes as before.

## Risks

- A comment such as "not a duplicate of #5" on an issue closed as a duplicate names issue 5. Limited by: only a person's comment on an issue closed as a duplicate is read, each comment on a target names the closed issue and says that reopening it ends the comments, and a newer comment replaces the target. Noticed by: the `bound` result names the target and its owner sees a comment not meant for it.
- An organization member without write access names a target. Limited by: one comment a day on an issue of the same repository that says where it comes from. Noticed by: the same `bound` result.
- A target that stays open collects a comment a day while the cause recurs. Limited by: `seen_again.max_per_issue_per_day`, and closing the target as not planned mutes the cause. Noticed by: the `comment_capped` results.
- A comment of the loop on an issue that later closes as a duplicate is read as a closing comment. Limited by: a target that is the closed issue itself binds nothing (BND-B2) and the loop's opening sentence avoids the phrase the rule reads. Noticed by: a `bound` result whose target the person did not name.

## Assumptions

- A1: the design needs no REST event for the target of GitHub's own close-as-duplicate control, and whether the control leaves one is not checked, since the three closes read were made by comment. Check: close a scratch issue through the control and read `issues/<n>/events` and `issues/<n>/timeline`. If wrong: nothing breaks, and a close through the control with no typed comment mutes as before.
- A2: the host's `author_association` and account type are right, and a comment by a person with standing says what that person means, also when an agent writes it under that account. Check: read both for each comment the loop binds from. If wrong: a target nobody meant gets comments (the first risk).
- A3: people who close loop issues write `duplicate of #<n>`, as the three closes read did. Check: count `bound` against `muted` results of duplicate closes over a month. If wrong: such closes mute as before.
- A4: a `#<n>` in a comment names an issue of the same repository. Check: none needed, the form is repository-local. If wrong: a comment goes to an issue nobody meant.

## Revisit when

- The code host's REST answers for an issue or its timeline hold the target of a close as a duplicate.
- A person reports a comment sent to an issue the closing comment did not mean.
