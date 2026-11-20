---
title: Promotion check and workflow stages
type: component
status: review
prefix: PRO
adrs: [0041, 0089, 0124]
---

# Promotion check and workflow stages

## 1. Overview

A workflow is improved locally until it needs little supervision, then moved to a pipeline ([ADR-0041](../adr/0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md)). This spec owns the three **stages** (`local-dev`, `local-stable`, `pipeline`), the model-free verb `promote-check` that measures a workflow version against each stage's criteria and writes a **promotion stamp**, the stage every run carries, and the **regressed** watch after a move. Release 2 builds the stages, the check and the stamp for `local-stable`; `--to pipeline`, the `pipeline` stage, the regressed watch and pipeline runs (§2.5, §2.6, the `pipeline` column) are designed here and built with CI pipelines in a later release, refused meanwhile with `not_in_release` (owner, 2026-11-20; [ADR-0124](../adr/0124-promotion-is-a-model-free-stamp-per-workflow-version.adr.md)). Until then a paused run moves between machines by [CAR](96-run-state-on-a-branch.spec.md).

The engine never promotes or demotes a workflow by itself, and a pipeline run never answers its own pause.

## 2. Contract

```text
tempergraph promote-check <workflow> --to local-stable|pipeline [--executor <name>] [--window <n>] [--stamp] [--json]
```

Read-only without `--stamp`; exit 0 when every criterion is met, 6 when any is not (as an advisory verb, [CON §2.9](01-contracts.spec.md)), 2 on a usage error. `--stamp` writes only when every criterion is met.

### 2.1 Stage of a run

| Stage | When |
|---|---|
| `pipeline` (later release) | The caller is `pipeline` or `scheduler` ([PRV §2.1](85-caller-provenance.spec.md)), and the workflow version holds a `pipeline` stamp; in release 2 no run has this stage |
| `local-stable` | Otherwise, the workflow declares `improvement_mode: stable` |
| `local-dev` | Otherwise |

A run with caller `pipeline` whose workflow version has no `pipeline` stamp runs at its local stage and records `unpromoted_pipeline: true`; `attention` lists it. The stage is recorded on the run's `settings_resolved` record and on every ledger row, and is read by [LAD §2.5](92-effort-ladder-and-model-escalation.spec.md), [JRK](93-judge-model-by-risk.spec.md) and [CXR §2.6](94-complexity-routing.spec.md).

### 2.2 Window

The window is the last `--window` finished runs (default 20 for `pipeline`, 10 for `local-stable`) of the **current** workflow version ([VER §2.4](61-version-metadata.spec.md)), excluding trial, scenario and rerun-of-trial runs. A gate escape inside the window restarts it after the escape ([ADR-0041](../adr/0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md)).

### 2.3 Criteria

Defaults with no data behind them, held in one engine config file, raisable per workflow, never lowered. A criterion whose data is missing is `unmeasured`, which is not met.

| # | Criterion | To `local-stable` | To `pipeline` |
|---|---|---|---|
| P1 | Runs in the window, with distinct requests | 10, 3 distinct | 20, 3 distinct |
| P2 | First-pass yield of rung-0 attempts ([LAD §2.7](92-effort-ladder-and-model-escalation.spec.md)) | ≥ 0.5 | ≥ 0.7 |
| P3 | Gate escapes in the window | ≤ 2 | 0 |
| P4 | Every gate's judge binding `accepted`, each risk level used in route mode included ([JRK §2.4](93-judge-model-by-risk.spec.md)) | on the local binding | on the pipeline's executor and alias, and FBK grade `reliable` |
| P5 | Supervision rows of [SUP §2.7](86-supervision-metrics.spec.md) | as SUP | as SUP |
| P6 | Run cost per run, p90 | reported | under the declared `run_cost_cap_usd`, which must be set |
| P7 | Open improvement issues of kind engine or executor fault for this workflow ([SIL](16-self-improvement.spec.md)) | reported | none |
| P8 | Eval suites of the workflow pass on the target executor ([EVS](51-eval-suites.spec.md)) | reported | pass |
| P9 | Escalated attempts: count and pass rate per unit ([LAD §2.7](92-effort-ladder-and-model-escalation.spec.md)) | reported | for every unit with `escalation` `auto` at `pipeline`, ≥ 5 escalated attempts in the window or the last 60 days, with a pass-rate lower bound ≥ 0.5 |
| P10 | Effort ladder seen: share of climbed attempts per unit | reported | reported; a unit whose ladder never climbed is listed `ladder_unseen` |
| P11 | Switch arms: runs per arm used in route mode ([CXR §2.7](94-complexity-routing.spec.md), [SWM](79-measured-switches.spec.md)) | reported | ≥ 5 runs per arm the window used, and the first-pass yield of each arm ≥ P2's bar |
| P12 | Unattended credentials for the target executor on this machine's profile ([TCK §2.4](84-schedule-ticks-and-unattended-fires.spec.md)) | — | a non-interactive credential that every step and judge can use; `interactive_login` is not met |

### 2.4 Promotion stamp

`--stamp` writes `promotion.json` beside the package's `stamp.json` ([VER §2.5](61-version-metadata.spec.md)), outside the content digest, one entry per stage:

