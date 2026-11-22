---
task: loop-fixes
complexity: complex
status: completed
specs: [plugins/tempergraph/docs/specs/44-session-review.spec.md, plugins/tempergraph/docs/specs/08-budgets-and-failures.spec.md, plugins/tempergraph/docs/specs/16-self-improvement.spec.md, plugins/tempergraph/docs/specs/17-engine-cli.spec.md, plugins/tempergraph/docs/specs/31-run-detail-document.spec.md, plugins/tempergraph/docs/specs/40-improvement-proposals.spec.md]
---

# Plan: The improvement loop finds what a reviewer finds

## 0. Hand-off

- Triage note: `plugins/tempergraph/docs/tasks/loop-fixes.triage.md`
- Hand-off: `plugins/tempergraph/docs/tasks/loop-fixes.handoff.md`
- Specs read: `plugins/tempergraph/docs/specs/44-session-review.spec.md` (SRV-B21, SRV-B22, SRV-B24 to SRV-B28, SRV-AC8 to SRV-AC11), `plugins/tempergraph/docs/specs/08-budgets-and-failures.spec.md` (BUD-B8, BUD-B11, BUD-B16, BUD-AC8), `plugins/tempergraph/docs/specs/16-self-improvement.spec.md` (SIL-B16, SIL-B17, SIL-B22, SIL-B23, SIL-AC14, SIL-AC15), `plugins/tempergraph/docs/specs/17-engine-cli.spec.md` (CLI-B6, CLI-B20, CLI-AC10), `plugins/tempergraph/docs/specs/31-run-detail-document.spec.md` (RDD-B7, RDD-AC6), `plugins/tempergraph/docs/specs/40-improvement-proposals.spec.md` (PRP-B12, read only); the decision record `plugins/tempergraph/docs/adr/a-review-category-kept-in-several-sessions-is-a-finding-that-never-files-alone.adr.md` and the research note `plugins/tempergraph/docs/research/R-160-does-the-improvement-loop-find-what-a-reviewer-finds.rsrch.md`.
- Code read: `plugins/tempergraph/engine/src/tempergraph/improve/review.py` (`plan`, `run`, `show`, `summary`), `improve/child.py` (`process`), `improve/record.py` (`record_exit`, findings file), `improve/causes.py` (`CAUSES`), `improve/params.py`, `run/gate.py` (`decide`, `ESCALATE_CAUSES`), `run/nodes.py` (`_judge`, the step record with `changed`), `observe/attention.py`, `observe/detail.py`, `cli/observe_cli.py` (`cmd_attention`).
- Why this design: the work is five independent changes that share the loop's records and findings, so each is a phase with its own tests: the review reads the sessions of units in trouble first and pays for each review from what was reported (SRV-B24, SRV-B25, SRV-B21); a category kept in three sessions of one unit becomes one finding that corroborates its own category and never files (SRV-B26 to SRV-B28); the gate escalates at once on the same check failure twice (BUD-B16) and the loop records it (SIL-B23); the loop child writes a summary that `attention` and the detail document show (SIL-B22, CLI-B20, RDD-B7); a last phase proves the whole with the offline suite and lint (AC 6).
- Choices the plan fixes where the hand-off left them to this step:
  - SRV-B27: `improve review show`, `improve review summary` and the backlog's `review_weight` read the `review_repeat` finding and the `review_done` records together, on the reader side. No `review_done` record is rewritten, because the log is append-only and the records are written one session at a time before the count is known.
  - SRV-B25: the spend counts over the run's review records in `loop.jsonl` (each finished review at its reported cost where reported, else its estimate), so earlier plans of the thread count too; a review that is `review_failed` counts at what it cost.
  - SRV-B24: the plan reads the run's own records (`run.jsonl`: `check`, `gate`, `route`, `pause`, `judgement`) to name the units in trouble; the units are passed to `plan` as a keyword with an empty default, so a plan built from digests alone keeps working and orders by start time only.
  - BUD-B16: the earlier attempt's failing findings are carried in the run state next to the attempt (the state keeps only the latest attempt of a unit today); the later attempt's `changed` flag already exists on the attempt record. The cause joins `ESCALATE_CAUSES` in `run/gate.py` so the gate escalates at once before any counter, infra try or ladder step.
