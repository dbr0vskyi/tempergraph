---
goal: Build the gate funnel — run log and cost, checks and command runs, the judge and verdict rule, the independence guard, the gate and human nodes, budgets and failures, script units and the finalizer, and the runner that drives a thread
version: 1
date_created: 2026-11-20
last_updated: 2026-11-20
owner: dbr0vskyi
status: In progress
tags: [track-plan, tempergraph, T5]
tracker: none
spec: plugins/tempergraph/docs/specs/05-judge-and-verdict.spec.md
spec_commit: d5bdd1c
task_id: first-release-t5
---

# T5 Gate funnel

## 0. Hand-off

| Field | Value |
|---|---|
| Origin | [Release 1 plan](first-release.plan.md) track T5 |
| Specs | [OBS](../specs/15-observability-and-cost.spec.md), [CHK](../specs/75-check-contract-and-command-runs.spec.md), [JDG](../specs/05-judge-and-verdict.spec.md), [GRD](../specs/06-independence-guard.spec.md), [HUM](../specs/07-gate-and-human.spec.md), [BUD](../specs/08-budgets-and-failures.spec.md), [SCR](../specs/70-script-units-and-hybrid-steps.spec.md), [FIN](../specs/78-finalizer-contract.spec.md), [OUT](../specs/90-run-outcome.spec.md) |
| Event kinds | [EVT §2.2](../specs/30-run-events.spec.md) |

**Status: In progress.** The funnel runs end to end with scripted executors: start, step, check, judge, re-ask, guard, verdict by rule, gate routing, pauses, resume with a decision, BACK to an earlier unit, budget ask or stop, infra stop with exit 5, the run cost cap drain, and the finalizer. Status pass: all nine specs are `ready-for-implementation`; GRD, BUD, CHK and OUT have release 1 defaults for their open questions.

Doc changes this track made:
- OBS §2.2 names the release 1 default price table. It uses the first-party list prices of the generation the tier aliases resolve to, as of 2026-11.
- LOS §2.1 lists `exit.json` in the run folder. DUR-B5 names it as the place a run's own exit code is recorded.

The open rows below are honest gaps, not deferrals to a later release. Each one is release 1 scope and keeps the track open.

## 1. Requirements

| Req | Spec | Criteria | Phase |
|---|---|---|---|
| REQ-13 | OBS | all (the analysis verbs in T7.4) | T5.1 |
| REQ-14 | CHK | all but AC-6 | T5.2 |
| REQ-15 | JDG | all but AC-7 | T5.3 |
| REQ-16 | GRD | all | T5.4 |
| REQ-17 | HUM | AC-1, AC-4; AC-2 for escalation, budget, approval | T5.5 |
| REQ-18 | BUD | all | T5.6 |
| REQ-19 | SCR, FIN | SCR all but AC-4; FIN all | T5.7 |
| REQ-34 | OUT | AC-1 to AC-5 | T5.8 |

## 2. Phases

All tests are in `engine/tests/test_run.py` unless named. ✓ means built and tested; ○ means open.

### T5.1 Run log, ledger and cost

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 5.1.1 | `run/log.py` | `RunLog` (schema line, envelope), `LiveSink` (`live.json`, `activity.jsonl`), `Ledger`, `CostTotals` with reported and estimated apart, `estimate` with the default price table | OBS §2.1–2.3, EVT §2.1 | yes | P1 | ✓ | 2026-11-20 |
| 5.1.2 | `run/nodes.py`, `run/runner.py` | `attempt_start`, `agent_run`, `check`, `judgement`, `gate`, `pause`, `human`, `script`, `finalize`, `unit_entered`, `run_started`, `stop_requested`, `run_exit` records; `exit.json`; one ledger row per segment | OBS §2.1, EVT §2.2 | yes | P1 | ✓ | 2026-11-20 |
| 5.1.5 | `run/log.py` | `seq` continues across segments, read from the log's tail (EVT-B2); the `pause` record carries `pause_kind` | EVT §2.1, B2 | yes | P1 | ✓ | 2026-11-20 |
| 5.1.6 | `run/gate.py`, `run/nodes.py`, `run/runner.py` | A trip back gives every later unit that already ran a new visit, so it writes `unit_entered` again; `entered_from` is `start`, `proceed`, `back:<unit>` or `rewind:<unit>`; `run_started` carries `alias`, `label`, `workflow_version`, `plan_digest` and the planned executors | EVT §2.2 | yes | P1 | ✓ | 2026-11-20 |
| 5.1.3 | `run/log.py`, `run/nodes.py`, `run/runner.py` | `cost_so_far` (reported, estimated, completeness) on `gate`, `pause` and `run_exit` ✓; `settings_resolved` ✓ (T6.2); the `supervision` record before `run_exit` ✓ (T6.5) | EVT §2.2, SUP §2.2, RST §2.7 | yes | P2 | ✓ | 2026-11-20 |
| 5.1.7 | `run/runner.py`, `workspace.py` | The `workspace` record (action, mode, resolved_by, branch, base_commit, reason, counts; the path in the local log only) where a worktree is prepared, reused, attached or kept; `removed` and `foreign` wait for `cleanup: on_finish` (release 2) and the foreign worktree scan | EVT §2.2, WTR §2.6, §2.10 | yes | P2 | ✓ | 2026-11-20 |
| 5.1.4 | `tests/test_run_log.py` | OBS-B3: a full disk while writing the ledger or the exit file keeps the exit code, and one `engine_error` record of the failure is attempted | OBS-B3 | yes | P1 | ✓ | 2026-11-20 |
| 5.1.8 | `identity.py`, `run/runner.py`, `run/rerun.py`, `tests/test_identity.py` | IMD-R1 join keys on every `run_segment` and intervention ledger row: `workflow_version`, `machine` (the random id of `machine.json`), `repo` (16 hex of the SHA-256 of the normalized `origin` URL, null without one) | IMD-R1 | yes | P1 | ✓ | 2026-11-20 |

