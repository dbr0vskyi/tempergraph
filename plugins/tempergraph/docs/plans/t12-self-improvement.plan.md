---
goal: Build the self-improvement loop's model-free core first (records, cause codes, lenses, filing and measurement), then lessons; labels, calibration, proposals and trials follow once T7 and T8 land
version: 1
date_created: 2026-11-20
last_updated: 2026-11-20
owner: dbr0vskyi
status: In progress
tags: [track-plan, tempergraph, T12]
tracker: none
spec: plugins/tempergraph/docs/specs/16-self-improvement.spec.md
spec_commit: 804d094
task_id: first-release-t12
---

# T12 Self-improvement

## 0. Hand-off

| Field | Value |
|---|---|
| Origin | [Release 1 plan](first-release.plan.md) track T12 |
| Specs | [SIL](../specs/16-self-improvement.spec.md), [IMD](../specs/43-improvement-data.spec.md), [LSN](../specs/42-workflow-lessons.spec.md); later [FBK](../specs/41-feedback-and-judge-reliability.spec.md), [JCL](../specs/50-judge-calibration.spec.md), [PRP](../specs/40-improvement-proposals.spec.md) |
| Split | This thread: T12.1, T12.2, T12.7 (and T9.1). T7 keeps FBK's `label` verb and the reports; T8 keeps T9.2 and T9.3. T12.3 to T12.6 are built in the thread "Build judge calibration and proposals" on T7's label rows and T8's readiness hooks; `author verify` rungs 8 and 9 are T8's |

**Status: In progress.** T12.1 records, causes and lenses, T12.2 filing and measurement, T12.3 labels and reliability, T12.4 judge calibration, T12.5 proposals, T12.6 trials and T12.7 lessons are built and tested offline; T12.8 remains; the loop child (12.1.5) runs the friction judge and files after a final exit.

Status pass: SIL and IMD move to `ready-for-implementation` with release 1 defaults recorded in their Open questions; FBK, JCL and PRP move to `ready-for-implementation` with their release 1 build recorded in §5.

Release 1 defaults and assumptions (recorded in SIL §5 and Open questions, EVT §2.2 `finding_recorded`):
- Findings live in `runs/<workflow>/<task>/findings.json` and evidence in `runs/<workflow>/<task>/evidence/record.json`, as LOS §2.1 lays out; both owner-only, and only the recorder names the evidence file (source test).
- A **final exit** is an exit that is not a pause (exit 0, 4 or 5). Findings are recorded at every exit; lenses decide only at final exits.
- Cause codes and their classes, sides and fixed remedies are one table in `improve/causes.py`; each threshold is a parameter record with provenance `default_no_data` (IMD §2.5).

## 1. Requirements

| Req | Spec | Criteria | Phase |
|---|---|---|---|
| REQ-60 | SIL | §2.1 to §2.4, B1, B5, B6, B7; AC on the publish boundary | T12.1, T12.2 |
| REQ-61 | IMD | R1, R13 to R15 on the records this track writes; §2.5 parameters | T12.1 |
| REQ-62 | LSN | all | T12.7 |

## 2. Phases

