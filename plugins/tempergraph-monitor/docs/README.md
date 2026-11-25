# tempergraph-monitor design docs

The design of the `tempergraph-monitor` plugin: a Claude Code **mod** that shows tempergraph runs live inside Claude Code, the way Claude Code shows a dynamic workflow, with tempergraph's own layers on top: gates, checks, judges, cost and the full session logs the engine keeps.

This set follows the engine's doc rules unchanged: [plugins/tempergraph/docs/README.md](../../tempergraph/docs/README.md) (folders, file naming with type suffixes, spec rules, decision rules, research rules, truth ranking, readiness flags). Only what differs is written here.

## Where things live

| Folder | Holds |
|---|---|
| [specs/](specs/overview.spec.md) | Overview and component specs of the mod |
| [adr/](adr/README.md) | Decision records of the mod |
| [research/](research/README.md) | Research notes: how Claude Code mods and the dynamic workflows view work |

Read in this order: the [overview](specs/overview.spec.md), the [data sources](specs/data-sources.spec.md), then the view spec you need.

## Names and ids

- No document carries a number. A decision record or a research note is cited by its file name; a link to an engine artifact always names its path into `plugins/tempergraph/docs/`. Inside this set a monitor record is written "MADR `<name>`" in prose, so that it is not taken for an engine record.
- Each monitor spec owns one prefix starting with `M` (listed in the overview), so no id collides with an engine prefix.

## Shared types

The monitor defines no engine type. Every document it reads is defined by the engine: the status document ([DUR-B11](../../tempergraph/docs/specs/durability-and-resume.spec.md)), the detail document ([RDD](../../tempergraph/docs/specs/run-detail-document.spec.md)), run-log records and the activity journal ([EVT](../../tempergraph/docs/specs/run-events.spec.md)), the store layout ([LOS](../../tempergraph/docs/specs/local-observability-store.spec.md)), stats and heartbeats ([CST](../../tempergraph/docs/specs/central-run-stats.spec.md)) and the orchestration status document ([ORC-B25](../../tempergraph/docs/specs/orchestration.spec.md)). The mod's own state shapes live in its type contract when code exists.

## Status

Written standalone without the owner. Every spec is `ready-for-implementation`, and release 1 builds most of them (code in `hooks/`, tests in `tests/`); what is built, and where the code differs, is in each spec's design notes and in the [T10 plan](../../tempergraph/docs/plans/t10-monitor.plan.md). The mod's own state shapes are in its type contract, `types/index.d.ts`. The Claude Code mods API is versioned by Claude Code build and moves between releases ([research `claude-code-mods`](research/claude-code-mods.rsrch.md)); each API fact this set relies on is listed with its confidence there.
