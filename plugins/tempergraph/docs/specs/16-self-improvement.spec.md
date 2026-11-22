# Self-improvement loop

## Purpose

A built-in program that reads every finished run's record, judges it with an independent judge, and files, comments on or only records a finding in the repository that owns the fault: the engine's or the workflow's. It is inside the engine so every run is analyzed without an optional install ([ADR-0003](../adr/0003-workflows-as-data.adr.md)); it runs as a detached child and never pauses. The loop closes through people: an issue is evidence, not an order, and a measurement call never writes code. It is the first half of the loop: clusters of its findings become measured proposals ([PRP](40-improvement-proposals.spec.md)), human ground truth becomes labels and judge grades ([FBK](41-feedback-and-judge-reliability.spec.md)), its data needs are [IMD](43-improvement-data.spec.md), and what it reads from sessions is [SRV](44-session-review.spec.md). Workflow owners, the engine's maintainers and operators who read the issues depend on it. Its thresholds are parameter records with provenance `default_no_data` ([IMD §2.5](43-improvement-data.spec.md)), to be revisited with real runs.

## Behaviours

### SIL-B8 Records on every exit

WHEN a run exits THE engine SHALL write, with no model call, the findings `runs/<workflow>/<task>/findings.json` (signal and step names, cause codes, counts, executor names, published only as metadata; one document per thread that each segment appends to), the local evidence file `runs/<workflow>/<task>/evidence/record.json` (request, outputs, scrubbed feedback, never published), both owner-only ([LOS §2.1](33-local-observability-store.spec.md)), one ledger row (names, counts, hashes, executor and CLI versions, no text), the session digests ([SRV §2.1](44-session-review.spec.md)), and a `finding_recorded` run-log record with the causes, sides and, at a final exit, the lenses.

- GIVEN a run that exits 5 WHEN recording finishes THEN `findings.json`, `evidence/record.json` and one ledger row exist and no session ran
- GIVEN a paused run resumed and finished WHEN its findings are read THEN both segments appended to the one document

### SIL-B1 Detached and best effort

WHEN a final exit's friction lens fires on at least one fault, its outcome lens has candidates, or its session review plan has a depth THE engine SHALL write a hand-off ticket (ids, enums, the state root path and the fingerprints, never request text) to `improve/tickets/` under the home and start the loop child detached through the detached child launcher ([SEC §2.2](14-security.spec.md)), and the child's failure SHALL never change the parent's exit code.

- GIVEN a run that exits 0 and a loop child that crashes WHEN the parent's exit code is read THEN it is 0
- GIVEN `TEMPERGRAPH_LOOP=inline` WHEN the run exits THEN the loop runs in-process; with `off` it does not run

### SIL-B9 Final exits

WHEN the loop decides which exits are final THE engine SHALL treat every exit that is not a pause (exit 0, 4 or 5) as final.

- GIVEN a run that pauses (exit 3) WHEN it exits THEN no lens of a final exit runs

### SIL-B10 Lenses

WHEN a final exit is judged THE loop SHALL apply the friction lens (where the process hurt and whose fault: every flagged final exit in dev mode; in stable mode a `tool_access` pause or tool grant, spent retries or a stop, an uncleared failed step, a gap escalation, repeated blockers, a retry burst, cost above the version's p90, a new version's first five runs, or a person pushing back), the outcome lens (read from the run's outcome record, [OUT §2.5](90-run-outcome.spec.md): every final exit in dev mode; in stable mode a person pushing back, a pass at judge confidence at most 0.5, or every 20th clean run), the cost lens (every 10th final exit of a version), the session lens (digest causes on every exit, a model review only on a plan, [SRV §2.3, §2.4](44-session-review.spec.md)) and the per-gate quality scorecard (reported for every gate; a gate's rows may file only while its judge binding is graded `reliable`, [FBK-B5](41-feedback-and-judge-reliability.spec.md)).

