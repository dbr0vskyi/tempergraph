# Improving workflows

Tempering a workflow means running it, measuring where it struggles, and changing it only when a change is shown to help. tempergraph records everything this needs on every run and gives every decision to you.

## What happens on its own

After every run, with no model call, the engine records findings: which gates failed, what was retried, where a person had to step in, and what it cost. When a run ends with friction, a background job judges those findings and files one de-duplicated issue per cause in the workflow's issue repository (set by `issue_repository` in the declaration, filed through a signed-in `gh`). A cause that repeats becomes a comment on its issue, never a second issue, and an issue gets at most one such comment a day. Issues never contain your request text.

An issue carries the labels `tempergraph-loop` and `needs-triage` and a label for the side that owns the fault (`side:workflow`, `side:engine` or `executor:<name>`); a workflow that triages differently lists its own names under `improvement.issue_labels` in its `tempergraph.json` (a value that is not a list of names is ignored). There is one issue per cause: the same cause at another step, or in a later run, adds a "seen again" comment to the open issue instead of a new one, at most one a UTC day for each issue (a comment over that bound is not sent and leaves a `comment_capped` record). Its body has hidden fingerprint and cause lines, then `## Summary`, `## Environment` (engine, workflow, executor and CLI versions, models, Python and OS), `## Run` (thread, exit code, cost, attempts), `## Steps to reproduce` (the `status`, `logs` and `rerun --check` commands to run on the machine that made the run), `## Run log` (an excerpt of ids, enums and numbers, never request text or model output), `## Evidence`, `## What was answered` (only for the five answer causes below: decisions by word, reasons, criterion ids with counts, items, runs and the median wait; ids, enums and numbers only), `## Fingerprint` and `## Suggested remedy`. The loop finds its issues by the `tempergraph-loop` label, so keep that label on them; to have a hand-written issue collect a cause's findings, give it the label and the cause line from a loop issue. Your close reasons teach the loop. Close an issue as not planned or as a duplicate, and the same cause opens no issue and no comment for 30 days (the finding is still recorded, as `muted`). Close it as completed, and if the cause comes back the loop opens a new issue whose Summary names the closed one as a possible regression. Reopen an issue to end a mute at once.

