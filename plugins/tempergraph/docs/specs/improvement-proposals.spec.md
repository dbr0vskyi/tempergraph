# Improvement proposals and trials

## Purpose

The second half of the self-improvement loop. [SIL](self-improvement.spec.md) turns runs into findings and issues; this spec turns a cluster of findings into a proposal (a typed, small change to one workflow package), measures it in a trial (the current and the proposed version on the same fixed cases), and hands the result to a person as a draft pull request. The loop never merges, never changes engine code and never changes a step together with the gate that grades it ([ADR `improvement-closes-through-measured-proposals`](../adr/improvement-closes-through-measured-proposals.adr.md), [ADR `steps-and-their-graders-change-apart`](../adr/steps-and-their-graders-change-apart.adr.md)); trials and the post-release comparison write no code, and only the proposer writes, workflow data on its own branch (OVR-B16). The path is: findings, ranked clusters, a proposer patch on a branch, the class check, a paired trial decided by rule ([ADR `paired-trial-on-a-fixed-case-set`](../adr/paired-trial-on-a-fixed-case-set.adr.md)), a draft pull request, a person's merge, and a post-release watch. The background is [research `self-improving-agent-systems`](../research/self-improving-agent-systems.rsrch.md) and [research `self-improvement-gap-analysis`](../research/self-improvement-gap-analysis.rsrch.md); defaults without data behind them are recorded as parameters with that provenance ([IMD](improvement-data.spec.md)). Workflow owners and the people who review the loop's pull requests depend on it.

## Behaviours

### PRP-B11 Autonomy level

WHEN a workflow declares `improvement.autonomy` in its `tempergraph.json` THE engine SHALL read one of `record` (findings, evidence and ledger rows only), `file` (also file and comment on issues, the default), `propose` (also run the proposer and open a draft pull request without a trial) and `trial` (also run trials under the trial caps), let a machine lower it and never raise it (`TEMPERGRAPH_AUTONOMY`), show it in `improve backlog`, offer no level that merges, and let a person start the proposer or a trial at any level with the verbs.

- GIVEN a workflow at `trial` and `TEMPERGRAPH_AUTONOMY=file` WHEN the loop runs THEN it files issues and proposes nothing

### PRP-B12 Clusters and the ranked backlog

WHEN `improve backlog [workflow]` runs THE engine SHALL list clusters, read-only, each with `cluster_id` (a digest of side, workflow, unit and leading cause, or of unit and criterion id for judge-sent-back retries), member `findings[]` and `issues[]`, `runs`, `distinct_requests` and `machines` (from the shared store when present, else the local ledger, [IMD](improvement-data.spec.md)), `repeat_cost_usd` (estimated cost of repeats whose cause is in the cluster, 30-day window), `label_weight` (negative human labels joined to its gates, [FBK](feedback-and-judge-reliability.spec.md)), `review_weight` (kept, corroborated session-review observations, [SRV](session-review.spec.md), shown and not scored until it has data), `score` (`repeat_cost_usd + label_value × label_weight`, `label_value` $5 by default) in order, and `twin_of`, a cluster with a twin on the other side shown once under the side the friction judge attributed first with the twin linked.

- GIVEN an engine-side and a workflow-side cluster with the same unit and cause WHEN the backlog is listed THEN one is shown with the other linked

### PRP-B13 Proposal record

WHEN a proposal is recorded THE engine SHALL write `improve/proposals/<id>.json` under the state root with `proposal_id`, `workflow`, `base_version`, `base_digest`, one `cluster_id`, `author` (`person`, `proposer` or `loop`), `patch` (a unified diff over the workflow package), `classes[]` computed by the engine and never taken from the author, `side` (`producer` or `grader`) from the classes, `rule` (one sentence of the general rule, with no id, URL, number or quote), `state` (`drafted`, `refused`, `trialling`, `shown_better`, `not_shown`, `regressed`, `aborted`, `opened`, `merged`, `closed`) and `refusal` when refused.

- GIVEN a person's patch WHEN recorded THEN its classes are computed by the engine

### PRP-B14 Change classes

