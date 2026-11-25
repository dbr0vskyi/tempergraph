# Research notes

Background findings for the monitor's design. Rules: [engine docs README](../../../tempergraph/docs/README.md#research-rules).

| Note | Answers | Feeds |
|---|---|---|
| [R-001 Claude Code mods](R-001-claude-code-mods.rsrch.md) | What a mod can draw, read, run and keep; how its tools reach sessions; probes P-MOD-1 to P-MOD-3. | [MDS](../specs/data-sources.spec.md), [MBA](../specs/band-status-and-alerts.spec.md), [MAC](../specs/actions-and-safety.spec.md), [MADR-0001](../adr/0001-a-claude-code-mod-that-observes.adr.md) |
| [R-002 The dynamic workflows view](R-002-dynamic-workflows-view.rsrch.md) | How Claude Code shows a workflow run, and what a tempergraph run adds. | [MRV](../specs/run-view.spec.md), [MDD](../specs/drill-down.spec.md), [MADR-0004](../adr/0004-borrow-the-workflows-view-and-add-gates.adr.md) |

The engine-side gap list (what the monitor needs that the engine did not write) is [engine R-021](../../../tempergraph/docs/research/R-021-observer-needs-against-engine-documents.rsrch.md).
