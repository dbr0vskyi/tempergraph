---
task: loop-fixes
complexity: complex
status: planned
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

### Phase 2: A category kept in several sessions

Goal: three kept sessions of one category on one unit give one `review_repeat` finding that is listed by `improve backlog`, corroborates its own category in the review readers and files nothing, alone or across runs.
Weight: medium

### Phase 3: The same check failure twice

Goal: a check that fails with the same findings on two attempts in a row, the later step having changed files, makes the gate pause at once with cause `check_repeat`, and the loop records the finding for that unit.
Weight: medium

### Phase 4: The loop's summary

Goal: the loop child writes `loop_summary`, `attention` shows the newest summary of each workflow beside its items, and the thread's detail document carries the `loop` block.
Weight: medium

### Phase 5: Whole-suite proof

Goal: every criterion of the task is carried by an offline test, the engine's whole offline suite and lint pass, and any spec or record that still disagrees with the code is corrected.
Weight: light

## 3. Verification

- `cd plugins/tempergraph/engine && pytest`
- `cd plugins/tempergraph/engine && ruff check src tests`

## 4. Docs to update

- None. Discovery already wrote the behaviours and criteria of the five specs and the decision record, and the plan's code does what they say. The user guides' lines on `attention` and `improve review` stay true, since they describe the items and the verbs, which do not change. A spec that still disagrees with the code after the build is corrected by the code step in the same change and listed in its report.
