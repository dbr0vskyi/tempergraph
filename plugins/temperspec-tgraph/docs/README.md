# Docs

Rules: provisional (the engine's docs README). Criterion text lives in `outcome.json`; the specs under `specs/` name each criterion by id.

| Folder | Holds |
|---|---|
| [specs/](specs/00-overview.spec.md) | The overview and one spec per unit, generated at scaffold in the engine's layout |
| [adr/](adr/0001-ts-spec-sync.adr.md) | Decisions recorded while authoring |
| [research/](research/sources.rsrch.md) | What the authoring session read |
| [plans/](plans/live-checks.plan.md) | The checks still to run on a signed-in machine |

The documents a run of temperspec writes in a target repository follow the rule files in [`../rules/`](../rules/documents.rule.md), not the layout of this folder. This folder moves to that format when the engine's own specs do.
