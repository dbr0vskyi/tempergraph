# Self-improvement loop

## Purpose

A built-in program that reads every finished run's record, judges it with an independent judge, and files, comments on or only records a finding in the repository that owns the fault: the engine's or the workflow's. It is inside the engine so every run is analyzed without an optional install ([ADR `workflows-as-data`](../adr/workflows-as-data.adr.md)); it runs as a detached child and never pauses. The loop closes through people: an issue is evidence, not an order, and a measurement call never writes code. It is the first half of the loop: clusters of its findings become measured proposals ([PRP](improvement-proposals.spec.md)), human ground truth becomes labels and judge grades ([FBK](feedback-and-judge-reliability.spec.md)), its data needs are [IMD](improvement-data.spec.md), what it reads from sessions is [SRV](session-review.spec.md), and how its issues are labelled, written and read back is [ISS](loop-issues.spec.md). Workflow owners, the engine's maintainers and operators who read the issues depend on it. Its thresholds are parameter records with provenance `default_no_data` ([IMD-B23](improvement-data.spec.md)), to be revisited with real runs.

## Behaviours

### SIL-B8 Records on every exit

WHEN a run exits THE engine SHALL write, with no model call, the findings `runs/<workflow>/<task>/findings.json` (signal and step names, cause codes, counts, executor names, published only as metadata; one document per thread that each segment appends to), the local evidence file `runs/<workflow>/<task>/evidence/record.json` (request, outputs, scrubbed feedback, never published), both owner-only ([LOS-B7, LOS-B8, LOS-B9](local-observability-store.spec.md)), one ledger row (names, counts, hashes, executor and CLI versions, no text), the session digests ([SRV-B11](session-review.spec.md)), and a `finding_recorded` run-log record with the causes, sides and, at a final exit, the lenses.

- GIVEN a run that exits 5 WHEN recording finishes THEN `findings.json`, `evidence/record.json` and one ledger row exist and no session ran
- GIVEN a paused run resumed and finished WHEN its findings are read THEN both segments appended to the one document

### SIL-B1 Detached and best effort

WHEN a final exit's friction lens fires on at least one fault, its outcome lens has candidates, or its session review plan has a depth THE engine SHALL write a hand-off ticket (ids, enums, the state root path and the fingerprints, never request text) to `improve/tickets/` under the home and start the loop child detached through the detached child launcher ([SEC-B7](security.spec.md)), and the child's failure SHALL never change the parent's exit code.

- GIVEN a run that exits 0 and a loop child that crashes WHEN the parent's exit code is read THEN it is 0
- GIVEN `TEMPERGRAPH_LOOP=inline` WHEN the run exits THEN the loop runs in-process; with `off` it does not run

### SIL-B9 Final exits

WHEN the loop decides which exits are final THE engine SHALL treat every exit that is not a pause (exit 0, 4 or 5) as final.

- GIVEN a run that pauses (exit 3) WHEN it exits THEN no lens of a final exit runs

### SIL-B10 Lenses

