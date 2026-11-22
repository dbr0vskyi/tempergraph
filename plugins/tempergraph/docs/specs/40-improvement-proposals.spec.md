# Improvement proposals and trials

## Purpose

The second half of the self-improvement loop. [SIL](16-self-improvement.spec.md) turns runs into findings and issues; this spec turns a cluster of findings into a proposal (a typed, small change to one workflow package), measures it in a trial (the current and the proposed version on the same fixed cases), and hands the result to a person as a draft pull request. The loop never merges, never changes engine code and never changes a step together with the gate that grades it ([ADR-0030](../adr/0030-improvement-closes-through-measured-proposals.adr.md), [ADR-0031](../adr/0031-steps-and-their-graders-change-apart.adr.md)); trials and the post-release comparison write no code, and only the proposer writes, workflow data on its own branch (OVR-B16). The path is: findings, ranked clusters, a proposer patch on a branch, the class check, a paired trial decided by rule ([ADR-0034](../adr/0034-paired-trial-on-a-fixed-case-set.adr.md)), a draft pull request, a person's merge, and a post-release watch. The background is [R-030](../research/R-030-self-improving-agent-systems.rsrch.md) and [R-031](../research/R-031-self-improvement-gap-analysis.rsrch.md); defaults without data behind them are recorded as parameters with that provenance ([IMD](43-improvement-data.spec.md)). Workflow owners and the people who review the loop's pull requests depend on it.

## Behaviours

### PRP-B11 Autonomy level

WHEN a workflow declares `improvement.autonomy` in its `tempergraph.json` THE engine SHALL read one of `record` (findings, evidence and ledger rows only), `file` (also file and comment on issues, the default), `propose` (also run the proposer and open a draft pull request without a trial) and `trial` (also run trials under the trial caps), let a machine lower it and never raise it (`TEMPERGRAPH_AUTONOMY`), show it in `improve backlog`, offer no level that merges, and let a person start the proposer or a trial at any level with the verbs.

- GIVEN a workflow at `trial` and `TEMPERGRAPH_AUTONOMY=file` WHEN the loop runs THEN it files issues and proposes nothing

### PRP-B12 Clusters and the ranked backlog

WHEN `improve backlog [workflow]` runs THE engine SHALL list clusters, read-only, each with `cluster_id` (a digest of side, workflow, unit and leading cause, or of unit and criterion id for judge-sent-back retries), member `findings[]` and `issues[]`, `runs`, `distinct_requests` and `machines` (from the shared store when present, else the local ledger, [IMD](43-improvement-data.spec.md)), `repeat_cost_usd` (estimated cost of repeats whose cause is in the cluster, 30-day window), `label_weight` (negative human labels joined to its gates, [FBK](41-feedback-and-judge-reliability.spec.md)), `review_weight` (kept, corroborated session-review observations, [SRV](44-session-review.spec.md), shown and not scored until it has data), `score` (`repeat_cost_usd + label_value × label_weight`, `label_value` $5 by default) in order, and `twin_of`, a cluster with a twin on the other side shown once under the side the friction judge attributed first with the twin linked.

- GIVEN an engine-side and a workflow-side cluster with the same unit and cause WHEN the backlog is listed THEN one is shown with the other linked

### PRP-B13 Proposal record

WHEN a proposal is recorded THE engine SHALL write `improve/proposals/<id>.json` under the state root with `proposal_id`, `workflow`, `base_version`, `base_digest`, one `cluster_id`, `author` (`person`, `proposer` or `loop`), `patch` (a unified diff over the workflow package), `classes[]` computed by the engine and never taken from the author, `side` (`producer` or `grader`) from the classes, `rule` (one sentence of the general rule, with no id, URL, number or quote), `state` (`drafted`, `refused`, `trialling`, `shown_better`, `not_shown`, `regressed`, `aborted`, `opened`, `merged`, `closed`) and `refusal` when refused.

- GIVEN a person's patch WHEN recorded THEN its classes are computed by the engine

### PRP-B14 Change classes