WHEN a patch is classified THE engine SHALL load the workflow before and after it from a scratch copy and compare them by meaning, so a reformatted or reordered file is classified by what changed and a patch with no change in meaning is refused `no_change`: producer classes `prompt` (a step's template text or tools block), `standard` (a file the package declares in `step_files`, [PKG-B13](workflow-package.spec.md), whose added lines the literals check of PRP-B3 reads too; a changed file the package does not declare is no class), `lessons` ([LSN](workflow-lessons.spec.md)), `limits` (timeout, retry budget or idle limit), `model` (alias or executor), `tools` (declared tools, MCP tools, skills or command prefixes) and `flow` (a route arm, a split into passes, a new unit); grader classes `brief`, `criterion` (text, a new criterion, a method), `check` (code or declared commands), `judge_model`, `outcome` (the outcome file, a verifier moved up the ladder with its evidence, [OUT](run-outcome.spec.md)) and `weakening` (a criterion removed, a severity lowered from blocker, a verifier moved down the ladder, a check that passes on a fixture where it failed before, a judge view set widened, or a budget raised above 2×).

- GIVEN a weakening hidden in a reordered file WHEN classified THEN `weakening` is set
- GIVEN a package that declares `standards/*.md` in `step_files` WHEN a patch adds a sentence to `standards/notes.md` THEN it is class `standard` on the producer side, and WHEN the same sentence goes to an undeclared file THEN it is refused `no_change`

### PRP-B15 Widening tools from grants

WHEN a `tools` patch is drafted from `grant_missing` findings THE proposer SHALL declare exactly the grants people gave and used, name the runs they came from, and have it opened for a person's review, never trialled alone; a judge view widened from `views.add` grants is class `weakening` ([ADR `a-person-may-grant-a-step-tools-for-a-run`](../adr/a-person-may-grant-a-step-tools-for-a-run.adr.md)).

- GIVEN a judge view widened from grants WHEN classified THEN it is `weakening`

### PRP-B1 One side only

WHEN a patch that edits a step's template and the same step's criterion text is classified THE engine SHALL find classes `prompt` and `criterion` on different sides and refuse the proposal with `mixed_sides`, trialling nothing.

- GIVEN a proposer patch with classes `prompt` and `check` WHEN classified THEN it is refused `mixed_sides`
- GIVEN a proposer patch with classes `prompt` and `lessons` WHEN classified THEN it is drafted

### PRP-B2 Weakening is person-only

WHEN a patch that lowers a criterion from blocker to warning is classified THE engine SHALL set `weakening`, refuse it with `weakening` from `author=proposer`, and from `author=person` keep it, trial it only on grader metrics, and label the pull request `weakens-gate` with the before and after severity.

- GIVEN a proposer patch with `criterion` and `weakening` WHEN classified THEN it is refused `weakening`
- GIVEN a person's patch with `criterion` and `weakening` WHEN classified THEN it is drafted and labelled

### PRP-B3 No request literals

WHEN a patch adds a ticket id, a URL or a run's request words to a prompt or lesson THE engine SHALL fail the literals check of prompt lint ([LIF](lifecycle-and-evals.spec.md)) and refuse the proposal with `literal`.

- GIVEN a lesson naming `PROJ-123` WHEN classified THEN it is refused `literal`

### PRP-B16 Other refusals

WHEN a patch touches a path outside the package, does not apply to `base_digest` or the package changed since the proposal (`evals/` being outside that digest), or yields a workflow that fails validation THE engine SHALL refuse it `outside_package`, `stale_base` (the proposer may rerun on the new version) or `invalid` with the validation output.

- GIVEN a patch over a stale base WHEN classified THEN it is refused `stale_base`

### PRP-B4 Proposer is gated like any workflow

WHEN `improve propose <cluster> [--patch <file>]` runs THE engine SHALL record a person's patch, or run the proposer (a fixed engine program: a step session in its own worktree on branch `improve/<proposal_id>` that reads the cluster's cause codes, per-criterion statuses and fixes, its member runs' local evidence and kept session-review observations, datamarked as untrusted ([SRV](session-review.spec.md)), then the engine's class check applying the patch and validating the workflow, then an independent judge grading whether the change addresses the cause and states a general rule, refusing `judge_not_met` otherwise), never writing outside the package and never pushing the default branch.

