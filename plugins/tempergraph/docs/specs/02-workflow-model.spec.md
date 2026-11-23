# Workflow model and validation

## Purpose

A workflow is data: a `WorkflowSpec` ([CON-B4](01-contracts.spec.md)) in its own package, registered once and validated in full before anything is spent. The same validation guards the catalog, a start, a resume, the pre-start check and the upgrade check, so a bad workflow fails before a model call. This spec owns what a workflow may declare and what is refused, and OVR-B10: the engine core never names a workflow ([ADR-0129](../adr/0129-the-engine-names-no-workflow-and-takes-requests-as-general-capabilities.adr.md)). What a package holds and how it is loaded is [PKG](88-workflow-package.spec.md). The compiler ([CMP](03-compiler-and-flow.spec.md)), the CLI, authoring ([SCF](91-blueprint-and-scaffold.spec.md)) and upgrade depend on it; design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### WFM-B1 Refuse early

WHEN a workflow has an error finding THE engine SHALL show its catalog row as invalid with the finding, refuse a start with exit 2, and create nothing under the state root.

- GIVEN an unbalanced brace in one prompt WHEN an operator lists the catalog or starts a run THEN the row is invalid, the start exits 2 and the state root is unchanged

### WFM-B2 Missing input refuses

WHEN a prompt names a field the request does not supply THE pre-start check and the start SHALL both refuse the request in the same way.

- GIVEN a prompt that names `{ticket}` and a request without `ticket` WHEN `run --check` and `run` run THEN both refuse it alike

### WFM-B3 Portable declaration

WHEN a step declares neutral tools and a tier THE engine SHALL validate it for each executor whose `tool_map` and bindings cover them, so an executor switch needs no edit of the workflow, and refuse with exit 2 where an alias has no binding.

- GIVEN a step with tools `read`, `search`, `shell` and model `medium` WHEN validated for `claude`, `agent-sdk`, `messages-api` and `antigravity` THEN it is valid for each (`shell` mapped to `Bash` or `run_command`)
- GIVEN `antigravity` with no binding for `medium` WHEN validated THEN it fails with exit 2

### WFM-B4 Wait unit has no person's pass

WHEN a `wait` unit is validated THE engine SHALL require a deterministic check, allow no judge, and never let a person's proceed pass it ([HUM](07-gate-and-human.spec.md)).

- GIVEN a `wait` unit with a judge WHEN it is validated THEN it is refused

### WFM-B5 Defaults keep old workflows working

WHEN a workflow written before a field existed loads THE engine SHALL give the field its default and validate the workflow unchanged, every new spec field being appended last with a default, recorded in the compatibility changelog and kept out of the diagram digest unless it changes the shape.

- GIVEN a workflow that predates `effort` WHEN it loads THEN it validates with the default effort

### WFM-B6 Command resolver

WHEN a workflow declares a `command_resolver` THE engine SHALL run the argv it maps a declared prefix to in both the check and a step's tools block, and validation SHALL confirm the resolver is pure (same input, same argv) and calls no model; without a resolver a prefix is its own argv split on spaces.

- GIVEN a Go repository whose `command_resolver` maps `test` to `["go", "test", "./..."]` WHEN the check and a step use `test` THEN both run that argv

### WFM-B7 Loading and the registry

WHEN workflows are listed or started THE engine SHALL offer `load(package_path) -> WorkflowSpec` (reading the manifests, importing the declaration and attaching the outcome, [PKG-B15](88-workflow-package.spec.md)) and `validate(spec, executors) -> list[Finding]`, a `Finding` holding `code`, `unit` or null, `message` and `severity` `error` or `warning`; read the workflow registry in the home store (name to package folder, kept across engine updates, [UPD-B20](60-engine-update.spec.md)) and load each package lazily; find the built-in self-improvement workflow by a flag on its spec, not by its name, registered last so no package can shadow it; show a package folder missing from disk as `not loaded`, an import that raises as `not loaded` with the exception type only, two packages registering the same name as both invalid, and an unreadable registry as an empty catalog with one finding that the update verb repairs, a start exiting 2 in each case; and call the same `validate` from the catalog, start, resume, pre-start check and upgrade check.

- GIVEN two packages that register `notes` WHEN the catalog is listed THEN both rows are invalid

### WFM-B8 Structure and flow refusals

