# R-004 Anthropic Messages API as an executor

## Problem statement

The owner asked for an executor on Anthropic's Messages API. Unlike the two CLIs ([R-001](R-001-claude-code-cli-headless.rsrch.md), [R-002](R-002-antigravity-cli-headless.rsrch.md)), the API runs no agent loop on the client and executes no file or shell tool: the caller sends messages and tool definitions, the model answers with `tool_use` blocks, and the caller runs them and sends results back. [ADR-0006](../adr/0006-executors-as-capability-adapters.adr.md) rejected "model APIs directly" as the *only* executor shape. This note records what the API offers and what the engine would have to own, so that a Messages API executor ([EMA](../specs/20-executor-messages-api.spec.md)) and its tool host ([THS](../specs/22-tool-host.spec.md)) rest on documented facts.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| `claude-api` skill: overview, models table, thinking, caching, server tools, provider clients | Official guidance, local copy (models cached 2026-11-03) | Skill `SKILL.md` |
| Tool use concepts (loop, stop reasons, server tools, bash and text editor tools) | Official guidance, local copy | Skill `shared/tool-use-concepts.md` |
| HTTP error codes | Official guidance, local copy | Skill `shared/error-codes.md` |
| Python client SDK README (usage fields) | Official guidance, local copy | Skill `python/claude-api/README.md` |

Read on 2026-11-19. The skill notes that the API changed shape several times in 2025 and 2026; the executor records the client library version and the API version header on every session.

## Key findings

### The loop

| # | Finding | Confidence |
|---|---|---|
| M1 | Everything goes through `POST /v1/messages`. A tool call ends a response with `stop_reason: "tool_use"`; the caller runs each `tool_use` block and returns every `tool_result` in one user message, matched by `tool_use_id`, with `is_error: true` for a failed call. The loop ends at `end_turn`. | confirmed |
| M2 | Other stop reasons the loop must handle: `max_tokens` (a `tool_use` input may be truncated; do not run it), `refusal` (with `stop_details`; never run that turn's tools), `pause_turn` (a server-tool loop hit its limit; resend to continue). | confirmed |
| M3 | Client tools are caller-defined (name, description, JSON schema, optional `strict: true`). The Anthropic-defined `bash` and text-editor tools are schema-less and also client-executed; the text editor combines `view` with `create`, `str_replace` and `insert`, so it cannot be offered read-only. | confirmed |
| M4 | Server tools run on Anthropic's side and return result blocks in the same response: web search, web fetch (fetches only URLs already in the conversation), code execution, tool search. Availability differs by model and platform (for example no web fetch on Vertex AI). | confirmed |
| M5 | The client SDK has a beta tool runner that drives the loop for caller-defined tools; a manual loop gives full control. | confirmed |
| M6 | One response may hold several `tool_use` blocks (parallel tool use, on by default); `disable_parallel_tool_use` limits it to one. | confirmed |

### Usage, limits and errors

| # | Finding | Confidence |
|---|---|---|
| M7 | Each response reports `usage.input_tokens`, `output_tokens`, `cache_creation_input_tokens` and `cache_read_input_tokens`. No cost figure is returned; cost is tokens times the published price per model. | confirmed |
| M8 | Prompt caching is a prefix match over tools, then system, then messages; a stable tool list and system prompt make repeated turns cheaper. | confirmed |
| M9 | Effort is `output_config.effort` (`low` to `max`; defaults differ by model). On current models thinking is adaptive and some settings return 400 on some models, so request parameters are model-specific. | confirmed |
| M10 | Errors are typed: 400 invalid request, 401 authentication, 402 billing, 403 permission, 404 not found, 413 too large, 429 rate limit (or a spend cap, which carries no `retry-after`), 500 API error, 529 overloaded. The SDK retries 408, 409, 429 and 5xx twice by default and exposes `.type` on errors. | confirmed |
| M11 | The API is stateless: no session id is kept between requests by default, and the caller holds the conversation. Each response has a message id. | confirmed |
| M12 | The same request shape reaches Claude on Amazon Bedrock, Google Vertex AI and Microsoft Foundry through dedicated client classes; model ids differ per platform (for example an `anthropic.` prefix on Bedrock). | confirmed |
| M13 | Credentials resolve from `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, a stored profile or workload identity federation, or from the cloud platform's own credentials. | confirmed |

## Conclusions

1. A Messages API executor must bring its own **agent loop and tool host**: reading, searching, listing, editing and writing files, and running declared commands, all inside the workspace. Web search and fetch can be server tools where the model and platform offer them.
2. Because the engine itself executes every tool, restriction is a property of the engine, not of a third-party binary: a judge session is offered only read tools and the engine runs only those. `restricts_judge_tools`, `enforces_step_tools` and `isolates_user_config` hold by construction, with no probe of a binary (contract tests replace probes).
3. Cost is never reported (M7). The engine's price table gives the estimate ([ADR-0012](../adr/0012-cost-when-executor-reports-tokens-only.adr.md)), and because the engine sees usage after every response, a cost cap and a turn cap can be enforced between responses, which the Antigravity CLI cannot do.
4. The executor has no instruction files, skills, agents or subagents. A workflow that relies on its authoring surface (CLAUDE.md, skills) cannot move a step onto it without bringing that content into the prompt.
5. Failure causes come from typed errors and stop reasons (M2, M10), never from text.
6. It is the lightest executor to run in CI: one Python dependency and an API or cloud credential.

## Open questions

| Question | Owner | How to settle |
|---|---|---|
| Should long sessions use server-side compaction or context editing, both beta, or end at the context window? | Executor implementer | First release ends the session with a model error and records peak context; revisit with measured sessions. |
| Does a judge on this executor grade as well as a judge on Claude Code, given a smaller tool set and no system prompt of Claude Code? | Engine owner | Calibration sets per gate, scored on both judge executors ([LIF](../specs/18-lifecycle-and-evals.spec.md)). |
</content>
</invoke>
<invoke name="Bash">
<parameter name="command">cd /home/user/tempergraph/plugins/tempergraph/docs/research && sed -i '1s/.*/# R-005 Claude Agent SDK as an executor/' R-005-claude-agent-sdk-executor.rsrch.md && head -1 R-005*.md