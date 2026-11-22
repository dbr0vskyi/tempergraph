# Promotion check and workflow stages

## Purpose

A workflow is improved locally until it needs little supervision, then moved to a pipeline ([ADR-0041](../adr/0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md)). This spec owns the three stages (`local-dev`, `local-stable`, `pipeline`), the model-free verb `promote-check` that measures a workflow version against each stage's criteria and writes a promotion stamp, the stage every run carries, and the regressed watch after a move ([ADR-0124](../adr/0124-promotion-is-a-model-free-stamp-per-workflow-version.adr.md)). The engine never promotes or demotes a workflow by itself, and a pipeline run never answers its own pause. Effort ladders ([LAD](92-effort-ladder-and-model-escalation.spec.md)), risk rules ([JRK](93-judge-model-by-risk.spec.md)) and complexity switches ([CXR](94-complexity-routing.spec.md)) read the stage; until pipelines exist a paused run moves between machines by [CAR](96-run-state-on-a-branch.spec.md). Design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### PRO-B1 Report, then stamp

WHEN `promote-check` finds every criterion met THE engine SHALL print every row met and exit 0, and with `--stamp` write `promotion.json`.

- GIVEN 22 runs of `1.2.0+ab12` with yield 0.75, no escapes, every gate `accepted` on `claude/medium` and `reliable`, SUP rows met, a p90 of $3.10 under a $5 cap, eval suites passing and an API key in the profile WHEN `promote-check --to pipeline --stamp` runs THEN every row is met, exit 0, and `promotion.json` is written

### PRO-B2 Unmeasured is not met

WHEN a criterion's data is missing THE engine SHALL report it `unmeasured`, which is not met, exit 6 and write no stamp.

- GIVEN 30% of runs with no supervision cost WHEN the check runs THEN "runs with supervision cost measured" is `unmeasured`, exit 6, and `--stamp` writes nothing

### PRO-B3 Escalation must be covered

WHEN a unit has `escalation` `auto` at stage `pipeline` with fewer than 5 escalated attempts in the window or the last 60 days THE engine SHALL fail P9 naming the unit and offer setting the unit's pipeline stage to `off` or gathering escalations locally.

- GIVEN a unit with `escalation.stages.pipeline: auto` and 2 escalated attempts WHEN `promote-check --to pipeline` runs THEN P9 fails naming the unit

### PRO-B4 A new version runs unpromoted

WHEN a `pipeline` caller runs a workflow version with no `pipeline` stamp THE engine SHALL run it at its local stage and record `unpromoted_pipeline: true`, any `auto` escalation behaving as at that stage.

- GIVEN a `pipeline` stamp on `1.2.0+ab12` WHEN a CI job runs `1.2.1+cd34` THEN the stage is `local-stable` and the record says `unpromoted_pipeline: true`

### PRO-B5 Regressed

WHEN a run exits at stage `pipeline` and a re-read criterion fails THE engine SHALL mark the workflow `regressed` with the number on the status row and in `attention`, fire the hook event `workflow_regressed` ([HOK](17-engine-cli.spec.md)), demote nothing, stop no pipeline, and refuse `promote-check --stamp` on the same version until the criterion holds again.

- GIVEN a promoted workflow whose last 20 pipeline runs show one gate escape WHEN the next run exits THEN the status row shows `regressed: P3 = 1` and the next pipeline run still starts

### PRO-B6 The verb

WHEN `promote-check <workflow> --to local-stable|pipeline [--executor <name>] [--window <n>] [--stamp] [--json]` runs THE engine SHALL be read-only without `--stamp`, writing nothing (contract C13); exit 0 when every criterion is met, 6 when any is not (an advisory verb, [CON-B12](01-contracts.spec.md)) and 2 on a usage error; read the same functions as `report --supervision`, `report --loop` and `evals bar`, so a number never differs between two verbs; and refuse `--to pipeline`, and a `--executor` not registered in this release, with exit 2 `not_in_release`.

- GIVEN `promote-check --to pipeline` WHEN it runs THEN it exits 2 `not_in_release`

### PRO-B7 Stage of a run

WHEN a run starts THE engine SHALL give it stage `pipeline` when the caller is `pipeline` or `scheduler` ([PRV-B11](85-caller-provenance.spec.md)) and the workflow version holds a `pipeline` stamp; else `local-stable` when the workflow declares `improvement_mode: stable`; else `local-dev`; and record the stage on the run's `settings_resolved` record and on every ledger row, where LAD, JRK and CXR read it.

- GIVEN a workflow with `improvement_mode: stable` started at a terminal WHEN it runs THEN its stage is `local-stable`

### PRO-B8 Window

