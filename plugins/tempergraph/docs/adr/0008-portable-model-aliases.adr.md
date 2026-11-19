# ADR-0008 Workflows name portable model tiers and tool capabilities; executors bind them

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The two executors use different model families (Claude: `haiku`, `sonnet`, `opus`, `fable`; Antigravity: Gemini slugs listed per account by `agy models`) and different tool names (`Read`, `Bash` against `view_file`, `run_command`). Deployment ids differ per account and region (Bedrock inference profiles). Workflows are shared across machines and should move a step between executors without a rewrite.

## Decision

We will let workflow data name models as `inherit`, an engine-neutral tier (`small`, `medium`, `large`) or an executor-qualified alias (`claude:opus`, `antigravity:<name>`), and tools as engine-neutral capabilities (`read`, `search`, `list`, `edit`, `write`, `shell`, `web_fetch`, `web_search`, `subagent`, `mcp:<server>/<tool>`). Each executor binds tiers and aliases through a per-machine binding table and maps capabilities through a constant tool map.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Neutral tiers and capabilities, executor-qualified escape hatch (chosen) | Portable workflows; one field moves a step | Tiers are coarse; "large" means different strengths on each family |
| Executor-native names only | Exact | A workflow is tied to one executor; moving a step edits prompts, tools and models |
| Model ids in workflow data | Exact | Breaks across machines and gateways; ids leak into argv as typed text |

## Decision rationale

| Criterion | Chosen | Native names | Ids |
|---|---|---|---|
| Workflow portable across executors | yes | no | no |
| Workflow portable across machines | yes | yes | no |
| Precise model choice possible | yes (qualified alias) | yes | yes |
| Typed text reaches argv | no | no | risk |

## Consequences

- Positive: the same workflow validates against both executors ([WFM-B3](../specs/02-workflow-model.spec.md)).
- Negative: a tier hides a real capability difference between families. Mitigation: a step that needs a specific model uses a qualified alias, and validation warns when a qualified alias is used where a tier would do.
- Risk: the tool maps drift with CLI releases. Mitigation: conformance fixtures per CLI version; an unknown tool name in a stream is a self-improvement cause attributed to the executor.

## Revisit when

A third executor needs a capability the list cannot express.
