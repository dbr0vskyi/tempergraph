# tempergraph-monitor design docs

The design of the `tempergraph-monitor` plugin: a Claude Code **mod** that shows tempergraph runs live inside Claude Code, the way Claude Code shows a dynamic workflow, with tempergraph's own layers on top: gates, checks, judges, cost and the full session logs the engine keeps.

This set follows the engine's doc rules unchanged: [plugins/tempergraph/docs/README.md](../../tempergraph/docs/README.md) (folders, file naming with type suffixes, spec rules, decision rules, research rules, truth ranking, readiness flags). Only what differs is written here.

## Where things live

| Folder | Holds |
|---|---|
| [specs/](specs/00-overview.spec.md) | Overview and component specs of the mod |
| [adr/](adr/README.md) | Decision records of the mod |
| [research/](research/README.md) | Research notes: how Claude Code mods and the dynamic workflows view work |

Read in this order: the [overview](specs/00-overview.spec.md), the [data sources](specs/01-data-sources.spec.md), then the view spec you need.

## Numbering and ids

- Spec, ADR and research numbers are the monitor's own and start again at 00, 0001 and R-001; a link to an engine artifact always names its path, so "ADR-0022" in this set means the engine's only when it links into `plugins/tempergraph/docs/`. Inside this set a record is written "MADR-0001" in prose to avoid the clash.
- Each monitor spec owns one prefix starting with `M` (listed in the overview), so no id collides with an engine prefix.

## Shared types

The monitor defines no engine type. Every document it reads is defined by the engine: the status document ([DUR §2.2](../../tempergraph/docs/specs/09-durability-and-resume.spec.md)), the detail document ([RDD](../../tempergraph/docs/specs/31-run-detail-document.spec.md)), run-log records and the activity journal ([EVT](../../tempergraph/docs/specs/30-run-events.spec.md)), the store layout ([LOS](../../tempergraph/docs/specs/33-local-observability-store.spec.md)), stats and heartbeats ([CST](../../tempergraph/docs/specs/34-central-run-stats.spec.md)) and the orchestration status document ([ORC §2.7](../../tempergraph/docs/specs/45-orchestration.spec.md)). The mod's own state shapes live in its type contract when code exists.

## Status

Written standalone without the owner. MDS, MBA, MRV and MDD are `ready-for-implementation` and partly built in release 1 (code in `hooks/`, tests in `tests/`; what is built is listed in each spec's design notes and in the [T10 plan](../../tempergraph/docs/plans/t10-monitor.plan.md)); MOV, MAC and MCF stay `review`. The mod's own state shapes are in its type contract, `types/index.d.ts`. The Claude Code mods API is versioned by Claude Code build and moves between releases ([R-001](research/R-001-claude-code-mods.rsrch.md)); each API fact this set relies on is listed with its confidence there.
