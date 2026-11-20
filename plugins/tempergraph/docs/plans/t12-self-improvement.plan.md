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
| Split | This thread: T12.1, T12.2, T12.7 (and T9.1). T7 keeps FBK's `label` verb and the reports; T8 keeps T9.2 and T9.3. T12.3 to T12.6 wait on T7's label rows and T8's readiness hooks (`package/readiness.py`, `run/outcome_trust.trust(accepted=…)`, `author verify` rungs 8 and 9) |

**Status: In progress.** T12.1 records, causes and lenses, T12.2 filing and measurement and T12.7 lessons are built model-free; the loop child (12.1.5) runs the friction judge and files after a final exit.

Status pass: SIL and IMD move to `ready-for-implementation` with release 1 defaults recorded in their Open questions.

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
| 12.1.5 | `engine/src/tempergraph/improve/child.py` | The loop as a built-in workflow started detached through a hand-off ticket after a final exit (friction and outcome steps and judges on a mid-tier alias, 1800 s); uses T7's `tempergraph.detach` launch site; release 1 shape recorded in SIL Open questions | SIL-B1, B2, B6, §5 | yes | P1 | ✓ | 2026-11-20 |

### T12.2 Filing and measurement

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 12.2.1 | `engine/src/tempergraph/improve/filing.py` | De-duplication by fingerprint (search retried once, then file anyway), the pattern rule (3 runs, 3 requests, 30 days; one engine fault is enough), `uncalibrated` stays local, host findings never filed, dry run, an outbox for an unreachable code host; `improve/codehost.py` (`gh` client, a sanctioned launch site, SEC §2.2); executor causes carry the CLI version and `unknown_tool_name` comes from the view catalog | SIL-B2, B3, B4, B6, B7, §4 | yes | P1 | ✓ | 2026-11-20 |
| 12.2.2 | `engine/src/tempergraph/improve/measure.py` | The model-free comparison of two versions (cost per run and unit, repeat share, gate pass rate, outcome mix); one comment, or a reopen after a regression (`measure.quality_drop`) | SIL-B5, C14 | yes | P1 | ✓ | 2026-11-20 |

### T12.7 Lessons

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 12.7.1 | `engine/src/tempergraph/improve/lessons.py`, `model/validate.py`, `render/prompt.py`, `run/nodes.py` | Per-step lessons files, validation (budget, literal floor, unknown unit, malformed), the step-only block after the tools block, `lessons_digest` on the step's `agent_run`, the §2.3 delta rules for the proposal classifier | LSN, PRM §2.1 | yes | P2 | ✓ | 2026-11-20 |

### T12.3 to T12.6, T12.8

Planned after T7 and T8 are merged into this branch: labels and judge reliability (T7 builds the `label` verb and its ledger rows), calibration (feeds T8's readiness and trust hooks), proposals and trials, stable mode's daily cap and `report --loop`.

### T12.9 Session digest and dev-mode review

Planned, not started: [SRV](../specs/44-session-review.spec.md) as scoped in the [release plan](first-release.plan.md) T12.9 (I-92 to I-94). Code it needs: `improve/digest.py` (SRV §2.1, §2.2, called by `improve/record.py` before findings), new rows in `improve/causes.py`, `improve/review.py` (plan, condensed view, reviewer launch, citation check, records), `improve/child.py` (run the plan after the friction judge), the `improve review` verbs in `cli/`, the tool-less reviewer launch in the session launcher's pinned list, and a second publish-boundary source test for `evidence/review/`. Stable-mode plans are release 2 (X2-26).

## 3. Verification

From `plugins/tempergraph/engine/`: `python -m pytest`, `ruff check src tests` and `mypy` are clean. No test calls a model.