### T12.1 Records and lenses

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 12.1.1 | `engine/tests/test_improve.py` | Cause derivation from fixture run logs and ledger rows (each row of the cause table), fault sides (engine, workflow, `executor:<name>`, host), retry burst and `judge_blocked:<id>`, `blocked_without_check`, `grant_missing` and `grant_unused`, `agent_decided:<cause>`; findings and evidence on every exit; the publish boundary source test; lens triggers in dev and stable mode; the cost rules on a window | SIL §2, IMD §2.5 | yes | P1 | ✓ | 2026-11-20 |
| 12.1.2 | `engine/src/tempergraph/improve/causes.py` | The cause table (code, class `fault`/`infra`/`designed`, side, fixed remedy), `derive(run_log, ledger_rows, thread)` with no model call | SIL §2.3, §2.4 | | P1 | ✓ | 2026-11-20 |
| 12.1.3 | `engine/src/tempergraph/improve/record.py`, `run/runner.py` | `record_exit`: findings (metadata only, IMD-R1 keys, fingerprint by side, workflow, leading cause and step), the evidence file, the `finding_recorded` event as a run-log record; called best-effort after every `run_exit` | SIL §2.1, IMD §2.2, §2.3 | | P1 | ✓ | 2026-11-20 |
| 12.1.4 | `engine/src/tempergraph/improve/lenses.py`, `improve/params.py` | Which lenses fire at a final exit (dev and stable triggers), the outcome lens read from the outcome record, the model-free cost rules over a 30-day window of one version, the per-gate quality scorecard; parameters with provenance | SIL §2.2, IMD §2.5 | | P1 | ✓ | 2026-11-20 |
| 12.1.5 | `engine/src/tempergraph/improve/child.py` | The loop as a built-in workflow started detached through a hand-off ticket after a final exit (friction and outcome steps and judges on a mid-tier alias, 1800 s); uses T7's `tempergraph.detach` launch site; release 1 shape recorded in SIL Open questions; outcome-lens candidates (`outcome_unmet:<criterion>`) file through `calibration.has_score` and the pattern rule | SIL-B1, B2, B3, B6, B7, §5 | yes | P1 | ✓ | 2026-11-20 |

### T12.2 Filing and measurement

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 12.2.1 | `engine/src/tempergraph/improve/filing.py` | De-duplication by fingerprint (search retried once, then file anyway), the pattern rule (3 runs, 3 requests, 30 days; one engine fault is enough), `uncalibrated` stays local, host findings never filed, dry run, an outbox for an unreachable code host; `improve/codehost.py` (`gh` client, a sanctioned launch site, SEC §2.2); executor causes carry the CLI version and `unknown_tool_name` comes from the view catalog | SIL-B2, B3, B4, B6, B7, §4 | yes | P1 | ✓ | 2026-11-20 |
| 12.2.2 | `engine/src/tempergraph/improve/measure.py` | The model-free comparison of two versions (cost per run and unit, repeat share, gate pass rate, outcome mix); one comment, or a reopen after a regression (`measure.quality_drop`) | SIL-B5, C14 | yes | P1 | ✓ | 2026-11-20 |

### T12.7 Lessons

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 12.7.1 | `engine/src/tempergraph/improve/lessons.py`, `model/validate.py`, `render/prompt.py`, `run/nodes.py` | Per-step lessons files, validation (budget, literal floor, unknown unit, malformed), the step-only block after the tools block, `lessons_digest` on the step's `agent_run`, the §2.3 delta rules for the proposal classifier | LSN, PRM §2.1 | yes | P2 | ✓ | 2026-11-20 |

### T12.3 Labels and judge reliability

Built in the thread "Build judge calibration and proposals".

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 12.3.1 | `engine/src/tempergraph/improve/reliability.py`, `observe/labels.py`, `run/judging.py`, `run/nodes.py` | Derived labels (`approval`, `override`, `pushback`, `audit`, `rerun`) at every exit with deterministic ids; `brief_digest` and `criteria_digest` on the `judgement` record so the binding is complete | FBK §2.1, §2.2, EVT §2.2 | yes | P1 | ✓ | 2026-11-20 |
| 12.3.2 | `engine/src/tempergraph/improve/reliability.py`, `improve/params.py` | Figures and grade per gate and binding (FBK-B3 order), live score from JCL's state, `labels queue` and `labels grades` | FBK §2.3, §2.4, JCL §2.5 | yes | P1 | ✓ | 2026-11-20 |
| 12.3.3 | `engine/src/tempergraph/improve/reliability.py`, `improve/causes.py`, `run/runner.py` | Binding-shift watch as `binding_shift` findings; `after_exit` adds labels and shifts to `finding_recorded` | FBK §2.5, EVT §2.2 | yes | P1 | ✓ | 2026-11-20 |

