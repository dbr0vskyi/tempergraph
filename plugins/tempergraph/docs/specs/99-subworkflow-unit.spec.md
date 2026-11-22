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

WHEN a sub-workflow unit is validated THE engine SHALL refuse, with no spend, a child that names the parent directly or not (`subworkflow-recursive`), a nesting deeper than three levels, the parent's child being level one (`subworkflow-depth`), an unmapped required input (`subworkflow-input-missing`; every input the child declares is required, and a child that declares none has the one input `request`, [VAL-B8](76-step-values-and-template-keys.spec.md)), a child version outside `requires` (`subworkflow-version`), a child that is not registered or does not load (`subworkflow-unknown`, naming the child), a key in `produces` the child declares no producer for (`subworkflow-produces`), a child that needs git under a parent outside git (`needs_git`, [WSP-B18](13-workspace-and-concurrency.spec.md)), and a built-in workflow with `builtin` set as a child (`subworkflow-builtin`, [UWF](64-upgrade-workflow.spec.md)).

- GIVEN a child that names the parent WHEN validation runs THEN it fails `subworkflow-recursive` with no spend
- GIVEN `deliver` declares `a`, `a` declares `b` and `b` declares `deliver` WHEN `deliver` validates THEN it fails `subworkflow-recursive`
- GIVEN `deliver` declares `a`, `a` declares `b` and `b` declares `c` (three levels) WHEN `deliver` validates THEN it passes the depth check
- GIVEN the same chain with `c` declaring `d` (four levels) WHEN `deliver` validates THEN it fails `subworkflow-depth`
- GIVEN a child that declares the input `scope` and a parent whose `inputs` does not map it WHEN validation runs THEN it fails `subworkflow-input-missing` naming `scope`
- GIVEN a child that declares no input and a parent whose `inputs` does not map `request` WHEN validation runs THEN it fails `subworkflow-input-missing` naming `request`
- GIVEN `requires=">=0.3,<0.4"` and a child at version 0.4.0 WHEN validation runs THEN it fails `subworkflow-version`
- GIVEN a child that no registry entry names WHEN validation runs THEN it fails `subworkflow-unknown` naming the child
- GIVEN a child whose registered package does not load WHEN validation runs THEN it fails `subworkflow-unknown` naming the child
- GIVEN `produces=["overview"]` and a child none of whose units produces `overview` WHEN validation runs THEN it fails `subworkflow-produces` naming `overview`
- GIVEN a child with a stock risk rule on changed paths and a parent run started outside git WHEN the run starts THEN it is refused `needs_git` before anything is created
- GIVEN a child whose spec has `builtin` set WHEN validation runs THEN it fails `subworkflow-builtin`

### SWF-B7 Declaration

WHEN a workflow declares `Subworkflow(workflow=…, requires=…, inputs=…, produces=…, gate=…, summary=…)` THE engine SHALL resolve `workflow` from the registry at run start ([PKG-B15](88-workflow-package.spec.md)); read `requires` as the child version range the parent was written for, in the form [VER-B14](61-version-metadata.spec.md) gives `requires_engine`, none meaning any version and an invalid range refused `subworkflow-version`; read `inputs` as child parameter to `request`, `<unit>.<key>` or a quoted literal; read `produces` as the child artifact or value keys the parent's later units, gate and outcome see under the unit's name, empty meaning the child's deliverables ([OUT-B8](90-run-outcome.spec.md)); read `summary` as a step's ([CON-B6](01-contracts.spec.md)); grade with `gate` what `produces` exposes against the parent's intermediate criteria for the unit; and at run time fail the unit's gate check as a missing artifact for a `produces` key the child did not make.

- GIVEN `produces=["overview"]` and a child run that made no `overview` WHEN the unit's gate checks THEN it fails as a missing artifact
- GIVEN `deliver` declares `setup = Subworkflow(workflow="repo-setup", requires=">=0.3,<1", inputs={"request": "request"}, produces=["overview"])` and `repo-setup` is registered at version 0.3.1, declares no input and has a unit that produces `overview` WHEN `deliver` validates THEN it has no error finding and its catalog row is valid
- GIVEN `requires="newer"` WHEN the workflow validates THEN it fails `subworkflow-version`

### SWF-B8 Where the child runs

WHEN a child runs THE engine SHALL record its `workflow_version` at run start in `run_started.children` and the thread's engine file ([MIG-B8](62-state-and-run-migration.spec.md)); compile it as a LangGraph subgraph under the parent's checkpointer and thread, checkpoint namespace `<unit>` (`<unit>[<item>]` in a map); run it in the parent's workspace (the run worktree, or the item's writer worktree in a writing map), ignoring the child's own `run.workspace` with one note; write its records to the parent's `run.jsonl`, each carrying `child: <unit>` and its own `unit`, session keys being `<unit>/<child unit>.<attempt>.<kind>`; apply the child's declared defaults under every layer of the parent's run, a flag reaching a child unit as `<unit>/<child unit>.<key>` ([RST-B22](80-run-settings-and-overrides.spec.md)); never run the child's finalizer, warning once at validation `subworkflow-finalizer-skipped` for a child that declares one; keep the child's outcome record under the parent's as `children[<unit>]` ([OUT-B18](90-run-outcome.spec.md)); and refuse with exit 2 naming the child a resume whose child was removed while the parent was paused inside it, `workflows register` restoring it.

