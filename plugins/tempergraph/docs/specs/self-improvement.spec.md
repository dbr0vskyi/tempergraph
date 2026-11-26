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

WHEN a run had a pause on cause `tool_access` or a tool grant ([RST-B28, RST-B29, RST-B30](run-settings-and-overrides.spec.md)) THE loop SHALL make a friction finding `tool_access:<refusal class>` ([TSA-B7](tool-surface-audit.spec.md)), write each grant and allowed command as one entry of the ledger row's `grants[]` (unit, capability or prefix, the refusal class it answered, `via` `cli`, `orchestration` or `profile`, whether a later attempt called it, the unit's outcome after it), make a grant a passing attempt used a workflow finding `grant_missing` whose remedy is the declaration, record a grant never called as `grant_unused` without filing, and cluster both by workflow, unit and capability.

- GIVEN `--grant code=shell` used by a passing attempt WHEN the loop runs THEN a `grant_missing` finding is made for `code`
- GIVEN the same grant on five runs on three machines WHEN the pattern rule runs THEN one issue is filed
- GIVEN stable mode and a run that paused on cause `tool_access` after a step was refused a tool WHEN a person stops it at that pause THEN its findings hold `tool_access:<refusal class>` of the refused call and the friction lens is on for that final exit

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

### SIL-B36 The loop records what its friction judge answered

WHEN the friction judge's session ends THE loop child SHALL write in the `loop_judged` record an `answers[]` entry for each finding the judge answered for, holding the finding's fingerprint, `confidence` and `attributed` and no other part of the reply, and an empty `answers[]` when it answered for none.

- GIVEN a judge that answers for two of three findings, one attributed at 0.5 and one not attributed at 0.7 WHEN the child ends THEN `loop_judged` holds two `answers[]` entries with those fingerprints, confidences and attributions and none for the third finding
- GIVEN a judge reply that explains each answer in a sentence WHEN the child ends THEN no word of an explanation is in `loop.jsonl`
- GIVEN a judge session that fails WHEN the child ends THEN `loop_judged` holds an empty `answers[]`

### SIL-B38 No text of a run reaches the friction judge or the loop's log

WHEN the loop child asks the friction judge about findings THE loop child SHALL put no request text, no text of feedback or of a ruling, no content of the run's outputs and no content of a workspace file in the judge's prompt or in the thread's `loop.jsonl`.

- GIVEN a thread whose request, feedback, an output and a workspace file each hold a distinct word WHEN the loop child asks the friction judge about its findings THEN none of the four words is in the judge's prompt or in `loop.jsonl`
- GIVEN a segment that ended in a final exit and holds a finding of cause `gap_escalation` at unit `review` WHEN the judge's prompt is built THEN it names the finding's fingerprint, cause, class, side, unit and count, and the counts of the record kinds of `review` with the ids of the criteria that blocked it

### SIL-B18 Filing by attribution or by count

WHEN a finding files THE loop SHALL file engine and `executor:<name>` findings to the engine repository, workflow findings to the workflow's `issue_repository`, and a friction finding only when its judge attributed it (confirmed the side it names) and either its confidence is at or above `friction.file_confidence` (0.75) or its fingerprint meets the pattern rule of SIL-B3, opening each issue body with the hidden line `<!-- tempergraph:fp=<fingerprint> -->`.

- GIVEN a friction finding attributed at 0.6 whose fingerprint is recorded in two runs WHEN filing runs THEN it is recorded and not filed
- GIVEN a friction finding attributed at 0.5 whose fingerprint is recorded in three runs with three distinct requests in 30 days WHEN filing runs THEN one issue is filed
- GIVEN that finding marked not attributed at 0.9 WHEN filing runs THEN it is recorded and not filed

### SIL-B35 A finding its judge gave no answer for is not filed

WHEN the friction judge gave no answer for a friction finding (its session failed, its reply could not be read, the daily cap skipped the judge, or the reply left the finding out) THE loop SHALL record the finding `not_judged` and file nothing for it, even when its fingerprint meets the pattern rule of SIL-B3.

