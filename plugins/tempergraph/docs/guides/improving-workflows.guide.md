# Improving workflows

Tempering a workflow means running it, measuring where it struggles, and changing it only when a change is shown to help. tempergraph records everything this needs on every run and gives every decision to you.

## What happens on its own

After every run, with no model call, the engine records findings: which gates failed, what was retried, where a person had to step in, and what it cost. When a run ends with friction, a background job judges those findings and files one de-duplicated issue per cause in the workflow's issue repository (set by `issue_repository` in the declaration, filed through a signed-in `gh`). A cause that repeats becomes a comment on its issue, never a second issue. Issues never contain your request text.

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

Each trial ends in a recorded result, so you open only changes that measurably help. After a change merges, the next runs are compared with the old version, and a quality drop reopens the issue.

## 4. Review sessions

To see how a run's sessions actually went, step by step:

```sh
tempergraph improve review <workflow>/<task> --dry-run   # what the review would read, no spend
tempergraph improve review <workflow>/<task>
```

## 5. Revise the outcome

Runs also collect evidence that the outcome itself is wrong: a criterion that never fails, one people keep overriding, or a gap that keeps showing up. See it with `tempergraph outcome candidates <workflow>`, then revise the outcome as described in [Authoring workflows](authoring-workflows.guide.md#revise-a-workflow).

## How much babysitting

The aim is a workflow that needs less of you over time:

```sh
tempergraph report --supervision     # how often runs needed a person, and for what
tempergraph report --loop            # what the self-improvement loop did and spent
tempergraph supervision show         # the cost of supervising runs
```
