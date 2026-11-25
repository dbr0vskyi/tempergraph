# Release 2 readiness: what each item has, and what still lacks a spec or research

## Problem statement

On 2026-11-20 the owner asked to start the research and specs for release 2, adding `upgrade`, judges and strict ladders, and complexity-based branching ([ADR `release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing`](../adr/release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing.adr.md)). This note checks every release 2 item against the set as it stands after that work: which spec owns it, its status, its open questions, the research behind it, the live probes it needs, and what is still missing. It is the release 2 counterpart of [research `implementation-readiness`](implementation-readiness.rsrch.md).

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S1 | ADR `first-release-is-simple-trusted-workflows-on-one-machine` release 2 and 3 rows; the first-release plan's excluded lists (X2-1 to X2-26, X3-13) | Design set | [ADR `first-release-is-simple-trusted-workflows-on-one-machine`](../adr/first-release-is-simple-trusted-workflows-on-one-machine.adr.md), [first-release plan §1.3](../plans/first-release.plan.md) |
| S2 | Front matter `status` and the Open questions table of every spec named below, read on this branch | Design set | [specs](../specs/overview.spec.md) |
| S3 | [research `design-gap-review`](design-gap-review.rsrch.md) G9 (non-git workflows) and U3 (platforms) | Design set | research/ |
| S4 | [research `effort-ladders-and-one-step-model-escalation`](effort-ladders-and-one-step-model-escalation.rsrch.md), [research `judge-model-by-risk-and-evidence-for-escalation`](judge-model-by-risk-and-evidence-for-escalation.rsrch.md), [research `routing-by-complexity-between-decompositions`](routing-by-complexity-between-decompositions.rsrch.md) | Design set | research/ |
| S5 | Engine code on `main`: `improve/child.py` and `improve/review.py` (loop alias), `run/nodes.py` (retry-count ladder) | Code | `plugins/tempergraph/engine/src/tempergraph/` |

## Key findings

### F1 Every release 2 item now has an owning spec but two `confirmed`