WHEN a final exit is judged THE loop SHALL apply the friction lens (where the process hurt and whose fault: every flagged final exit in dev mode; in stable mode a `tool_access` pause or tool grant, spent retries or a stop, an uncleared failed step, a gap escalation, repeated blockers, a retry burst, cost above the version's p90, a new version's first five runs, or a person pushing back), the outcome lens (read from the run's outcome record, [OUT-B18, OUT-B19](run-outcome.spec.md): every final exit in dev mode; in stable mode a person pushing back, a pass at judge confidence at most 0.5, every 20th clean run, or an earlier run whose pull request this exit's read has shown to be an escape, which gets the finding of SIL-B33 and one `loop_lens` record and starts no session), the cost lens (every 10th final exit of a version), the session lens (digest causes on every exit, a model review only on a plan, [SRV-B13, SRV-B14, SRV-B15, SRV-B16, SRV-B5](session-review.spec.md)) and the per-gate quality scorecard (reported for every gate; a gate's rows may file only while its judge binding is graded `reliable`, [FBK-B5](feedback-and-judge-reliability.spec.md)).

- GIVEN stable mode and a clean run that is the 20th since the last outcome review WHEN it exits THEN the outcome lens runs
- GIVEN a gate whose judge binding is not `reliable` WHEN its scorecard rows show a drop THEN they are reported and not filed
- GIVEN stable mode and an earlier `met` run whose pull request this exit reads with a review in state `changes_requested` WHEN the exit is recorded THEN the exit's `loop.jsonl` holds one `loop_lens` record for the outcome lens with the trigger `outcome_escape` and that run's thread, the run holds its finding, and no session starts

### SIL-B11 Fault sides

WHEN a cause is classified THE loop SHALL take cause codes from run-log and session-digest names and numbers only ([SRV-B12](session-review.spec.md)), class each `fault`, `infra` or `designed`, attribute a fault to `engine`, `workflow`, `executor:<name>` (an unknown event or message shape, a tool name outside the catalog, a refused flag or option, an API error type the classifier does not list) or `host` (the host-speed preflight warned, or timeouts sorted `slow_host`, [OBS](observability-and-cost.spec.md)), file executor-side issues to the engine's repository with an executor label, and record host findings only.

- GIVEN a timeout on a host whose preflight warned WHEN classified THEN the finding is `host` and nothing is filed

### SIL-B4 Executor drift is visible

WHEN sessions show a tool name the executor's view catalog does not map THE loop SHALL attribute cause `unknown_tool_name:<name>` to `executor:<name>` with the CLI version from the session's `agent_run` record, and not blame the workflow.

- GIVEN runs on `antigravity` after a CLI update whose sessions call an unmapped tool WHEN friction is judged THEN the finding is `executor:antigravity` with the CLI version

### SIL-B12 What a friction finding carries

WHEN a friction finding is made THE loop SHALL carry the cause code's fixed remedy and, where the fault is in a prompt or check, the file and the kind of change (a person decides; the loop opens no pull request); mark three or more retries of one unit in one visit `retry_burst` with the blockers' criterion ids, and a judge-sent-back retry `judge_blocked:<criterion id>` ([PRP-B12](improvement-proposals.spec.md)); and mark a pause on `BLOCKED:` whose check ran no command and read no file as the workflow fault `blocked_without_check`.

- GIVEN a unit retried three times in one visit WHEN its finding is made THEN it carries `retry_burst` with the criterion ids
- GIVEN a `BLOCKED:` pause whose check ran nothing WHEN classified THEN the fault is the workflow's `blocked_without_check`

### SIL-B23 A repeated check failure is a finding

WHEN a run exits after its gate escalated with cause `check_repeat` ([BUD-B16](budgets-and-failures.spec.md)) THE loop SHALL make a friction finding `check_repeat` on that unit, a fault of the workflow with no evidence text and the fixed remedy that a person decides whether the check, the environment or the prompt is wrong.

- GIVEN a run that paused on `check_repeat` at unit `code` WHEN it exits THEN the findings of `code` carry `check_repeat` and the exit's `finding_recorded` record names it

### SIL-B13 Outcome evidence

WHEN the outcome lens judges a run THE loop SHALL include the run branch's commits, changed paths and diff stat, and spend no session of its own: its candidates from the outcome gate's judge are the final criteria it graded `UNMET` or `PARTIAL`, recorded as `outcome_unmet:<criterion>` on the `outcome` unit.

- GIVEN a final criterion graded `UNMET` WHEN the outcome lens runs THEN `outcome_unmet:<criterion>` is recorded and no judge session starts

### SIL-B33 An escape is a finding on the units that wrote the changed files

WHEN a read of a run's pull request ends and the pull request has shown the run to be an escape (OUT-B26) THE outcome lens SHALL record for that run, in dev and in stable mode and with no model call, a finding `outcome_escape` of the workflow's side, once for each unit whose step sessions changed a file the run wrote that a follow-up commit changed ([OUT-B28](pull-request-read.spec.md)), by any tool or command and committed or not, or for the `outcome` unit when none did.

- GIVEN stable mode and a `met` run whose pull request a read shows with a review in state `changes_requested` and no follow-up commit WHEN the read ends THEN one finding `outcome_escape` is recorded for the `outcome` unit and no session starts
- GIVEN a follow-up commit that changed a file unit `a` wrote through a shell command and a file unit `b` wrote with an editing tool WHEN a read shows it THEN a finding `outcome_escape` is recorded for `a` and for `b`
- GIVEN a run that an earlier read showed with a review in state `changes_requested` WHEN a later read shows a follow-up commit on a file unit `a` wrote THEN the run holds one finding for `a` beside the one for the `outcome` unit, and a read after that, showing more changes to files `a` wrote, records none

### SIL-B34 An escape files by the pattern rule

WHEN an `outcome_escape` finding would file THE loop SHALL apply the pattern rule of SIL-B3 to it and not the calibration test of SIL-B7.

- GIVEN `outcome_escape` findings for one unit of three runs with three distinct requests in 30 days and an outcome judge with no calibration score WHEN filing runs THEN one issue is filed
- GIVEN such findings of two runs WHEN filing runs THEN they are recorded and nothing is filed

### SIL-B14 Tool access and grants

WHEN a run had a `tool_access` pause or a tool grant ([RST-B28, RST-B29, RST-B30](run-settings-and-overrides.spec.md)) THE loop SHALL make a friction finding `tool_access:<refusal class>` ([TSA-B7](tool-surface-audit.spec.md)), write each grant and allowed command as one entry of the ledger row's `grants[]` (unit, capability or prefix, the refusal class it answered, `via` `cli`, `orchestration` or `profile`, whether a later attempt called it, the unit's outcome after it), make a grant a passing attempt used a workflow finding `grant_missing` whose remedy is the declaration, record a grant never called as `grant_unused` without filing, and cluster both by workflow, unit and capability.