WHEN a patch is classified THE engine SHALL load the workflow before and after it from a scratch copy and compare them by meaning, so a reformatted or reordered file is classified by what changed and a patch with no change in meaning is refused `no_change`: producer classes `prompt` (a step's template text or tools block), `lessons` ([LSN](42-workflow-lessons.spec.md)), `limits` (timeout, retry budget or idle limit), `model` (alias or executor), `tools` (declared tools, MCP tools, skills or command prefixes) and `flow` (a route arm, a split into passes, a new unit); grader classes `brief`, `criterion` (text, a new criterion, a method), `check` (code or declared commands), `judge_model`, `outcome` (the outcome file, a verifier moved up the ladder with its evidence, [OUT](90-run-outcome.spec.md)) and `weakening` (a criterion removed, a severity lowered from blocker, a verifier moved down the ladder, a check that passes on a fixture where it failed before, a judge view set widened, or a budget raised above 2×).

- GIVEN a weakening hidden in a reordered file WHEN classified THEN `weakening` is set

### PRP-B15 Widening tools from grants

WHEN a `tools` patch is drafted from `grant_missing` findings THE proposer SHALL declare exactly the grants people gave and used, name the runs they came from, and have it opened for a person's review, never trialled alone; a judge view widened from `views.add` grants is class `weakening` ([ADR-0080](../adr/0080-a-person-may-grant-a-step-tools-for-a-run.adr.md)).

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

WHEN a patch adds a ticket id, a URL or a run's request words to a prompt or lesson THE engine SHALL fail the literals check of prompt lint ([LIF](18-lifecycle-and-evals.spec.md)) and refuse the proposal with `literal`.

- GIVEN a lesson naming `PROJ-123` WHEN classified THEN it is refused `literal`

### PRP-B16 Other refusals

WHEN a patch touches a path outside the package, does not apply to `base_digest` or the package changed since the proposal (`evals/` being outside that digest), or yields a workflow that fails validation THE engine SHALL refuse it `outside_package`, `stale_base` (the proposer may rerun on the new version) or `invalid` with the validation output.

- GIVEN a patch over a stale base WHEN classified THEN it is refused `stale_base`

### PRP-B4 Proposer is gated like any workflow

WHEN `improve propose <cluster> [--patch <file>]` runs THE engine SHALL record a person's patch, or run the proposer (a fixed engine program: a step session in its own worktree on branch `improve/<proposal_id>` that reads the cluster's cause codes, per-criterion statuses and fixes, its member runs' local evidence and kept session-review observations, datamarked as untrusted ([SRV](44-session-review.spec.md)), then the engine's class check applying the patch and validating the workflow, then an independent judge grading whether the change addresses the cause and states a general rule, refusing `judge_not_met` otherwise), never writing outside the package and never pushing the default branch.

- GIVEN a proposer patch the judge finds off the cluster's cause WHEN proposed THEN it is refused `judge_not_met`

### PRP-B10 Engine side stays an issue

WHEN `improve propose` is asked for a cluster on side `engine` or `executor:<name>` THE engine SHALL refuse it with `engine_side`, drafting no engine code.

- GIVEN an engine-side cluster WHEN proposed THEN it is refused `engine_side`

### PRP-B17 Case set

WHEN a trial reads a workflow package's case set THE engine SHALL read `schema_version` and per case `case_id` (or `id`), `base` (a commit of the target repository or a fixture folder in the package), `request` (scrubbed), `expected_scope` (one line a person wrote), `origin` (`authored` or `harvested:<run id>`) and `reviewed_by`, use no harvested case without `reviewed_by`, mark a case harvested from a run in the proposal's cluster in-sample, and refuse a trial before spend with exit 2 when no reviewed case exists.

- GIVEN a case set whose only cases are unreviewed harvests WHEN a trial is asked THEN it exits 2 and spends nothing

### PRP-B18 Trial record and arms

WHEN `improve trial <proposal> [--cases <set>] [--cap <usd>]` runs THE engine SHALL write `improve/trials/<id>.json` with `trial_id`, `proposal_id`, `case_set_digest`, arms `A` (base) and `B` (patched) each run per case one at a time as an engine child run with `origin: trial`, `--dry-run` and an engine worktree at the case's base ([WTR](82-worktree-mode.spec.md)), `target_metric` (one of `first_pass_yield(unit)`, `gate_pass(unit)`, `criterion_met(unit, id)`, `run_cost`, `outcome_met`, `label_agreement(gate)`), `guards[]` (by default run cost +15 %, outcome met −1 case, any check pass rate −1 case, gate escapes +1), `pairs[]` (A value, B value, `win`, `loss` or `tie`, in-sample flag), `noise_floor` (the share of differing pairs in the last A/A run, or `unknown`), `decision` and `spend` (reported and estimated apart), log each session's spend like any run joined to no workflow run's cost line, and stop a case at its first pause as a tie.

- GIVEN a case that reaches a pause WHEN trialled THEN it stops and counts as a tie

### PRP-B19 Decision rule

WHEN a trial decides THE engine SHALL count out-of-sample non-tied pairs only, deciding `shown_better` when wins reach the one-sided sign-test p ≤ 0.05 count ([R-031](../research/R-031-self-improvement-gap-analysis.rsrch.md) F3) and every guard holds, `regressed` when losses reach that count or any guard fails, and `not_shown` otherwise, with reason `too_few_pairs` under 8 such pairs, adding the warning `noisy_case_set` for a noise floor above 0.5 and reporting in-sample pairs without counting them.

