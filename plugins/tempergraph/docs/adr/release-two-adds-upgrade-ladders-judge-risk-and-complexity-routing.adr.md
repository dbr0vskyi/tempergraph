# Release 2 is trusted workflows that move: evals, promotion, update and upgrade, strict ladders, judge by risk and complexity routing

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | The release 2 and release 3 rows of [ADR `first-release-is-simple-trusted-workflows-on-one-machine`](first-release-is-simple-trusted-workflows-on-one-machine.adr.md) named below; ADR `first-release-is-simple-trusted-workflows-on-one-machine`'s release 1 rows stand |

## Context

Release 1 code is complete on `main` ([first-release plan](../plans/first-release.plan.md)). ADR `first-release-is-simple-trusted-workflows-on-one-machine` forecast release 2 as eval suites, promotion, update and migration, audit history, the additive node features, hooks and a slice of schedules, and put the full workflow upgrade in release 3. On 2026-11-20 the owner asked to:

1. include `upgrade` in release 2;
2. include "judges and ladders", with ladders that never raise model or effort on just any failure;
3. include switching between workflow branches by task complexity or other parameters, at least a simple against a detailed decomposition with a map.

Later the same day the owner asked for research on running on Windows and outside a git repository, moved CI pipelines to a later release, and proposed carrying a run's `.tempergraph` state on a branch meanwhile, removed when the run is done.

On 2026-11-21 the owner reviewed the list and approved a trim: release 2 keeps the owner's asks, what the first authored workflow needs, evals, promotion, update and upgrade and carried state; items nothing uses yet move to release 3.

Readiness of the release 2 list is in [research `release-two-readiness-and-gaps`](../research/release-two-readiness-and-gaps.rsrch.md).

## Decision

We will commit release 2 to the scope below, planned in the [second-release plan](../plans/second-release.plan.md). Release 2 is done when a workflow from release 1 can be **measured** by eval suites and its judges, **routed** by complexity and **escalated** only on trusted evidence, **promoted** to stable mode by a stamp, **moved** between machines with its state on a branch, and **carried** across engine releases by `update` and `upgrade` without losing a run.

| Capability | Release | Change from ADR `first-release-is-simple-trusted-workflows-on-one-machine` |
|---|---|---|
| Eval suites, live scoring, harvest and replay, the eval skill ([EVS](../specs/eval-suites.spec.md)) | 2 | — |
| Promotion check, stages and stamp to `local-stable` ([PRO](../specs/promotion-check.spec.md), [ADR `promotion-is-a-model-free-stamp-per-workflow-version`](promotion-is-a-model-free-stamp-per-workflow-version.adr.md)) | 2 | Now specified |
| **Run state carried on its own branch**, deleted when the run finishes ([CAR](../specs/run-state-on-a-branch.spec.md), [ADR `a-run-carries-scrubbed-thread-state-on-its-own-branch`](a-run-carries-scrubbed-thread-state-on-its-own-branch.adr.md)) | 2 | New, owner 2026-11-20: the stopgap until pipelines |
| **CI pipelines**: `promote-check --to pipeline`, the `pipeline` stage, the regressed watch, pipeline runs | later (3) | Moved out of release 2 by the owner on 2026-11-20 |
| `update`, rollback, migration, changelog and transforms, the update skill ([UPD](../specs/engine-update.spec.md), [MIG](../specs/state-and-run-migration.spec.md), [VER](../specs/version-metadata.spec.md), [LSK](../specs/lifecycle-skills.spec.md)) | 2 | — |
| **Workflow upgrade beyond `--check`, the built-in upgrade workflow, the upgrade skill** ([WUP](../specs/workflow-upgrade.spec.md), [UWF](../specs/upgrade-workflow.spec.md), [LSK](../specs/lifecycle-skills.spec.md)) | 2 | Moved from 3 by the owner |
| **Effort ladder and one-step model escalation**, `xhigh` effort, retirement of the retry-count model ladder ([LAD](../specs/effort-ladder-and-model-escalation.spec.md), [ADR `ladders-climb-only-on-trusted-substantive-evidence`](ladders-climb-only-on-trusted-substantive-evidence.adr.md)) | 2 | New |
| **Judge model by risk** ([JRK](../specs/judge-model-by-risk.spec.md), [ADR `a-judge-is-raised-by-a-model-free-risk-rule`](a-judge-is-raised-by-a-model-free-risk-rule.adr.md)) | 2 | New |
| **Complexity switches between decompositions** ([CXR](../specs/complexity-routing.spec.md), [ADR `complexity-chooses-a-decomposition-through-a-measured-switch`](complexity-chooses-a-decomposition-through-a-measured-switch.adr.md)) with measured switches ([SWM](../specs/measured-switches.spec.md)) and the sequential map ([MAP](../specs/map-unit.spec.md)) | 2 | New; pulls SWM and MAP to the front of the release |
| Audit history layer, history rules, tool surface audit ([AUD](../specs/workflow-audit.spec.md), [ARC](../specs/audit-rule-catalog.spec.md), [TSA](../specs/tool-surface-audit.spec.md)) | 3 | Moved from 2 by the owner on 2026-11-21: nothing uses it yet |
| Ask unit, event waits, breakpoints, deadlines, fallback target, parallel read-only branches, `self-check` ([ASK](../specs/ask-unit.spec.md), [HUM](../specs/gate-and-human.spec.md), [FLX](../specs/flow-extensions.spec.md), [SCR](../specs/script-units-and-hybrid-steps.spec.md), [CHK](../specs/check-contract-and-command-runs.spec.md), [JDG](../specs/judge-and-verdict.spec.md), [GRD](../specs/independence-guard.spec.md)) | 2 | — |
| Script cache, sampled audit judge, judge MCP views | 3 | Moved from 2 by the owner on 2026-11-21 |
| Deliverables required per path, a repository-level command declaration, `GitFacts.pushed` set ([research `release-two-readiness-and-gaps`](../research/release-two-readiness-and-gaps.rsrch.md) F5) | 2 | New, asked by the first authored workflow, stated for any workflow |
| Lifecycle hooks, wider hook events | 2 | — |
| In-process observers | 3 | Moved from 2 by the owner on 2026-11-21 |
| Schedules, release 2 slice ([SCH](../research/rationale-carried-from-the-engine-specs.rsrch.md), [TCK](../specs/schedule-ticks-and-unattended-fires.spec.md)); worktree extras ([WTR](../specs/worktree-mode.spec.md)); session review in stable mode ([SRV](../specs/session-review.spec.md)) | 3 | Moved from 2 by the owner on 2026-11-21 |
| State root outside git ([WSP-B15 to WSP-B18](../specs/workspace-and-concurrency.spec.md), [ADR `outside-git-the-state-root-is-found-by-walk-up`](outside-git-the-state-root-is-found-by-walk-up.adr.md)) | 2 | Researched in [research `running-outside-a-git-repository`](../research/running-outside-a-git-repository.rsrch.md) |
| Native Windows ([WIN](../specs/windows-support.spec.md), [ADR `windows-is-supported-natively-with-job-objects`](windows-is-supported-natively-with-job-objects.adr.md)) | 3 | Moved from 2 by the owner on 2026-11-21: its probes need a Windows machine. Designed in [research `running-on-windows`](../research/running-on-windows.rsrch.md) |
| Orchestration, council, contest, writer branches, parallel map, sub-workflows, other executors, the rest of schedules | 3 | — |

