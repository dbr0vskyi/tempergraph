---
title: Workflow model and validation
type: component
status: ready-for-implementation
prefix: WFM
adrs: [0003, 0008, 0062, 0070, 0090]
---

# Workflow model and validation

## 1. Overview

A workflow is data: a `WorkflowSpec` ([CON §2.1](01-contracts.spec.md)) in its own package, registered once and validated in full before anything is spent. The same validation guards the catalog, a start, a resume, the pre-start check and the upgrade check, so a bad workflow fails before a model call. This spec owns what a workflow may declare and what is refused. Contract C8 is owned here: the engine core never names a workflow.

## 2. Contract

```python
def load(package_path: Path) -> WorkflowSpec: ...           # reads the manifests, imports the declaration, attaches the outcome (PKG §2.3)
def validate(spec: WorkflowSpec, executors: Registry) -> list[Finding]: ...
class Finding: code: str; unit: str | None; message: str; severity: Literal["error", "warning"]
```

What a package holds and how `load` reads it is [PKG](88-workflow-package.spec.md). The registry reads the workflow registry in the home folder (name → package folder, kept across engine updates, [UPD §2.8](60-engine-update.spec.md)) and loads each package lazily. The built-in self-improvement workflow is found by a flag on its spec, not by its name, and is registered last so no package can shadow it.

### 2.1 What is refused

| Area | Refused before a run (`error`) |
|---|---|
| Structure | Empty `order`; a unit `order` does not know; a step with no gate; a model step whose gate has no judge or no criterion (`wait`, `ask` and `script` units are the exceptions); a judge reference not produced on every path into the step, unless declared optional |
| Flow | A target outside `order`; a backward target the gate does not list; an unreachable unit or finalizer; a parallel block with fewer than two branches or a join before a branch; a sub-workflow that is unregistered, recursive or nested deeper than three; a writer branch or writing map item in a workflow without worktrees |
| Executors | An executor name not registered; an alias no binding resolves for that executor; a tool capability missing from the executor's `tool_map` |
| Judge view | A judge tool outside the read-only catalog; an artifact kind whose read view the judge executor cannot give, unless the criterion is marked as an unverified system |
| Tools, commands | A command no workflow allow-list entry covers; a command with a shell metacharacter; a command on a step that does not declare `shell`; a `command_resolver` that is not importable, or whose argv for a declared prefix contains a shell metacharacter |
| Prompts | Anything outside the template grammar ([CON §2.2](01-contracts.spec.md)); a field that is neither an engine key nor an input name; an unreadable template |
| Settings | A non-positive or non-integer timeout; a malformed or missing `issue_repository`; a ladder longer than eight; a declared setting whose default is outside its kind, choices or range; a profile naming a key outside the settings catalog or a value outside its range ([RST §4](80-run-settings-and-overrides.spec.md)) |
| Routing | A missing description, or a start example that does not resolve |
| Package, outcome | The refusals of [PKG §2.1, §2.3, §4](88-workflow-package.spec.md) (manifests, interface level, private imports, hooks, MCP servers, `bin/`, non-importable callables) and of [OUT §4](90-run-outcome.spec.md) (no outcome file or final criterion, unknown or missing units, unknown `serves`, duplicate ids, `none` without a reason); a unit named `outcome` |
| Unit kinds | The refusals of each kind's owning spec: [SCR §2.4](70-script-units-and-hybrid-steps.spec.md), [CNL §2.6](71-council-unit.spec.md), [CTS §2.4](72-contest-unit.spec.md), [ASK §2.2](73-ask-unit.spec.md), [FLX §2.6](74-flow-extensions.spec.md), [MAP §2.3](77-map-unit.spec.md), [SWM §4](79-measured-switches.spec.md) |
| Release | A unit kind, flow primitive or field that the running engine release does not build, finding `not_in_release` naming it and the release that adds it ([ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md)) |
| Checks, values, finalizer | `mechanical` on a gate with no check, `self_check` on a step whose gate has no check ([CHK §4](75-check-contract-and-command-runs.spec.md)); a reserved or misplaced template key, a bad `choices` or `pattern` ([VAL §4](76-step-values-and-template-keys.spec.md)); a finalizer without `finalizer_outcomes` or importing an executor ([FIN §4](78-finalizer-contract.spec.md)); a `skill:` capability naming a plugin path that is not installed with the workflow |

### 2.2 What only warns (`warning`)