- GIVEN a noise floor of 0.6 WHEN decided THEN the trial carries `noisy_case_set`

### PRP-B6 Trial on paired cases

WHEN a trial on 14 out-of-sample cases with target `first_pass_yield(plan)` ends THE engine SHALL decide by PRP-B19.

- GIVEN 9 wins, 1 loss, 4 ties and guards holding WHEN decided THEN it is `shown_better`
- GIVEN 7 wins, 3 losses, 4 ties and guards holding WHEN decided THEN it is `not_shown`
- GIVEN 9 wins, 1 loss, 4 ties and cost +22 % WHEN decided THEN it is `regressed`
- GIVEN 4 wins, 1 loss, 9 ties WHEN decided THEN it is `not_shown` with `too_few_pairs`

### PRP-B5 Grader proposals are scored on labels

WHEN a proposal of side `grader` is trialled THE engine SHALL run the judge alone on the gate's calibration cases and labelled past attempts ([LIF-B15](18-lifecycle-and-evals.spec.md)) with target `label_agreement(gate)`, running no step session.

- GIVEN a sharper criterion text WHEN trialled THEN no step session runs

### PRP-B20 Judge-graded targets need a reliable judge

WHEN a trial's target is a judge grade (`gate_pass`, `criterion_met`, `outcome_met`) and that judge is not graded `reliable` by [FBK](41-feedback-and-judge-reliability.spec.md) THE engine SHALL refuse the trial before spend with exit 2.

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

### PRP-B22 Show a record

WHEN `improve show <proposal|trial>` runs THE engine SHALL print the one record, read-only.

- GIVEN a trial id WHEN shown THEN nothing is written

### PRP-B23 The loop's own proposals

WHEN the loop child runs in stable mode within its daily cap ([SIL](16-self-improvement.spec.md)) THE loop SHALL at `propose` run the proposer on the top-ranked workflow-side cluster this run's findings belong to (an `outcome_unmet:<criterion>` cluster included) and open a draft pull request, at `trial` trial that proposal under the lower of the trial cap and the day's room and open a pull request only on `shown_better`, make one proposal per workflow per day, skip a cluster with a live proposal and a day with less than `autonomy.min_room_usd` ($5) left, record `author: loop` with `loop_proposed`, `loop_trialled`, `loop_opened` or `loop_skipped`, and propose nothing in dev mode or at `record`.

- GIVEN dev mode WHEN the loop runs THEN it proposes nothing

### PRP-B9 Measured after release

WHEN the first 10 final exits of a merged proposal's new version are recorded THE engine SHALL run the post-release comparison of [SIL-B5](16-self-improvement.spec.md) on the trial's target and guards, and on a guard worse than its margin reopen the issues and record `regressed_after_release` on the proposal.

- GIVEN a merged proposal whose run cost rose 30 % over 10 exits WHEN compared THEN the issues reopen and `regressed_after_release` is recorded

## Acceptance criteria

- PRP-AC1 (PRP-B1, PRP-B2, PRP-B14): Every scenario of PRP-B1 and PRP-B2 is reproduced by the classifier on fixture patches, including a weakening hidden in a reordered file
- PRP-AC2 (PRP-B8, PRP-B4): No code path merges a pull request or pushes a default branch; a source test fails if one calls a merge
- PRP-AC3 (PRP-B6, PRP-B19): Every scenario of PRP-B6 is reproduced by the decision function
- PRP-AC4 (PRP-B20, PRP-B17, PRP-B7): A trial on a judge-graded target with an unreliable judge, with no reviewed case, or past the monthly cap spends nothing
- PRP-AC5 (PRP-B19, PRP-B17): In-sample pairs are reported and never counted in the decision
- PRP-AC6 (PRP-B18): A trial's spend is logged per session like any run and joined to no workflow run's own cost line
- PRP-AC7 (PRP-B3, PRP-B10, PRP-B11, PRP-B12, PRP-B13, PRP-B15, PRP-B16, PRP-B21, PRP-B22, PRP-B23, PRP-B5, PRP-B9): Fixtures cover each refusal, the autonomy levels, the backlog's ranking and twins, an A/A run, a grader trial, the loop's own proposals and the post-release watch

## Open questions

- Should `propose` become the default autonomy once the first workflow has a reviewed case set? Until answered: `file` stays the default. Owner: owner.
- May a trial apply a case's recorded answer at a pause? Until answered: a case stops at the first pause and counts as a tie. Owner: owner.
- Not built yet: PRP-B9 waits on the merge being seen, since `pr_state` is not derived in release 1 ([FBK](41-feedback-and-judge-reliability.spec.md)); `regressed_after_release` is not recorded yet. Owner: engine owner.