- Documents already written by discovery and not changed by this plan: the five specs, spec 40's first open-question bullet and the decision record listed above. The code step edits a spec only where code and spec still disagree after the build, and says so in its report.
- Known hazards the expand step searches for before writing rows: tests that build a review plan by position from digests (`plugins/tempergraph/engine/tests/test_session_review.py` lines 136, 158, 165 call `review.plan` with two arguments and read `targets`); the parameter `review.max_sessions.full` (named only by `improve/params.py` and `improve/review.py` in code); tests whose check fails with the same finding on two attempts in a row while the stand-in step writes files (the new gate rule pauses them), found by running the suite; tests that pin the keys of `attention --json` or of the detail document (`plugins/tempergraph/engine/tests/test_detail.py`, `plugins/tempergraph/engine/tests/test_cli.py`); tests that pin the list of causes or their classes; the spec size budget test `plugins/tempergraph/engine/tests/test_spec_budget.py` (spec 44 has about 2.5 KB of room).

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | A review plan lists its targets in priority order and the reviews run in that order: first the sessions of a unit whose gate in the run failed its check, sent the run back, escalated or paused, then the sessions a signal names, then the rest, and inside each group the session that started later before the one that started earlier; a run with no unit in trouble lists targets from the session that started last to the one that started first | SRV-B24, SRV-AC8 |
| R2 | AC 1, AC 2 | Before each review the engine adds the run's review spend so far (reported cost where reported, else the estimate) to an estimate for this review, the mean reported cost of the run's finished reviews or, until one has reported, the price of its view by size, and starts the review when the sum stays within the money caps; otherwise it skips this target and every later one as `skipped: budget`, so a skipped target always ranks below every target reviewed; a `full` plan has no count cap, so 18 targets with 12 reviews reporting 0.66 USD against a cap of 3.46 USD skips none | SRV-B21, SRV-B25, SRV-AC9 |
| R3 | AC 3 | When the reviews of a run keep the same category on the same unit in at least three distinct sessions (`review.repeat_sessions`, default 3, provenance `default_no_data`) the loop records one finding `review_repeat:<category>` on that unit, once per unit and category in the run, with the unit, the category and the session keys and no note text, a workflow fault except `environment_fault` (`infra`) and `request_ambiguous` (`designed`); the finding is listed by `improve backlog`, corroborates the kept observations of its category on its unit (`review:<category>`, `review_weight`, `corroborated` in `improve review show` and `improve review summary`) and no other, and files no issue and no comment in the run that records it or in any later run | SRV-B26, SRV-B27, SRV-B28, SRV-AC10, SRV-AC11, SIL-B16 |
| R4 | AC 4 | When the loop child ends it writes one `loop_summary` record with `recorded`, `filed` and at most three kept review observations by confidence (category, unit, confidence, no note text); `attention` prints the newest summary of each workflow that holds a finding or an observation after its items, as `loop[]` beside `items` in `--json` and never as an item, with the command `tempergraph improve review show <thread>`, and creates nothing; the thread's detail document carries the `loop` block, `null` until a loop child has ended | SIL-B22, SIL-B17, CLI-B6, CLI-B20, RDD-B7, SIL-AC14, CLI-AC10, RDD-AC6 |
| R5 | AC 5 | When a unit's check fails on two attempts in a row of one visit and item with the same failing findings by criterion, place and message (or the same scrubbed evidence text when it returns none) and the later attempt's step changed files, the gate escalates at once with cause `check_repeat`, spends no further retry, infra try or ladder step, and shows the repeated findings in the pause payload; a failure that changed, or a later step that changed no file, keeps the normal retries; the loop records `check_repeat` as a workflow fault finding on that unit, named in the exit's `finding_recorded` record | BUD-B16, BUD-B8, BUD-B11, BUD-AC8, SIL-B23, SIL-AC15 |
| R6 | AC 6 | Each criterion SRV-AC8 to SRV-AC11, BUD-AC8, SIL-AC14, SIL-AC15, CLI-AC10 and RDD-AC6 has an offline test (stand-in executor or fixture loop records) that carries its id; the edited specs and the decision record say what the code does; the engine's offline suite and `ruff check src tests` pass | SRV-AC8, SRV-AC9, SRV-AC10, SRV-AC11, BUD-AC8, SIL-AC14, SIL-AC15, CLI-AC10, RDD-AC6 |

