# R-140 Release 3 readiness: what release 2 left, what is asked for next, and what still lacks a spec

## Problem statement

On 2026-11-21 the owner asked to check whether release 2 is ready, close its gaps if not, and then prepare release 3 with research and specs. This note records the release 2 check (F1), then sorts every release 3 candidate the same way [R-130](R-130-release-two-readiness-and-gaps.rsrch.md) sorted release 2: who asks for it, which spec owns it, its status, and what is missing (F2 to F7). It is the input to [ADR-0132](../adr/0132-release-three-is-workflows-that-compose-run-in-parallel-and-grade-in-the-pipeline.adr.md) and the [third-release plan](../plans/third-release.plan.md).

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S1 | The release 2 plan, its track plans and code reports; ADR-0125's capability table, with the rows moved to release 3 on 2026-11-21 | Design set | [second-release plan](../plans/second-release.plan.md), [ADR-0125](../adr/0125-release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing.adr.md) |
| S2 | The offline suite on `main` and on this branch; `ruff`, `mypy` | Code | `plugins/tempergraph/engine/` |
| S3 | Live checks L-21, L-25, L-27, L-28 and L-29 run in the cloud container on 2026-11-22 (Claude Code 2.1.330), with the earlier cloud rows | Live runs | [live-checks plan](../plans/live-checks.plan.md) |
| S4 | temperspec's backlog rows B11 to B14 and its next-features note | Package docs | `plugins/temperspec-tgraph/docs/plans/backlog.plan.md` |
| S5 | The pull-request gate research, open as its own pull request: R-135, with ADR-0130, ADR-0131 and spec 98 reserved | Design set (in review) | R-135 on its branch |
| S6 | Front matter `status` and the Open questions table of every spec named below | Design set | [specs](../specs/00-overview.spec.md) |

## Key findings

### F1 Release 2 is finished on the engine side `confirmed`

Code, specs and plans agreed except for the gaps below, all closed on this branch with a test each (S2):

| Gap | Fix |
|---|---|
| A restamp of a current package dropped the entries it had already applied | The stamp keeps the prior entries and their `by` (VER §2.5) |
| `author verify` regraded every judge seed on each run | Seeds keep a pass keyed on gate, binding and fixture digest (SCF §2.5 rung 8) |
| A judge was asked to grade `person` and `none` criteria | Those criteria are left out of the judge's list (JDG §2.1) |
| A step route record lacked the signals it routed on | `signals` added (OBS §2.1) |
| The two examples' judges could not see what changed, so they paused for a person (L-25) | Each example's check lists the changes as evidence, and the judge is told check evidence is given, not claimed; each example has an outcome check |
| A model skipped the check preview because the prompt said "There is no shell" (L-29) | The tools block names the one granted command (CHK §2.5) |
| A thread from before the engine record failed to resume | It resumes with its start recorded as unknown (MIG §4) |
| GRD-AC-5 had no recorded stream | Scrubbed 2.1.330 recordings with a planted subagent call |
| A blueprint refused release 2's `map`, `parallel`, `ask` and `wait` | Blueprint, scaffold and comparison take them (SCF §2.1) |
| A parallel branch's output was "not produced on every path" past its join | Dominance passes through the join (WFM validation) |
| `deadline_s` on a wait or ask was refused as a later release | Settable, as RST §2.2 says |
| The engine reported itself as release 1; refusals named release 2 for items moved to 3 | Fixed |

Every live check that can run in a cloud container now passes (S3). What is left needs the owner's machine or hands, and does not block the engine: L-12 parts, L-14, L-17 and L-19 (a scratch GitHub repository), L-18 (the owner's labels), L-23 part, L-24 and the P-LSK skill scenarios (interactive), TS-L2's owner grade, and the Windows probes, which moved to release 3 with Windows. `released_at` stays unset until the owner tags the release.

### F2 What the first real workflow asks of release 3 `confirmed`

temperspec's backlog names five features that wait for the engine (S4). Each maps onto a capability already designed for release 3, so none needs a new engine concept ([ADR-0129](../adr/0129-the-engine-names-no-workflow-and-takes-requests-as-general-capabilities.adr.md)):