- GIVEN stable mode and a clean run that is the 20th since the last outcome review WHEN it exits THEN the outcome lens runs
- GIVEN a gate whose judge binding is not `reliable` WHEN its scorecard rows show a drop THEN they are reported and not filed

### SIL-B11 Fault sides

WHEN a cause is classified THE loop SHALL take cause codes from run-log and session-digest names and numbers only ([SRV §2.2](44-session-review.spec.md)), class each `fault`, `infra` or `designed`, attribute a fault to `engine`, `workflow`, `executor:<name>` (an unknown event or message shape, a tool name outside the catalog, a refused flag or option, an API error type the classifier does not list) or `host` (the host-speed preflight warned, or timeouts sorted `slow_host`, [OBS](15-observability-and-cost.spec.md)), file executor-side issues to the engine's repository with an executor label, and record host findings only.

- GIVEN a timeout on a host whose preflight warned WHEN classified THEN the finding is `host` and nothing is filed

### SIL-B4 Executor drift is visible

WHEN sessions show a tool name the executor's view catalog does not map THE loop SHALL attribute cause `unknown_tool_name:<name>` to `executor:<name>` with the CLI version from the session's `agent_run` record, and not blame the workflow.

- GIVEN runs on `antigravity` after a CLI update whose sessions call an unmapped tool WHEN friction is judged THEN the finding is `executor:antigravity` with the CLI version

### SIL-B12 What a friction finding carries

WHEN a friction finding is made THE loop SHALL carry the cause code's fixed remedy and, where the fault is in a prompt or check, the file and the kind of change (a person decides; the loop opens no pull request); mark three or more retries of one unit in one visit `retry_burst` with the blockers' criterion ids, and a judge-sent-back retry `judge_blocked:<criterion id>` ([PRP §2.2](40-improvement-proposals.spec.md)); and mark a pause on `BLOCKED:` whose check ran no command and read no file as the workflow fault `blocked_without_check`.

- GIVEN a unit retried three times in one visit WHEN its finding is made THEN it carries `retry_burst` with the criterion ids
- GIVEN a `BLOCKED:` pause whose check ran nothing WHEN classified THEN the fault is the workflow's `blocked_without_check`

### SIL-B13 Outcome evidence

WHEN the outcome lens judges a run THE loop SHALL include the run branch's commits, changed paths and diff stat, and spend no session of its own: its candidates are the final criteria the outcome gate's judge graded `UNMET` or `PARTIAL`, recorded as `outcome_unmet:<criterion>` on the `outcome` unit.

- GIVEN a final criterion graded `UNMET` WHEN the outcome lens runs THEN `outcome_unmet:<criterion>` is recorded and no judge session starts

### SIL-B14 Tool access and grants

WHEN a run had a `tool_access` pause or a tool grant ([RST §2.8](80-run-settings-and-overrides.spec.md)) THE loop SHALL make a friction finding `tool_access:<refusal class>` ([TSA §2.2](57-tool-surface-audit.spec.md)), write each grant and allowed command as one entry of the ledger row's `grants[]` (unit, capability or prefix, the refusal class it answered, `via` `cli`, `orchestration` or `profile`, whether a later attempt called it, the unit's outcome after it), make a grant a passing attempt used a workflow finding `grant_missing` whose remedy is the declaration, record a grant never called as `grant_unused` without filing, and cluster both by workflow, unit and capability.

- GIVEN `--grant code=shell` used by a passing attempt WHEN the loop runs THEN a `grant_missing` finding is made for `code`
- GIVEN the same grant on five runs on three machines WHEN the pattern rule runs THEN one issue is filed

### SIL-B15 Agent rescues and supervision

WHEN an agent decided a `rescue` touch on its own ([SUP §2.1](86-supervision-metrics.spec.md), [PRV §2.4](85-caller-provenance.spec.md)) THE loop SHALL make a friction finding `agent_decided:<pause cause>` clustered by workflow, unit and pause cause, file a workflow issue whose remedy is a check or an environmental cause for a cluster whose decisions were mostly `proceed` with no workspace change, write `supervision{}` on the ledger row, and show supervision cost in the cost lens as its own figure, never in run cost ([SCO](87-supervision-cost.spec.md)).