- GIVEN `--grant code=shell` used by a passing attempt WHEN the loop runs THEN a `grant_missing` finding is made for `code`
- GIVEN the same grant on five runs on three machines WHEN the pattern rule runs THEN one issue is filed

### SIL-B15 Agent rescues and supervision

WHEN an agent decided a `rescue` touch on its own ([SUP-B9](supervision-metrics.spec.md), [PRV-B14](caller-provenance.spec.md)) THE loop SHALL make a friction finding `agent_decided:<pause cause>` clustered by workflow, unit and pause cause, file a workflow issue whose remedy is a check or an environmental cause for a cluster whose decisions were mostly `proceed` with no workspace change, write `supervision{}` on the ledger row, and show supervision cost in the cost lens as its own figure, never in run cost ([SCO](supervision-cost.spec.md)).

- GIVEN ten agent `proceed` rescues on unit `test` with no workspace change WHEN clustered THEN one workflow issue is filed

### SIL-B16 Review observations corroborate

WHEN a session review keeps an observation THE loop SHALL keep it local and file nothing from it alone, adding `review:<category>` and `review_weight` to a model-free finding on the same unit and run that it corroborates ([SRV-B22](session-review.spec.md), [ADR `review-observations-are-candidates-corroborated-before-they-file`](../adr/review-observations-are-candidates-corroborated-before-they-file.adr.md)).

- GIVEN a review observation with no model-free finding on its unit WHEN filing runs THEN nothing is filed for it

### SIL-B7 Uncalibrated stays local

WHEN an outcome finding comes from a judge with no calibration score for the gate ([LIF](lifecycle-and-evals.spec.md)) THE loop SHALL record it `uncalibrated` and make no issue or comment, filing the next matching finding normally once a score exists.

- GIVEN an outcome gap from an unscored judge WHEN the filing rule runs THEN the finding is `uncalibrated` and no issue exists
- GIVEN a score recorded later WHEN the next matching finding comes THEN it files

### SIL-B17 The loop child

WHEN the loop child claims a ticket THE loop child SHALL run one friction judge session on the run's judge executor, on the run setting `loop_model` (default `medium`, [RST-B18, RST-B19, RST-B20, RST-B21](run-settings-and-overrides.spec.md)) at the run setting `loop_effort` (default `max`, [the decision record](../adr/the-loop-thinks-at-max-effort-on-the-medium-tier.adr.md)) for 1800 s, over the findings' metadata and the segment's record kinds and never the evidence file, then run the session review when planned, decide and file each finding, write `loop_started`, `loop_judged`, `issue_filed`, `issue_commented`, the review records (`review_planned`, `review_session`, `review_skipped`, `review_done`, `review_failed`) and `loop_summary` (SIL-B22) and, at autonomy `propose` or `trial`, `loop_proposed`, `loop_trialled`, `loop_opened` and `loop_skipped` ([PRP-B23](improvement-proposals.spec.md)) to the thread's `loop.jsonl`, and add one `loop` ledger row with its cost.

- GIVEN a ticket WHEN the child ends THEN `loop.jsonl` holds `loop_started` and `loop_judged`, and the ledger holds one `loop` row with its cost

### SIL-B25 A review that hit a usage limit is run again once the limit has passed

WHEN the loop child's session review has ended with reviews failed as `usage_limit` whose `resets_at` falls at most `review.retry_wait_hours` after that moment (6, provenance `default_no_data`, [IMD-B23](improvement-data.spec.md)) THE loop child SHALL run each of those reviews once more, in plan order ([SRV-B24](session-review.spec.md)) and within the money caps ([SRV-B21, SRV-B25](session-review.spec.md)), starting no earlier than the latest of those reset times and marking every record of a retry `retry` true ([the decision record](../adr/a-review-that-hit-a-usage-limit-is-run-again-once.adr.md)).

