# Sub-workflow unit

## Purpose

A sub-workflow unit runs another registered workflow, the child, as one unit of a parent workflow. The compiler states the shape (a registered workflow compiled as a subgraph under the parent's checkpointer, depth at most three, no recursion, [CMP](03-compiler-and-flow.spec.md)) and flow extensions map one over items ([FLX-B7](74-flow-extensions.spec.md)); this spec fills in which version of the child runs, what it reads and gives back, and where its records, spend, pauses, outcome and findings go ([R-140](../research/R-140-release-three-readiness-and-gaps.rsrch.md) F3, [ADR-0133](../adr/0133-a-sub-workflow-runs-inside-its-parents-thread-workspace-and-cap.adr.md)). The first asker is a delivery workflow whose repository setup should be a workflow of its own, used alone or inside the delivery run; the design names no workflow ([ADR-0129](../adr/0129-the-engine-names-no-workflow-and-takes-requests-as-general-capabilities.adr.md)), and any registered workflow can be a child. Workflow authors, status, carrying ([CAR](96-run-state-on-a-branch.spec.md)), the monitor and the improvement loop depend on it; design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### SWF-B1 A child as a unit

WHEN a run reaches a sub-workflow unit THE engine SHALL run the child's units in the parent's workspace with records marked `child: <unit>`, run the child's outcome gate on its final criteria, run the parent's gate for the unit on what `produces` exposes, and let the parent's later units read `{<unit>.<key>}`.

- GIVEN a parent `deliver` with `setup = Subworkflow(workflow="repo-setup", produces=["overview"])` WHEN the run reaches `setup` THEN the child runs in the parent's worktree, its outcome gate grades its final criteria, and the next parent unit reads `{setup.overview}`

### SWF-B2 A child pause

WHEN a child unit pauses (approval, escalation, ask, wait) THE engine SHALL pause the parent with the child's payload, its `unit` reading `<unit>/<child unit>`, and `resume --decision …` SHALL answer it as any pause ([CMP-B17](03-compiler-and-flow.spec.md)), no parent unit after the sub-workflow starting before.

- GIVEN the child's `survey` gate needs approval WHEN it pauses THEN `status` shows the parent paused at `setup/survey` and `resume deliver <task> --decision proceed` releases it

### SWF-B3 A changed child under a paused parent

WHEN a parent paused inside a child resumes after the child's version changed THE engine SHALL apply the change-under-a-thread rules ([MIG-B15](62-state-and-run-migration.spec.md)) to the child's units, per child, with one `workflow_changed` record naming `child: <unit>`.

- GIVEN a parent paused inside `setup` on child `0.3.0+aaa` WHEN the child is upgraded to `0.3.1+bbb` and the parent resumes THEN one `workflow_changed` record names `child: setup`

### SWF-B4 One cap

WHEN a child attempt would start at or over the parent's run cost cap THE engine SHALL drain the run with exit 5 reason `cost_cap` as for a parent attempt ([BUD](08-budgets-and-failures.spec.md)), the child's spend counting against the parent's run and daily caps and shown on its own line in reports, never summed into the parent's own steps ([OBS](15-observability-and-cost.spec.md)).

- GIVEN a parent cap of 5 USD with 4 USD spent WHEN a child attempt would cross it THEN the run drains with exit 5 `cost_cap` and the report shows the child's spend apart

### SWF-B5 Upstream defect

WHEN a child judge's `defect_in` or `UPSTREAM` names a key the parent mapped into `inputs` THE engine SHALL end the child `upstream` and route the parent's gate for the unit back to the parent unit that made that key when it is in `back_targets`, else ask a person; and a child outcome verdict of `unmet` or `needs_person` SHALL fail the unit's gate with the child's failing final criteria as blockers, child gate retries and trips back staying within the child's own budgets.

- GIVEN `inputs={"scope": "triage.scope"}` and a child judge that puts a defect in `scope` WHEN the child ends THEN the parent's `setup` gate sends the run back to `triage` with the child's reason, once

### SWF-B6 Refusals

WHEN a sub-workflow unit is validated THE engine SHALL refuse, with no spend, a child that names the parent directly or not (`subworkflow-recursive`), a nesting deeper than three (`subworkflow-depth`), an unmapped required input (`subworkflow-input-missing`), a child version outside `requires` (`subworkflow-version`), a child that is not registered or does not load (`subworkflow-unknown`, naming the child), a key in `produces` the child declares no producer for (`subworkflow-produces`), a child that needs git under a parent outside git (`needs_git`, [WSP-B15](13-workspace-and-concurrency.spec.md)), and a built-in workflow with `builtin` set as a child ([UWF](64-upgrade-workflow.spec.md)).

- GIVEN a child that names the parent WHEN validation runs THEN it fails `subworkflow-recursive` with no spend

### SWF-B7 Declaration

WHEN a workflow declares `Subworkflow(workflow=…, requires=…, inputs=…, produces=…, gate=…, summary=…)` THE engine SHALL resolve `workflow` from the registry at run start ([PKG-B15](88-workflow-package.spec.md)); read `requires` as the child version range the parent was written for; read `inputs` as child parameter to `request`, `<unit>.<key>` or a quoted literal; read `produces` as the child artifact or value keys the parent's later units, gate and outcome see under the unit's name, empty meaning the child's deliverables ([OUT-B8](90-run-outcome.spec.md)); grade with `gate` what `produces` exposes against the parent's intermediate criteria for the unit; and at run time fail the unit's gate check as a missing artifact for a `produces` key the child did not make.

- GIVEN `produces=["overview"]` and a child run that made no `overview` WHEN the unit's gate checks THEN it fails as a missing artifact

### SWF-B8 Where the child runs

WHEN a child runs THE engine SHALL record its `workflow_version` at run start in `run_started.children` and the thread's engine file ([MIG-B8](62-state-and-run-migration.spec.md)); compile it as a LangGraph subgraph under the parent's checkpointer and thread, checkpoint namespace `<unit>` (`<unit>[<item>]` in a map); run it in the parent's workspace (the run worktree, or the item's writer worktree in a writing map), ignoring the child's own `run.workspace` with one note; write its records to the parent's `run.jsonl`, each carrying `child: <unit>` and its own `unit`, session keys being `<unit>/<child unit>.<attempt>.<kind>`; apply the child's declared defaults under every layer of the parent's run, a flag reaching a child unit as `<unit>/<child unit>.<key>` ([RST-B22](80-run-settings-and-overrides.spec.md)); never run the child's finalizer, warning once at validation `subworkflow-finalizer-skipped` for a child that declares one; keep the child's outcome record under the parent's as `children[<unit>]` ([OUT-B18](90-run-outcome.spec.md)); and refuse with exit 2 naming the child a resume whose child was removed while the parent was paused inside it, `workflows register` restoring it.

