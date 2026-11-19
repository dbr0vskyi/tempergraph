# ADR-0003 Workflows are data in their own packages; the engine names none

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The repository is a plugin marketplace: `tempergraph` (the engine) beside workflow plugins such as temperspec. One shared plugin holding every team's process cannot change fast, and a special case for one workflow makes every other second class.

## Decision

We will define a workflow as a declarative `WorkflowSpec` in its own package, found through a register-once manifest, carrying its own prompts, checks, start facts, routing metadata, authoring surface and eval scenarios. The engine core never names or imports a workflow; the built-in self-improvement workflow is found by a flag.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Separate package per workflow, manifest discovery (chosen) | Independent versioning; private workflows stay private; skills travel with their workflow | Packages share the engine's Python process; isolation is by rule |
| All workflows in the engine package | One install | Ties release cadence to every workflow; blocks private workflows |
| Python entry points | Standard | Needs a pip install per workflow; plugins install as source folders |
| Copy the process into each target repository | No plugin needed | Copies drift from their source; every change threads through every copy |

## Decision rationale

| Criterion | Package + manifest | One package | Entry points | Copy-in |
|---|---|---|---|---|
| Add a workflow with no engine edit | yes | no | yes | yes |
| Fits plugin source-folder install | yes | yes | no | yes |
| Private workflows | yes | no | yes | yes |
| Drift risk | low | low | low | high |

## Consequences

- Positive: temperspec and later workflows evolve on their own; validation and the catalog work for any of them.
- Negative: a bad dependency in a workflow can break the engine's process. Mitigation: a dependency gate and the rule that workflows import only the engine's public interface.
- Risk: routing metadata ("when to use") rots. Mitigation: review it with the spec; routing misses feed self-improvement.

## Revisit when

A workflow needs code the engine must run in another process, or a third-party workflow needs sandboxing.
