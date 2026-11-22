# Code report: loop-fixes

## Verification

- `cd plugins/tempergraph/engine && pytest`: passed, whole offline suite (the `live` checks stay skipped without `TEMPERGRAPH_LIVE=1`), 0 failures
- `cd plugins/tempergraph/engine && ruff check src tests`: passed, "All checks passed!"
- `cd plugins/tempergraph/engine && pytest tests/test_session_review.py tests/test_review_priority.py tests/test_review_budget.py`: passed
- `cd plugins/tempergraph/engine && pytest tests/test_review_repeat.py`: passed
- `cd plugins/tempergraph/engine && pytest tests/test_check_repeat.py tests/test_improve.py`: passed
- `cd plugins/tempergraph/engine && pytest tests/test_loop_summary.py tests/test_detail.py tests/test_loop_child.py`: passed
- Not in the plan, run for information: `mypy` reports one error in `src/tempergraph/improve/harvest.py:37` (`Need type annotation for "ws"`), a file this change does not touch; `ruff format --check` would reformat 243 files, so the repository does not use it.

Tests the new gate rule broke: none. The whole suite passed with the rule in place and no existing test edited for it.

Spec 44 against `test_spec_budget.py`: 27,496 bytes of 30,720 and 206 lines of 400. No spec was edited by this change.

## Deviations

- Files changed that no task row names, each needed by a row's behaviour:
  - `plugins/tempergraph-monitor/tests/fixtures/detail-paused.json` and `plugins/tempergraph-monitor/tests/fixtures/documents.ts`: `test_monitor_fixtures_match_the_engine` compares the key shape of the detail document with these held fixtures, and row 4.9 adds the key `loop`. I added `"loop": null,` before `events_tail` by hand, in the place the generator writes it, because `make_fixtures.py` is not among the commands this step may run. A later `make_fixtures.py` run should give the same file apart from times and ids.
  - `plugins/tempergraph/engine/src/tempergraph/improve/proposals.py`: `clusters()` gains `review_weight` (the sum of its findings' `review_weight`), because SRV-B27 says "the cluster of `improve backlog` has a `review_weight` of 3". Tested in `test_review_repeat.py` (SRV-AC10).
  - `plugins/tempergraph/engine/src/tempergraph/improve/child.py` also leaves findings of lens `review` out of the friction judge's list and out of the filing candidates (SRV-B28, tested by SRV-AC11 in `test_review_repeat.py`); rows 4.6 names this file for the summary.
- `plugins/tempergraph/engine/tests/test_session_review.py` (row 1.1): only the `pruned`/`infra_only` skip order of `test_capture_levels` needed rewriting (reversed run order). The other two tests the row names did not break; `test_dev_plan_reads_every_session_within_the_cap` gained assertions for the new order and for no count cap, and `test_stable_signals_plan_is_release_2` stays as it was.
- The plan's choice for BUD-B16 says the earlier attempt's failing findings are carried "in the run state next to the attempt": they are carried on the attempt record as `prior_failing` (findings by criterion, place and message, plus the evidence text) and, when a repeat is found, `repeated` and `repeated_evidence`; the pause payload shows `repeated` and, for a check with no findings, `repeated_evidence` (400 characters).
- Review records gained `cost_usd` and `reported` on `review_done` and `review_failed`; SRV-B25 needs a per-review cost in the loop log to sum "the run's review spend so far" across plans. No spec lists these fields.
- `review.max_sessions.full` was removed from `improve/params.py` as row 1.4 says; no test or other code named it.
- `repeat.record` is called by `review.run` only when at least one review finished, and takes its `workflow_version`, `machine` and similar keys from the thread's first existing finding when there is one (the loop ticket does not pass them).
- `improve/repeat.py` imports the private `_jsonl` from `improve/record.py`.
- Rows marked: all 30 rows of the plan are marked and its status is `completed`.