Two ends that have no exit of their own are handed to the same job. A thread you stop while it is paused (`resume --decision stop`, at a gate or before a unit named by `--pause-before`) is recorded as an exit with code 4. Every exit that is not a pause is a final exit: exit 0, exit 4 (a person's stop at a pause, a stop by request, the attempt cap) and exit 5 (a spent budget or the cost cap, an infra failure, a lost runner). At every final exit of a thread the job also judges the findings of the thread's earlier segments that ended in a pause and that a loop has not yet dealt with: a pause finding is handed at every final exit until a loop has dealt with it. A finding that a held job (autonomy `record` or `--dry-run`) or a judge that gave no answer left is handed again, a waiting or claimed job of the thread holds its findings, and a recorded judge answer is used without asking again. A decision may carry `resume --reason` with one of `engine_defect`, `judge_error`, `environment`, `plan`, `request` or `other` (anything else is refused); `resume --reason` is required when an agent decides at a pause (exit 2 before any change, naming the six words), and a person may omit it. The judge is told the reason and an issue's facts line shows it. For each such finding the judge is told the pause that ended its own segment (the unit, the item and the reason) and what answered it: the decision, the kind of caller, whether feedback was given and whether a ruling was given (never the text of either), the class of the decision's touch, whether the workspace changed (what the run itself committed or left uncommitted before the pause is not a change) and the verdict of the next gate of that unit and item. Its prompt also shows, for the final segment and for each of those earlier segments, the record kinds of its units and the criteria that blocked them under the segment's exit code and reason, and an issue filed for such a finding is built from that segment. An answer given by the agent that started the run is recorded as `agent_decided`, class `designed`, and never judged or filed; an answer by another agent is judged as a fault of the workflow. Five causes read the answer itself and are class `fault` whoever decided, even for the starting agent: `answer_overrode:<kind>` (a `proceed` over a failed check, environment, gap or budget), `upstream_confirmed:<unit>` (a `back:<unit>` to the unit the judgement claimed), `retry_passed_unchanged:<reason>` (a `retry` that passed with the workspace unchanged), `retry_same_failure` (a `retry` followed by a pause at the same unit and item) and `resume_no_progress` (a segment that ran no step). They file by their count with no judge answer (`resume_no_progress` on 2 in a thread), and the section `## What was answered` of their issue says what was answered. A thread whose runner was killed, crashed or cut off by a timeout writes no exit; the next `tempergraph status`, `stop` or `attention` that looks at it records it as an exit with code 5 and reason `runner_lost` and hands it over, once per thread, when its newest record is at most 7 days old. The thread stays resumable, and `status --detail` still shows it as orphaned.

A workflow in `dev` mode has no daily limit on this spending. In `stable` mode the loop stops at a daily cap, $50 by default, set by `daily_cap_usd` in the workflow or `--daily-cap` on a run.

## Hold filing

Three holds make the loop record what it finds and file nothing. None of them changes the run: its steps, checks and judges still run and spend, and the findings, the evidence and the ledger rows are written as always.

- **A setting, for a machine.** The run setting `loop_autonomy` lowers the autonomy level of a workflow (`record`, `file`, `propose` or `trial`, as `improvement.autonomy` in its `tempergraph.json` declares it) and never raises it. Write it in a settings file, under `overrides` for one workflow or under `defaults` for every workflow. `tempergraph config paths` prints where the user file (for the machine) and the project file (in the repository's state root) are. The engine reads the file at each final exit, so a run that started before you wrote the line is held too, and deleting the line ends the hold at the next exit.
- **`--dry-run`, for one thread.** `tempergraph run <workflow> '<request>' --dry-run` starts a held thread, and `tempergraph resume <workflow> <thread> --dry-run` holds one that exists. The hold starts with that call and lasts for the rest of the thread.
- **`TEMPERGRAPH_AUTONOMY=record`, for the processes that carry it.** The variable lowers the level of each run that ends in a process that has it. A run that started earlier takes the variable of the process that ends it, so for a whole machine use the setting.

```json
{"schema_version": 1,
 "overrides": [{"workflow": "<workflow>", "set": {"run.loop_autonomy": "record"}}]}
```

What a hold still runs and records. The loop child still runs its judge and any session review its plan calls for, so it still spends, and `loop.jsonl` still holds the judge's answers (`loop_judged`). At `record`, from the setting or the variable, it writes a `loop_result` record with the reason `autonomy_record` for each finding it decided on, and it files nothing, comments on nothing, reads no pull request and proposes nothing. With `--dry-run` each finding that would have filed is a `loop_result` record `would_file`, each one that would not carries the reason it was not filed, and nothing is filed, commented, read or proposed.

A thread whose last exit was held has no later exit, so nothing hands its findings on again.

**The outbox.** A payload the code host refused waits in the filing outbox and is delivered at the next filing as a comment on an open issue of its cause, or on the target of a bound cause (within the one comment a day): the waiting create of a bound cause is delivered as a comment and opens no issue. It is dropped when its cause is muted or when it was first queued more than 30 days earlier (`outbox.max_age_days`), and each drop leaves a `loop_result` record `outbox_dropped`. `tempergraph improve outbox list` prints the waiting entries without their text. `tempergraph improve outbox clear --all` or `tempergraph improve outbox clear --fingerprint <fingerprint>` removes them; neither option, or both, is refused.

A close reason holds one cause instead of a workflow: close a loop issue as not planned and for 30 days (`mute.days`) the same cause opens no issue and no comment and is recorded as `muted`. Reopen the issue to end it at once.

A close as a duplicate with a comment of yours that says `Duplicate of #<n>` binds the cause to that issue and sends the cause's later sightings to that issue as comments, at most one a day, also after `mute.days`, and opens no new issue. Note that a duplicate with no such comment mutes the cause for `mute.days` as not planned does, and that reopening the loop issue ends the binding. Also, a closed target decides by its close reason as a closed loop issue does: completed opens a new issue that names a possible regression, not planned or duplicate mutes the cause for `mute.days` from the target's close, and a target that is open again takes the comments.

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