Claude CLI stays the only executor through release 2 ([ADR `first-release-ships-the-claude-executor-only`](first-release-ships-the-claude-executor-only.adr.md)). Kinds and fields not built are still refused with `not_in_release`.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Keep ADR `first-release-is-simple-trusted-workflows-on-one-machine`'s forecast | No change | Ignores the owner's three asks |
| **ADR `first-release-is-simple-trusted-workflows-on-one-machine`'s forecast plus the owner's three asks (chosen)** | Matches the ask; upgrade lands with the first release that can break a workflow (the ladder retirement is such a break) | A larger release 2 |
| Also move orchestration in | One fewer release | Against the owner's "orchestration later" |

## Decision rationale

| Criterion | Keep | Chosen | Add orchestration |
|---|---|---|---|
| Owner's asks of 2026-11-20 | no | yes | yes |
| A release 1 workflow survives the update | partly (pins only) | yes (transforms and upgrade) | yes |
| Ladders and routers measured before unattended use | no | yes (PRO P9 to P11, built with pipelines) | yes |
| Size | smallest | medium | largest |

## Consequences

- Positive: release 2 ships its own first breaking change (the model ladder list) together with the tools that carry workflows across it.
- Negative: more calibration work per workflow: each judge risk level is a binding to score.
- Risk: release 2 is large. Mitigation: the plan orders tracks so switches, maps and ladders land first; the owner trimmed it on 2026-11-21 to what the asks and the first authored workflow use.

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| R1 | "Judges" means the judge model by risk ([ADR `a-judge-is-raised-by-a-model-free-risk-rule`](a-judge-is-raised-by-a-model-free-risk-rule.adr.md) J1). | Scope |
| R2 | "Ladders" means the effort ladder and the one-step model escalation of research `effort-ladders-and-one-step-model-escalation`, tightened ([ADR `ladders-climb-only-on-trusted-substantive-evidence`](ladders-climb-only-on-trusted-substantive-evidence.adr.md)). | Scope |
| R3 | Release 1's live checks pass before release 2's code depends on them; a failing probe moves the dependent item, not the release. | Plan entry conditions |

## Revisit when

Release 1 is live-proven, or the owner trims or widens release 2.
