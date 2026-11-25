# MADR-0003 Every action fills the prompt; the person sends it; no model tool by default

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

From a view a person wants to resume a paused run, stop a runaway one or ask about a failure. tempergraph's rules say only a person decides a pause (engine OVR-B8). A monitor tool registered in every session, headless ones included, can be called by a judge; the guard then discards a complete verdict and the run pauses. A mod can fill the prompt without sending (`$.prompt.fill`), and `!` runs a line as a shell command ([R-001](../research/R-001-claude-code-mods.rsrch.md)).

## Decision

We will make every changing action a prompt fill with the exact command, sent only by the person; we will register no model tool unless the person opts in, and then only in sessions with a drawing surface and never for a subagent loop ([MAC](../specs/actions-and-safety.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Prompt fills, tool opt-in and interactive only (chosen) | The person acts and can edit; a record stays in the conversation; no headless reach | One extra key press |
| Buttons that run verbs directly | One press | A mod answering a pause; nothing in the conversation shows it happened |
| A model tool in every session | Claude can check runs on its own | Can reach a judge; costs a voided verdict |
| No actions at all | Simplest | The person copies commands by hand |

## Decision rationale

| Criterion | Prompt fills | Direct run | Tool everywhere | None |
|---|---|---|---|---|
| Person decides (C6) | yes | weak | n/a | yes |
| Cannot reach a headless judge | yes | yes | no | yes |
| Leaves a record | yes | no | yes | no |
| Effort for the person | one Enter | one press | none | copy and paste |

## Consequences

- Positive: the monitor is safe to leave on during runs.
- Negative: Claude cannot read run state through the mod unless the person opts in. Mitigation: the run driver skill reads `status` itself.
- Risk: headless detection is unconfirmed (P-MOD-1). Mitigation: the opted-in tool registers only after the person first opens the pane in that session.

## Assumptions

- The `!` prefix runs a shell line on every surface the monitor targets.

## Revisit when

Claude Code documents that a mod's tools never reach `-p`, SDK or subagent sessions.
