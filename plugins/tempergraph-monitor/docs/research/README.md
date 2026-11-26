# Research notes

Background findings for the monitor's design. Rules: [engine docs README](../../../tempergraph/docs/README.md#research-rules).

| Note | Answers | Feeds |
|---|---|---|
| [Claude Code mods](claude-code-mods.rsrch.md) | What a mod can draw, read, run and keep; how its tools reach sessions; probes P-MOD-1 to P-MOD-3. | [MDS](../specs/data-sources.spec.md), [MBA](../specs/band-status-and-alerts.spec.md), [MAC](../specs/actions-and-safety.spec.md), [MADR `a-claude-code-mod-that-observes`](../adr/a-claude-code-mod-that-observes.adr.md) |
| [The dynamic workflows view](dynamic-workflows-view.rsrch.md) | How Claude Code shows a workflow run, and what a tempergraph run adds. | [MRV](../specs/run-view.spec.md), [MDD](../specs/drill-down.spec.md), [MADR `borrow-the-workflows-view-and-add-gates`](../adr/borrow-the-workflows-view-and-add-gates.adr.md) |
| [An at-a-glance home view](an-at-a-glance-home-view.rsrch.md) | Whether the pane can open on a dense overview of everything tempergraph is doing, from which data, drawn how, and how it drills down. | [MRV](../specs/run-view.spec.md), [MDS](../specs/data-sources.spec.md), [MADR `one-pane-many-levels`](../adr/one-pane-many-levels.adr.md) |

The engine-side gap list (what the monitor needs that the engine did not write) is [engine research `observer-needs-against-engine-documents`](../../../tempergraph/docs/research/observer-needs-against-engine-documents.rsrch.md).
