# Improving workflows

Tempering a workflow means running it, measuring where it struggles, and changing it only when a change is shown to help. tempergraph records everything this needs on every run and gives every decision to you.

## What happens on its own

After every run, with no model call, the engine records findings: which gates failed, what was retried, where a person had to step in, and what it cost. When a run ends with friction, a background job judges those findings and files one de-duplicated issue per cause in the workflow's issue repository (set by `issue_repository` in the declaration, filed through a signed-in `gh`). A cause that repeats becomes a comment on its issue, never a second issue. Issues never contain your request text.

An issue carries the labels `tempergraph-loop` and `needs-triage` and a label for the side that owns the fault (`side:workflow`, `side:engine` or `executor:<name>`); a workflow that triages differently lists its own names under `improvement.issue_labels` in its `tempergraph.json` (a value that is not a list of names is ignored). There is one issue per cause: the same cause at another step, or in a later run, adds a "seen again" comment to the open issue instead of a new one. Its body has hidden fingerprint and cause lines, then `## Summary`, `## Environment` (engine, workflow, executor and CLI versions, models, Python and OS), `## Run` (thread, exit code, cost, attempts), `## Steps to reproduce` (the `status`, `logs` and `rerun --check` commands to run on the machine that made the run), `## Run log` (an excerpt of ids, enums and numbers, never request text or model output), `## Evidence`, `## Fingerprint` and `## Suggested remedy`. The loop finds its issues by the `tempergraph-loop` label, so keep that label on them; to have a hand-written issue collect a cause's findings, give it the label and the cause line from a loop issue. Your close reasons teach the loop. Close an issue as not planned, and the same cause opens no issue and no comment for 30 days (the finding is still recorded, as `muted`). Close it as completed, and if the cause comes back the loop opens a new issue whose Summary names the closed one as a possible regression. Reopen an issue to end a mute at once.

Two ends that have no exit of their own are handed to the same job. A thread you stop while it is paused (`resume --decision stop`, at a gate or before a unit named by `--pause-before`) is recorded as an exit with code 4. At every final exit of a thread (exit 0, a person's stop, a lost runner) the job also judges the findings of the thread's earlier segments that ended in a pause and that no earlier job of the thread was handed, once per thread, and the judge is told for each what answered the pause: the decision, the kind of caller, whether feedback was given (never its text), whether the workspace changed and the verdict of the unit's next gate. A thread whose runner was killed, crashed or cut off by a timeout writes no exit; the next `tempergraph status`, `stop` or `attention` that looks at it records it as an exit with code 5 and reason `runner_lost` and hands it over, once per thread, when its newest record is at most 7 days old. The thread stays resumable, and `status --detail` still shows it as orphaned.

A workflow in `dev` mode has no daily limit on this spending. In `stable` mode the loop stops at a daily cap, $50 by default, set by `daily_cap_usd` in the workflow or `--daily-cap` on a run.

## 1. Label judgements

Judges are only as good as their agreement with you. Tell the engine when you agree or disagree with a gate's verdict:

```sh
tempergraph labels queue <workflow>                             # judgements waiting for a label
tempergraph label <thread> <step> --value agree|disagree [--criterion <id>]
tempergraph labels grades <workflow>                            # each judge's reliability grade
```

## 2. Calibrate judges

Gold labels are your expected verdict on a reviewed case. Scoring a judge runs it on those cases and compares:

```sh
tempergraph evals label <workflow>/<gate>/<case> --criterion <id> --expected MET|PARTIAL|UNMET --reason '…'
tempergraph evals score <workflow> <gate> --cap 2     # spends, capped
tempergraph evals bar <workflow>                      # each gate: accepted or not, and why
```

A workflow should move to `stable` mode only once its judges clear the bar. That move is always the owner's decision.

## 3. Review proposals

From the filed causes, the loop groups problems into clusters, drafts changes and measures them:

```sh
tempergraph improve backlog <workflow>                  # clusters worth working on
tempergraph improve propose <workflow> <cluster>        # draft a change
tempergraph improve trial <proposal> --cap 5            # paired trial: old against new, capped
tempergraph improve show <proposal|trial>
tempergraph improve open <proposal>                     # open the change for your review
```

Each trial ends in a recorded result, so you open only changes that measurably help. A drafted change may edit a step's prompt and the files your package lists under `step_files` in its `tempergraph.json` (for example `["rules/*.rule.md"]`): the standards and rule files its steps are told to read. A change to any other file of the package is refused as no change. An opened change writes `Closes #<n>` for each issue of its cluster that lives in the same repository, so merging it closes them, and a finished trial leaves one comment with its decision and figures on each of those issues (none when the machine's autonomy is `record`). After a change merges, the next runs are compared with the old version, and a quality drop reopens the issue.