| Field | Meaning |
|---|---|
| `stage`, `workflow_version`, `executor`, `alias_bindings` | What was measured |
| `criteria` | Each criterion's number, bar and verdict |
| `ladder_seen`, `escalation_covered`, `arms_covered` | P9 to P11, read by LAD §2.5 and CXR |
| `stamped_at`, `caller` | When and by whom ([PRV](85-caller-provenance.spec.md)); a stamp needs a person or a pipeline caller that a person started |

Any change to the workflow version voids its stamps: the new version runs at its local stage until stamped again.

### 2.5 Regressed watch

After every final exit at stage `pipeline`, the engine re-reads P2, P3, P5, P6 and P9 over the sliding window, best effort (contract C2). A failing criterion marks the workflow `regressed` with the number on the status row and in `attention`; a lifecycle hook event `workflow_regressed` fires ([CLI §2.2](17-engine-cli.spec.md)). Nothing is demoted and no pipeline is stopped; `promote-check --stamp` on the same version is refused until the criterion holds again.

### 2.6 Pauses in a pipeline

A pipeline run that pauses exits 3, and the job ends. The question reaches a person through `attention`, a hook or the monitor; the person resumes where the run's state root lives ([ADR-0041](../adr/0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md)). An `offer` of an escalation is never made at stage `pipeline` (LAD §2.5).

## 3. Behaviours

**PRO-B1 Report, then stamp.** Given 22 runs of version `1.2.0+ab12` with yield 0.75, no escapes, every gate `accepted` on `claude/medium` and `reliable`, SUP rows met, a p90 of $3.10 under a $5 cap, eval suites passing and an API key in the profile, when `promote-check --to pipeline` runs, then it prints every row met and exits 0; with `--stamp` it writes `promotion.json`.

**PRO-B2 Unmeasured is not met.** Given the same workflow with no supervision cost on 30% of runs, when the check runs, then the SUP row "runs with supervision cost measured" is `unmeasured`, the exit is 6, and `--stamp` writes nothing.

**PRO-B3 Escalation must be covered.** Given a unit with `escalation.stages.pipeline: auto` and 2 escalated attempts in the window, when the check runs, then P9 fails naming the unit, and the fix offered is to set the unit's pipeline stage to `off` or to gather escalations locally.

**PRO-B4 A new version runs unpromoted.** Given a `pipeline` stamp on `1.2.0+ab12`, when version `1.2.1+cd34` is run by a CI job, then the stage is `local-stable`, the record says `unpromoted_pipeline: true`, and any `auto` escalation behaves as at that stage.

**PRO-B5 Regressed.** Given a promoted workflow whose last 20 pipeline runs show one gate escape, when the next run exits, then the status row shows `regressed: P3 = 1`, `attention` lists it, and the next pipeline run still starts.

## 4. Error conditions

| Condition | Result |
|---|---|
| `--to pipeline` with `--executor` not registered in this release | Exit 2 with `not_in_release` |
| A package that is an installed copy | `--stamp` refused, as for the upgrade stamp ([WUP §2.6](63-workflow-upgrade.spec.md)) |
| No run in the window | Every criterion `unmeasured`; exit 6 |
| `promotion.json` unreadable | Treated as no stamp, warned |

## 5. Design notes

- The check reads the same functions as `report --supervision`, `report --loop` and `evals bar`, so a number never differs between two verbs (SUP-AC-3).
- When pipelines arrive, the pipeline's executor is `claude` with an API key, an `apiKeyHelper` or cloud credentials, or `agent-sdk` (ADR-0041 C1); each executor's stamp is a separate entry.
- P9 to P11 exist because a ladder, an escalation or a router is a path the pipeline must not take unmeasured ([R-120](../research/R-120-effort-ladders-and-one-step-model-escalation.rsrch.md), [R-126](../research/R-126-routing-by-complexity-between-decompositions.rsrch.md)).

## 6. Acceptance criteria

- [ ] PRO-AC-1 PRO-B1 to PRO-B5 hold offline on fixture ledgers, run logs, score files and labels.
- [ ] PRO-AC-2 Without `--stamp` the verb creates and changes nothing (contract C13).
- [ ] PRO-AC-3 Every criterion of §2.3 has a fixture where it alone fails, and its row names the number and the bar.
- [ ] PRO-AC-4 A change to any file inside the content digest voids every stamp of the package.
- [ ] PRO-AC-5 Later release, live: one pipeline run on `claude` with an API key reaches the outcome gate on a scratch repository, and its pause exits 3 (probe P-PRO-1).
- [ ] PRO-AC-6 Release 2: `--to pipeline` and a `pipeline` caller's stamp are refused with `not_in_release`.

## Open questions

| Question | Owner | Default |
|---|---|---|
| Where does a pipeline run's state root live between jobs? (ADR-0041 C2) | Owner | CAR's state branch, as the owner proposed on 2026-11-20; a hosted store later |
| Are 20 runs and the other bars right? | Owner, after the first 20 runs of one workflow | As stated |

## References

[ADR-0041](../adr/0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md) · [SUP §2.7](86-supervision-metrics.spec.md) · [JCL](50-judge-calibration.spec.md) · [FBK](41-feedback-and-judge-reliability.spec.md) · [EVS](51-eval-suites.spec.md) · [TCK §2.4](84-schedule-ticks-and-unattended-fires.spec.md) · [LAD](92-effort-ladder-and-model-escalation.spec.md) · [CXR](94-complexity-routing.spec.md)