- GIVEN ten agent `proceed` rescues on unit `test` with no workspace change WHEN clustered THEN one workflow issue is filed

### SIL-B16 Review observations corroborate

WHEN a session review keeps an observation THE loop SHALL keep it local and file nothing from it alone, adding `review:<category>` and `review_weight` to a model-free finding on the same unit and run that it corroborates ([SRV §2.8](44-session-review.spec.md), [ADR-0119](../adr/0119-review-observations-are-candidates-corroborated-before-they-file.adr.md)).

- GIVEN a review observation with no model-free finding on its unit WHEN filing runs THEN nothing is filed for it

### SIL-B7 Uncalibrated stays local

WHEN an outcome finding comes from a judge with no calibration score for the gate ([LIF](18-lifecycle-and-evals.spec.md)) THE loop SHALL record it `uncalibrated` and make no issue or comment, filing the next matching finding normally once a score exists.

- GIVEN an outcome gap from an unscored judge WHEN the filing rule runs THEN the finding is `uncalibrated` and no issue exists
- GIVEN a score recorded later WHEN the next matching finding comes THEN it files

### SIL-B17 The loop child

WHEN the loop child claims a ticket THE loop child SHALL run one friction judge session on the run's judge executor, on the run setting `loop_model` (default `medium`, [RST §2.2](80-run-settings-and-overrides.spec.md)) for 1800 s, over the findings' metadata and the segment's record kinds and never the evidence file, then decide and file each finding, run the session review when planned, write `loop_started`, `loop_judged`, `issue_filed`, `issue_commented` and the review records (`review_planned`, `review_session`, `review_skipped`, `review_done`, `review_failed`) and, at autonomy `propose` or `trial`, `loop_proposed`, `loop_trialled`, `loop_opened` and `loop_skipped` ([PRP §5](40-improvement-proposals.spec.md)) to the thread's `loop.jsonl`, and add one `loop` ledger row with its cost.

- GIVEN a ticket WHEN the child ends THEN `loop.jsonl` holds `loop_started` and `loop_judged`, and the ledger holds one `loop` row with its cost

### SIL-B18 Filing by attribution

WHEN a finding files THE loop SHALL file engine and `executor:<name>` findings to the engine repository, workflow findings to the workflow's `issue_repository`, and a friction finding only when its judge attributed it at or above `friction.file_confidence` (0.75), opening each issue body with the hidden line `<!-- tempergraph:fp=<fingerprint> -->`.

- GIVEN a friction finding attributed at 0.6 WHEN filing runs THEN it is recorded and not filed

### SIL-B2 De-duplication by cause

WHEN a finding's fingerprint (side, workflow, leading cause, step) matches an open issue's hidden line THE loop SHALL add a "seen again" comment instead of a new issue, and retry a failed search once, then file anyway and record why.

- GIVEN an open issue with the same fingerprint WHEN the finding files THEN one comment is added and no issue is created

### SIL-B3 Pattern rule

WHEN a workflow-side outcome gap would file THE loop SHALL require at least three runs with three distinct requests in 30 days, counted from the shared store when one is reachable and otherwise from the local ledger with a note saying so ([IMD-B1](43-improvement-data.spec.md)); one clear engine fault is enough.

- GIVEN two runs with the same gap in 30 days WHEN filing runs THEN nothing is filed

### SIL-B19 Code host unreachable

WHEN the code host refuses or cannot be reached THE loop SHALL keep the payload in the state root's `filing-outbox.jsonl` ([LOS §2.1](33-local-observability-store.spec.md)) and redeliver it with the next filing.

- GIVEN `gh` failing with a network error WHEN an issue files THEN the payload is in the outbox, and the next filing sends it

### SIL-B20 Daily cap