- GIVEN a proposer patch the judge finds off the cluster's cause WHEN proposed THEN it is refused `judge_not_met`

### PRP-B10 Engine side stays an issue

WHEN `improve propose` is asked for a cluster on side `engine` or `executor:<name>` THE engine SHALL refuse it with `engine_side`, drafting no engine code.

- GIVEN an engine-side cluster WHEN proposed THEN it is refused `engine_side`

### PRP-B17 Case set

WHEN a trial reads a workflow package's case set THE engine SHALL read `schema_version` and per case `case_id` (or `id`), `base` (a commit of the target repository or a fixture folder in the package), `request` (scrubbed), `expected_scope` (one line a person wrote), `origin` (`authored` or `harvested:<run id>`) and `reviewed_by`, use no harvested case without `reviewed_by`, mark a case harvested from a run in the proposal's cluster in-sample, and refuse a trial before spend with exit 2 when no reviewed case exists.

- GIVEN a case set whose only cases are unreviewed harvests WHEN a trial is asked THEN it exits 2 and spends nothing

### PRP-B18 Trial record and arms

WHEN `improve trial <proposal> [--cases <set>] [--cap <usd>]` runs THE engine SHALL write `improve/trials/<id>.json` with `trial_id`, `proposal_id`, `case_set_digest`, arms `A` (base) and `B` (patched) each run per case one at a time as an engine child run with `origin: trial`, `--dry-run` and an engine worktree at the case's base ([WTR](worktree-mode.spec.md)), `target_metric` (one of `first_pass_yield(unit)`, `gate_pass(unit)`, `criterion_met(unit, id)`, `run_cost`, `outcome_met`, `label_agreement(gate)`), `guards[]` (by default run cost +15 %, outcome met −1 case, any check pass rate −1 case, gate escapes +1), `pairs[]` (A value, B value, `win`, `loss` or `tie`, in-sample flag), `noise_floor` (the share of differing pairs in the last A/A run, or `unknown`), `decision` and `spend` (reported and estimated apart), log each session's spend like any run joined to no workflow run's cost line, and stop a case at its first pause as a tie.

- GIVEN a case that reaches a pause WHEN trialled THEN it stops and counts as a tie

### PRP-B19 Decision rule

WHEN a trial decides THE engine SHALL count out-of-sample non-tied pairs only, deciding `shown_better` when wins reach the one-sided sign-test p ≤ 0.05 count ([research `self-improvement-gap-analysis`](../research/self-improvement-gap-analysis.rsrch.md) F3) and every guard holds, `regressed` when losses reach that count or any guard fails, and `not_shown` otherwise, with reason `too_few_pairs` under 8 such pairs, adding the warning `noisy_case_set` for a noise floor above 0.5 and reporting in-sample pairs without counting them.

- GIVEN a noise floor of 0.6 WHEN decided THEN the trial carries `noisy_case_set`

### PRP-B6 Trial on paired cases

WHEN a trial on 14 out-of-sample cases with target `first_pass_yield(plan)` ends THE engine SHALL decide by PRP-B19.

- GIVEN 9 wins, 1 loss, 4 ties and guards holding WHEN decided THEN it is `shown_better`
- GIVEN 7 wins, 3 losses, 4 ties and guards holding WHEN decided THEN it is `not_shown`
- GIVEN 9 wins, 1 loss, 4 ties and cost +22 % WHEN decided THEN it is `regressed`
- GIVEN 4 wins, 1 loss, 9 ties WHEN decided THEN it is `not_shown` with `too_few_pairs`

### PRP-B5 Grader proposals are scored on labels

WHEN a proposal of side `grader` is trialled THE engine SHALL run the judge alone on the gate's calibration cases and labelled past attempts ([LIF-B15](lifecycle-and-evals.spec.md)) with target `label_agreement(gate)`, running no step session.

- GIVEN a sharper criterion text WHEN trialled THEN no step session runs

### PRP-B20 Judge-graded targets need a reliable judge

