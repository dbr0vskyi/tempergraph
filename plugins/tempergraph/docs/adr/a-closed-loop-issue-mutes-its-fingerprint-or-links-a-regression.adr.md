# A closed loop issue mutes its fingerprint or links a possible regression

## Context

The loop de-duplicates a finding against open issues only. `GhCodeHost.search` in `plugins/tempergraph/engine/src/tempergraph/improve/codehost.py` (lines 72 to 77) lists `--state open` issues, and `file` in `plugins/tempergraph/engine/src/tempergraph/improve/filing.py` (lines 169 to 186) comments on a match or opens an issue ([SIL-B2](../specs/self-improvement.spec.md)). Once an issue is closed, the next occurrence of its fingerprint opens a new issue that says nothing of the first, whatever the reason the first was closed. The fingerprint holds side, workflow, leading cause and step, and no version (SIL-B2).

The repository has made GitHub issues its one list of scope, and its guide says how a person triages the loop's issues: `CONTRIBUTING.md` (section 2, Triage) says "Close an issue as `not planned` when it will not be built. The improvement loop reads close reasons (#1)", and section 5.4 says the loop's issues are triaged like any other. [R-160](../research/R-160-does-the-improvement-loop-find-what-a-reviewer-finds.rsrch.md) F7 records that overnight the loop filed nothing; issue 1 asks that the issues it does file sit in the same queue and that the owner's close reasons teach it.

The store already names the same two readings for the loop's own metrics: `fixed` (closed by a merged change) and `noise` (closed as not planned) ([IMD-B9](../specs/improvement-data.spec.md)). Release 1 reads neither, and who reads them on a team is open there. This record concerns the read the loop makes when it is about to file, on the machine that files.

The code host is GitHub through the person's `gh` (`codehost.py`, module docstring). The GitHub CLI manual lists `stateReason` and `closedAt` among the JSON fields of `gh issue list`, and its `--state` takes `open`, `closed` or `all` (https://cli.github.com/manual/gh_issue_list). The two reasons the repository's guide asks people to choose between are completed and not planned. A host can report another reason (a close as a duplicate) or none, and the loop cannot list the reasons of every host. The exact spelling of the values is for the code step to read from the host's output and pin in a fixture; this record names them in words.

The loop's other windows are 30 days: `pattern_rule.window_days` ([SIL-B3](../specs/self-improvement.spec.md)) and `cost.window_days` (`plugins/tempergraph/engine/src/tempergraph/improve/params.py`, lines 24 and 29). A threshold of the loop is a parameter record with provenance `default_no_data` until data fits it ([IMD-B23](../specs/improvement-data.spec.md)). The owner was away, so the period below is such a default.

## Decision

We will read the close reason of the matching issue that closed most recently, when no matching issue is open, and map it to the loop's action as follows (option A; the behaviours are [ISS-B3 to ISS-B6](../specs/loop-issues.spec.md)):

| What the loop finds | What the loop does |
|---|---|
| An open issue of the fingerprint | The "seen again" comment of SIL-B2, unchanged |
| Closed as not planned, less than `mute.days` ago | Nothing is opened or commented; the finding is recorded `muted` |
| Closed as not planned, `mute.days` or more ago | A new issue, with no link |
| Closed as completed, at any age | A new issue whose Summary names the closed issue as a possible regression |
| Closed with another reason, or none | A new issue, with no link and no mute |
| The search of closed issues fails twice | A new issue, with no link and no mute, and the failure recorded |

- `mute.days` is a parameter record, 30 days, provenance `default_no_data`. It counts from the close time the host reports, not from the loop's first read.
- The close that decides is the latest one. An open issue wins over any closed one, so a person ends a mute at once by reopening the issue.
- A close as completed carries no age limit and no version check. The new issue says "possible", and a person decides.
- The link is a link only. It records nothing on a proposal; `regressed_after_release` stays with the measured comparison of [PRP-B9](../specs/improvement-proposals.spec.md).

## Options considered

### A. Read the latest close; mute 30 days after not planned; link after completed; read no other reason (chosen)

For: it uses the two reasons the repository's guide already tells people to choose between, so the owner teaches the loop with one gesture and no new vocabulary, label or comment syntax. A mute that ends needs no action. A completed close keeps the history of a fault in view instead of opening a stranger issue. Thirty days is the length of the pattern rule's window, so after a mute ends a new issue rests on runs made after the owner's decision. Against: one more search per finding that would file; a mute hides a returning fault for up to 30 days; and a completed close with no fix (the host's default close) makes the next occurrence a linked issue.

### B. Mute until a person reopens the issue

For: it respects the owner's decision for good and is the simplest rule. Against: the loop could never raise a declined fault again, even when it has grown or the workflow has changed, and the issue asks for a period.

### C. A short mute of 7 days

For: a worsening fault resurfaces soon. Against: a declined fault returns every week with `needs-triage`, so the owner declines the same fault weekly, and the pattern rule's window of 30 days still holds runs from before the close.

### D. A long mute of 90 days

For: the fewest repeats. Against: a quarter is long for a fault declined for a reason that passes, such as a release or a change of model, and no data supports a value above the loop's other windows.

### E. Mute until the workflow's version changes

For: it ties the decision to what the owner judged, because a new version can carry the fault or remove it. Against: the fingerprint holds no version, a version changes on edits unrelated to the cause so the mute would lapse at random, and a workflow never released would stay muted. It can refine option A later.

### F. Read nothing back (today)

For: no new read of the code host and no new behaviour. Against: a declined issue returns as a new issue at the next occurrence, so the owner declines the same thing again and again, and a recurrence after a fix has no link to it.

### G. One reaction to every close

For: one rule. Against: muting after every close loses the regression signal of a completed close, and linking after every close nags the owner after a close as not planned.

## Consequences

- A person teaches the loop with the gesture the guide already asks for. The loop's issues carry the repository's triage labels and fixed sections ([ISS-B1, ISS-B2](../specs/loop-issues.spec.md)), so they sit in the same queue as every other issue.
- The loop reads the code host once more for each finding that would file and matches no open issue. The code host's interface and its fake grow by one read of closed issues with their reason and close time.
- Risk: a mute hides a real fault. The finding is still recorded on every run and listed by `improve backlog`, the mute lapses after 30 days, and reopening the issue ends it at once.
- Risk: a close as completed without a fix makes every later occurrence a linked new issue. The link says "possible", and a person closes the new issue as not planned to mute it.
- Risk: a recurrence on a workflow version older than the fix opens a possible regression that is not one. The Evidence section of the issue names the workflow version so a person can compare; the loop does not (option E).
- Risk: a host that reports no reason, or one the loop does not read, gives no signal, and the loop then behaves as it did before this record: a new issue with no link.
- Risk: a failed search of closed issues files anyway, which can break a mute once. The rule is the one SIL-B2 has for a failed search of open issues, and a failure of the search usually fails the create too, which goes to the outbox ([SIL-B19](../specs/self-improvement.spec.md)).
- The loop's own proposals ([PRP-B23](../specs/improvement-proposals.spec.md)) do not yet respect a mute; the proposals spec holds that as an open question.
- `mute.days` must exist as a parameter record with a provenance ([IMD-AC3](../specs/improvement-data.spec.md)).

## Revisit when

The owner finds 30 days too short or too long, a muted fingerprint is declined again and again, the loop's own proposals should respect a mute, the host reports a reason the loop should read, or the merge of a proposal is seen ([PRP-B9](../specs/improvement-proposals.spec.md)) and a regression link can name its proposal.