WHEN stable mode's spend for the UTC day reaches the run setting `daily_cap_usd` (default 50 USD, from the workflow, a settings file or `--daily-cap`, [RST §2.2](80-run-settings-and-overrides.spec.md)), counting the workflow's `loop` ledger rows and the proposals and trials the loop started itself, THE loop SHALL skip its judges, still write the records, and write `loop_skipped` with reason `daily_cap`; dev mode has no daily limit.

- GIVEN stable mode and 50 USD spent today WHEN a run exits THEN records are written and `loop_skipped` says `daily_cap`

### SIL-B6 Dry run files nothing

WHEN the operator's dry-run switch is on THE loop SHALL show what it would file and file nothing, every step of the parent still having run and spent.

- GIVEN `--dry-run` WHEN the child runs THEN no issue or comment is made and the would-file list is shown

### SIL-B5 Measurement writes nothing

WHEN a cost-fix comparison of two workflow versions runs THE loop SHALL compare cost per run, repeat share, gate first-try pass rate and outcome mix with no model call and no file, ledger row or code written, its only writes being one issue comment and, after a quality drop above `measure.quality_drop` (5 points), one reopen before that comment; it also runs unasked on the first 10 final exits after a merged proposal ([PRP-B9](40-improvement-proposals.spec.md)).

- GIVEN a version whose gate pass rate dropped 7 points WHEN the comparison runs THEN the issue is reopened and then commented once

### SIL-B21 Cost rules

WHEN the cost lens runs THE loop SHALL apply six rules, each a finding per unit over 30 days of one version with at least 5 runs: `repeat_share` (retries at least 30% of the unit's cost), `retry_after_check` (retries after a failed deterministic check), `judge_over_step`, `expensive_unblocked` (a `large` step whose judge never blocked in the window), `recurring_blocker` (one criterion blocking on 3 or more runs) and `unpriced_gate`, assuming a lever removes at most half, and record without filing a saving under 10 USD a month.

- GIVEN a unit with retries at 40% of its cost over 6 runs WHEN the lens runs THEN a `repeat_share` finding is made

## Acceptance criteria

- SIL-AC1 (SIL-B8): Every exit writes findings, evidence and one ledger row, with no model call
- SIL-AC2 (SIL-B8, SIL-B1): The canary test shows no request text in any issue, comment, ticket or ledger row
- SIL-AC3 (SIL-B2, SIL-B18): A repeated cause produces one issue and comments, never a duplicate issue
- SIL-AC4 (SIL-B4, SIL-B11): An executor-attributed cause is filed with the executor label and CLI version, never against the workflow
- SIL-AC5 (SIL-B1, SIL-B17): A loop child that fails leaves the parent's exit code unchanged, and a child that runs writes its loop records and one `loop` ledger row
- SIL-AC6 (SIL-B9, SIL-B10): Each lens runs on the exits its triggers name and on no others
- SIL-AC7 (SIL-B12, SIL-B13, SIL-B14, SIL-B15): Each named cause is produced by a fixture run that shows it
- SIL-AC8 (SIL-B16, SIL-B7): No issue is filed from a review observation alone or from an uncalibrated judge
- SIL-AC9 (SIL-B3): A workflow-side outcome gap files only at three runs with three distinct requests in 30 days
- SIL-AC10 (SIL-B19, SIL-B20, SIL-B6): A refused payload is redelivered, the daily cap skips judges with `loop_skipped`, and a dry run files nothing
- SIL-AC11 (SIL-B5): A measurement makes no model call and writes only one comment and at most one reopen
- SIL-AC12 (SIL-B21): Each cost rule is produced by a fixture ledger, and a saving under 10 USD a month is not filed

## Open questions

- Keep or drop the 0.75 confidence floor for filing a new friction issue? It may carry no signal; FBK's `confidence_bands` will give the data. Owner: owner. Until answered: kept, as parameter `friction.file_confidence`.
- Is the loop a compiled built-in workflow? Release 1 runs it as a fixed engine program with one judged session per ticket, so it gets no gate of its own; the outcome lens reuses the calibrated outcome judge and files only while JCL holds that judge `accepted` and only by the pattern rule. Owner: engine owner.
