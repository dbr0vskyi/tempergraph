The answer to a pause is a finding: what a decision overrode, confirmed or repeated is recorded with ids, given a cause code and filed by the count (issue: #255)

Owner's direction of 2026-11-27: the loop must notice what a person had to do in a run and report it. The measurement is in `batch-queue/loop-automation-gap.md`: seven operator touches on four threads in one night, none filed, none with a cause that names what was overridden. This run builds stage S1 of that file. The area is the engine only (`plugins/tempergraph`): specs `friction-causes`, `supervision-metrics`, `loop-issues`, `engine-cli` (CLI-B24), `check-contract-and-command-runs` (CHK-B14). The engine names no workflow.

What the code does today, on the trunk at `9149f0fd`:

- `run/runner.py` writes one `intervention` ledger row for each decision: the unit, the decision, the pause kind, the pause reason (`cause`), `wait_s`, the caller, the touch classes, and `operator_reason` only when `resume --reason` was given. The row has no item and nothing about what the decision answered.
- `run/nodes.py` writes a `check` record with `result`, `environmental` and 200 characters of evidence. The criterion ids of the failing findings the check returned (CHK-B14) are not on it.
- `improve/causes.py` derives `check_fail:<unit>`, `environmental` (class `infra`), `blocked`, `loop_budget_spent` and `agent_decided:<pause kind>`. The last is class `designed` when the caller that started the run answers (FRC-B6), so it never files. No cause says that a decision overrode a gate.
- `improve/pause_facts.py` gives the friction judge one row of facts for each paused segment, as a hint for attribution. A judgement's `claim` (the unit an upstream claim names) is recorded and not read by any cause.

Acceptance criteria:

1. A `check` record holds `failed`: the criterion ids of the check's findings with status `fail`, each once, in the check's order, at most 20, and an empty list when no finding names an id. No message, place or fix is added to the record.
2. An `intervention` row holds the item of the pause it answers and `answered`: the last check result of the paused unit and item, its `failed` ids, whether it was `environmental`, the blockers and the `gap` flag of the last judgement, that judgement's `claim` and its `guard` word. A fact the run log does not hold is `not recorded`. The row holds ids, enums and numbers only.
3. A decision `proceed` that answers a pause whose last check result is FAIL and not environmental makes the finding `answer_overrode:check` on the paused unit; with an environmental FAIL, `answer_overrode:environment`; with a judgement whose `gap` is true or whose pause reason is `unresolved_gap`, `answer_overrode:gap`; at a pause of kind `budget`, `answer_overrode:budget`. One finding per unit and kind in a segment, with the count of such decisions.
4. An `answer_overrode` finding carries `criteria`: each failing or blocking criterion id with its count, and `items`: the number of distinct items. Two overrides of two criteria of one gate make one finding, and a test proves one fingerprint.
5. A decision `back:<unit>` that answers a pause whose last judgement holds `claim` equal to that unit makes the finding `upstream_confirmed:<unit>` on the claimed unit, with the paused unit in `from_unit`.
6. A decision `retry` after which the next gate of the paused unit and item is `PROCEED` with the workspace unchanged makes the finding `retry_passed_unchanged:<pause reason>` on the paused unit. A decision `retry` after which the same unit and item pauses again before any `PROCEED` makes `retry_same_failure` on that unit.
7. A segment started by a decision other than `stop` that opens no session and ends with exit 4, or with a pause of the same unit, item and reason, makes the finding `resume_no_progress` with side `engine`, counted once for each such segment of the thread.
8. Each cause of criteria 3 to 7 is class `fault` whoever decided, a person or an agent, the caller that started the run or another. `agent_decided` keeps the class FRC-B6 gives it. A fixture run started and answered by one agent session proves both in the same findings document.
9. The causes of criteria 3 to 6 file by the pattern rule of SIL-B3 without the friction judge's answer, as SIL-B34 does for an escape; `resume_no_progress` files at a final exit when its count in the thread is 2 or more. A replay test of three fixture runs with three requests files one issue for `answer_overrode:check` at one unit, and two runs file none.
10. `resume --reason` is required when the caller that decides is an agent and the decision answers a pause: without it the engine refuses before any change with exit 2 and a message that lists the six words. A person's decision without it is accepted as today. The resume line a pause prints names the option.
11. A finding of criteria 3 to 7 carries `reasons`: the count of each operator reason over its decisions, `not given` among them, and `wait_s_median`.
12. The body of an issue filed for one of these causes has a section `## What was answered`: decisions by word, operator reasons by word, criterion ids with counts, the number of items and runs, and the median wait. It holds ids, enums and numbers only, and the canary test for free text (ISS-B10) covers it.
13. The friction judge's prompt lists the new findings like any other; its answer does not change whether they file. `loop_result` holds the reason `pattern_met` or `below_count` with the counted numbers (FFD-B4).
14. A fixture for each of seven shapes proves the finding it makes and nothing else new: a gap answered `proceed`; a decision that ends `stopped` with no session; an environmental FAIL answered `proceed`; a check FAIL of one criterion on a map item answered `proceed`; a spent loop budget with a claim answered `back:` to the claimed unit; a `retry` followed by the same pause and then `proceed`; a discarded judgement answered `retry` that then passes unchanged.
15. The behaviours go in `friction-causes.spec.md` (9.7 KB of 30 KB) with their criteria; `self-improvement.spec.md` (30.1 KB of 30 KB) changes only where it would be false; `supervision-metrics`, `engine-cli` and `check-contract-and-command-runs` state the row, the option and the record field. The guide `improving-workflows` names the causes. Each new test carries the id of the spec criterion it proves, and the existing tests of `test_friction_causes.py` and `test_friction_replay.py` still pass, changed only where a criterion above changes the fact they assert.

Out of scope, each named in the report:

- A record of a command ended at its limit, a warning before such a run, and a finding for a pause whose payload lacks facts (stage S2).
- A decision record written at autonomy `record` or under `--dry-run` (stage S3, #208).
- Any change to what a run does at a pause: a re-ask after a discarded judgement, a judge's re-read (#204), an environmental FAIL that does not block (#203).
- The analysis session, check replay and their output (stages S5 to S7).
- Feedback or ruling text in any record the loop reads (SIL-B38), and the class rule of FRC-B6.
- Findings of a thread that never reaches a final exit (#170), and issues a person already filed (#196).

Likely files: `plugins/tempergraph/engine/src/tempergraph/run/runner.py` (the intervention row), `run/nodes.py` (the `check` record), `improve/causes.py`, `improve/record.py`, `improve/filing.py` (`decide`, `body`), `improve/issue_context.py`, `improve/pause_facts.py`, `cli/main.py`; tests beside `tests/test_friction_causes.py`, `tests/test_friction_replay.py` and `tests/test_loop_issues.py`; the specs and the guide above. No file of a workflow package.

To settle before the run starts: no issue exists for this request; the owner files one and its number replaces the first line's note. Criterion 10 changes what an agent caller must pass; the owner may cut it to a later request.