## 2. Phases

### Phase 1: Review order and the budget decision

Goal: a review plan lists its targets with the units in trouble first and later attempts before earlier ones, and each review is paid for from the run's reported review spend with no count cap in a `full` plan.
Weight: medium

| Row | Kind | Req | File | Proves | Change | Completed |
|---|---|---|---|---|---|---|
| 1.1 | test | R1, R2 | `plugins/tempergraph/engine/tests/test_session_review.py` | SRV-AC8 | Update the three tests that call `review.plan` with two arguments and read `targets` by position (lines 136, 158, 165): with no unit in trouble the targets now list from the session that started last to the one that started first, and a `full` plan has no count cap, so each expected list is rewritten to that order and a test that expected a `budget` skip from the count cap now expects none | ✓ 2026-11-22 |
| 1.2 | test | R1 | `plugins/tempergraph/engine/tests/test_review_priority.py` | SRV-AC8 | New file. With fixture run records (`check` FAIL, `gate` BACK, ESCALATE, `pause`, `judgement` with blockers) and digests of several units, `review.plan` given the units in trouble lists their sessions first, later attempt before earlier, then sessions a signal names, then the rest, each group latest start first; a plan with no unit in trouble lists latest start first; a target skipped for `budget` ranks below every target reviewed; a plan built from digests alone with no keyword still works | ✓ 2026-11-22 |
| 1.3 | test | R2 | `plugins/tempergraph/engine/tests/test_review_budget.py` | SRV-AC9 | New file, stand-in reviewer executor with reported costs. the R-160 figures (18 targets, 12 reviews reporting 0.66 USD in all, cap 3.46 USD) skip no target; a run whose reported spend plus the estimate exceeds the cap skips that target and every later one as `skipped: budget`; the estimate is the mean reported cost of finished reviews once one has reported, else the price of the view by size; a `review_failed` review counts at what it cost | ✓ 2026-11-22 |
| 1.4 | code | R2 | `plugins/tempergraph/engine/src/tempergraph/improve/params.py` | | Remove the parameter `review.max_sessions.full` (a `full` plan has no count cap; named only here and in `improve/review.py`); keep `review.max_sessions.signals` | ✓ 2026-11-22 |
| 1.5 | code | R1 | `plugins/tempergraph/engine/src/tempergraph/improve/review.py` | | `plan` takes a keyword `trouble` (units in trouble, empty default) and orders its pool: sessions of a unit in trouble, then sessions a signal names (`keys`), then the rest, each group from the session that started last to the one that started first (the run order of `_run_digests`, reversed); drop the count cap of the `full` plan; add `_trouble(root, workflow, task)` reading `run.jsonl` (`check` FAIL, `gate` BACK or ESCALATE, `route`, `pause`, `judgement` with blockers) and have `run` pass it to `plan` | ✓ 2026-11-22 |
| 1.6 | code | R2 | `plugins/tempergraph/engine/src/tempergraph/improve/review.py` | | In `run`, decide each review from the sum of the run's review spend so far (every `review_done` and `review_failed` of `loop.jsonl`, at the reported cost where reported, else the estimate, so earlier plans of the thread count) and an estimate for this review (mean reported cost of the run's finished reviews, else the existing price of the view by size); start the review when the sum stays within `cap_usd`, otherwise skip this target and every later one as `skipped: budget` with a `review_skipped` record | ✓ 2026-11-22 |

### Phase 2: A category kept in several sessions

Goal: three kept sessions of one category on one unit give one `review_repeat` finding that is listed by `improve backlog`, corroborates its own category in the review readers and files nothing, alone or across runs.
Weight: medium