WHEN the window is read THE engine SHALL take the last `--window` finished runs (default 20 for `pipeline`, 10 for `local-stable`, never fewer than P1's count) whose `run_started` `content_version` (the workflow version with its content digest, [VER-B14](61-version-metadata.spec.md)) is the package's current one, or for a workflow that is not a package its declared version; leave out runs with origin `trial`, `scenario` or `evals`, dry runs, reruns of a trial and runs that did not reach a final exit; and restart the window after a gate escape for a stage whose escape bar is 0 ([ADR-0041](../adr/0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md)).

- GIVEN a change inside the content digest WHEN the window is read THEN it is empty and every criterion is `unmeasured`

### PRO-B9 Criteria

WHEN the criteria are measured, their bars being defaults with no data behind them held in one engine bars file, raisable per workflow and never lowered THE engine SHALL measure P1 runs with distinct requests (10 with 3 distinct to `local-stable`, 20 with 3 distinct to `pipeline`); P2 first-pass yield of rung-0 attempts ([LAD-B16](92-effort-ladder-and-model-escalation.spec.md)) (at least 0.5, 0.7); P3 gate escapes (at most 2, 0); P4 every gate's judge binding `accepted`, each risk level used in route mode included ([JRK-B9](93-judge-model-by-risk.spec.md)) (on the local binding; on the pipeline's executor and alias with FBK grade `reliable`); P5 the supervision rows ([SUP-B17](86-supervision-metrics.spec.md)), `unmeasured` when a window run has no supervision record and the share `unmeasured` when fewer than half the runs have it measured; P6 p90 run cost (reported; under a declared `run_cost_cap_usd` that must be set); P7 open engine or executor fault findings for the workflow ([SIL](16-self-improvement.spec.md)) (reported; none); P8 the workflow's eval suites on the target executor ([EVS](51-eval-suites.spec.md)) (reported; pass); P9 escalated attempts per unit (reported; PRO-B3, with a pass-rate lower bound of at least 0.5); P10 the share of climbed attempts per unit, a unit whose ladder never climbed listed `ladder_unseen` (reported both); P11 runs per switch arm used in route mode ([CXR-B13](94-complexity-routing.spec.md), [SWM](79-measured-switches.spec.md)) (reported; at least 5 per arm used with each arm's yield at P2's bar); and P12, for `pipeline` only, a non-interactive credential on this machine's profile that every step and judge can use ([TCK-B19](84-schedule-ticks-and-unattended-fires.spec.md)), `interactive_login` not met; each row naming its number and bar, and no run in the window making every criterion `unmeasured`.

- GIVEN a window where only P3 fails WHEN the check runs THEN the P3 row alone fails, naming the number and the bar

### PRO-B10 Promotion stamp

WHEN `--stamp` runs and every criterion is met THE engine SHALL write `promotion.json` beside the package's `stamp.json` ([VER-B16](61-version-metadata.spec.md)), outside the content digest, one entry per stage with `stage`, `workflow_version`, `executor`, `alias_bindings`, `criteria` (each number, bar and verdict), `ladder_seen`, `escalation_covered` and `arms_covered` (read by LAD and CXR), `stamped_at` and `caller` ([PRV](85-caller-provenance.spec.md)); require a person (at a terminal, or `--relayed` with a person turn) or a pipeline caller a person started, and a source package, refusing an installed copy as for the upgrade stamp ([WUP-B19](63-workflow-upgrade.spec.md)); void every stamp of the package on any change to the workflow version; and treat an unreadable `promotion.json` as no stamp, with a warning.

- GIVEN a stamped package WHEN a file inside the content digest changes THEN every stamp of the package is void

### PRO-B11 Pauses in a pipeline

WHEN a pipeline run pauses THE engine SHALL exit 3, ending the job, the question reaching a person through `attention`, a hook or the monitor and the person resuming where the run's state root lives ([ADR-0041](../adr/0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md)), and never make an escalation `offer` at stage `pipeline` ([LAD-B13](92-effort-ladder-and-model-escalation.spec.md)); the regressed watch re-reading P2, P3, P5, P6 and P9 over the sliding window after every final exit at stage `pipeline`, best effort (contract C2).

- GIVEN a pipeline run that pauses WHEN it exits THEN the exit is 3 and `attention` lists the pause

## Acceptance criteria

- PRO-AC1 (PRO-B1, PRO-B2, PRO-B3, PRO-B4, PRO-B5, PRO-B7, PRO-B8): PRO-B1 to PRO-B5 hold offline on fixture ledgers, run logs, score files and labels
- PRO-AC2 (PRO-B6): Without `--stamp` the verb creates and changes nothing
- PRO-AC3 (PRO-B9): Every criterion has a fixture where it alone fails, and its row names the number and the bar
- PRO-AC4 (PRO-B10): A change to any file inside the content digest voids every stamp of the package
- PRO-AC5 (PRO-B11): Live: one pipeline run on `claude` with an API key reaches the outcome gate on a scratch repository, and its pause exits 3 (probe P-PRO-1)
- PRO-AC6 (PRO-B6): `--to pipeline` and a `pipeline` caller's stamp are refused with `not_in_release` while the `pipeline` stage is not built

## Open questions

- Where does a pipeline run's state root live between jobs (ADR-0041 C2)? Until answered: CAR's state branch, as the owner proposed on 2026-11-20; a hosted store later. Owner: owner.
- Are 20 runs and the other bars right? Until answered: as stated, revisited after the first 20 runs of one workflow. Owner: owner.
- Not built yet: `--to pipeline`, the `pipeline` stage, the regressed watch (PRO-B3, PRO-B5, PRO-B11) and pipeline runs come with CI pipelines in a later release, refused meanwhile `not_in_release` (owner, 2026-11-20); a workflow cannot raise a bar yet; the `attention` listing of `unpromoted_pipeline` runs waits for the `pipeline` stage; the stage is on the `run_segment` ledger row only. Owner: engine owner.
