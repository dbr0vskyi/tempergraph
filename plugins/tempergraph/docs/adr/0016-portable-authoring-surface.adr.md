# ADR-0016 The engine adds nothing to instruction files; workflows carry per-executor authoring surfaces

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Claude Code reads `CLAUDE.md`, skills under `.claude/skills`, agents and plugin content ([R-001](../research/R-001-claude-code-cli-headless.rsrch.md)). Antigravity reads `GEMINI.md` and `AGENTS.md`, its own skills and rules under `.agents` or `~/.gemini` ([R-002](../research/R-002-antigravity-cli-headless.rsrch.md)). A workflow may need the same rules on both. The engine could translate one surface into the other, write files into the workspace, or leave the surface to the workflow.

## Decision

We will not write or translate instruction files. Each step's prompt is rendered by the engine ([PRM](../specs/04-prompt-rendering.spec.md)) and carries what the step must know. Rules that must hold on both executors live in the workflow's own authoring surface, shipped once per executor form it supports (for example one `AGENTS.md` that Antigravity reads and a `CLAUDE.md` that imports it). The plugin shell documents the pattern ([SHL](../specs/19-plugin-shell.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Engine adds nothing; workflows carry both forms (chosen) | No hidden writes to the workspace; each CLI used as designed | Authors maintain two small forms |
| Engine translates one surface into the other | One source | Formats and semantics differ (skills, frontmatter); silent wrong translations |
| Engine writes instruction files into the worktree per session | Exact control | Changes the repository under work; collides with the project's own files; the judge sees engine text as project text |

## Decision rationale

| Criterion | Nothing added | Translate | Write per session |
|---|---|---|---|
| Workspace untouched by the engine | yes | no | no |
| Rules identical on both executors | by convention | by tool | yes |
| Risk of wrong translation | none | high | low |
| Author effort | medium | low | low |

## Consequences

- Positive: the workspace a judge reads is exactly the project plus the step's work.
- Negative: rules can drift between the two forms. Mitigation: the import pattern keeps one source where both CLIs allow it.
- Risk: a CLI changes which files it reads. Mitigation: listed in the conformance fixtures per CLI version.

## Revisit when

Both CLIs read one shared instruction format (for example `AGENTS.md`) with the same semantics.