| Row | Kind | Req | File | Proves | Change | Completed |
|---|---|---|---|---|---|---|
| 2.1 | test | R3 | `plugins/tempergraph/engine/tests/test_review_repeat.py` | SRV-AC10 | New file. Fixture `review_done` records keep one category on one unit in three distinct sessions: one `review_repeat:<category>` finding is recorded with unit, category and the session keys and no note text, once per unit and category in the run (a second pass adds none); two sessions or three sessions of two units record none; `environment_fault` is class `infra` and `request_ambiguous` class `designed`, any other category `fault`; `improve backlog` lists the finding as a cluster; `review.repeat_sessions` is a parameter with default 3 | ✓ 2026-11-22 |
| 2.2 | test | R3 | `plugins/tempergraph/engine/tests/test_review_repeat.py` | SRV-AC11 | Same file: `improve review show` and `improve review summary` mark the kept observations of the finding's category on its unit as corroborated, with `review_weight`, and leave other categories and other units uncorroborated; the loop child's `process` on the recording run and on a later run files no issue and no comment for the finding (stand-in code host sees no call) | ✓ 2026-11-22 |
| 2.3 | code | R3 | `plugins/tempergraph/engine/src/tempergraph/improve/params.py` | | Add the parameter `review.repeat_sessions` (value 3, source SRV-B26, provenance `default_no_data` as the other defaults carry) | ✓ 2026-11-22 |
| 2.4 | code | R3 | `plugins/tempergraph/engine/src/tempergraph/improve/causes.py` | | Add the cause `review_repeat` (fault, side workflow, a remedy text naming the category kept in several sessions) and make `cause_of` return class `infra` side `host` for `review_repeat:environment_fault` and class `designed` side `workflow` for `review_repeat:request_ambiguous` | ✓ 2026-11-22 |
| 2.5 | code | R3 | `plugins/tempergraph/engine/src/tempergraph/improve/record.py` | | Add `append_findings(root, workflow, task_id, thread, lines)` that appends finding lines to the thread's `findings.json` in the same private write `record_exit` uses, and have `record_exit` use it, so the loop can add a finding after the exit | ✓ 2026-11-22 |
| 2.6 | code | R3 | `plugins/tempergraph/engine/src/tempergraph/improve/repeat.py` | | New module: `record(root, workflow, task_id, thread)` reads the run's `review_done` records, counts distinct sessions per unit and kept category, and for each count of at least `review.repeat_sessions` not yet recorded in `findings.json` appends one finding (`cause` `review_repeat:<category>`, unit, class and side from `cause_of`, fingerprint from `record.fingerprint`, `lens` `review`, the session keys, no note text); `repeated(root, workflow)` returns the (unit, category) pairs recorded across the workflow's runs, for the readers | ✓ 2026-11-22 |
| 2.7 | code | R3 | `plugins/tempergraph/engine/src/tempergraph/improve/review.py` | | `run` calls `repeat.record` after its last review; `show` and `summary` read the `review_repeat` findings together with the `review_done` records, set `corroborated` true and a `review_weight` on kept observations of a recorded (unit, category) and count them in `corroborated` and `corroboration_rate`; no `review_done` record is rewritten | ✓ 2026-11-22 |

### Phase 3: The same check failure twice

Goal: a check that fails with the same findings on two attempts in a row, the later step having changed files, makes the gate pause at once with cause `check_repeat`, and the loop records the finding for that unit.
Weight: medium

