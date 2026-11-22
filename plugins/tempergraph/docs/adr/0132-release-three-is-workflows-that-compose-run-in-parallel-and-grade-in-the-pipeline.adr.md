# ADR-0132 Release 3 is workflows that compose, run in parallel and are graded in the pipeline

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-22 |
| Authors | Claude (release 3 preparation for the owner) |
| Supersedes | The release 3 rows of [ADR-0090](0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md) and [ADR-0125](0125-release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing.adr.md) named below |

## Context

Release 2 is finished on the engine side; what is left of it is the owner's own checks ([R-140](../research/R-140-release-three-readiness-and-gaps.rsrch.md) F1). On 2026-11-21 the owner asked to prepare release 3. Three sources fill it:

1. What ADR-0090 and ADR-0125 put in release 3: orchestration, council, contest, writer branches, the parallel map, sub-workflows, other executors, the rest of schedules, CI pipelines, and the items trimmed from release 2 on 2026-11-21.
2. What the first real workflow is waiting for: sub-workflows, writer branches and the parallel map, contest and council, schedules (R-140 F2).
3. What running release 2 found: a step's reach is wider than declared inside a host session, and the cost cap assumes one session at a time (R-140 F4, F5). The owner also asked for a pull-request gate, researched in R-135.

## Decision

We will commit release 3 to the scope below, planned in the [third-release plan](../plans/third-release.plan.md). Release 3 is done when a workflow can **contain** another workflow, **run** independent work at once without passing its cap, **ask** several sessions for one hard answer, **fire** on a schedule, and have its result **re-graded** in the pull request's pipeline.

| Capability | Release | Change |
|---|---|---|
| Sub-workflow units ([SWF](../specs/99-subworkflow-unit.spec.md), [ADR-0133](0133-a-sub-workflow-runs-inside-its-parents-thread-workspace-and-cap.adr.md)) | 3 | New spec |
| Writer branches, the concurrent map mode ([FLX](../specs/74-flow-extensions.spec.md), [MAP](../specs/77-map-unit.spec.md)) | 3 | — |
| Council and contest units ([CNL](../specs/71-council-unit.spec.md), [CTS](../specs/72-contest-unit.spec.md)) | 3 | — |
| A cap that reserves for sessions in flight ([BUD §2.3](../specs/08-budgets-and-failures.spec.md)) | 3 | New: needed by every row above |
| A step reaches only what it declares inside a host session ([ECC §2.8](../specs/11-executor-claude-code.spec.md)) | 3 | New: found by L-29 |
| Schedules and unattended fires ([SCH](../specs/83-schedules.spec.md), [TCK](../specs/84-schedule-ticks-and-unattended-fires.spec.md)) | 3 | The release 2 slice and the rest together |
| CI pipelines: the `pipeline` stage, `promote-check --to pipeline`, the regressed watch ([PRO](../specs/95-promotion-check.spec.md)) | 3 | — |
| The pull-request gate (R-135; ADR-0130, ADR-0131 and spec 98 when accepted) | 3 | New, the owner's ask; its first slice does not wait for pipeline runs |
| Items moved from release 2: script cache, sampled audit judge, judge MCP views, in-process observers, worktree extras, session review in stable mode, the audit history layer and tool surface audit | 3 | — |
| Native Windows ([WIN](../specs/97-windows-support.spec.md)) | 3, behind its probes | Built only once P-WIN-1 to P-WIN-3 have run on a Windows machine |
| A complexity switch in an example workflow | 3 | New: release 2's routing is proven only on a fixture |
| Other executors: Antigravity, the Messages API, the Agent SDK ([EAG](../specs/12-executor-antigravity.spec.md), [EMA](../specs/20-executor-messages-api.spec.md), [EAS](../specs/21-executor-agent-sdk.spec.md)) | **4** | Moved from 3: no asker, no probe run, and each is a track of its own |
| Orchestration of runs and its skill ([ORC](../specs/45-orchestration.spec.md), [OSK](../specs/46-orchestrator-skill.spec.md)) | **4** | Moved from 3: needs sub-workflows and the reserving cap first; no asker yet |

Claude CLI stays the only executor through release 3. The design keeps meeting the four-executor requirement: every executor-facing contract is stated in [EXI](../specs/10-executor-interface.spec.md) terms. Kinds and fields not built are still refused with `not_in_release`.

## Options considered

| Option | For | Against |
|---|---|---|
| ADR-0090's release 3 as forecast, all of it | Meets the four-executor requirement in code at release 3 | The largest release yet; three executors with no live probe; orchestration before what it orchestrates |
| **What workflows and the owner ask for, plus release 2's findings (chosen)** | Every row has an asker or a found defect; executors get a release of their own | The four executors are built a release later than ADR-0090 said |
| Only temperspec's four asks | Smallest | Leaves the owner's pull-request gate and the two safety fixes out |

## Decision rationale

| Criterion | All of ADR-0090 | Chosen | temperspec only |
|---|---|---|---|
| Every row has an asker or a defect behind it | no | yes | yes |
| The owner's pull-request gate | yes | yes | no |
| Cap and reach safe before parallel work | only if added | yes | only if added |
| Size | largest | large | medium |

## Consequences

- Positive: temperspec's four waiting features become buildable; parallel work lands with a cap that holds.
- Negative: other executors wait for release 4.
- Risk: release 3 is still large. Mitigation: the plan builds the cap and reach fixes first, then sub-workflows, then the parallel shapes, and the pull-request gate as a separate track that does not wait on them.

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| R1 | The owner's 2026-11-20 phasing ("advanced node types and orchestration come later") still holds: orchestration can wait while node types arrive. | Release 4 row |
| R2 | The pull-request gate lands in release 3 if the owner accepts R-135's recommendation; its track starts only after that answer. | Plan track R3-T7 |