- GIVEN a friction finding whose fingerprint is recorded in three runs with three distinct requests and a judge session that failed WHEN filing runs THEN the finding is recorded `not_judged` and no issue or comment is made
- GIVEN stable mode with the day's spend at `daily_cap_usd` and such a finding WHEN the loop child runs THEN the judge is skipped, the finding is recorded `not_judged` and nothing is filed
- GIVEN a judge reply that answers for the other findings of the run and not for this one WHEN filing runs THEN the finding is recorded `not_judged` and nothing is filed

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
- SIL-AC7 (SIL-B12, SIL-B13, SIL-B14, SIL-B15): Each named cause is produced by a fixture run that shows it, from the records that run wrote
- SIL-AC8 (SIL-B16, SIL-B7): No issue is filed from a review observation alone or from an uncalibrated judge
- SIL-AC9 (SIL-B3): A workflow-side outcome gap files only at three runs with three distinct requests in 30 days
- SIL-AC10 (SIL-B19, SIL-B20, SIL-B6): A refused payload is redelivered, the daily cap skips judges with `loop_skipped`, and a dry run files nothing
- SIL-AC11 (SIL-B5): A measurement makes no model call and writes only one comment and at most one reopen
- SIL-AC12 (SIL-B21): Each cost rule is produced by a fixture ledger, and a saving under 10 USD a month is not filed
- SIL-AC13 (SIL-B17): The ticket carries `loop_effort`, `max` when unset, and the friction judge, every reviewer session and the proposer's step and judge are asked at that effort
- SIL-AC15 (SIL-B23): The fixture run of BUD-AC8 that pauses on `check_repeat` exits with `check_repeat` among the findings of its unit and in its `finding_recorded` record
- SIL-AC29 (SIL-B10, SIL-B33): Against a fake code host, a stable-mode fixture whose `met` run has a pull request with a review in state `changes_requested` gets one `outcome_escape` finding for the `outcome` unit at the next final exit of the workflow and one `loop_lens` record for the outcome lens with that run's thread, and no model session starts
- SIL-AC30 (SIL-B16, SIL-B33): A kept review observation of a run on a unit that holds its `outcome_escape` finding makes that finding carry `review:<category>` and `review_weight`, and an observation on a unit with no such finding changes none
- SIL-AC31 (SIL-B34): With an outcome judge that has no calibration score, `outcome_escape` findings for one unit of three fixture runs with three distinct requests in 30 days file one issue and those of two runs file none
- SIL-AC32 (SIL-B33): A run of a fixture package whose steps commit, one of them through a shell command, and whose finalizer returns the url of a pull request, read against a fake code host that shows a person's follow-up commit on the file that step wrote, is an escape in `outcome show` and holds one `outcome_escape` finding for the unit of that step, and for each of two units when the commit changes a file of each
- SIL-AC33 (SIL-B33): Against a fake code host, a run whose pull request a first read shows with a review in state `changes_requested` and a later read shows with a follow-up commit on a file unit `a` wrote holds one `outcome_escape` finding for the `outcome` unit and one for `a`, and a third read adds none
- SIL-AC34 (SIL-B18, SIL-B2): Against a fake code host, friction findings of one fingerprint that a fixture judge attributes at 0.5 in three runs with three distinct requests file one issue, those of two runs file none, and a fourth run adds one "seen again" comment and no second issue
- SIL-AC35 (SIL-B18, SIL-B35, SIL-B20): A friction finding whose fingerprint is recorded in three runs with three distinct requests files nothing when its judge marked it not attributed at 0.9, and is recorded `not_judged` and files nothing when the judge session fails, when its reply leaves the finding out and when the daily cap skips the judge
- SIL-AC36 (SIL-B18, SIL-B6): A dry run lists a friction finding that meets the pattern rule as one that would file and makes no issue and no comment
- SIL-AC37 (SIL-B18, SIL-B11): A friction finding that meets the pattern rule files to the engine's repository when its side is the engine or an executor, to the workflow's `issue_repository` when its side is the workflow, and is recorded and not filed when its side is `host`
- SIL-AC38 (SIL-B36): A fixture loop child whose judge answers for two of three findings leaves a `loop_judged` record whose `answers[]` holds the fingerprint, `confidence` and `attributed` of those two and no other text of the reply, and a child whose judge session fails leaves an empty `answers[]`
- SIL-AC44 (SIL-B38): In a fixture thread whose request, feedback, an output and a workspace file each hold a distinct canary word, no canary word is in the friction judge's prompt or in `loop.jsonl`, and the prompt holds the fingerprint, cause, class, side, unit and count of each finding

## Open questions

- Keep or drop the 0.75 confidence floor for filing a new friction issue? On nine threads of real work measured on 2026-11-25 the friction judge answered for 64 findings, with a highest confidence of 0.70, a median of 0.50 and 16 answers `attributed: false`, so none of them reached the floor; FBK's `confidence_bands` will give more data. Owner: owner. Until answered: kept, as parameter `friction.file_confidence`.
- Is the loop a compiled built-in workflow? Release 1 runs it as a fixed engine program with one judged session per ticket, so it gets no gate of its own; the outcome lens reuses the calibrated outcome judge and files only while JCL holds that judge `accepted` and only by the pattern rule. Owner: engine owner.
- Is 7 days the right window for a lost runner (`lost_runner.window_days`)? It keeps the first `status` after an upgrade from starting a loop for every old dead thread. Until answered: 7, as a parameter with provenance `default_no_data`. Owner: owner.
- Is a lost runner a stable-mode signal of its own? SIL-B10 and [SRV-B16](session-review.spec.md) name the signals that fire the lenses in stable mode, and a lost runner is none. Until answered: it is not, so a stable-mode lost runner starts the loop only when its segment holds a signal. Owner: owner.
- Should `resume` and `wait` also find a lost runner? Until answered: only `status`, `stop` and `attention` do (SIL-B29), so a thread resumed before any of them looked is not handed to the loop. Owner: owner.