| Row | Feature | Engine capability | Spec, status |
|---|---|---|---|
| B8 | Reading in parallel: discovery per gap, the setup survey per component | The concurrent map over a list, under the reserving cap (release 2's parallel block has fixed branches only) | [MAP](../specs/77-map-unit.spec.md) `review`, [BUD §2.3](../specs/08-budgets-and-failures.spec.md) |
| B11 | Repository setup as a workflow of its own, used alone or inside the delivery run | Sub-workflow units | CMP §2.2 has one row; **no spec** (F3) |
| B12 | Coding phases in parallel, behind declared independence and a disjoint-files check | Writer branches, concurrent map mode | [FLX](../specs/74-flow-extensions.spec.md), [MAP](../specs/77-map-unit.spec.md) `review` |
| B13 | Several answers to a hard choice, then a pick or a vote | Contest and council units | [CTS](../specs/72-contest-unit.spec.md), [CNL](../specs/71-council-unit.spec.md) `review` |
| B14 | A scheduled drift audit | The rest of schedules | [SCH](../specs/83-schedules.spec.md), [TCK](../specs/84-schedule-ticks-and-unattended-fires.spec.md) `review` |

The owner's other open ask is the pull-request gate (S5): one check and an optional judge that re-grade a run's result in the pipeline, buildable before pipeline runs. Its research recommends release 3 and leaves five questions to the owner. The package also asks for an `on_deadline` choice that fills each unanswered question of an ask unit with its default and proceeds, so the `answers` artifact is complete (FLX §2.3 offers escalate, stop or a forward unit, and a forward unit leaves no answers); it is general, and is listed in the plan as I3-15 for the owner to accept.

### F3 Sub-workflows had a row, not a spec `confirmed`

[CMP §2.2](../specs/03-compiler-and-flow.spec.md) says a sub-workflow is a registered workflow compiled as a subgraph under the parent's checkpointer, at most three deep, never recursive. It leaves open: which child version runs and what a resume does when it changed; how parameters are mapped; what the parent sees; whose workspace, log, settings, cap and finalizer apply; where pauses, upstream defects and the child's outcome go; and where findings and calibration land. A workflow cannot be written against a row. New spec [SWF](../specs/99-subworkflow-unit.spec.md) answers each, and [ADR-0133](../adr/0133-a-sub-workflow-runs-inside-its-parents-thread-workspace-and-cap.adr.md) records the main choice: the child runs inside the parent's thread, workspace and cap, not as a separate run.

### F4 A step's reach is wider than its declaration inside a host session `confirmed`

In L-29, run from inside a Claude Code session, a step's `system/init` listed about 35 tools, among them the host's `Artifact` and `SendMessage`, and the host's additional directories; one session read a file of the host's memory folder outside the workspace (S3). The allow rules held: judges stayed in `dontAsk`, and nothing outside the step's grants was written. The cause is the environment the step inherits from the host, plus `--tools` being sent only under the operator's enforcement setting. `--bare` on 2.1.330 also still lists user-scope plugins, so `isolates_user_config` stays false. A pipeline or a scheduled fire does not run inside a host session, but an operator's own `claude` session does, and that is where most runs start. Resolution: [ECC §2.8](../specs/11-executor-claude-code.spec.md), with probes P-CC-10 and P-CC-11.

### F5 The cost cap assumes one session at a time `confirmed`

[BUD §2](../specs/08-budgets-and-failures.spec.md) checks the run's spend before each attempt. With one session in flight that bounds the overrun to one session. Release 2's parallel read-only branches already break the assumption: two branches may start just under the cap and both finish above it. Release 3 adds concurrent maps, contest slots and council members, where the overrun grows with the width. Resolution: [BUD §2.3](../specs/08-budgets-and-failures.spec.md), where a session reserves its own cap or its projection before it starts.

### F6 Specs a release 3 item rests on are still in `review` `confirmed`

| Spec | Open questions | Release 3 need |
|---|---|---|
| FLX (writer branches), MAP (concurrent mode) | FLX none; MAP 1 | B12 |
| CNL, CTS | 2 and 2 | B13 |
| SCH, TCK | 3 and 2 (SCH's "is scheduling in the first release?" is answered by ADR-0090) | B14 |
| PRO (pipeline stage) | 2 | CI pipelines, moved from release 2 |
| WIN | 2 | Windows, moved from release 2 |
| TSA | 2 | Tool surface audit, moved from release 2 |
| SWF (new) | 2 | B11 |
| Pull-request gate (spec 98, not written) | R-135 lists 5 for the owner | Owner's ask |

Moving these to `ready-for-implementation` is the first track of the plan, as the status pass was for release 2. The items moved from release 2 on 2026-11-21 that are already `ready-for-implementation` (script cache, sampled audit judge, judge MCP views, in-process observers, worktree extras, session review in stable mode, the audit history layer) need no spec work.

### F7 What stays out `likely`

Two items ADR-0090 forecast for release 3 have no asker yet and the most unknowns:

- **Other executors** (Antigravity, the Messages API, the Agent SDK). Their specs are `review`, no probe of theirs has run, and the only executor proven live is Claude Code. The "four executors" requirement is a design requirement the specs already meet; building them is a release of its own.
- **Orchestration of runs** ([ORC](../specs/45-orchestration.spec.md), the orchestrator skill). It needs sub-workflows and the reserving cap first, and nothing asks for it yet.

Both are proposed for release 4 in ADR-0132; the owner decides.

A smaller one: no example workflow has a complexity switch, so the release 2 routing is proven only on an engine fixture. Adding one to an example is a release 3 row, since it changes an example's outcome.

## Conclusions

Release 2 is finished on the engine side; what is left is the owner's own checks (F1). Release 3 should be the capabilities the first real workflow is waiting for (sub-workflows, writer branches and the concurrent map, contest and council, schedules), the pull-request gate the owner asked for, the pipeline stage moved out of release 2, and the two safety fixes found by running release 2 (step reach, a cap for concurrent sessions). Windows stays in release 3 behind its probes. Other executors and orchestration move to release 4.

## Open questions

| Question | Owner | Default |
|---|---|---|
| Accept the release 3 scope, or move executors or orchestration back in? | Owner | ADR-0132 as proposed |
| The pull-request gate's five questions (R-135) | Owner | R-135's defaults: report mode first, GitHub first, statuses without judge reasons, only on runs that name the workflow, release 3 |
| Tag release 2 now, or after the owner's remaining live checks? | Owner | After: `released_at` stays unset |

## References

[R-130](R-130-release-two-readiness-and-gaps.rsrch.md) · [ADR-0125](../adr/0125-release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing.adr.md) · [ADR-0129](../adr/0129-the-engine-names-no-workflow-and-takes-requests-as-general-capabilities.adr.md) · [SWF](../specs/99-subworkflow-unit.spec.md) · [ECC](../specs/11-executor-claude-code.spec.md) · [BUD](../specs/08-budgets-and-failures.spec.md) · [live-checks plan](../plans/live-checks.plan.md)
