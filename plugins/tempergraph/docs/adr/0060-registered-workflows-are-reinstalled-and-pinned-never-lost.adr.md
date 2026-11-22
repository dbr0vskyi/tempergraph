# ADR-0060 Registered workflows live in a home registry, are reinstalled into every new engine, and are pinned to the old engine when they break

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner added that during an engine update the installed workflows must be reinstalled automatically, so that registered workflows are not lost and keep working. A reinstall can make a workflow vanish from the manifest, and an entry pinned to a cache folder silently runs old code. A workflow package is imported into the engine's process ([WFM](../specs/02-workflow-model.spec.md)), so its Python dependencies live in the engine environment. With side-by-side environments ([ADR-0055](0055-side-by-side-engine-environments-switched-atomically.adr.md)), a new environment starts without them. A release can also tighten validation, so that a workflow that ran yesterday is refused today until its owner upgrades it.

## Decision

We will ([UPD-B20 to UPD-B24](../specs/60-engine-update.spec.md)):

1. Keep registration in `~/.tempergraph/registry.json`, outside every environment, with `plugin`, `local` and `builtin` entries. Only `workflows unregister` removes an entry.
2. On every update and install, install each entry's declared Python dependencies into the new environment, then load and validate each workflow under the new engine before the switch.
3. Pin a workflow that worked on the old engine and fails on the new one to the old engine. Its runs are dispatched there, the pin is shown everywhere, and it clears itself once the workflow validates on the current engine.
4. Add `workflows list|register|unregister|reinstall` verbs, and an `install` verb run from a launcher in the plugin.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Home registry, reinstall, pin on breakage (chosen) | Nothing lost; every workflow keeps running; the update is never held back by one workflow; reuses the thread dispatch | An old engine kept while a workflow is pinned; one more state to show |
| Refuse the update while any workflow would break | No mixed engines | One stale workflow blocks every engine fix; its owner may be someone else |
| Switch and leave broken workflows refused | Simplest | Breaks the owner's explicit need: workflows stop working after an update |
| Keep the manifest inside the environment | No new file | Lost with every new environment |

## Decision rationale

| Criterion | Registry + pin | Refuse update | Switch, refuse | In-env manifest |
|---|---|---|---|---|
| Registration never lost | yes | yes | yes | no |
| Workflows keep working | yes | yes | no | no |
| Engine fixes not blocked | yes | no | yes | yes |
| Old engines kept | while pinned | none | none | none |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | "Reinstall the installed workflows" means re-registering them and reinstalling their Python dependencies into the new engine, not reinstalling their plugins, which Claude Code owns. | UPD-B20 to UPD-B24 |
| A2 | A workflow package declares its Python dependencies in its package metadata; the exact place waits for the package-layout spec ([R-011](../research/R-011-design-gap-review.rsrch.md) G2). | UPD-B20 to UPD-B24 |
| A3 | Running a pinned workflow on an older engine is acceptable to the owner, as long as it is visible. | UPD-B7 |

## Consequences

- Positive: an update never loses or stops a workflow; the report names exactly what to do for each one.
- Negative: dependency installs make an update slower in proportion to the workflows registered.
- Risk: pins linger and old engines pile up. Mitigation: every catalog and run check shows the pin and its remedy, and the update skill offers the upgrade for local sources.

## Revisit when

Workflows get their own isolated environments (a sandbox), which would make reinstalling into the engine environment unnecessary.