- GIVEN 16 reviews failed as `usage_limit` with `resets_at` 2 hours ahead WHEN the session review has ended THEN the child starts no retry before that instant, then runs the 16 once more in plan order, and every record of a retry has `retry` true
- GIVEN reviews failed as `usage_limit` with `resets_at` 1 hour and 2 hours ahead WHEN the session review has ended THEN every retry starts no earlier than the later instant
- GIVEN a retry that fails as `usage_limit` again WHEN it ends THEN its `review_failed` has `retry` true and the review is not run a third time
- GIVEN a retry whose estimate passes a money cap WHEN it is decided THEN it and every later retry are `review_skipped` with reason `budget` and stay failed

### SIL-B26 A usage limit that will not pass soon is not waited for

WHEN a review failed as `usage_limit` with no `resets_at` or one later than `review.retry_wait_hours` after its session review ended, or ran in the foreground (a person's `improve review`, or the loop run inline with `TEMPERGRAPH_LOOP=inline`), THE engine SHALL leave it failed and start no wait for it.

- GIVEN a review failed as `usage_limit` with `resets_at` 40 hours ahead WHEN the session review has ended THEN the child starts no wait and no retry, and its summary counts the review under `usage_limit`
- GIVEN a review failed as `usage_limit` with no `resets_at` WHEN the session review has ended THEN the child starts no wait and no retry
- GIVEN reviews failed as `usage_limit` with `resets_at` 2 hours and 40 hours ahead WHEN the session review has ended THEN the first is retried after its reset and the second stays failed
- GIVEN `improve review` run by a person whose reviews fail as `usage_limit` WHEN it ends THEN it returns at once with `review_failed` records of that class and no retry
- GIVEN `TEMPERGRAPH_LOOP=inline` and reviews failed as `usage_limit` with `resets_at` 2 hours ahead WHEN the run exits THEN the loop starts no wait and returns

### SIL-B22 The loop's summary

WHEN the loop child ends THE loop child SHALL write one `loop_summary` record to the thread's `loop.jsonl` with `recorded` (the findings the thread holds), `filed` (the issues this child opened or commented on) and `top[]`, at most three kept review observations of the thread, the highest `confidence` first and ties in plan order ([SRV-B24](session-review.spec.md)), each with `category`, `unit` and `confidence` and no note text.

- GIVEN a child that leaves 14 findings, files none and keeps five observations with confidence 0.7, 0.7, 0.55, 0.5 and 0.45 WHEN it ends THEN `loop_summary` has `recorded` 14, `filed` 0 and `top[]` of the first three, each with category, unit and confidence and none with a note
- GIVEN a child that keeps no observation WHEN it ends THEN `loop_summary` has an empty `top[]`

### SIL-B24 The summary counts the reviews that failed

WHEN the loop child ends, which is after the last retry of SIL-B25, THE loop child SHALL write in its `loop_summary` record `review_failed`, the number of reviews that ended failed counted by `error_class` ([SRV-B29](session-review.spec.md)) and empty when none did, a review having ended failed when the latest `review_done` or `review_failed` record of its reviewed session is `review_failed`, and a `review_failed` record that names no session counting as one review.

- GIVEN a child that finds nothing and whose 16 reviews all end `review_failed` as `usage_limit` WHEN it ends THEN `loop_summary` has `review_failed` with `usage_limit` 16, `recorded` as the thread holds and an empty `top[]`
- GIVEN two reviews failed as `unparsed` and one as `timed_out` WHEN the child ends THEN `review_failed` holds `unparsed` 2 and `timed_out` 1
- GIVEN a review that failed as `usage_limit` and ended `review_done` on its retry WHEN the child ends THEN `loop_summary` does not count it
- GIVEN a child whose review raised before any session ended WHEN it ends THEN `review_failed` holds `error` 1
- GIVEN a child none of whose reviews failed WHEN it ends THEN `review_failed` is empty

### SIL-B18 Filing by attribution

WHEN a finding files THE loop SHALL file engine and `executor:<name>` findings to the engine repository, workflow findings to the workflow's `issue_repository`, and a friction finding only when its judge attributed it at or above `friction.file_confidence` (0.75), opening each issue body with the hidden line `<!-- tempergraph:fp=<fingerprint> -->`.

- GIVEN a friction finding attributed at 0.6 WHEN filing runs THEN it is recorded and not filed

### SIL-B2 De-duplication by cause

WHEN a finding's fingerprint (side, workflow, leading cause, step) matches an open issue's hidden line, or its cause matches the issue's cause line ([ISS-B7](loop-issues.spec.md)), THE loop SHALL add a "seen again" comment instead of a new issue, and retry a failed read of the issues once, then file anyway and record why.

- GIVEN an open issue with the same fingerprint WHEN the finding files THEN one comment is added and no issue is created

### SIL-B3 Pattern rule

WHEN a workflow-side outcome gap would file THE loop SHALL require at least three runs with three distinct requests in 30 days, counted from the shared store when one is reachable and otherwise from the local ledger with a note saying so ([IMD-B1](improvement-data.spec.md)); one clear engine fault is enough.

- GIVEN two runs with the same gap in 30 days WHEN filing runs THEN nothing is filed

### SIL-B19 Code host unreachable

WHEN the code host refuses or cannot be reached THE loop SHALL keep the payload in the state root's `filing-outbox.jsonl` ([LOS-B7, LOS-B8, LOS-B9](local-observability-store.spec.md)) and redeliver it with the next filing.

- GIVEN `gh` failing with a network error WHEN an issue files THEN the payload is in the outbox, and the next filing sends it

### SIL-B20 Daily cap

WHEN stable mode's spend for the UTC day reaches the run setting `daily_cap_usd` (default 50 USD, from the workflow, a settings file or `--daily-cap`, [RST-B18, RST-B19, RST-B20, RST-B21](run-settings-and-overrides.spec.md)), counting the workflow's `loop` ledger rows and the proposals and trials the loop started itself, THE loop SHALL skip its judges, still write the records, and write `loop_skipped` with reason `daily_cap`; dev mode has no daily limit.

- GIVEN stable mode and 50 USD spent today WHEN a run exits THEN records are written and `loop_skipped` says `daily_cap`

### SIL-B6 Dry run files nothing

WHEN the operator's dry-run switch is on THE loop SHALL show what it would file and file nothing, every step of the parent still having run and spent.

- GIVEN `--dry-run` WHEN the child runs THEN no issue or comment is made and the would-file list is shown

### SIL-B5 Measurement writes nothing

WHEN a cost-fix comparison of two workflow versions runs THE loop SHALL compare cost per run, repeat share, gate first-try pass rate and outcome mix with no model call and no file, ledger row or code written, its only writes being one issue comment and, after a quality drop above `measure.quality_drop` (5 points), one reopen before that comment; it also runs unasked on the first 10 final exits after a merged proposal ([PRP-B9](improvement-proposals.spec.md)).

- GIVEN a version whose gate pass rate dropped 7 points WHEN the comparison runs THEN the issue is reopened and then commented once

### SIL-B21 Cost rules

WHEN the cost lens runs THE loop SHALL apply six rules, each a finding per unit over 30 days of one version with at least 5 runs: `repeat_share` (retries at least 30% of the unit's cost), `retry_after_check` (retries after a failed deterministic check), `judge_over_step`, `expensive_unblocked` (a `large` step whose judge never blocked in the window), `recurring_blocker` (one criterion blocking on 3 or more runs) and `unpriced_gate`, assuming a lever removes at most half, and record without filing a saving under 10 USD a month.

- GIVEN a unit with retries at 40% of its cost over 6 runs WHEN the lens runs THEN a `repeat_share` finding is made

## Acceptance criteria

- SIL-AC1 (SIL-B8): Every exit writes findings, evidence and one ledger row, with no model call
- SIL-AC2 (SIL-B8, SIL-B1): The canary test shows no request text in any issue, comment, ticket or ledger row
- SIL-AC3 (SIL-B2, SIL-B18): A repeated cause produces one open issue and comments, never a second open issue
- SIL-AC4 (SIL-B4, SIL-B11): An executor-attributed cause is filed with the executor label and CLI version, never against the workflow
- SIL-AC5 (SIL-B1, SIL-B17): A loop child that fails leaves the parent's exit code unchanged, and a child that runs writes its loop records and one `loop` ledger row
- SIL-AC6 (SIL-B9, SIL-B10): Each lens runs on the exits its triggers name and on no others
- SIL-AC7 (SIL-B12, SIL-B13, SIL-B14, SIL-B15): Each named cause is produced by a fixture run that shows it
- SIL-AC8 (SIL-B16, SIL-B7): No issue is filed from a review observation alone or from an uncalibrated judge
- SIL-AC9 (SIL-B3): A workflow-side outcome gap files only at three runs with three distinct requests in 30 days
- SIL-AC10 (SIL-B19, SIL-B20, SIL-B6): A refused payload is redelivered, the daily cap skips judges with `loop_skipped`, and a dry run files nothing
- SIL-AC11 (SIL-B5): A measurement makes no model call and writes only one comment and at most one reopen
- SIL-AC12 (SIL-B21): Each cost rule is produced by a fixture ledger, and a saving under 10 USD a month is not filed
- SIL-AC13 (SIL-B17): The ticket carries `loop_effort`, `max` when unset, and the friction judge, every reviewer session and the proposer's step and judge are asked at that effort
- SIL-AC14 (SIL-B22): A fixture loop child leaves one `loop_summary` record with the counts of findings recorded and filed and at most three kept observations by confidence, each with category, unit and confidence and none with note text
- SIL-AC15 (SIL-B23): The fixture run of BUD-AC8 that pauses on `check_repeat` exits with `check_repeat` among the findings of its unit and in its `finding_recorded` record
- SIL-AC16 (SIL-B24): A fixture loop child that finds nothing and whose reviews all end `review_failed` as `usage_limit` leaves a `loop_summary` with `review_failed` holding `usage_limit` and their number, a review that failed and then ended `review_done` on its retry is not counted, and a child with no failed review has an empty `review_failed`
- SIL-AC17 (SIL-B25, SIL-B26): A fixture loop child on a fake clock whose reviews all return `usage_limit` true with `resets_at` 2 hours ahead starts no retry before that instant, runs each review once more in plan order with `retry` true on every record of a retry, never a third time, and writes its summary after the last retry; with `resets_at` 40 hours ahead or none, from `improve review`, or inline, it starts no wait and no retry
- SIL-AC29 (SIL-B10, SIL-B33): Against a fake code host, a stable-mode fixture whose `met` run has a pull request with a review in state `changes_requested` gets one `outcome_escape` finding for the `outcome` unit at the next final exit of the workflow and one `loop_lens` record for the outcome lens with that run's thread, and no model session starts
- SIL-AC30 (SIL-B16, SIL-B33): A kept review observation of a run on a unit that holds its `outcome_escape` finding makes that finding carry `review:<category>` and `review_weight`, and an observation on a unit with no such finding changes none
- SIL-AC31 (SIL-B34): With an outcome judge that has no calibration score, `outcome_escape` findings for one unit of three fixture runs with three distinct requests in 30 days file one issue and those of two runs file none
- SIL-AC32 (SIL-B33): A run of a fixture package whose steps commit, one of them through a shell command, and whose finalizer returns the url of a pull request, read against a fake code host that shows a person's follow-up commit on the file that step wrote, is an escape in `outcome show` and holds one `outcome_escape` finding for the unit of that step, and for each of two units when the commit changes a file of each
- SIL-AC33 (SIL-B33): Against a fake code host, a run whose pull request a first read shows with a review in state `changes_requested` and a later read shows with a follow-up commit on a file unit `a` wrote holds one `outcome_escape` finding for the `outcome` unit and one for `a`, and a third read adds none

## Open questions

- Keep or drop the 0.75 confidence floor for filing a new friction issue? It may carry no signal; FBK's `confidence_bands` will give the data. Owner: owner. Until answered: kept, as parameter `friction.file_confidence`.
- Is the loop a compiled built-in workflow? Release 1 runs it as a fixed engine program with one judged session per ticket, so it gets no gate of its own; the outcome lens reuses the calibrated outcome judge and files only while JCL holds that judge `accepted` and only by the pattern rule. Owner: engine owner.
- Is 7 days the right window for a lost runner (`lost_runner.window_days`)? It keeps the first `status` after an upgrade from starting a loop for every old dead thread. Until answered: 7, as a parameter with provenance `default_no_data`. Owner: owner.
- Is a lost runner a stable-mode signal of its own? SIL-B10 and [SRV-B16](session-review.spec.md) name the signals that fire the lenses in stable mode, and a lost runner is none. Until answered: it is not, so a stable-mode lost runner starts the loop only when its segment holds a signal. Owner: owner.
- Should `resume` and `wait` also find a lost runner? Until answered: only `status`, `stop` and `attention` do (SIL-B29), so a thread resumed before any of them looked is not handed to the loop. Owner: owner.
