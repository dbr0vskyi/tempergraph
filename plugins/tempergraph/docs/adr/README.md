# Architecture decision records

Each record states one decision, the options weighed, and when to revisit it. All records are `proposed` until the owner reviews them. A record is never edited to change its decision: a new record supersedes it.

| # | Decision | Status |
|---|---|---|
| [0001](0001-standalone-design-assumptions.adr.md) | Design tempergraph as a spec-driven doc set, standalone, with recorded assumptions | proposed |
| [0002](0002-langgraph-graph-runtime.adr.md) | Use LangGraph as the graph runtime | proposed |
| [0003](0003-workflows-as-data.adr.md) | Workflows are data in their own packages; the engine names none | proposed |
| [0004](0004-four-nodes-per-unit.adr.md) | Four nodes per unit; retries are edges; one interrupt per gate | proposed |
| [0005](0005-independent-judge-engine-verdict.adr.md) | An independent read-only judge reports; the engine derives the verdict | proposed |
| [0006](0006-executors-as-capability-adapters.adr.md) | Executors are capability-declaring adapters over headless agent CLIs | proposed |
| [0007](0007-two-first-class-executors.adr.md) | Ship two first-class executors: Claude Code CLI and Antigravity CLI | proposed |
| [0008](0008-portable-model-aliases.adr.md) | Workflows name portable model tiers and tool capabilities; executors bind them | proposed |
| [0009](0009-normalized-session-event-stream.adr.md) | Executors translate CLI streams into one normalized session event stream | proposed |
| [0010](0010-judge-isolation-per-executor.adr.md) | Judge isolation is a declared, probe-gated capability per executor | proposed |
| [0011](0011-isolated-config-home-for-antigravity.adr.md) | Restrict Antigravity sessions with an isolated config home and a deny-only gatekeeper hook | proposed |
| [0012](0012-cost-when-executor-reports-tokens-only.adr.md) | Cost is reported and estimated apart; an engine price table fills gaps; unknown is never zero | proposed |
| [0013](0013-cross-executor-judging.adr.md) | A judge may run on another executor than its step; selection is a fixed order | proposed |
| [0014](0014-sqlite-checkpointer.adr.md) | One SQLite checkpoint database per workflow; Postgres stays a seam | proposed |
| [0015](0015-exit-codes-as-caller-contract.adr.md) | Exit codes, not prose, are the contract with every caller | proposed |
| [0016](0016-portable-authoring-surface.adr.md) | The engine adds nothing to instruction files; workflows carry per-executor authoring surfaces | proposed |
| [0017](0017-artifact-type-suffixes.adr.md) | Every SDD artifact names its type in a double file suffix | proposed |
| [0018](0018-add-messages-api-and-agent-sdk-executors.adr.md) | Add two Anthropic executors: the Messages API and the Claude Agent SDK | proposed |
| [0019](0019-in-process-executors-run-in-a-worker-process.adr.md) | Library-based executors run in an engine worker process behind the same launcher | proposed |
| [0020](0020-engine-owned-tool-loop-for-the-messages-api.adr.md) | The Messages API executor runs an engine-owned loop over a minimal engine tool host | proposed |
| [0021](0021-scope-of-planned-work.adr.md) | Fold planned work into the design by fixed rules | proposed |
| [0022](0022-observers-read-files-not-sockets.adr.md) | Observers follow a run through append-only files and read-only verbs, not a socket or a daemon | proposed |
| [0023](0023-local-activity-journal-with-tool-input-summaries.adr.md) | Keep a local activity journal per session, with scrubbed and clipped tool input summaries | proposed |
| [0024](0024-one-local-store-layout-with-a-manifest.adr.md) | One versioned layout for everything a repository's runs leave, with manual retention | proposed |
| [0025](0025-cross-machine-stats-through-opt-in-sinks.adr.md) | Gather numbers across machines through opt-in, metadata-only sinks; no tempergraph server | proposed |
| [0026](0026-telemetry-export-as-otel-genai-without-content.adr.md) | Export telemetry as OpenTelemetry with the GenAI conventions, pinned, never with content | proposed |
| [0027](0027-in-process-observers-and-wider-hook-events.adr.md) | Add an in-process observer interface for exporters, and widen lifecycle hook events | proposed |
| [0028](0028-stop-verb-as-the-only-observer-control.adr.md) | A stop verb with drain is the only run control an observer may ask for | proposed |
