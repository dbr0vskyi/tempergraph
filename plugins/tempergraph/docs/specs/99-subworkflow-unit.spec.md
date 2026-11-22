---
title: Sub-workflow unit
type: component
status: review
prefix: SWF
adrs: [0133, 0040, 0062]
---

# Sub-workflow unit

## 1. Overview

A **sub-workflow unit** runs another registered workflow, the **child**, as one unit of a parent workflow. [CMP §2.2](03-compiler-and-flow.spec.md) states the shape in one row (a registered workflow compiled as a subgraph under the parent's checkpointer, depth at most three, no recursion) and [FLX §2.2](74-flow-extensions.spec.md) maps one over items; this spec fills in what that row leaves open: which version of the child runs, what it reads and gives back, where its records, spend, pauses, outcome and findings go ([R-140](../research/R-140-release-three-readiness-and-gaps.rsrch.md) F3, [ADR-0133](../adr/0133-a-sub-workflow-runs-inside-its-parents-thread-workspace-and-cap.adr.md)).

The first asker is a delivery workflow whose repository setup should be a workflow of its own, used alone or inside the delivery run. The design names no workflow ([ADR-0129](../adr/0129-the-engine-names-no-workflow-and-takes-requests-as-general-capabilities.adr.md)): any registered workflow can be a child.

## 2. Contract

```python
Subworkflow(workflow="repo-setup", requires=">=0.3,<1",
            inputs={"request": "request", "scope": "triage.scope"},   # child input <- parent request or artifact
            produces=["overview", "setup_note"],                       # child artifact keys the parent sees
            gate=Gate(check=..., judge=...), summary="Set up the repository")
```

### 2.1 Declaration

| Field | Kind | Meaning |
|---|---|---|
| `workflow` | workflow name | A registered workflow; resolved from the registry at run start ([PKG §2.3](88-workflow-package.spec.md)) |
| `requires` | version range, optional | The child versions the parent was written for; outside it, validation fails `subworkflow-version` |
| `inputs` | map child parameter → `request` \| `<unit>.<key>` \| a literal in quotes | Every required input parameter of the child must be mapped (`subworkflow-input-missing`) |
| `produces` | list of the child's artifact or value keys | What the parent's later units, its gate and its outcome see, under the unit's name. Empty means the child's deliverables ([OUT §2.1](90-run-outcome.spec.md)) |
| `gate` | as any unit | Grades what `produces` exposes against the parent's intermediate criteria for this unit |

The child may hold no sub-workflow deeper than the limit of three, never the parent (directly or not), and never a built-in workflow with `builtin` set ([UWF](64-upgrade-workflow.spec.md)).

### 2.2 Where the child runs

| Concern | Rule |
|---|---|
| Version | The child's `workflow_version` at run start is recorded in `run_started.children` and in the thread's engine file ([MIG §2.1](62-state-and-run-migration.spec.md)); a resume finds a changed child as it finds a changed parent (MIG §2.5), per child |
| Graph and state | A LangGraph subgraph under the parent's checkpointer and thread, checkpoint namespace `<unit>` (and `<unit>[<item>]` in a map) |
| Workspace | The parent's workspace: the run worktree, or the item's writer worktree in a writing map. The child's own `run.workspace` is ignored and noted once |
| Run log | The parent's `run.jsonl`; every record the child writes carries `child: <unit>` and its own `unit`. Session keys are `<unit>/<child unit>.<attempt>.<kind>`, so they never repeat a parent key |
| Settings | The child's declared defaults, under every layer of the parent's run; a flag reaches a child unit as `<unit>/<child unit>.<key>` ([RST §2.3](80-run-settings-and-overrides.spec.md)) |
| Spend | Counts against the parent's run cost cap and daily cap; reports show it as the unit's child figure, not summed into the parent's own steps ([OBS §2.2](15-observability-and-cost.spec.md)) |
| Finalizer | The child's finalizer never runs; the parent's finalizer owns every side effect. A child that declares one is warned once at validation (`subworkflow-finalizer-skipped`) |
| Outcome | The child's outcome gate runs as the child's last unit and grades the child's final criteria; its outcome record is kept under the parent's as `children[<unit>]` ([OUT §2.5](90-run-outcome.spec.md)). Then the parent's gate for the unit runs |

### 2.3 Gates, pauses and trips back

| Event in the child | Effect |
|---|---|
| A child gate retries or goes back | Within the child, by the child's own budgets |
| A child pause (approval, escalation, ask, wait) | The parent pauses with the child's payload; `unit` reads `<unit>/<child unit>` and `resume --decision …` answers it as any pause (CMP §4) |
| A child judge's `defect_in` or `UPSTREAM` names a key the parent mapped into `inputs` | The child ends `upstream`; the parent's gate for the unit routes back to the parent unit that made that key, if that unit is in its `back_targets`, else it asks a person |
| The child's outcome verdict is `unmet` or `needs_person` | The unit's gate fails with the child's failing final criteria as blockers |

### 2.4 Learning and measurement

| Concern | Rule |
|---|---|
| Calibration | A child's judges keep the child's own bindings and cases: they grade the child's criteria ([JCL](50-judge-calibration.spec.md)) |
| Findings | The loop files a finding about a child unit to the child workflow, `sides: [workflow]`, `workflow: <child>`, with the parent named ([SIL](16-self-improvement.spec.md)) |
| Stats | The child's outcome record counts in the child's measures with `origin: subworkflow:<parent>`; promotion bars of the child count those runs only when the child's own window says so ([PRO §2.3](95-promotion-check.spec.md)) |
| Upgrade | A parent's `upgrade` reads the child's change notes ([VER §2.6](61-version-metadata.spec.md), [WUP-B6](63-workflow-upgrade.spec.md)) |

## 3. Behaviours

**SWF-B1 A child as a unit.** Given a parent `deliver` with unit `setup = Subworkflow(workflow="repo-setup", produces=["overview"])`, when the run reaches `setup`, then the child's units run in the parent's worktree with records marked `child: setup`, the child's outcome gate grades its final criteria, the parent's gate for `setup` grades `overview`, and the parent's next unit reads `{setup.overview}`.

**SWF-B2 A child pause.** Given the child's `survey` gate needs approval, when it pauses, then `status` shows the parent paused at `setup/survey`, and `resume deliver <task> --decision proceed` releases it; no parent unit after `setup` started.

**SWF-B3 A changed child under a paused parent.** Given the parent paused inside `setup` on child version `0.3.0+aaa`, when the child is upgraded to `0.3.1+bbb` and the parent resumes, then MIG §2.5's rules apply to the child's units and one `workflow_changed` record names `child: setup`.

**SWF-B4 One cap.** Given a parent cap of 5 USD with 4 USD spent, when a child attempt would start at or over the cap, then the run drains with exit 5 reason `cost_cap` as for a parent attempt ([BUD §2](08-budgets-and-failures.spec.md)), and the report shows the child's spend on its own line.

**SWF-B5 Upstream defect.** Given `inputs={"scope": "triage.scope"}` and a child judge that puts a defect in `scope`, when the child ends, then the parent's `setup` gate sends the run back to `triage` with the child's reason, once.

**SWF-B6 Refusals.** Given a child that names the parent, a child below the depth limit of three, an unmapped required input, or a child outside `requires`, when validation runs, then it fails with `subworkflow-recursive`, `subworkflow-depth`, `subworkflow-input-missing` or `subworkflow-version`, with no spend.

## 4. Error conditions

| Condition | Result |
|---|---|
| The child is not registered, or does not load | Validation error `subworkflow-unknown`; the catalog names the child |
| The child is removed while the parent is paused inside it | The resume refuses with exit 2 naming the child; `workflows register` restores it |
| A key in `produces` the child never makes | Validation error `subworkflow-produces` when the child declares no producer for it; at run time a missing key fails the unit's gate check as a missing artifact |
| The child needs git and the parent runs outside git | Validation error `needs_git` naming the child ([WSP §2.4](13-workspace-and-concurrency.spec.md)) |

## 5. Design notes

- A subgraph in the parent's thread keeps one checkpoint, one lock, one log and one cap per run, so `status`, `stop`, carrying ([CAR](96-run-state-on-a-branch.spec.md)) and the monitor need nothing new. A separate child run per unit (the batch shape) was rejected: two threads to resume, two caps, and a parent that cannot pause on the child's question ([ADR-0133](../adr/0133-a-sub-workflow-runs-inside-its-parents-thread-workspace-and-cap.adr.md)).
- The child's finalizer is skipped because the parent's finalizer is the one place a run leaves a trace outside its branch ([FIN](78-finalizer-contract.spec.md)).
- The child keeps its own calibration and findings so that the same workflow, run alone or inside a parent, learns in one place.

## 6. Acceptance criteria

- [ ] SWF-AC-1 SWF-B1 to SWF-B6 hold offline on stand-ins with an engine fixture parent and child, neither a shipped workflow.
- [ ] SWF-AC-2 A parent run with a child leaves one `run.jsonl`, one checkpoint thread and one ledger row; every child record carries `child`.
- [ ] SWF-AC-3 A carried parent paused inside its child resumes on a second state root ([CAR-AC-1](96-run-state-on-a-branch.spec.md)).

## Open questions

None. Closed with the owner's acceptance of ADR-0133 on 2026-11-22: a parent never runs the child's finalizer, even when the child is its last unit (the parent's finalizer can call the same code), and the child's outcome gate is never skipped (its outcome record is what the child's measures read).

## References

[CMP](03-compiler-and-flow.spec.md) · [FLX](74-flow-extensions.spec.md) · [MIG](62-state-and-run-migration.spec.md) · [OUT](90-run-outcome.spec.md) · [BUD](08-budgets-and-failures.spec.md) · [PKG](88-workflow-package.spec.md) · [R-140](../research/R-140-release-three-readiness-and-gaps.rsrch.md)