| Row | Kind | Req | File | Proves | Change | Completed |
|---|---|---|---|---|---|---|
| 3.1 | test | R5 | `plugins/tempergraph/engine/tests/test_check_repeat.py` | BUD-AC8 | New file, stand-in executor with a script check that fails with the same findings on attempts 1 and 2 while the step writes a file: the gate pauses at once with cause `check_repeat`, no further retry, infra try or ladder step is spent (counters unchanged) and the pause payload shows the repeated findings; a failure that changes between attempts keeps the normal retries; a later step that changed no file keeps the normal retries; a failure with no findings repeats on the same scrubbed evidence text | ✓ 2026-11-22 |
| 3.2 | test | R5 | `plugins/tempergraph/engine/tests/test_improve.py` | SIL-AC15 | Add a test that a pause with reason `check_repeat` derives the cause `check_repeat` (class fault, side workflow) and not `escalation:check_repeat`, and that the exit's `finding_recorded` record names it; the existing tests there pin only other causes (`cause_of` lines 49 to 53) and stay | ✓ 2026-11-22 |
| 3.3 | code | R5 | `plugins/tempergraph/engine/src/tempergraph/improve/causes.py` | | Add the cause `check_repeat` (fault, side workflow, remedy: the same check failure twice although the step changed files; tell the step what the check needs) and in `derive` map a `pause` with reason `check_repeat` to it | ✓ 2026-11-22 |
| 3.4 | code | R5 | `plugins/tempergraph/engine/src/tempergraph/run/checks.py` | | Add `repeat_key(findings, evidence)` returning the failing findings by criterion, place and message, or the scrubbed evidence text when there are none, as a comparable value; and `failing(res)` returning the failing finding rows to carry | ✓ 2026-11-22 |
| 3.5 | code | R5 | `plugins/tempergraph/engine/src/tempergraph/run/nodes.py` | | In the step record (line 410 onward) carry `prior_failing`: the failing findings of the same visit and item's previous attempt, read from the previous attempt's `check` (state keeps only the latest attempt); in `_judge`, when the check fails and is not environmental, the previous attempt's key equals this attempt's (`checks.repeat_key`) and this attempt's `changed` is true, set `att["escalate"] = "check_repeat"`, `att["repeated"]` to the findings and an ESCALATE judgement with reason `check_repeat` before any RETRY verdict | ✓ 2026-11-22 |
| 3.6 | code | R5 | `plugins/tempergraph/engine/src/tempergraph/run/gate.py` | | Add `check_repeat` to `ESCALATE_CAUSES` so `decide` escalates at once before any counter, infra try or ladder step; `pause_payload` adds `repeated` (the attempt's repeated findings) when the reason is `check_repeat` | ✓ 2026-11-22 |

### Phase 4: The loop's summary

Goal: the loop child writes `loop_summary`, `attention` shows the newest summary of each workflow beside its items, and the thread's detail document carries the `loop` block.
Weight: medium

| Row | Kind | Req | File | Proves | Change | Completed |
|---|---|---|---|---|---|---|
| 4.1 | test | R4 | `plugins/tempergraph/engine/tests/test_loop_summary.py` | SIL-AC14 | New file with fixture loop records. `loop_summary` holds `recorded`, `filed` and at most three kept observations by confidence (category, unit, confidence, no note text); a loop child with no finding and no observation writes a summary with zero counts; written once per ticket | ✓ 2026-11-22 |
| 4.2 | test | R4 | `plugins/tempergraph/engine/tests/test_loop_summary.py` | CLI-AC10 | Same file: `attention --json` carries `loop[]` beside `items` with the newest summary of each workflow that holds a finding or an observation, never as an item, with the command `tempergraph improve review show <thread>`; the text form prints it after the items; `attention` creates no file; `items` of paused threads is unchanged (the existing `test_reports.py` reads `items` only and needs no edit) | ✓ 2026-11-22 |
| 4.3 | test | R4 | `plugins/tempergraph/engine/tests/test_detail.py` | RDD-AC6 | Add a test that the detail document carries `loop` as `null` before a loop child has ended and as the newest summary after (the existing tests there compare unit states only, not the document's keys, so they stay) | ✓ 2026-11-22 |
| 4.4 | test | R4 | `plugins/tempergraph/engine/tests/test_loop_child.py` | SIL-AC14 | Add an assertion to the child's `process` test that the thread's `loop.jsonl` ends with one `loop_summary` record whose `recorded` and `filed` match the ticket's results | ✓ 2026-11-22 |
| 4.5 | code | R4 | `plugins/tempergraph/engine/src/tempergraph/improve/loop_summary.py` | | New module: `build(root, workflow, task_id, results)` (recorded findings of the thread plus `review_repeat`, filed from the results, top three kept observations of `review_done` by confidence, no note text) and `newest(root, workflow, task_id=None)` reading the newest `loop_summary` of a thread or of each thread of a workflow | ✓ 2026-11-22 |
| 4.6 | code | R4 | `plugins/tempergraph/engine/src/tempergraph/improve/child.py` | | At the end of `process`, after the review and the proposal and before the ledger row, append one `loop_summary` record to the thread's `loop.jsonl` built by `loop_summary.build`; a failure to write it never stops the loop | ✓ 2026-11-22 |
| 4.7 | code | R4 | `plugins/tempergraph/engine/src/tempergraph/observe/attention.py` | | `attention` adds `loop`: for each workflow of each root the newest summary that holds a finding or an observation, with the command `tempergraph improve review show <thread>`; `line` gains a sibling `loop_line` for the text form; it reads only and creates nothing | ✓ 2026-11-22 |
| 4.8 | code | R4 | `plugins/tempergraph/engine/src/tempergraph/cli/observe_cli.py` | | `cmd_attention` prints the `loop_line` of each summary after the items, and the "Nothing is waiting" line only when there is no item and no summary | ✓ 2026-11-22 |
| 4.9 | code | R4 | `plugins/tempergraph/engine/src/tempergraph/observe/detail.py` | | `detail` adds the key `loop` to the document: the newest `loop_summary` of the thread, `null` until a loop child has ended; `cut` leaves it in place | ✓ 2026-11-22 |

### Phase 5: Whole-suite proof

Goal: every criterion of the task is carried by an offline test, the engine's whole offline suite and lint pass, and any spec or record that still disagrees with the code is corrected.
Weight: light

| Row | Kind | Req | File | Proves | Change | Completed |
|---|---|---|---|---|---|---|
| 5.1 | test | R6 | `plugins/tempergraph/engine/tests/test_loop_fixes_coverage.py` | AC 6 | New file: reads the engine's test files and asserts each of SRV-AC8, SRV-AC9, SRV-AC10, SRV-AC11, BUD-AC8, SIL-AC14, SIL-AC15, CLI-AC10 and RDD-AC6 appears in the name or a comment of a test that is not skipped | ✓ 2026-11-22 |
| 5.2 | docs | R6 | `plugins/tempergraph/docs/tasks/loop-fixes.report.md` | | Write the code report: the verification commands as run (the whole offline suite, `ruff check src tests`), every test the new gate rule broke and how it was fixed, the size of spec 44 against `test_spec_budget.py`, and each spec or the decision record that still disagreed with the code and was corrected in the same change, or `None` | ✓ 2026-11-22 |

## 3. Verification

- `cd plugins/tempergraph/engine && pytest`
- `cd plugins/tempergraph/engine && ruff check src tests`
- `cd plugins/tempergraph/engine && pytest tests/test_session_review.py tests/test_review_priority.py tests/test_review_budget.py`
- `cd plugins/tempergraph/engine && pytest tests/test_review_repeat.py`
- `cd plugins/tempergraph/engine && pytest tests/test_check_repeat.py tests/test_improve.py`
- `cd plugins/tempergraph/engine && pytest tests/test_loop_summary.py tests/test_detail.py tests/test_loop_child.py`

| Criterion | Test | Command |
|---|---|---|
| AC 1 | `plugins/tempergraph/engine/tests/test_review_priority.py` | `cd plugins/tempergraph/engine && pytest tests/test_session_review.py tests/test_review_priority.py tests/test_review_budget.py` |
| AC 2 | `plugins/tempergraph/engine/tests/test_review_budget.py` | `cd plugins/tempergraph/engine && pytest tests/test_session_review.py tests/test_review_priority.py tests/test_review_budget.py` |
| AC 3 | `plugins/tempergraph/engine/tests/test_review_repeat.py` | `cd plugins/tempergraph/engine && pytest tests/test_review_repeat.py` |
| AC 4 | `plugins/tempergraph/engine/tests/test_loop_summary.py` | `cd plugins/tempergraph/engine && pytest tests/test_loop_summary.py tests/test_detail.py tests/test_loop_child.py` |
| AC 5 | `plugins/tempergraph/engine/tests/test_check_repeat.py` | `cd plugins/tempergraph/engine && pytest tests/test_check_repeat.py tests/test_improve.py` |
| AC 6 | `plugins/tempergraph/engine/tests/test_loop_fixes_coverage.py` | `cd plugins/tempergraph/engine && pytest` |

## 4. Docs to update

- None. Discovery already wrote the behaviours and criteria of the five specs and the decision record, and the plan's code does what they say. The user guides' lines on `attention` and `improve review` stay true, since they describe the items and the verbs, which do not change. A spec that still disagrees with the code after the build is corrected by the code step in the same change and listed in its report.