| Finding | Why only a warning |
|---|---|
| A prompt names a tool or command its step does not declare | Promoted to `error` when `improvement_mode` is `stable` |
| `effort` on an executor that cannot apply it | It changes cost, not safety |
| A criterion with no `check_method` | Judge quality, graded by the readiness report ([LIF](18-lifecycle-and-evals.spec.md)) |
| An executor-qualified alias where a tier would do | Portability across executors |
| A prompt names a skill, agent or instruction file and its step's executor does not host an authoring surface | The step may still work if the template carries the content |
| A judge brief branches on facts a check could compute | Rule-like branching belongs in the check or a route ([JDG-B6](05-judge-and-verdict.spec.md)) |
| A blocker verified by `none`; `docs-drift` | Promoted to `error` when `improvement_mode` is `stable` ([OUT §2.2](90-run-outcome.spec.md), [PKG §2.5](88-workflow-package.spec.md)) |

## 3. Behaviours

**WFM-B1 Refuse early.** Given a workflow with an unbalanced brace in one prompt, when an operator lists the catalog or starts a run, then the row is shown as invalid with the finding, the start exits 2, and nothing is created under the state root.

**WFM-B2 Missing input refuses.** Given a prompt that names `{ticket}` and a request that does not supply `ticket`, when the pre-start check and the start run, then both refuse the request in the same way.

**WFM-B3 Portable declaration.** Given a step declaring tools `read`, `search`, `shell` and model `medium`, when it is validated against all four executors, then it is valid for each whose `tool_map` and bindings cover them; a later executor switch needs no edit of the workflow.

| Step executor | `medium` bound | `shell` mapped | Valid |
|---|---|---|---|
| claude | yes | `Bash` | yes |
| agent-sdk | yes | `Bash` | yes |
| messages-api | yes | `run_command` (tool host) | yes |
| antigravity | yes | `run_command` | yes |
| antigravity | no binding | — | no (exit 2) |

**WFM-B4 Wait unit has no person's pass.** Given a `wait` unit, when it is validated, then it must declare a deterministic check; no judge is allowed and a person's proceed cannot pass it ([HUM](07-gate-and-human.spec.md)).

**WFM-B5 Defaults keep old workflows working.** Given a workflow written before a field existed, when it loads, then the field takes its default and the workflow validates unchanged.

**WFM-B6 Command resolver.** Given a workflow for a Go repository whose check runs the declared prefix `test` and whose `command_resolver` maps `test` to `["go", "test", "./..."]`, when the check and a step's tools block use the prefix, then both run that argv, and validation confirms the resolver is pure (same input, same argv) and calls no model. Without a resolver a prefix is its own argv split on spaces.

## 4. Error conditions

| Type | Result |
|---|---|
| Package folder missing from disk | Catalog row `not loaded`; start exit 2 |
| Declaration module raises on import | Catalog row `not loaded` with the exception type only; start exit 2 |
| Two packages register the same name | Both rows invalid |
| Manifest unreadable | Catalog empty with one finding; the update verb repairs it |

## 5. Design notes

- Routing metadata sits on the spec so a classifier can pick a workflow without the engine naming one ([ADR-0003](../adr/0003-workflows-as-data.adr.md)).
- Workflows declare neutral tiers and capabilities so a team can move a step between executors by changing one field ([ADR-0008](../adr/0008-portable-model-aliases.adr.md)).
- A workflow package is imported into the engine's process. Isolation is by rule and review, not a sandbox: workflows import the engine's public interface only, and new dependencies pass the dependency gate.
- A new spec field is appended last with a default, recorded in the compatibility changelog, and kept out of the diagram digest unless it changes the shape.

## 6. Acceptance criteria

- [ ] WFM-AC-1 Every row of §2.1 has a fixture workflow that fails validation with its own finding code.
- [ ] WFM-AC-2 The catalog, start, resume, pre-start check and upgrade check call the same `validate`.
- [ ] WFM-AC-3 A refused start leaves the state root byte-for-byte unchanged.
- [ ] WFM-AC-4 No engine source file names a shipped workflow (source-scan test).
- [ ] WFM-AC-5 A workflow using only tiers and capability names validates against all four shipped executors.
- [ ] WFM-AC-6 A fixture workflow using each kind, primitive and field outside the running release fails validation with `not_in_release`, on the catalog, a start and the pre-start check alike.

## Open questions

None.

## References

