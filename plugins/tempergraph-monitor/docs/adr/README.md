# Monitor decision records

Each record states one decision of the `tempergraph-monitor` design. In prose a monitor record is written "MADR `<name>`" so that it is not taken for an engine record. All are `proposed` until the owner reviews them. Rules: [engine docs README](../../../tempergraph/docs/README.md#decision-rules).

| Record | Decision | Status |
|---|---|---|
| [`a-claude-code-mod-that-observes`](a-claude-code-mod-that-observes.adr.md) | The monitor is a Claude Code mod that only observes | proposed |
| [`poll-files-and-read-only-verbs`](poll-files-and-read-only-verbs.adr.md) | Poll engine files by stat and offset; call read-only verbs for combined documents | proposed |
| [`actions-fill-the-prompt`](actions-fill-the-prompt.adr.md) | Every action fills the prompt; the person sends it; no model tool by default | proposed |
| [`borrow-the-workflows-view-and-add-gates`](borrow-the-workflows-view-and-add-gates.adr.md) | Borrow the workflows view's navigation; add the graph, the four nodes, judges and money | proposed |
| [`three-scopes-repo-machine-fleet`](three-scopes-repo-machine-fleet.adr.md) | Three scopes: repository, machine, fleet through a sink | proposed |
| [`one-pane-many-levels`](one-pane-many-levels.adr.md) | One pane with levels, not a pane per run | proposed |

The engine-side decisions the monitor depends on are engine ADRs `observers-read-files-not-sockets`, `local-activity-journal-with-tool-input-summaries`, `one-local-store-layout-with-a-manifest`, `cross-machine-stats-through-opt-in-sinks`, `telemetry-export-as-otel-genai-without-content`, `in-process-observers-and-wider-hook-events` and `stop-verb-as-the-only-observer-control` ([engine index](../../../tempergraph/docs/adr/README.md)).