## 4. Review sessions

To see how a run's sessions actually went, step by step:

```sh
tempergraph improve review <workflow>/<task> --dry-run   # what the review would read, no spend
tempergraph improve review <workflow>/<task>
tempergraph improve review show <workflow>/<task>        # the reviews that failed, and why
```

A review can fail, for example because the signed-in account has used up its allowance. A failed review is never silent:

- `tempergraph improve review show <workflow>/<task>` lists the reviews that failed.
- `tempergraph attention` shows a loop whose reviews failed, with the failed reviews counted by class (`usage_limit`, `unparsed`, and so on), even when the loop found nothing. A loop that read nothing is not shown as a loop that found nothing.
- When a review failed on a usage limit and the reset the executor reported is within six hours, the background loop waits for the reset and runs that review once more. The retry is recorded, and the loop's summary is written after it.
- A review that is not retried stays failed: when no reset time was reported, when the reset is more than six hours away, and always when you run `tempergraph improve review` yourself, which never waits. After the reset, run `tempergraph improve review <workflow>/<task>` again.

## 5. Revise the outcome

Runs also collect evidence that the outcome itself is wrong: a criterion that never fails, one people keep overriding, or a gap that keeps showing up. When a run's finalizer opened a pull request, the loop also reads the review of an owner, member or collaborator of the repository through `gh` (not a bot, and not the loop's own marked comments; counts and kinds only; review text stays in the run's local evidence), and a `met` run that was sent back (rerun, a `changes_requested` review, or a follow-up commit on a file the run wrote; the files the run wrote are those that differ between its branch start and its end commit, whatever tool or command changed them) is shown as an escape by `outcome show` and `outcome candidates`. See it with `tempergraph outcome candidates <workflow>`, then revise the outcome as described in [Authoring workflows](authoring-workflows.guide.md#revise-a-workflow).

## How much babysitting

The aim is a workflow that needs less of you over time:

```sh
tempergraph report --supervision     # how often runs needed a person, and for what
tempergraph report --loop            # what the self-improvement loop did and spent
tempergraph supervision show         # the cost of supervising runs
```

## 6. Run the eval suite

Cases live in the package's `evals/`. A regression case must pass; a capability case measures.

```sh
tempergraph evals run <workflow> --kind check        # no model
tempergraph evals run <workflow> --kind judge --cap 2
tempergraph evals report <workflow>
tempergraph evals harvest <workflow> <gate>          # turn labelled judgements into cases
tempergraph evals harvest <workflow> outcome         # also a candidate for each escape (no text)
```

## 7. Promote a workflow

A workflow starts in the `local-dev` stage, where the engine offers a stronger model and you decide. When it has earned it, promote it:

```sh
tempergraph promote-check <workflow> --to local-stable            # read-only: each criterion, met or not
tempergraph promote-check <workflow> --to local-stable --stamp    # write the stamp when all are met
```

The check reads your runs: enough of them, judges accepted by calibration, the suite passing, and how much of a person's time a run still takes.

## 8. Keep up with the engine

```sh
tempergraph update --check          # is a newer engine staged?
tempergraph update                  # install it beside the current one and switch; --rollback goes back
tempergraph upgrade <workflow> --check
tempergraph upgrade <workflow>      # on a branch: deterministic rewrites first, a gated workflow for the rest
```

A paused run stays on the engine it started on unless the new one can resume it.