WHEN a trial's target is a judge grade (`gate_pass`, `criterion_met`, `outcome_met`) and that judge is not graded `reliable` by [FBK](feedback-and-judge-reliability.spec.md) THE engine SHALL refuse the trial before spend with exit 2.

- GIVEN an unreliable judge on a `gate_pass` target WHEN a trial is asked THEN it exits 2 and spends nothing

### PRP-B7 Cap stops a trial cleanly

WHEN both arms' estimated spend reaches the trial cap (`trial.cap_usd`, $200, per workflow `improvement.trial_cap_usd`) THE engine SHALL start no further case, let running children finish, decide `aborted` and keep the pairs so far, and refuse a trial before spend with exit 2 once the monthly cap (`trial.monthly_cap_usd`, $500, per workflow `improvement.monthly_trial_cap_usd`) is reached, the backlog showing it.

- GIVEN a $200 cap reached WHEN the next case is due THEN it does not start and the decision is `aborted`

### PRP-B21 A/A runs

WHEN `improve aa <workflow> [--cases <set>]` runs THE engine SHALL run the case set twice on the current version and record the noise floor in a trial record.

- GIVEN 2 of 14 pairs differing in an A/A run WHEN recorded THEN the noise floor is 2/14

### PRP-B8 Draft pull request, never a merge

WHEN `improve open <proposal>` runs, or a trial ends `shown_better` at autonomy `trial` THE engine SHALL push only the proposal's branch and ask the code host (the person's `gh` sign-in) for a draft pull request with the trial report (pairs as counts, metrics, spend, noise floor, classes, the rule sentence) linked to the cluster's issues, labelled `weakens-gate` when it weakens, merge nothing, leave the issues open until a person merges, and keep the proposal `shown_better` so `open` can be rerun when the code host is unreachable.

- GIVEN an unreachable code host WHEN `improve open` runs THEN the proposal stays `shown_better`

### PRP-B24 The pull request closes the cluster's issues

WHEN the engine opens a proposal's draft pull request (PRP-B8) THE engine SHALL write `Closes #<n>` in its body for each issue of the proposal's cluster that is in the pull request's repository.

- GIVEN a proposal whose cluster came from an issue `n` of the pull request's repository WHEN `improve open` runs THEN the pull request's body holds `Closes #n`
- GIVEN a cluster whose issues are `n` and `m` of that repository WHEN the pull request opens THEN the body holds `Closes #n` and `Closes #m`
- GIVEN a cluster with no issue WHEN the pull request opens THEN the body holds no `Closes` line
- GIVEN a proposal of the loop at autonomy `trial` whose trial ends `shown_better` WHEN its pull request opens THEN the body holds `Closes #<n>` for the cluster's issue

### PRP-B25 A trial's result is one comment on the cluster's issue

WHEN a trial of a proposal ends at autonomy `file` or above THE engine SHALL post its result as one comment on each issue of the proposal's cluster, in the agent comment format of `CONTRIBUTING.md` (section 5.1) with the marker `<!-- tg-agent: kind=result agent=loop -->`, holding the decision and the figures of the trial report of PRP-B8 and no run text.

- GIVEN a trial that ends `shown_better` on a cluster whose issue is `n` WHEN it ends THEN issue `n` gains one comment that starts with the marker line, ends with the generated-by footer and names `shown_better`
- GIVEN a trial that ends `not_shown`, `regressed` or `aborted` WHEN it ends THEN the issue gains one comment that names that decision
- GIVEN a cluster of two issues WHEN a trial ends THEN each issue gains one comment
- GIVEN autonomy `record` WHEN a trial ends THEN no comment is made
- GIVEN a code host that cannot be reached WHEN a trial ends THEN the trial record keeps its decision and the comment waits in the outbox of [SIL-B19](self-improvement.spec.md) for the next filing

### PRP-B22 Show a record

WHEN `improve show <proposal|trial>` runs THE engine SHALL print the one record, read-only.

- GIVEN a trial id WHEN shown THEN nothing is written

### PRP-B23 The loop's own proposals

