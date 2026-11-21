# R-130 Release 2 readiness: what each item has, and what still lacks a spec or research

## Problem statement

On 2026-11-20 the owner asked to start the research and specs for release 2, adding `upgrade`, judges and strict ladders, and complexity-based branching ([ADR-0125](../adr/0125-release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing.adr.md)). This note checks every release 2 item against the set as it stands after that work: which spec owns it, its status, its open questions, the research behind it, the live probes it needs, and what is still missing. It is the release 2 counterpart of [R-090](R-090-implementation-readiness.rsrch.md).

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S1 | ADR-0090 release 2 and 3 rows; the first-release plan's excluded lists (X2-1 to X2-26, X3-13) | Design set | [ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md), [first-release plan §1.3](../plans/first-release.plan.md) |
| S2 | Front matter `status` and the Open questions table of every spec named below, read on this branch | Design set | [specs](../specs/00-overview.spec.md) |
| S3 | [R-011](R-011-design-gap-review.rsrch.md) G9 (non-git workflows) and U3 (platforms) | Design set | research/ |
| S4 | [R-120](R-120-effort-ladders-and-one-step-model-escalation.rsrch.md), [R-121](R-121-judge-model-by-risk-and-evidence-for-escalation.rsrch.md), [R-126](R-126-routing-by-complexity-between-decompositions.rsrch.md) | Design set | research/ |
| S5 | Engine code on `main`: `improve/child.py` and `improve/review.py` (loop alias), `run/nodes.py` (retry-count ladder) | Code | `plugins/tempergraph/engine/src/tempergraph/` |

## Key findings

### F1 Every release 2 item now has an owning spec but two `confirmed`

