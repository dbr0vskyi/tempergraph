# One loop issue per cause, read from the label list, with the run's context

## Context

The owner, reviewing the loop's issues on 2026-11-25, found duplicates and issues too thin to act on, and asked that the loop never open a duplicate, comment on the existing issue instead, and give each issue every detail that helps a later fix or analysis: versions, environment, steps to reproduce and run logs.

What the repository held that day: four loop issues from one temperspec run, #114, #115 and #116 with the cause `judge_unread_pass` at the units `plan`, `expand` and `phase`, and #117 with `check_fail:phase`. Each body named the cause, the unit, the workflow version and a count of 1, and nothing else.

Three causes, read in the code:

1. The fingerprint is side, workflow, cause and unit (`fingerprint` in `plugins/tempergraph/engine/src/tempergraph/improve/record.py`), and [SIL-B2](../specs/self-improvement.spec.md) matched only that fingerprint. One cause at three units of one run is three fingerprints, so it opened three issues, each a duplicate to the person who triages them.
2. The open and closed issues were found with `gh issue list --search '"tempergraph:fp=…" in:body'`. That goes through GitHub's search index and GraphQL. In this project's cloud sessions GraphQL is refused (`gh` exits 1; checked on 2026-11-25 with the loop's own call), so every search failed, and by SIL-B2 the loop then filed anyway: every recurrence would have been a new issue. On a machine where search works, the index lags behind a new issue, so a recurrence filed minutes later can miss it too.
3. The body was built from the finding alone (`body` in `filing.py`), which holds the cause, unit, counts and the workflow version. The run log (`run.jsonl`) beside it holds the engine version, the executor and its CLI version, the models, attempts, check results, judge statuses, exit code and cost, and the issue showed none of them.

[The earlier record](a-closed-loop-issue-mutes-its-fingerprint-or-links-a-regression.adr.md) chose to read closed issues through `gh issue list`. This record replaces that choice of read; its mapping of close reasons stands.

The privacy rule stays: no request text in any issue or comment ([SIL-AC2](../specs/self-improvement.spec.md)), and the evidence file is never opened by filing code.

## Decision

We will key a loop issue by its cause, read the loop's issues from the label list, and fill each issue and comment from the run log through an allow-list (options A, C and E; behaviours [ISS-B7 to ISS-B10](../specs/loop-issues.spec.md)):

- A second hidden line, `<!-- tempergraph:cause=<key> -->`, where the key is side, workflow and cause without the unit. A finding goes to the open issue that holds its fingerprint line, else to the one that holds its cause line. The findings of one cause in one filing make one issue or one comment that lists every unit. The fingerprint stays as it is everywhere else (ledger, proposals, trials).
- The issues are read with the REST list endpoint, filtered on the `tempergraph-loop` label every loop issue carries ([ISS-B1](../specs/loop-issues.spec.md)), once per repository and state in a filing, and matched on their hidden lines on the machine.
- A body and a "seen again" comment carry Environment, Run, Steps to reproduce and Run log sections, built by `issue_context` from fixed record keys whose values are ids, enums, numbers, versions or model names. Any other value, and any value with a space or a slash in it, is left out.

## Options considered

### A. One issue per cause, units listed in it

For: what the owner calls a duplicate is the same cause at another unit; one issue gives one place to triage, close or mute it, and a remedy usually fixes it at every unit. Against: a cause that needs a different fix per unit holds them in one issue, and a close as not planned mutes the cause at every unit. A person can still split an issue by hand.

### B. Keep one issue per fingerprint, and link the siblings

For: no change to what a mute covers. Against: the three issues of 2026-11-25 would still be three, each with links; the owner asked for no duplicates.

### C. Read the label list, not the search index

For: works with only REST access, sees an issue the moment it exists, and costs one read per repository and state instead of one search per finding. Against: a closed list grows; at 100 issues a page it stays a few calls for years of loop issues. An issue a person wrote by hand is matched only once it carries the label and a hidden line.

### D. Keep search, and retry longer

For: no change. Against: does not help where GraphQL is refused, and the index lag stays.

### E. Context from the run log through an allow-list

For: the run log already holds what a fixer asks first (versions, models, attempts, checks, statuses, exit code, cost), and an allow-list of keys and value shapes keeps request text, model output, judge notes, check output and paths out, which a canary test holds. Against: an issue shows engine records, not the session's own output; steps to reproduce name the commands that show the rest on the machine that ran it.

### F. Attach the session logs or the evidence

For: the most context. Against: they hold request text and model output, which [SIL-B8](../specs/self-improvement.spec.md) and SIL-AC2 keep on the machine, and an issue can be read by anyone who can read the repository.

## Consequences

- One cause makes one open issue and comments; the duplicates of 2026-11-25 do not recur, and filing works where only REST reaches GitHub.
- Issues filed before this change hold only a fingerprint line. They still take their fingerprint's comments; a new unit of their cause opens one new issue with a cause line, and every later unit comments there.
- A close as not planned now mutes the cause at every unit for `mute.days`. Risk: a person who meant to decline one unit only declines all. Limited by the 30-day mute and by reopening, which ends it at once.
- Risk: a key added to the allow-list later could carry free text. Limited by the value-shape check, which drops any value with a space or a slash, and by the canary test.

## Revisit when

A workflow owner asks for separate issues per unit of one cause, or a code host other than GitHub is supported.
