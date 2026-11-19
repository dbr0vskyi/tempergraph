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
| [0035](0035-orchestration-is-data-run-by-a-model-free-supervisor.adr.md) | An orchestration of runs is data executed by a model-free engine supervisor | proposed |
| [0036](0036-orchestration-state-is-a-file-and-an-event-log.adr.md) | Orchestration state is the file plus an append-only event log; runs hold the truth; nodes are known by id | proposed |
| [0037](0037-attention-batched-waking-of-the-orchestrating-session.adr.md) | The orchestrating session is woken only when a person is needed, in batches | proposed |
| [0038](0038-batch-is-a-one-node-orchestration.adr.md) | A batch is a one-node map orchestration | proposed |
| [0039](0039-pauses-stay-with-the-person-failures-follow-node-policy.adr.md) | In an orchestration, pauses stay with the person; failures follow a declared node policy | proposed |
| [0040](0040-take-script-steps-attention-and-composition-from-archon.adr.md) | Take script and hybrid steps, an attention verb and composable workflow packs; keep step outputs free-form | accepted |
| [0041](0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md) | A workflow graduates from local runs to a pipeline by measured, model-free criteria | proposed |
