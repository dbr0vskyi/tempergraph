# The monitor is a Claude Code mod that only observes

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The plugin was scaffolded as "a Claude Mod showing progress of tempergraph runs". The owner wants to watch and enter runs from where they work: without a monitor, a gate can wait for most of a run while nobody knows. Claude Code mods can draw panes, a band, status entries, toasts and notifications, read files and run host commands ([research `claude-code-mods`](../research/claude-code-mods.rsrch.md)).

## Decision

We will build the monitor as a Claude Code mod that reads engine documents and runs read-only engine verbs, and changes nothing itself (contracts M1 and M2, [MOV](../specs/overview.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| A Claude Code mod, observer only (chosen) | Lives where the person works; panes, band and notifications built in; ships through the same marketplace | API is early access; draws only inside Claude Code |
| A terminal UI (`tempergraph top`) | Works without Claude Code | A second window; no notifications into the conversation; another program to maintain |
| A local web dashboard | Rich graphics | A server to run; a browser tab nobody looks at |
| A mod that also drives runs | One place for everything | Duplicates the run driver skill; risks a mod answering a pause |

## Decision rationale

| Criterion | Mod observer | TUI | Web | Mod driver |
|---|---|---|---|---|
| Seen without switching windows | yes | no | no | yes |
| Notifies a person who looks away | yes | no | partly | yes |
| Cannot change a run | yes | yes | yes | no |
| New moving parts | none | one | a server | none |

## Consequences

- Positive: one install from the marketplace; the run driver skill and the monitor sit side by side in one session.
- Negative: nothing outside Claude Code. Mitigation: every document the monitor reads is also printed by a CLI verb (`status`, `events`, `logs`, `stats`), so a shell user loses nothing but the drawing.
- Risk: the mods API changes. Mitigation: every API fact relied on is in research `claude-code-mods` with its confidence and a probe list.

## Assumptions

- "Claude Mod" in the manifest means a Claude Code mod in the sense of research `claude-code-mods`, not another product.

## Revisit when

The person's main surface for tempergraph is not Claude Code (for example CI only, or the Antigravity shell).