### T12.4 Judge calibration

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 12.4.1 | `engine/src/tempergraph/improve/calibration.py` | Cases and fixtures under the package's `evals/calibration/`, tune and holdout (`mark_tune` has no inverse), `evals label`, templated variants with no model call | JCL §2.1 to §2.3 | yes | P1 | ✓ | 2026-11-20 |
| 12.4.2 | `engine/src/tempergraph/improve/calibration.py`, `cli/improve.py` | `evals score` (the gate's judge on scratch copies, repeats, cap), figures with Wilson bounds, the bar and `evals bar`, the acceptance state per binding | JCL §2.4, §2.5, §2.6 | yes | P1 | ✓ | 2026-11-20 |
| 12.4.3 | `engine/src/tempergraph/package/readiness.py`, `run/outcome_trust.py`, `run/outcome_record.py`, `author/verify.py`, `audit/definition.py`, `cli/outcome.py` | `accepted_for` and `has_score` as the default readers of readiness, stable mode, outcome trust and corrected rates | JCL §2.5, LIF §2.2, OUT §2.2.1 | yes | P1 | ✓ | 2026-11-20 |

### T12.5 Proposals and the proposer

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 12.5.1 | `engine/src/tempergraph/improve/proposals.py` | Clusters and backlog with twins folded, proposal records, the classifier on parsed workflows, weakening person-only, literal check, `engine_side`, `stale_base`, `outside_package`, `invalid`, `no_change` | PRP §2.2 to §2.4, B1 to B3, B10, LSN §2.3 | yes | P1 | ✓ | 2026-11-20 |
| 12.5.2 | `engine/src/tempergraph/improve/proposals.py`, `improve/codehost.py` | The proposer (step session on `improve/<id>` in its own worktree, engine check, independent judge); `open` pushes only that branch and opens a draft, no merge method on any host | PRP §2.1, B4, B8, PRP-AC-2 | yes | P1 | ✓ | 2026-11-20 |

### T12.6 Case sets and trials

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 12.6.1 | `engine/src/tempergraph/improve/trials.py`, `workspace.py`, `settings.py`, `run/runner.py` | Case sets, in-sample cases apart, child runs one at a time (`origin: trial`, dry run, worktree on `ref:<case base>`), sign test, guards, caps, A/A noise floor, grader trials on label agreement | PRP §2.5, §2.6, B5 to B7, WTR §2.5 | yes | P1 | ✓ | 2026-11-20 |
| 12.6.2 | `engine/src/tempergraph/cli/improve.py`, `cli/main.py`, `constants.py`, `data/release.json` | `improve backlog\|propose\|trial\|aa\|open\|show`, schemas `proposal` and `trial` | PRP §2.7, CLI | yes | P1 | ✓ | 2026-11-20 |

Not built in release 1 (recorded in PRP §5): PRP-B9 (needs the merge to be seen; `pr_state` is not derived), the loop starting the proposer or a trial on its own at autonomy `propose` or `trial` (waits on T12.8's daily cap), the `label_recorded`, `proposal_state`, `trial_progress` and `binding_shift` events (IMD §2.3).

### T12.8

Planned: stable mode's daily cap and `report --loop`.

### T12.9 Session digest and dev-mode review

Planned, not started: [SRV](../specs/44-session-review.spec.md) as scoped in the [release plan](first-release.plan.md) T12.9 (I-92 to I-94). Code it needs: `improve/digest.py` (SRV §2.1, §2.2, called by `improve/record.py` before findings), new rows in `improve/causes.py`, `improve/review.py` (plan, condensed view, reviewer launch, citation check, records), `improve/child.py` (run the plan after the friction judge), the `improve review` verbs in `cli/`, the tool-less reviewer launch in the session launcher's pinned list, and a second publish-boundary source test for `evidence/review/`. Stable-mode plans are release 2 (X2-26).

## 3. Verification

From `plugins/tempergraph/engine/`: `python -m pytest`, `ruff check src tests` and `mypy` are clean. No test calls a model.