- GIVEN a parent run with a child WHEN it ends THEN it left one `run.jsonl`, one checkpoint thread and one ledger row, every child record carrying `child`

### SWF-B9 Learning and measurement

WHEN a child's work is learned from and measured THE engine SHALL keep the child's judges on the child's own bindings and cases ([JCL](50-judge-calibration.spec.md)); file a finding about a child unit to the child workflow with `sides: [workflow]`, `workflow: <child>` and the parent named ([SIL](16-self-improvement.spec.md)); count the child's outcome record in the child's measures with `origin: subworkflow:<parent>`, in the child's promotion window only when that window says so ([PRO](95-promotion-check.spec.md)); and let a parent's `upgrade` read the child's change notes ([VER-B17](61-version-metadata.spec.md), [WUP-B6](63-workflow-upgrade.spec.md)).

- GIVEN a child unit's friction finding WHEN the loop files it THEN it is filed to the child workflow with the parent named

### SWF-B10 The child's finalizer and outcome gate stay its own

WHEN a sub-workflow is the parent's last unit THE engine SHALL never run the child's finalizer from the parent, whose own finalizer can call the same code, and never skip the child's outcome gate when the parent's gate grades the same criteria, because the child's outcome record is what the child's measures read (ADR-0133, accepted 2026-11-22).

- GIVEN a parent whose last unit is a child with a finalizer and whose final gate grades the child's criteria WHEN the run ends THEN the child's outcome gate ran, the child's finalizer did not, and the parent's finalizer ran once

### SWF-B11 A child does not run yet

WHEN `run` or `run --check` is given a workflow with a sub-workflow unit and finds no other reason to refuse it THE engine SHALL refuse it with exit 2 `not_in_release`, before any session starts and with nothing created under the state root, in one message that names the first such unit and says that running a child is not built yet.

- GIVEN a parent `deliver` that nothing else refuses and that declares `setup = Subworkflow(workflow="repo-setup", inputs={"request": "request"})` WHEN `run deliver` starts it THEN it exits 2 `not_in_release`, the one message names `setup` and says that running a child is not built yet, no session ran and the state root is unchanged
- GIVEN the same parent WHEN `run --check` checks it THEN it exits 2 with the same finding and creates nothing
- GIVEN a parent whose sub-workflow unit fails `subworkflow-version` WHEN `run` starts it THEN the refusal is that finding and not this one
- GIVEN a child that needs git and a run started outside git WHEN `run` starts the parent THEN the refusal is `needs_git` and not this one

### SWF-B12 A child's key in a template

WHEN a template names `{<unit>.<key>}` THE engine SHALL accept it at validation only for a sub-workflow unit earlier in the order that exposes `<key>` (by its `produces`, or with `produces` empty by the child's deliverables, SWF-B7) and refuse any other field of that form with `template-unknown-field` ([CON-B8](01-contracts.spec.md), [VAL-B8](76-step-values-and-template-keys.spec.md)).

- GIVEN `setup = Subworkflow(workflow="repo-setup", produces=["overview"])` and a later unit whose prompt names `{setup.overview}` WHEN the workflow validates THEN it has no error finding
- GIVEN `produces` empty and a child whose outcome lists the deliverable `overview` WHEN a later prompt names `{setup.overview}` THEN it has no error finding
- GIVEN a later prompt that names `{setup.notes}`, a key `setup` does not expose WHEN the workflow validates THEN it fails `template-unknown-field`
- GIVEN a prompt of a unit before `setup` that names `{setup.overview}` WHEN the workflow validates THEN it fails `template-unknown-field`

## Acceptance criteria

- SWF-AC1 (SWF-B1, SWF-B2, SWF-B3, SWF-B4, SWF-B5, SWF-B6, SWF-B7, SWF-B9, SWF-B10): SWF-B1 to SWF-B6 hold offline on stand-ins with an engine fixture parent and child, neither a shipped workflow
- SWF-AC2 (SWF-B8): A parent run with a child leaves one `run.jsonl`, one checkpoint thread and one ledger row; every child record carries `child`
- SWF-AC3 (SWF-B8): A carried parent paused inside its child resumes on a second state root ([CAR-AC1](96-run-state-on-a-branch.spec.md))
- SWF-AC4 (SWF-B11): A workflow with a sub-workflow unit that nothing else refuses is refused by `run` and by `run --check` with exit 2 and `not_in_release`, in one message naming the unit and saying that running a child is not built yet, with no session started and the state root unchanged, and a workflow that another refusal stops (a validation finding, `needs_git`) gets that refusal instead
- SWF-AC5 (SWF-B12): A template that names `{<unit>.<key>}` validates for a key a sub-workflow unit before it exposes, and fails `template-unknown-field` for a key that unit does not expose and for a unit that comes after the template

## Open questions

- Not built yet: running a child (SWF-B1 to SWF-B5, SWF-B8, SWF-B10), which SWF-B11 refuses meanwhile, and measures and carrying (SWF-B9, SWF-AC3). Owner: engine owner.
