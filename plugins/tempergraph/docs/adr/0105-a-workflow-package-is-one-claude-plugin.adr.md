# ADR-0105 A workflow package is one Claude plugin with a Python part and a docs set

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner's direction (2026-11-20): creating a workflow produces a Claude plugin with the prompts, agents and skills specific to the workflow, plus executable Python code for the engine; and the workflow plugin has specs the same way the engine does. The design had no package layout ([R-090](../research/R-090-implementation-readiness.rsrch.md) D1). Claude Code strips unknown keys from `plugin.json` and does not install Python dependencies ([R-105](../research/R-105-workflow-packages-authoring-and-good-outcomes.rsrch.md) A1, A4).

## Decision

We will make a workflow package one folder that is a valid Claude Code plugin and holds, beside the plugin parts, an engine manifest `tempergraph.json`, the good outcome `outcome.json`, a Python half under `workflow/` with a `pyproject.toml` whose dependencies the engine installs, and a docs half under `docs/`. The engine imports the Python half from the folder and never installs it as a distribution. The layout is [PKG-B11, PKG-B12](../specs/workflow-package.spec.md).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| One folder: plugin plus Python plus docs (chosen) | One version, one install from a marketplace, one digest; a cache repoint runs the new code | Two manifests to keep in step (mitigated: the version is read from `plugin.json` only) |
| A plugin and a separate Python distribution on an index | Standard Python packaging | Two releases that drift; an index to publish to; the marketplace cannot install it |
| Engine fields inside `plugin.json` | One manifest | Claude Code strips unknown keys (R-105 A1) |
| Python half installed into the engine environment as a package | Normal imports | Every plugin update needs a reinstall; old and new code can both be importable |

## Decision rationale

| Criterion | One folder | Two artefacts | Fields in plugin.json | Installed Python |
|---|---|---|---|---|
| Survives Claude Code's manifest rules | yes | yes | no | yes |
| One version for prompts and code | yes | no | yes | yes |
| Plugin update runs new code without a reinstall | yes | no | yes | no |
| Docs travel with the workflow | yes | partly | yes | yes |

## Consequences

- Positive: a workflow is installed, versioned, audited and upgraded as one thing; the registry already repoints by version folder ([UPD-B20 to UPD-B24](../specs/engine-update.spec.md)).
- Negative: a workflow's own Python imports go through the engine's loader rules, not plain `sys.path`.
- Risk: claude.ai and Cowork do not install a plugin with `bin/` (R-105 A2). Mitigation: a workflow ships no `bin/`.

## Assumptions

- The owner's "Claude plugin" means a Claude Code plugin as documented on 2026-11-20.
- "Specs in the same way as the engine" means a docs set with the engine's rules, applied to one workflow ([ADR-0113](0113-the-workflow-docs-set-is-provisional-until-temperspec-owns-it.adr.md)).