WHEN a workflow is validated THE engine SHALL refuse an empty `order`, a unit `order` does not know, a step with no gate, a model step whose gate has no judge or no criterion (`wait`, `ask` and `script` units excepted), a judge reference not produced on every path into the step unless declared optional (a parallel branch's output counting as produced on every path past its join), a unit named `outcome`; a target outside `order`, a backward target the gate does not list, an unreachable unit or finalizer, a parallel block with fewer than two branches or a join before a branch (`parallel-branches`, `parallel-branch-unknown`, `parallel-join-before-branch`, `parallel-branch-kind`, `parallel-branch-flow`, `parallel-branch-shared`, `parallel-branches-not-adjacent`, `parallel-join-gate`), a sub-workflow that is unregistered, recursive or nested deeper than three ([SWF-B6](99-subworkflow-unit.spec.md)), and a writer branch ([WSP-B11](13-workspace-and-concurrency.spec.md)) or writing map item in a workflow without worktrees (one that declares `workspace: in_place`).

- GIVEN a backward target the gate does not list WHEN the workflow validates THEN it is refused
- GIVEN a parallel branch that declares `edit` in a workflow that declares `workspace: in_place` WHEN the workflow validates THEN it is refused
- GIVEN a parallel branch that declares `edit` in a workflow that declares no `workspace` WHEN the workflow validates THEN it validates

### WFM-B9 Executor, judge, tool and prompt refusals

WHEN a workflow is validated THE engine SHALL refuse an executor name not registered, an alias no binding resolves for that executor, a tool capability missing from the executor's `tool_map`, a `skill:` capability naming a plugin path not installed with the workflow; a judge tool outside the read-only catalog and an artifact kind whose read view the judge executor cannot give unless the criterion is marked an unverified system; a command no workflow allow-list entry covers, a command with a shell metacharacter, a command on a step that does not declare `shell`, a `command_resolver` that is not importable or whose argv for a declared prefix holds a shell metacharacter; and anything outside the template grammar ([CON-B8](01-contracts.spec.md)), a field that is neither an engine key nor an input name, and an unreadable template.

- GIVEN a step command `make test && rm -rf x` WHEN the workflow validates THEN it is refused for the shell metacharacter

### WFM-B10 Settings, routing and release refusals

WHEN a workflow is validated THE engine SHALL refuse a non-positive or non-integer timeout, a malformed or missing `issue_repository`, a ladder longer than eight, a declared setting whose default is outside its kind, choices or range, a profile naming a key outside the settings catalog or a value outside its range ([RST-B32](80-run-settings-and-overrides.spec.md)); a missing routing description or a start example that does not resolve; and a unit kind, flow primitive or field the running release does not build, with `not_in_release` naming it and the release that adds it on the catalog, a start and the pre-start check alike ([ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md)).

- GIVEN a `council` unit WHEN the workflow validates THEN it is refused `not_in_release` naming the release that adds it

### WFM-B11 Refusals owned elsewhere

WHEN a workflow is validated THE engine SHALL apply the refusals of the package ([PKG-B11](88-workflow-package.spec.md) to [PKG-B20](88-workflow-package.spec.md)) and of the outcome ([OUT-B22](90-run-outcome.spec.md)); of each unit kind's owning spec ([SCR-B6](70-script-units-and-hybrid-steps.spec.md), [CNL-B16](71-council-unit.spec.md), [CTS-B10](72-contest-unit.spec.md), [ASK-B7](73-ask-unit.spec.md), [FLX-B11](74-flow-extensions.spec.md), [MAP-B11](77-map-unit.spec.md), [SWM-B4](79-measured-switches.spec.md)), with the `ask-*`, `wait-*`, `deadline-*` and `fallback-*` codes; `mechanical` on a gate with no check and `self_check` on a step whose gate has no check (`self-check-without-check`, [CHK-B15](75-check-contract-and-command-runs.spec.md)); a reserved or misplaced template key or a bad `choices` or `pattern` ([VAL-B8](76-step-values-and-template-keys.spec.md)); and a finalizer without `finalizer_outcomes` or importing an executor ([FIN-B10](78-finalizer-contract.spec.md)).

- GIVEN `mechanical` on a gate with no check WHEN the workflow validates THEN it is refused

### WFM-B12 Warnings

WHEN a workflow is validated THE engine SHALL only warn when a prompt names a tool or command its step does not declare, or a blocker is verified by `none`, or `docs-drift` fires ([OUT-B10](90-run-outcome.spec.md), [PKG-B22](88-workflow-package.spec.md)), each an `error` when `improvement_mode` is `stable`; and always only warn on `effort` an executor cannot apply, a criterion with no `check_method` (graded by the readiness report, [LIF](18-lifecycle-and-evals.spec.md)), an executor-qualified alias where a tier would do, a prompt naming a skill, agent or instruction file whose step's executor hosts no authoring surface, and a judge brief that branches on facts a check could compute ([JDG](05-judge-and-verdict.spec.md)).

- GIVEN a prompt naming an undeclared tool WHEN the workflow validates in `stable` mode THEN it is an error

### WFM-B13 Wait and parallel fields

WHEN `wait` and `parallel` units are declared THE engine SHALL read a wait's `event` (a slug), `check` (callable ref), `deadline_s` and `on_deadline`, and a parallel unit's `branches` (two or more unit names), with `ask`, `wait` and `parallel` in the release, `council` refused `not_in_release`, and `subworkflow` and `contest` read as [SWF-B7](99-subworkflow-unit.spec.md) and [CTS-B6](72-contest-unit.spec.md) read them.

- GIVEN a parallel unit with one branch WHEN it validates THEN it is refused `parallel-branches`

## Acceptance criteria

- WFM-AC1 (WFM-B1, WFM-B4, WFM-B8, WFM-B9, WFM-B10, WFM-B11, WFM-B13): Every refusal has a fixture workflow that fails validation with its own finding code
- WFM-AC2 (WFM-B2, WFM-B7): The catalog, start, resume, pre-start check and upgrade check call the same `validate`
- WFM-AC3 (WFM-B1): A refused start leaves the state root byte-for-byte unchanged
- WFM-AC4 (WFM-B7): No engine source file, engine skill or engine test names a workflow package of the repository or its workflow; the scans take the names from the packages found, never from a typed list
- WFM-AC5 (WFM-B3, WFM-B5, WFM-B6, WFM-B12): A workflow using only tiers and capability names validates against all four shipped executors, and each warning has a fixture that warns and does not refuse outside `stable`
- WFM-AC6 (WFM-B10): A fixture workflow using each kind, primitive and field outside the running release fails validation with `not_in_release`, on the catalog, a start and the pre-start check alike
- WFM-AC7 (WFM-B8): A workflow whose parallel branch declares `write` or `edit` validates with no error finding, and the same workflow declaring `workspace: in_place` is refused with its own finding code
