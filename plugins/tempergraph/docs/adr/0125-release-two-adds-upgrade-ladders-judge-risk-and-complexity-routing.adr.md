# ADR-0125 Release 2 is trusted workflows that move: evals, promotion, update and upgrade, strict ladders, judge by risk and complexity routing

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | The release 2 and release 3 rows of [ADR-0090](0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md) named below; ADR-0090's release 1 rows stand |

## Context

Release 1 code is complete on `main` ([first-release plan](../plans/first-release.plan.md)). ADR-0090 forecast release 2 as eval suites, promotion, update and migration, audit history, the additive node features, hooks and a slice of schedules, and put the full workflow upgrade in release 3. On 2026-11-20 the owner asked to:

1. include `upgrade` in release 2;
2. include "judges and ladders", with ladders that never raise model or effort on just any failure;
3. include switching between workflow branches by task complexity or other parameters, at least a simple against a detailed decomposition with a map.

Readiness of the release 2 list is in [R-130](../research/R-130-release-two-readiness-and-gaps.rsrch.md).

## Decision

We will commit release 2 to the scope below, planned in the [second-release plan](../plans/second-release.plan.md). Release 2 is done when a workflow from release 1 can be **measured** by eval suites and its judges, **routed** by complexity and **escalated** only on trusted evidence, **promoted** to a pipeline on `claude` by a stamp, and **carried** across engine releases by `update` and `upgrade` without losing a run.

| Capability | Release | Change from ADR-0090 |
|---|---|---|
| Eval suites, live scoring, harvest and replay, the eval skill ([EVS](../specs/51-eval-suites.spec.md)) | 2 | — |
| Promotion check, stages, stamp, regressed watch; pipeline on `claude` ([PRO](../specs/95-promotion-check.spec.md), [ADR-0124](0124-promotion-is-a-model-free-stamp-and-release-2-pipelines-run-claude.adr.md)) | 2 | Now specified |
| `update`, rollback, migration, changelog and transforms, the update skill ([UPD](../specs/60-engine-update.spec.md), [MIG](../specs/62-state-and-run-migration.spec.md), [VER](../specs/61-version-metadata.spec.md), [LSK](../specs/65-lifecycle-skills.spec.md)) | 2 | — |
| **Workflow upgrade beyond `--check`, the built-in upgrade workflow, the upgrade skill** ([WUP](../specs/63-workflow-upgrade.spec.md), [UWF](../specs/64-upgrade-workflow.spec.md), [LSK](../specs/65-lifecycle-skills.spec.md)) | 2 | Moved from 3 by the owner |
| **Effort ladder and one-step model escalation**, `xhigh` effort, retirement of the retry-count model ladder ([LAD](../specs/92-effort-ladder-and-model-escalation.spec.md), [ADR-0121](0121-ladders-climb-only-on-trusted-substantive-evidence.adr.md)) | 2 | New |
| **Judge model by risk** ([JRK](../specs/93-judge-model-by-risk.spec.md), [ADR-0122](0122-a-judge-is-raised-by-a-model-free-risk-rule-and-every-level-is-calibrated.adr.md)) | 2 | New |
| **Complexity switches between decompositions** ([CXR](../specs/94-complexity-routing.spec.md), [ADR-0123](0123-complexity-chooses-a-decomposition-through-a-measured-switch.adr.md)) with measured switches ([SWM](../specs/79-measured-switches.spec.md)) and the sequential map ([MAP](../specs/77-map-unit.spec.md)) | 2 | New; pulls SWM and MAP to the front of the release |
| Audit history layer, history rules, tool surface audit ([AUD](../specs/55-workflow-audit.spec.md), [ARC](../specs/56-audit-rule-catalog.spec.md), [TSA](../specs/57-tool-surface-audit.spec.md)) | 2 | — |
| Ask unit, event waits, breakpoints, deadlines, fallback target, parallel read-only branches, script cache, `self-check`, sampled audit judge, judge MCP views ([ASK](../specs/73-ask-unit.spec.md), [HUM](../specs/07-gate-and-human.spec.md), [FLX](../specs/74-flow-extensions.spec.md), [SCR](../specs/70-script-units-and-hybrid-steps.spec.md), [CHK](../specs/75-check-contract-and-command-runs.spec.md), [JDG](../specs/05-judge-and-verdict.spec.md), [GRD](../specs/06-independence-guard.spec.md)) | 2 | — |
| Lifecycle hooks, in-process observers, wider hook events | 2 | — |
| Schedules, release 2 slice ([SCH §5](../specs/83-schedules.spec.md), [TCK](../specs/84-schedule-ticks-and-unattended-fires.spec.md)); worktree extras ([WTR](../specs/82-worktree-mode.spec.md)); session review in stable mode ([SRV](../specs/44-session-review.spec.md)) | 2 | — |
| State root outside git; Windows | 2, **at risk** | No spec or research yet ([R-130](../research/R-130-release-two-readiness-and-gaps.rsrch.md)); first to move to release 3 if release 2 must shrink |
| Orchestration, council, contest, writer branches, parallel map, sub-workflows, other executors, the rest of schedules | 3 | — |

Claude CLI stays the only executor through release 2 ([ADR-0091](0091-first-release-ships-the-claude-executor-only.adr.md)). Kinds and fields not built are still refused with `not_in_release`.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Keep ADR-0090's forecast | No change | Ignores the owner's three asks |
| **ADR-0090's forecast plus the owner's three asks (chosen)** | Matches the ask; upgrade lands with the first release that can break a workflow (the ladder retirement is such a break) | A larger release 2 |
| Also move orchestration in | One fewer release | Against the owner's "orchestration later" |

## Decision rationale

| Criterion | Keep | Chosen | Add orchestration |
|---|---|---|---|
| Owner's asks of 2026-11-20 | no | yes | yes |
| A release 1 workflow survives the update | partly (pins only) | yes (transforms and upgrade) | yes |
| Ladders and routers measured before a pipeline uses them | no | yes (PRO P9 to P11) | yes |
| Size | smallest | medium | largest |

## Consequences

- Positive: release 2 ships its own first breaking change (the model ladder list) together with the tools that carry workflows across it.
- Negative: more calibration work per workflow: each judge risk level is a binding to score.
- Risk: release 2 is large. Mitigation: the plan orders tracks so switches, maps and ladders land first; state root outside git and Windows move first if it must shrink.

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| R1 | "Judges" means the judge model by risk ([ADR-0122](0122-a-judge-is-raised-by-a-model-free-risk-rule-and-every-level-is-calibrated.adr.md) J1). | Scope |
| R2 | "Ladders" means the effort ladder and the one-step model escalation of R-120, tightened ([ADR-0121](0121-ladders-climb-only-on-trusted-substantive-evidence.adr.md)). | Scope |
| R3 | Release 1's live checks pass before release 2's code depends on them; a failing probe moves the dependent item, not the release. | Plan entry conditions |

## Revisit when

Release 1 is live-proven, or the owner trims or widens release 2.