| Item | Owning spec(s), status | Open questions | Research | Verdict |
|---|---|---|---|---|
| Eval suites, live scoring, harvest, replay, eval skill | [EVS](../specs/eval-suites.spec.md) `review` | 2 (live regression suite for stable; $20 suite cap) | research `evaluating-llm-judges-public-practice`, research `eval-and-judge-gap-analysis` | Status pass |
| Promotion to `local-stable`, stages (pipeline stage in a later release) | [PRO](../specs/promotion-check.spec.md) `review` (new), [SUP-B17](../specs/supervision-metrics.spec.md) `review` | 2 (state between machines; bars) | ADR `graduate-a-workflow-from-local-to-pipeline-by-measured-criteria`, research `callers-supervision-and-babysitting-cost` | **Was the gap of X2-1, now specified**; status pass; P-PRO-1 moves to the later release |
| Carried run state on a branch | [CAR](../specs/run-state-on-a-branch.spec.md) `review` (new) | 2 | research `carrying-run-state-on-a-branch` | New, from the owner's 2026-11-20 stopgap for pipelines |
| State root outside git | [WSP-B15 to WSP-B18](../specs/workspace-and-concurrency.spec.md) `review` | 2 in research `running-outside-a-git-repository` | research `running-outside-a-git-repository` | New section |
| Windows | [WIN](../specs/windows-support.spec.md) `review` (new) | 2 | research `running-on-windows` | New; probes P-WIN-1 to P-WIN-3 |
| `update`, rollback, migration, changelog, update skill | [UPD](../specs/engine-update.spec.md) `ready-for-implementation`, [MIG](../specs/state-and-run-migration.spec.md) `review`, [VER](../specs/version-metadata.spec.md) `ready-for-implementation`, [LSK](../specs/lifecycle-skills.spec.md) `ready-for-implementation` | 1 in MIG (thread converter) | research notes `updating-a-tool-with-long-lived-runs`, `automated-and-model-assisted-migrations` and `engine-update-and-workflow-upgrade-gaps` | Status pass of MIG |
| Workflow upgrade, upgrade workflow, upgrade skill (moved from release 3) | [WUP](../specs/workflow-upgrade.spec.md) `ready-for-implementation`, [UWF](../specs/upgrade-workflow.spec.md) `review`, [LSK](../specs/lifecycle-skills.spec.md) | 1 in UWF (grouping items per file) | research `automated-and-model-assisted-migrations` | Status pass of UWF. UWF uses two sequential maps and EVS fixtures, both release 2, so the track follows MAP and EVS |
| Effort ladder, one-step escalation, `xhigh` | [LAD](../specs/effort-ladder-and-model-escalation.spec.md) `review` (new) | 3 (bars; check-fail escalation; `xhigh` probe) | research `effort-ladders-and-one-step-model-escalation`, research `judge-model-by-risk-and-evidence-for-escalation` | New; probe P-LAD-1 |
| Judge model by risk | [JRK](../specs/judge-model-by-risk.spec.md) `review` (new) | 1 (stock rules) | research `judge-model-by-risk-and-evidence-for-escalation` | New |
| Complexity switches | [CXR](../specs/complexity-routing.spec.md) `review` (new), [SWM](../specs/measured-switches.spec.md) `review`, [MAP](../specs/map-unit.spec.md) `review` | 2 in CXR, 1 in SWM | research `routing-by-complexity-between-decompositions`, research `temperspec-needs-against-the-engine` | New; status pass of SWM and MAP |
| Audit history, history rules, tool surface audit | [AUD](../specs/workflow-audit.spec.md), [ARC](../specs/audit-rule-catalog.spec.md) `ready-for-implementation`, [TSA](../specs/tool-surface-audit.spec.md) `review` | 2 in TSA | research `why-runs-fail-stall-repeat-or-overspend` and `prior-art-for-workflow-audits` | Status pass of TSA |
| Ask unit, event waits, breakpoints, deadlines, fallback target, parallel read-only branches | [ASK](../specs/ask-unit.spec.md) `review`, [HUM](../specs/gate-and-human.spec.md), [FLX](../specs/flow-extensions.spec.md) `review` | none | research `node-types-against-langgraph` | Status pass |
| Script cache, `self-check`, audit judge, judge MCP views | [SCR](../specs/script-units-and-hybrid-steps.spec.md), [CHK-B17](../specs/check-contract-and-command-runs.spec.md), [JDG-B7](../specs/judge-and-verdict.spec.md), [GRD](../specs/independence-guard.spec.md), [ECC](../specs/executor-claude-code.spec.md), all `ready-for-implementation` | 1 in GRD | research `node-types-against-langgraph`, research `claude-code-cli-headless` | Ready; MCP views need the filtering-proxy live check |
| Lifecycle hooks, in-process observers, wider hook events | [HOK-B1 to HOK-B6](../specs/lifecycle-hooks.spec.md), [EVT-B22, EVT-B23, EVT-B24](../specs/run-events.spec.md) `ready-for-implementation` | 2 in EVT | research `observer-needs-against-engine-documents` | Ready |
| Schedules, release 2 slice | [SCH](../specs/schedules.spec.md) `review`, [TCK](../specs/schedule-ticks-and-unattended-fires.spec.md) `review` | 3 and 2; "Is scheduling in the first release?" is answered by ADR `first-release-is-simple-trusted-workflows-on-one-machine` and should be closed | research `scheduling-runs-prior-art-and-gaps` | Status pass; probes P-SCH-1, P-SCH-2 |
| Worktree extras | [WTR](../specs/worktree-mode.spec.md) `ready-for-implementation` | 2 | research `native-worktrees-and-executor-worktree-features` | Ready |
| Session review in stable mode | [SRV](../specs/session-review.spec.md) `ready-for-implementation` | 4 | research `reading-session-logs-for-self-improvement` | Ready |
| **State root outside git** (X2-24) | none: [WSP-B8, WSP-B9, WSP-B11](../specs/workspace-and-concurrency.spec.md) assumes git | — | research `design-gap-review` G9 proposes a resolution only | **Needs a spec section** (WSP) and a decision record |
| **Windows** (X2-25) | none | — | research `design-gap-review` U3 names it only | **Needs research**: process groups as job objects, path and lock rules, the shim, schedule triggers, worktrees |

### F2 Contracts the new specs add to existing ones `confirmed`

This branch updates them in place, so the set stays consistent:

