# Docs

Rules: provisional (the engine's docs README). Criterion text lives in `outcome.json`; the specs under `specs/` name each criterion by id.

| Folder | Holds |
|---|---|
| [specs/](specs/00-overview.spec.md) | The overview and one spec per unit, generated at scaffold in the engine's layout |
| [adr/](adr/0001-ts-spec-sync.adr.md) | Decisions recorded while authoring |
| [research/](research/sources.rsrch.md) | What the authoring session read, and the [comparison with other spec-driven development tools](research/sdd-tools-comparison.rsrch.md) the [next features proposed from it](research/next-features.rsrch.md), [what the plan could take from the reference plan](research/plan-format-against-reference.rsrch.md), and [a trust report on its pull requests](research/pull-request-report.rsrch.md) |
| [plans/](plans/live-checks.plan.md) | The [live-check runbook and results](plans/live-checks.plan.md) and the plans of past runs. Features not built yet are [GitHub issues](https://github.com/dbr0vskyi/tempergraph/issues?q=is%3Aissue+is%3Aopen+label%3A%22area%3A+temperspec%22) |

The documents a run of temperspec writes in a target repository follow the rule files in [`../rules/`](../rules/documents.rule.md), not the layout of this folder. This folder moves to that format when the engine's own specs do.