WHEN the loop child runs in stable mode within its daily cap ([SIL](self-improvement.spec.md)) THE loop SHALL at `propose` run the proposer on the top-ranked workflow-side cluster this run's findings belong to (an `outcome_unmet:<criterion>` cluster included) and open a draft pull request, at `trial` trial that proposal under the lower of the trial cap and the day's room and open a pull request only on `shown_better`, make one proposal per workflow per day, skip a cluster with a live proposal and a day with less than `autonomy.min_room_usd` ($5) left, record `author: loop` with `loop_proposed`, `loop_trialled`, `loop_opened` or `loop_skipped`, and propose nothing in dev mode or at `record`.

- GIVEN dev mode WHEN the loop runs THEN it proposes nothing

### PRP-B26 A proposal's pull request state is read from the code host

WHEN a final exit ([SIL-B9](self-improvement.spec.md)) of a workflow with an `opened` proposal is recorded at autonomy `file` or above, outside a dry run, THE loop SHALL read the state of the proposal's draft pull request from the code host (the person's `gh` sign-in, read-only) and keep it on the proposal as `pr_state`: `open`, `merged` or `closed` (closed without a merge), `unknown` from the opening until a read has succeeded.

- GIVEN a proposal just opened WHEN it is shown THEN `pr_state` is `unknown`
- GIVEN an opened proposal whose pull request is open WHEN a final exit that raises no finding is recorded THEN `pr_state` is `open` and the proposal stays `opened`
- GIVEN an opened proposal whose pull request was closed without a merge WHEN a final exit is recorded THEN `pr_state` is `closed` and the proposal stays `opened`
- GIVEN autonomy `record`, or a dry run WHEN a final exit is recorded THEN the code host is not asked and the proposal is unchanged

### PRP-B27 A merged pull request moves its proposal to merged

WHEN the code host reports the draft pull request of an `opened` proposal merged THE loop SHALL set the proposal `merged`, with the merge time the host reports as `merged_at`.

- GIVEN an opened proposal whose pull request is merged WHEN a final exit is recorded THEN the proposal is `merged`, `pr_state` is `merged` and `merged_at` holds the host's merge time

### PRP-B28 A pull request that cannot be read leaves its proposal as it was

WHEN the state of a proposal's pull request cannot be read, because the code host cannot be reached, no `gh` is installed or signed in, or the host's answer has no known state, THE loop SHALL leave the proposal as it was and fail nothing: `pr_state` stays as it was (`unknown` until a read has succeeded), nothing is recorded as merged, and the run's exit code and the loop's other work are unchanged.

- GIVEN an opened proposal never read and a code host that cannot be reached WHEN a final exit is recorded THEN `pr_state` is `unknown`, the proposal stays `opened` and the run's exit code is unchanged
- GIVEN an opened proposal whose pull request is merged and no `gh` signed in WHEN a final exit is recorded THEN the proposal stays `opened` with no `merged_at` and the loop's other records are written as before
- GIVEN an opened proposal last read `open` and a code host that cannot be reached WHEN a final exit is recorded THEN `pr_state` stays `open`
- GIVEN the code host reachable again WHEN the next final exit is recorded THEN the merged pull request moves the proposal to `merged`

### PRP-B9 Measured after release

WHEN the first 10 final exits of real runs after a proposal's merge are recorded (`trial.after_release_runs`; runs of trials, scenarios and evals and dry runs are no real runs, [PRO-B8](promotion-check.spec.md)), at autonomy `file` or above, THE engine SHALL run the post-release comparison of [SIL-B5](self-improvement.spec.md) between the final exits of the proposal's `base_version` recorded before the merge and those 10, and record `regressed_after_release` on the proposal, with the figures before and after, when the cost per run rose by more than 15 % (`trial.guard_cost`) or the gate first-try pass rate or the met share of outcomes fell by more than `measure.quality_drop` (5 points), and `held_after_release` when none did.