| Item | Owning spec(s), status | Open questions | Research | Verdict |
|---|---|---|---|---|
| Eval suites, live scoring, harvest, replay, eval skill | [EVS](../specs/51-eval-suites.spec.md) `review` | 2 (live regression suite for stable; $20 suite cap) | R-045, R-046 | Status pass |
| Promotion to `local-stable`, stages (pipeline stage in a later release) | [PRO](../specs/95-promotion-check.spec.md) `review` (new), [SUP §2.7](../specs/86-supervision-metrics.spec.md) `review` | 2 (state between machines; bars) | ADR-0041, R-085 | **Was the gap of X2-1, now specified**; status pass; P-PRO-1 moves to the later release |
| Carried run state on a branch | [CAR](../specs/96-run-state-on-a-branch.spec.md) `review` (new) | 2 | R-133 | New, from the owner's 2026-11-20 stopgap for pipelines |
| State root outside git | [WSP §2.4](../specs/13-workspace-and-concurrency.spec.md) `review` | 2 in R-131 | R-131 | New section |
| Windows | [WIN](../specs/97-windows-support.spec.md) `review` (new) | 2 | R-132 | New; probes P-WIN-1 to P-WIN-3 |
| `update`, rollback, migration, changelog, update skill | [UPD](../specs/60-engine-update.spec.md) `ready-for-implementation`, [MIG](../specs/62-state-and-run-migration.spec.md) `review`, [VER](../specs/61-version-metadata.spec.md) `ready-for-implementation`, [LSK](../specs/65-lifecycle-skills.spec.md) `ready-for-implementation` | 1 in MIG (thread converter) | R-055 to R-057 | Status pass of MIG |
| Workflow upgrade, upgrade workflow, upgrade skill (moved from release 3) | [WUP](../specs/63-workflow-upgrade.spec.md) `ready-for-implementation`, [UWF](../specs/64-upgrade-workflow.spec.md) `review`, [LSK](../specs/65-lifecycle-skills.spec.md) | 1 in UWF (grouping items per file) | R-056 | Status pass of UWF. UWF uses two sequential maps and EVS fixtures, both release 2, so the track follows MAP and EVS |
| Effort ladder, one-step escalation, `xhigh` | [LAD](../specs/92-effort-ladder-and-model-escalation.spec.md) `review` (new) | 3 (bars; check-fail escalation; `xhigh` probe) | R-120, R-121 | New; probe P-LAD-1 |
| Judge model by risk | [JRK](../specs/93-judge-model-by-risk.spec.md) `review` (new) | 1 (stock rules) | R-121 | New |
| Complexity switches | [CXR](../specs/94-complexity-routing.spec.md) `review` (new), [SWM](../specs/79-measured-switches.spec.md) `review`, [MAP](../specs/77-map-unit.spec.md) `review` | 2 in CXR, 1 in SWM | R-126, R-075 | New; status pass of SWM and MAP |
| Audit history, history rules, tool surface audit | [AUD](../specs/55-workflow-audit.spec.md), [ARC](../specs/56-audit-rule-catalog.spec.md) `ready-for-implementation`, [TSA](../specs/57-tool-surface-audit.spec.md) `review` | 2 in TSA | R-050 to R-052 | Status pass of TSA |
| Ask unit, event waits, breakpoints, deadlines, fallback target, parallel read-only branches | [ASK](../specs/73-ask-unit.spec.md) `review`, [HUM](../specs/07-gate-and-human.spec.md), [FLX](../specs/74-flow-extensions.spec.md) `review` | none | R-060 | Status pass |
| Script cache, `self-check`, audit judge, judge MCP views | [SCR](../specs/70-script-units-and-hybrid-steps.spec.md), [CHK §2.5](../specs/75-check-contract-and-command-runs.spec.md), [JDG-B7](../specs/05-judge-and-verdict.spec.md), [GRD](../specs/06-independence-guard.spec.md), [ECC](../specs/11-executor-claude-code.spec.md), all `ready-for-implementation` | 1 in GRD | R-060, R-001 | Ready; MCP views need the filtering-proxy live check |
| Lifecycle hooks, in-process observers, wider hook events | [CLI §2.2](../specs/17-engine-cli.spec.md), [EVT §2.6](../specs/30-run-events.spec.md) `ready-for-implementation` | 2 in EVT | R-021 | Ready |
| Schedules, release 2 slice | [SCH](../specs/83-schedules.spec.md) `review`, [TCK](../specs/84-schedule-ticks-and-unattended-fires.spec.md) `review` | 3 and 2; "Is scheduling in the first release?" is answered by ADR-0090 and should be closed | R-095 | Status pass; probes P-SCH-1, P-SCH-2 |
| Worktree extras | [WTR](../specs/82-worktree-mode.spec.md) `ready-for-implementation` | 2 | R-100 | Ready |
| Session review in stable mode | [SRV](../specs/44-session-review.spec.md) `ready-for-implementation` | 4 | R-110 | Ready |
| **State root outside git** (X2-24) | none: [WSP §2](../specs/13-workspace-and-concurrency.spec.md) assumes git | — | R-011 G9 proposes a resolution only | **Needs a spec section** (WSP) and a decision record |
| **Windows** (X2-25) | none | — | R-011 U3 names it only | **Needs research**: process groups as job objects, path and lock rules, the shim, schedule triggers, worktrees |

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
| G1 | State root outside git | Resolved: [WSP §2.4](../specs/13-workspace-and-concurrency.spec.md), ADR-0127, R-131 |
| G2 | Windows | Resolved: [WIN](../specs/97-windows-support.spec.md), ADR-0128, R-132 |
| G3 | Where a run's state lives between machines | Resolved for release 2 by [CAR](../specs/96-run-state-on-a-branch.spec.md) (ADR-0126); pipelines move to a later release |
| G4 | The loop alias `medium` hard-coded in `improve/child.py` and `improve/review.py`, where the loop may need the stronger model and one override pair for model and time | A setting in RST, small; noted since R-120 |
| G5 | Status passes: EVS, PRO, SUP, MIG, UWF, LAD, JRK, CXR, SWM, MAP, TSA, ASK, FLX, SCH, TCK, each turning its open questions into recorded defaults | First phase of each track (as release 1's EC-2) |
| G6 | Live probes: P-LAD-1 (`--effort xhigh` and `max` per alias), P-WIN-1 to P-WIN-3 (on a Windows machine), plus release 1's pending probes the release 2 items build on | [Second-release plan §2](../plans/second-release.plan.md) |

### F5 What the first authored workflow asks of the engine `confirmed`

The first authored workflow package (merged 2026-11-21) lists the engine limits it works around in its overview spec and backlog. By [ADR-0129](../adr/0129-the-engine-names-no-workflow-and-takes-requests-as-general-capabilities.adr.md) each is stated here for any workflow:

| # | Capability any workflow can use | Release 2 owner | State |
|---|---|---|---|
| G7 | Per-item coding in fresh sessions over a plan's phases | MAP sequential form (I2-2) | Covered |
| G8 | Parallel read-only branches; a batched pause with typed questions and defaults | ASK, FLX (I2-16) | Covered |
| G9 | A cheaper model for mechanical items, a stronger one only after a judged blocker | LAD, CXR | Covered |
| G10 | Deliverables required only on the paths that produce them, instead of on every path | None yet | Needs a WFM rule (I2-26) |
| G11 | Verification commands resolved per repository, not one fixed list per workflow | CHK §2.2 resolver exists; a repository-level declaration does not | Needs a CHK rule (I2-26) |
| G12 | `GitFacts.pushed` set as CHK §2.1 already specifies | CHK | A release 1 code gap, not a design gap (I2-26) |
| G13 | Sub-workflows | Release 3 (ADR-0125) | Unchanged |

### F4 The first breaking change lands with the tools to carry it `confirmed`

Retiring the model list (LAD §2.8) is release 2's only change that rewrites workflow source. It ships as a changelog entry with a transform and an owner item, so a release 1 workflow is carried by `upgrade`, which the owner moved into the same release.

## Conclusions

1. Every release 2 item has an owning spec; the state root outside git, Windows and carried state were added on 2026-11-20 (WSP §2.4, WIN, CAR).
2. The four new specs (LAD, JRK, CXR, PRO) close the owner's three asks and the old promotion gap.
3. Fifteen specs need a status pass before their tracks start; none has an open question that blocks design.
4. Two new live probes are added; neither blocks offline building.

## Open questions

| Question | Who answers | Default until answered |
|---|---|---|
| Keep state root outside git and Windows in release 2? | Owner (asked 2026-11-20 for research) | Kept; Windows judges wait for the probes |
| Where does carried state live: its own branch or the work branch? | Owner: its own state branch (decided 2026-11-21) | Its own state branch (CAR) |
