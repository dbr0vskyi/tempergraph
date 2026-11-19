# Monitor decision records

Each record states one decision of the `tempergraph-monitor` design. In prose they are written MADR-NNNN so they are not confused with the engine's ADR-NNNN. All are `proposed` until the owner reviews them. Rules: [engine docs README](../../../tempergraph/docs/README.md#decision-rules).

| # | Decision | Status |
|---|---|---|
| [0001](0001-a-claude-code-mod-that-observes.adr.md) | The monitor is a Claude Code mod that only observes | proposed |
| [0002](0002-poll-files-and-read-only-verbs.adr.md) | Poll engine files by stat and offset; call read-only verbs for combined documents | proposed |
| [0003](0003-actions-fill-the-prompt.adr.md) | Every action fills the prompt; the person sends it; no model tool by default | proposed |
| [0004](0004-borrow-the-workflows-view-and-add-gates.adr.md) | Borrow the workflows view's navigation; add the graph, the four nodes, judges and money | proposed |
| [0005](0005-three-scopes-repo-machine-fleet.adr.md) | Three scopes: repository, machine, fleet through a sink | proposed |
| [0006](0006-one-pane-many-levels.adr.md) | One pane with levels, not a pane per run | proposed |

The engine-side decisions the monitor depends on are engine ADR-0022 to ADR-0028 ([engine index](../../../tempergraph/docs/adr/README.md)).