- GIVEN a merged proposal whose run cost rose 30 % over 10 exits WHEN compared THEN `regressed_after_release` is recorded
- GIVEN a merged proposal whose gate first-try pass rate fell 7 points over 10 exits WHEN compared THEN `regressed_after_release` is recorded
- GIVEN a merged proposal whose cost per run rose 5 % and whose other figures held over 10 exits WHEN compared THEN `held_after_release` is recorded and `regressed_after_release` is not
- GIVEN a merged proposal with 9 final exits after its merge WHEN the 9th is recorded THEN nothing is compared and the proposal holds neither `regressed_after_release` nor `held_after_release`
- GIVEN 10 final exits after a merge, 4 of them trial runs WHEN a final exit is recorded THEN nothing is compared, as only 6 are real
- GIVEN a merge first seen with 12 final exits already after it WHEN the proposal moves to `merged` THEN its first 10 are compared at once
- GIVEN a proposal compared at its 10th exit WHEN its 11th final exit is recorded THEN nothing is compared again

### PRP-B29 A regression reopens the cluster's issues

WHEN `regressed_after_release` is recorded on a proposal THE engine SHALL reopen the issues of the proposal's cluster that are in the pull request's repository, the ones the merge closed (PRP-B24).

- GIVEN a regressed proposal whose cluster has two issues of the pull request's repository, closed by the merge WHEN the regression is recorded THEN both are open again
- GIVEN an issue of the cluster that is in another repository WHEN the regression is recorded THEN it is left as it is
- GIVEN a code host that cannot be reached WHEN the regression is recorded THEN the record stands and the reopen waits in the outbox of [SIL-B19](self-improvement.spec.md) for the next filing

### PRP-B30 A URL names a pull request

WHEN the engine takes a pull request from a text THE engine SHALL take its code host, repository (owner and name) and number from the text when the whole text is a URL with scheme `http` or `https` whose path is the owner, the name, the word `pull` and the number, in that order, and take none from any other text.

- GIVEN the text `https://code.example/team/app/pull/7` WHEN a pull request is taken from it THEN the code host is `code.example`, the repository `team/app` and the number 7
- GIVEN the text `https://code.example/team/app/issues/7` WHEN a pull request is taken from it THEN none is taken
- GIVEN the text `https://code.example/team/app/pull/7/files`, or a text that is no URL WHEN a pull request is taken from it THEN none is taken

### PRP-B31 The operator's setting lowers the autonomy at each final exit

WHEN a thread reaches a final exit ([SIL-B9](self-improvement.spec.md)) THE engine SHALL run the loop at the lowest of the workflow's declared autonomy level, the machine's `TEMPERGRAPH_AUTONOMY` and the run setting `loop_autonomy` ([RST-B20](run-settings-and-overrides.spec.md)) resolved with the settings files as they are at that moment.

- GIVEN a workflow at `file` and a thread started while no settings file names `loop_autonomy` WHEN `record` is written to a settings file and the thread then reaches its final exit THEN the loop makes no issue and no comment and records each finding it decides with the reason `autonomy_record`
- GIVEN a workflow declared at `record` and `loop_autonomy` set to `trial` WHEN a thread reaches its final exit THEN the loop runs at `record`
- GIVEN `loop_autonomy` set to `record` when a thread starts and removed before its final exit WHEN the thread reaches the exit THEN the loop runs at the workflow's declared level

## Acceptance criteria