### T5.2 Checks and command runs

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 5.2.1 | `run/commands.py` | Allow-list resolution, the command environment, `run_command` with timeout, tree stop and output file | CHK §2.3–2.4, SEC §2.4 | yes | P1 | ✓ | 2026-11-20 |
| 5.2.2 | `run/checks.py` | `CheckContext`, git facts, `normalise`, `run_check`; a raising check is an environmental FAIL; a failed check starts no judge (JDG-AC-2) | CHK §2.1–2.2, CON §2.8 | yes | P1 | ✓ | 2026-11-20 |
| 5.2.3 | `run/check_worker.py`, `tests/test_checks.py` | The check worker: a child engine process that gets the context on stdin, bounded by `check_timeout_s` plus 30 s with a tree stop through the session launcher; a check's prints go to stderr. A raising check is FAIL with `environmental: false` (CHK §4); a worker past its limit is environmental | CHK §2.6, §4, ADR-0019 | yes | P1 | ✓ | 2026-11-20 |
| 5.2.4 | `run/checks.py` | Mechanical criteria and their findings in the judge prompt ✓; command run reuse across a gate's check and the judge's facts ○ | CHK §2.2, §2.4 | yes | P2 | ○ | |

### T5.3 Judge and verdict

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 5.3.1 | `run/judging.py` | `render_judge`, `reask_prompt`, `parse_judgement` (last fenced block, id must match its number), `derive` by rule: MET without evidence is PARTIAL, gap or UNVERIFIABLE escalates, all `defect_in` gives BACK to the earliest, all `no_change` escalates, else RETRY | JDG §2.1, §2.2 | yes | P1 | ✓ | 2026-11-20 |
| 5.3.2 | `run/nodes.py` | One re-ask, then escalate (JDG-AC-3); the judge sees the request and never a verdict it writes | JDG-AC-1, AC-3 | yes | P1 | ✓ | 2026-11-20 |
| 5.3.3 | `tests/test_judging.py` | Table tests for every `derive` row and every `Unparsed` reason | JDG §2.2, B2 | yes | P1 | ✓ | 2026-11-20 |

### T5.4 Independence guard

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 5.4.1 | `run/guard.py` | `view_set` from the step's tools and the judge executor's capabilities; `guard` voids a judgement with an outside call, the step's own session or a changed workspace | GRD §2.1–2.3 | yes | P1 | ✓ | 2026-11-20 |
| 5.4.2 | `tests/test_guard.py` | GRD-AC-5 on recorded `claude` stream fixtures | GRD-AC-5 | yes | P2 | ○ | |

