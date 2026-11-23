# A trust report on temperspec's pull requests

| | |
|---|---|
| Date | 2026-11-21 |
| Asked by | The owner: for the temperspec flow, a code judge in the pull request's pipeline that shows plan and task completion together with the crucial code-to-spec alignment, so a reviewer sees whether to trust the result. It adds to the gates inside the run and moves none of them |
| Method | temperspec's final criteria (`outcome.json`, revision as of this date) read against the engine's research note on a pull-request gate, [R-135](../../../tempergraph/docs/research/R-135-a-final-gate-in-the-pull-request-pipeline.rsrch.md), which states the capability without naming any workflow |
| Status | Proposal. Waits for the engine's pull-request gate; backlog row B15 |

## 1. Summary

temperspec needs nothing of its own to get a pipeline report: every one of its nine final criteria can be graded from the pull request's branch alone, because the triage note, the plan and the specs are committed there and "what the run edited" is the branch's diff against its base. So the report is the engine's gate applied to temperspec's existing `outcome.json`, plus a short section shape the package declares. No new criterion and no second judge brief.

## 2. The final criteria in a pipeline

| Criterion | Verified by | Graded in CI from | Report section |
|---|---|---|---|
| `ts-committed` | check | the branch: no uncommitted file is possible on a pushed head, so it reduces to "the receipt's head is on the branch" | Completion |
| `ts-spec-form`, `ts-spec-cap`, `ts-spec-links` | check | the specs changed against the base, read with `specfmt.py` | Specs |
| `ts-traced` | check | the changed specs' criterion ids against the tests, and the test run's skips | Code and spec alignment |
| `ts-verify` | check | the plan's verification commands, run on the branch head by the engine's command runner | Completion |
| `ts-collateral` | check (warning) | the changed specs' diffs | Specs |
| `ts-spec-sync` | judge | the changed specs and the specs they link to | Code and spec alignment |
| `ts-accepted` | judge | the triage note's acceptance criteria, the diff, the test results and `ts-traced`'s findings as evidence | Task completion |

**Plan completion** is one more line the package's check can add as a fact without a new criterion: the plan's row marks and status (plan format, [plan format note](plan-format-review.rsrch.md)), counted as done, open and dropped rows. It is shown, not graded, since an open row is allowed when the plan says why.

## 3. The report a reviewer would see

1. One line: in-run outcome against pipeline outcome (for example `met` / `met`, or `met` / `unmet` with the criterion), and "commits since the run" when the head moved.
2. **Task completion**: each acceptance criterion of the triage note with its status, the proving test (`path::name`) and the command that ran it.
3. **Plan completion**: rows done, open and dropped; verification commands and exit codes.
4. **Code and spec alignment**: per changed spec, form, cap and links; criteria with no test or a skipped test; `ts-spec-sync`'s status and, if the owner allows reasons, its one-line reason.
5. Anything not graded, with why. For temperspec that list is empty today.

## 4. What temperspec's docs need when it is built

- Its final stage keeps writing the pull request body as now and appends the receipt the engine renders in its context: one line in `workflow/temperspec/`, within the body's 4,000-character cap.
- The two judge criteria start `uncalibrated` on the pipeline's binding; their seeds in `evals/calibration/outcome/` are scored on that binding before `block` mode can use them.
- The judge in CI stays at most Sonnet, per the owner's ruling for the whole workflow; its sizing and reason go into the blueprint's `pr_gate` block like every other session's.
- B3 of the backlog (a model-free drift check for pre-commit and CI) is the model-free half of the same pipeline job and can share its generated file.