- GIVEN a parent run with a child WHEN it ends THEN it left one `run.jsonl`, one checkpoint thread and one ledger row, every child record carrying `child`

### SWF-B9 Learning and measurement

WHEN a child's work is learned from and measured THE engine SHALL keep the child's judges on the child's own bindings and cases ([JCL](50-judge-calibration.spec.md)); file a finding about a child unit to the child workflow with `sides: [workflow]`, `workflow: <child>` and the parent named ([SIL](16-self-improvement.spec.md)); count the child's outcome record in the child's measures with `origin: subworkflow:<parent>`, in the child's promotion window only when that window says so ([PRO](95-promotion-check.spec.md)); and let a parent's `upgrade` read the child's change notes ([VER-B17](61-version-metadata.spec.md), [WUP-B6](63-workflow-upgrade.spec.md)).

- GIVEN a child unit's friction finding WHEN the loop files it THEN it is filed to the child workflow with the parent named

## Acceptance criteria

- SWF-AC1 (SWF-B1, SWF-B2, SWF-B3, SWF-B4, SWF-B5, SWF-B6, SWF-B7, SWF-B9): SWF-B1 to SWF-B6 hold offline on stand-ins with an engine fixture parent and child, neither a shipped workflow
- SWF-AC2 (SWF-B8): A parent run with a child leaves one `run.jsonl`, one checkpoint thread and one ledger row; every child record carries `child`
- SWF-AC3 (SWF-B8): A carried parent paused inside its child resumes on a second state root ([CAR-AC1](96-run-state-on-a-branch.spec.md))

## Open questions

- Should a parent be able to run the child's finalizer when the child is the parent's last unit? Until answered: no, the parent's finalizer can call the same code. Owner: owner.
- Should the child's outcome gate be skippable when the parent's gate grades the same criteria? Until answered: no, the child's outcome record is what its measures read. Owner: implementer.
- Not built yet: sub-workflows are release 3 work (third-release plan R3-T2). Owner: engine owner.
