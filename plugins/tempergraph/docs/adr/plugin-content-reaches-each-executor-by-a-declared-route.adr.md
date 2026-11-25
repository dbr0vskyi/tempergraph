# Plugin content reaches each executor by a declared route or the step is refused; workflow plugins ship no hooks, MCP servers or binaries

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

A workflow package is a Claude plugin, and four executors must run it. The engine renders every prompt itself ([PRM](../specs/prompt-rendering.spec.md)). Skills and agents load into `claude` by `--plugin-dir` and into `agent-sdk` by its `plugins` option; the Messages API runs only uploaded skills under code execution; Antigravity reads skills from its own folders ([research `workflow-packages-authoring-and-good-outcomes`](../research/workflow-packages-authoring-and-good-outcomes.rsrch.md) A8 to A10). [ADR `portable-authoring-surface`](portable-authoring-surface.adr.md) leaves per-executor forms to the workflow and adds nothing to instruction files; a `CLAUDE.md` at a plugin root is not read (research `workflow-packages-authoring-and-good-outcomes` A2).

## Decision

We will route plugin content per executor as [PKG-B23, PKG-B24](../specs/workflow-package.spec.md) lists, and refuse before spend a step whose declared skill or agent has no route on its executor (C15). Judges never load the workflow plugin. A workflow package ships no hooks, MCP servers, `bin/`, session settings or root instruction files; rules a step must follow are in its prompt or in a skill it declares. A second form of a skill for another executor is named in `tempergraph.json` `surfaces` and used once that executor's probe confirms the route.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Declared route or refusal; no hooks, MCP, bin (chosen) | What runs in a step session is what the step declares; same refusal on every executor | Workflows cannot ship their own MCP server |
| Load the whole plugin, hooks included | Full Claude Code power | A hook can change tool calls outside the declaration; judges at risk |
| Translate skills for every executor | One source | Wrong translations; ADR `portable-authoring-surface` rejected it |
| Upload skills to the Skills API for `messages-api` | Skills there too | Only under code execution, no network (research `workflow-packages-authoring-and-good-outcomes` A9); deferred |

## Decision rationale

| Criterion | Route or refuse | Whole plugin | Translate |
|---|---|---|---|
| Declared tools are the whole surface | yes | no | yes |
| Judge independence kept | yes | at risk | yes |
| Portable refusal before spend | yes | no | partly |

## Consequences

- Positive: the tool audit compares grant, need and use with nothing hidden in plugin hooks.
- Negative: a workflow needing an MCP server relies on the machine's configuration and declares the tools.
- Risk: `--plugin-dir` behaves differently headless. Mitigation: probe P-CC-9 before release 1 relies on workflow skills.

## Assumptions

- Workflow skills on `antigravity` and `messages-api` wait for their releases (release 3).

## Revisit when

The Messages API or Antigravity loads plugin folders as Claude Code does.