- PRP-AC1 (PRP-B1, PRP-B2, PRP-B14): Every scenario of PRP-B1 and PRP-B2 is reproduced by the classifier on fixture patches, including a weakening hidden in a reordered file
- PRP-AC2 (PRP-B8, PRP-B4): No code path merges a pull request or pushes a default branch; a source test fails if one calls a merge
- PRP-AC3 (PRP-B6, PRP-B19): Every scenario of PRP-B6 is reproduced by the decision function
- PRP-AC4 (PRP-B20, PRP-B17, PRP-B7): A trial on a judge-graded target with an unreliable judge, with no reviewed case, or past the monthly cap spends nothing
- PRP-AC5 (PRP-B19, PRP-B17): In-sample pairs are reported and never counted in the decision
- PRP-AC6 (PRP-B18): A trial's spend is logged per session like any run and joined to no workflow run's own cost line
- PRP-AC7 (PRP-B3, PRP-B10, PRP-B11, PRP-B12, PRP-B13, PRP-B15, PRP-B16, PRP-B21, PRP-B22, PRP-B23, PRP-B5, PRP-B9): Fixtures cover each refusal, the autonomy levels, the backlog's ranking and twins, an A/A run, a grader trial, the loop's own proposals and the post-release watch
- PRP-AC8 (PRP-B24): Against a fake code host, the body of the draft pull request of a proposal whose cluster has two issues of the pull request's repository holds a `Closes #<number>` line for each, and the body of one whose cluster has no issue holds no `Closes` line
- PRP-AC9 (PRP-B25): Against a fake code host, a trial that ends in each decision leaves one comment in the agent comment format on each issue of its cluster, a trial at autonomy `record` leaves none, and an unreachable code host leaves the comment in the outbox with the trial's decision unchanged
- PRP-AC10 (PRP-B26, PRP-B27): Against a fake code host, a final exit recorded for a workflow with an opened proposal leaves it `opened` with `pr_state` `open` while its pull request is open and `closed` when that was closed without a merge, and sets it `merged` with `merged_at` when that was merged; a proposal just opened shows `pr_state` `unknown`; at autonomy `record`, and in a dry run, the host is not asked
- PRP-AC11 (PRP-B28): Against a fake code host that cannot be reached or answers with no known state, and with no `gh` installed or signed in, an opened proposal whose pull request is merged stays `opened` with the `pr_state` it had and no `merged_at`, and the run's exit code and the loop's other records are the same as without it
- PRP-AC12 (PRP-B9): Over recorded runs before and after a merge, a proposal whose cost per run rose 30 %, or whose gate first-try pass rate fell 7 points, over its first 10 final exits after the merge holds `regressed_after_release` with the figures before and after; one whose cost rose 5 % with the other figures held holds `held_after_release` and no `regressed_after_release`; one with 9 final exits after its merge, or with only 6 real runs among 10, holds neither; none is compared twice, and a merge seen late is compared on its first 10 exits after it
- PRP-AC13 (PRP-B29): Against a fake code host, the cluster issues of a regressed proposal that are in the pull request's repository are open again and those of another repository are untouched, and with a host that cannot be reached the record stands and the reopen is in the outbox
- PRP-AC14 (PRP-B14, PRP-B1, PRP-B3): In a fixture package that declares `step_files`, a patch to a declared file is drafted with the one class `standard` on the producer side, the same patch with a criterion change is refused `mixed_sides`, one that adds a literal path is refused `literal`, and a patch to an undeclared file is refused `no_change`
- PRP-AC15 (PRP-B30): The URL of a pull request gives its code host, repository and number, and the URL of an issue, a URL with a path after the number and a text that is no URL give no pull request
- PRP-AC16 (PRP-B31): Against a fake code host, a fixture thread started with no `loop_autonomy` in any settings file and ending after `record` is written to the user settings file files nothing, comments on nothing and records every finding it decides with the reason `autonomy_record`, the setting `trial` leaves a workflow declared at `record` at `record`, and removing the setting before the exit leaves the workflow's declared level

## Open questions

- Should `propose` become the default autonomy once the first workflow has a reviewed case set? Until answered: `file` stays the default. Owner: owner.
- May a trial apply a case's recorded answer at a pause? Until answered: a case stops at the first pause and counts as a tie. Owner: owner.
- Should the loop's own proposals (PRP-B23) skip a cluster whose issues the owner closed as not planned ([ISS-B3](loop-issues.spec.md))? Until answered: no, PRP-B23 is unchanged, so at autonomy `propose` or `trial` a muted cluster can still get a draft pull request. Owner: owner.
- Should a proposal whose pull request was closed without a merge move to `closed`, so that it stops being live for the loop's own proposals (PRP-B23)? Until answered: no, it stays `opened` with `pr_state` `closed`, and the loop proposes nothing new for its cluster. Owner: owner.
- Should the post-release measure be the trial's target and guards (PRP-B18), counted per run over 10 exits before and 10 after the merge, rather than the figures of SIL-B5? Until answered: the figures of SIL-B5 with the margins of PRP-B9, so that a proposal opened without a trial has a measure too. Owner: owner.