### T5.5 Gate and human nodes

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 5.5.1 | `run/gate.py` | `decide` (pure); `pause_payload` with the resume command (HUM-AC-2); `check_decision` refuses before anything is written; `apply_decision` for proceed, retry, back, rewind, stop with feedback | HUM §2, §4 | yes | P1 | ✓ | 2026-11-20 |
| 5.5.2 | `run/nodes.py` | Escalation, budget, approval and tool-access pauses | HUM §2.1 | yes | P1 | ✓ | 2026-11-20 |
| 5.5.3 | `run/runner.py` | The intervention ledger row (HUM-B6), appended before the graph runs: id, `caller`, SUP §2.1 touch classes, pause kind, decision, wait seconds from the `pause` record, whether feedback was given, cause word. `ruling`, setting keys and grants stay empty until T6.2 to T6.4 give them values; the caller's kind, decider and relay evidence come with T6.5 | HUM-B6, SUP §2.1, PRV §2.5 | yes | P1 | ✓ | 2026-11-20 |
| 5.5.4 | `run/runner.py` | Rulings carried into later judge prompts (built in T6.4, 6.4.2) | RRN §2.3 | yes | P2 | ✓ | 2026-11-20 |
| 5.5.5 | `run/runner.py` | `--pause-before <unit>`: release 2 (X2-13); refused `not_in_release` by 6.1.6 | HUM §2.1 | yes | P2 | moved | |

### T5.6 Budgets and failures

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 5.6.1 | `run/nodes.py`, `run/gate.py` | Retry, loop and infra budgets by cause; 10, 20, 40 s backoff; infra never pauses (BUD-AC-3); auth and refusal escalate with no retry; attempt cap of 15 per invocation; run cost cap drains with exit 5; `slow_host` from the tool wall share | BUD §2.1–2.4 | yes | P1 | ✓ | 2026-11-20 |
| 5.6.2 | `run/runner.py` | A stopped thread re-opens through the human node | BUD-B4 | yes | P1 | ✓ | 2026-11-20 |
| 5.6.3 | `run/nodes.py` | Model ladder: a rung per retry, an infra rerun repeats its rung, a person's retry, a re-open or a trip back starts at the first rung, the judge on the last rung of a declared ladder (BUD-B7) | BUD §2.3 | yes | P2 | ✓ | 2026-11-20 |

### T5.7 Scripts and finalizer

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 5.7.1 | `run/nodes.py` | Script units through the command runner, `script` records, environmental failures escalate | SCR §2.1 | yes | P1 | ✓ | 2026-11-20 |
| 5.7.2 | `run/nodes.py` | Hybrid `before` and `after` scripts of a step: `before` runs after the prompt fields are built and its artifacts join them, a failure spends a retry with no session; `after` runs only on a clean session | SCR §2.2 | yes | P1 | ✓ | 2026-11-20 |
| 5.7.3 | `run/finalize.py` | `FinalizerContext`, `FinalizerResult`, `run_finalizer` with outcome, reason, url and manual steps; exported from `tempergraph.api` | FIN §2 | yes | P1 | ✓ | 2026-11-20 |

### T5.8 Run outcome gate

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 5.8.1 | `run/outcome.py`, `tests/test_outcome.py` | `read_outcome`, `parse_outcome` and the file rows of OUT §4; `gate_criteria` with `mechanical` for `check` criteria; `check_against` for the unit rows; scales in the judge prompt (with 5.8.2). Trust and coverage moved to T8 (`run/outcome_trust.py`, SCF §2.7) | OUT §2.1–2.3, ADR-0114 | yes | P1 | ✓ | 2026-11-20 |
| 5.8.2 | `run/outcome.py`, `run/nodes.py`, `run/gate.py` | The outcome unit compiled from `outcome.json` (no session, deliverables check plus the workflow's own outcome check, a fresh judge with the default stance and the strongest step-judge model, back target derived from `serves`, else escalate); `sign_off` in the approval pause; scales rendered in the judge prompt. The `on_trigger` mode for `stable` and per-criterion sign-off statuses (`--criterion id=signed`) are open | OUT §2.4, §2.2.1 | yes | P1 | ✓ | 2026-11-20 |
| 5.8.3 | `run/outcome_record.py`, `cli/outcome.py`, `tests/test_outcome_record.py` | The outcome record (`outcome` run-log record, the ledger row's `outcome{}`, `not_reached` before the gate; sign-off graded by its caller); the uncorrected measures per revision (met rate, escape rate, unverified share, upstream agreement, sign-off load); `outcome show [--runs]` and `outcome candidates` (read-only). Release 1 defaults in OUT Open questions. `outcome show` prints the record's own trust until T8's trust and coverage are wired in | OUT §2.5 | yes | P1 | ✓ | 2026-11-20 |

## 3. Verification

From `plugins/tempergraph/engine/`: `python -m pytest`, `ruff check src tests` and `mypy` are clean. Every run in these tests uses scripted stand-ins, so no model is called. Live checks against a signed-in `claude` wait for the owner's machine ([T3 plan](t3-executors.plan.md)).