| Spec | Change |
|---|---|
| CON | `xhigh` in the effort enum (closing its open question on normalization); `CheckFinding.kind`; a pointer from model resolution to LAD |
| RST | `xhigh`; an operator `effort` pins a ladder; the retired model list |
| BUD | BUD-B7 marked as release 1's ladder, retired by LAD |
| SWM, MAP | `effort_ladder` and `escalation` in `arm_overrides`; links to CXR |
| HUM, CLI, EVT, OBS | The escalation offer pause; `resume --escalate`, `promote-check`, `report --switch` and `--risk`; `ladder_decision` and `judge_risk` records; complexity fields on the `route` record |
| VER, WUP, LSK, JCL | The `model_list_to_escalation` transform; upgrade in release 2; JCL's reader row for climbing evidence |

### F3 What remains for the build `confirmed`

| # | Item | Where it goes |
|---|---|---|
| G1 | State root outside git | Resolved: [WSP-B15 to WSP-B18](../specs/workspace-and-concurrency.spec.md), ADR `outside-git-the-state-root-is-found-by-walk-up`, research `running-outside-a-git-repository` |
| G2 | Windows | Resolved: [WIN](../specs/windows-support.spec.md), ADR `windows-is-supported-natively-with-job-objects`, research `running-on-windows` |
| G3 | Where a run's state lives between machines | Resolved for release 2 by [CAR](../specs/run-state-on-a-branch.spec.md) (ADR `a-run-carries-scrubbed-thread-state-on-its-own-branch`); pipelines move to a later release |
| G4 | The loop alias `medium` hard-coded in `improve/child.py` and `improve/review.py`, where the loop may need the stronger model and one override pair for model and time | A setting in RST, small; noted since research `effort-ladders-and-one-step-model-escalation` |
| G5 | Status passes: EVS, PRO, SUP, MIG, UWF, LAD, JRK, CXR, SWM, MAP, TSA, ASK, FLX, SCH, TCK, each turning its open questions into recorded defaults | First phase of each track (as release 1's EC-2) |
| G6 | Live probes: P-LAD-1 (`--effort xhigh` and `max` per alias), P-WIN-1 to P-WIN-3 (on a Windows machine), plus release 1's pending probes the release 2 items build on | [Second-release plan §2](../plans/second-release.plan.md) |

### F5 What the first authored workflow asks of the engine `confirmed`

The first authored workflow package (merged 2026-11-21) lists the engine limits it works around in its overview spec and backlog. By [ADR `the-engine-names-no-workflow`](../adr/the-engine-names-no-workflow.adr.md) each is stated here for any workflow:

| # | Capability any workflow can use | Release 2 owner | State |
|---|---|---|---|
| G7 | Per-item coding in fresh sessions over a plan's phases | MAP sequential form (I2-2) | Covered |
| G8 | Parallel read-only branches; a batched pause with typed questions and defaults | ASK, FLX (I2-16) | Covered |
| G9 | A cheaper model for mechanical items, a stronger one only after a judged blocker | LAD, CXR | Covered |
| G10 | Deliverables required only on the paths that produce them, instead of on every path | None yet | Needs a WFM rule (I2-26) |
| G11 | Verification commands resolved per repository, not one fixed list per workflow | CHK-B11 resolver exists; a repository-level declaration does not | Needs a CHK rule (I2-26) |
| G12 | `GitFacts.pushed` set as CHK-B10 already specifies | CHK | A release 1 code gap, not a design gap (I2-26) |
| G13 | Sub-workflows | Release 3 (ADR `release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing`) | Unchanged |

### F4 The first breaking change lands with the tools to carry it `confirmed`

Retiring the model list (LAD-B18) is release 2's only change that rewrites workflow source. It ships as a changelog entry with a transform and an owner item, so a release 1 workflow is carried by `upgrade`, which the owner moved into the same release.

## Conclusions

1. Every release 2 item has an owning spec; the state root outside git, Windows and carried state were added on 2026-11-20 (WSP-B15 to WSP-B18, WIN, CAR).
2. The four new specs (LAD, JRK, CXR, PRO) close the owner's three asks and the old promotion gap.
3. Fifteen specs need a status pass before their tracks start; none has an open question that blocks design.
4. Two new live probes are added; neither blocks offline building.

## Open questions

| Question | Who answers | Default until answered |
|---|---|---|
| Keep state root outside git and Windows in release 2? | Owner: outside git stays; Windows and the items nothing uses yet move to release 3 (decided 2026-11-21, ADR `release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing`) | — |
| Where does carried state live: its own branch or the work branch? | Owner: its own state branch (decided 2026-11-21) | Its own state branch (CAR) |
