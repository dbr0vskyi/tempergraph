# R-001 Claude Code mods: what a mod can draw, read and run

## Problem statement

The monitor is to be a "Claude Mod". This note records what a Claude Code mod is and which parts of its API the monitor's design relies on: where it can draw, how it redraws, what it can read and run, where it keeps state, and how its tools reach (or do not reach) headless sessions. A monitor tool that reaches a headless session can be called by an engine judge there, so tool reach matters as much as drawing.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Claude Code docs, mods interface | Vendor documentation | https://code.claude.com/docs/en/plugins/mods/interface.md |
| Claude Code docs, mods reference | Vendor documentation | https://code.claude.com/docs/en/plugins/mods/reference |
| The plugin-authoring skill bundled with Claude Code 2.1.329, its `reference.md` and its generated `claude-code.d.ts` (about 27 600 lines) | Vendor reference shipped with the build | Read in the design session, 2026-11-19 |

## Key findings

| # | Finding | Confidence |
|---|---|---|
| F1 | A mod is a plugin folder with `.claude-plugin/plugin.json`, `hooks/hooks.json` naming one hooks module, and that module exporting `register(on, options)`. Hooks have the shape `($, e, next)`; `$` is the engine interface; the module has no DOM and no Node APIs. It ships through a plugin marketplace like any plugin. | confirmed |
| F2 | Draw sites: a **Pane** (`$.ui.open({id, title})` drawn by a `ui.render` hook on `Pane`), the **band** above the prompt (`AbovePrompt`, one row per plugin), tool-use rows, a context menu, and the status line (`$.ui.status`). Toasts (`$.ui.toast`, about 4 s) and native notifications (`$.ui.notify`, resolving sent or not with a reason). | confirmed |
| F3 | Surfaces: `terminal`, `desktop`, `vscode`; the build's types also name `mobile`, the public reference table does not. Element tables differ per surface (`Raster`, `Image` terminal-only; `Svg` desktop and VS Code; no `Client` in VS Code). `Progress` exists on every surface. | confirmed (three); supported (mobile) |
| F4 | A pane's placement is `dock` (sidebar in a wide fullscreen terminal), `inline` (framed region above the prompt) or, on desktop, `widget` (a minimized glance). A pane opened without a person's action appears only from about 144 columns (110 once opened before). | confirmed |
| F5 | Claude Code does not poll a mod: the mod redraws by writing session state (`$.state`, readers redraw) or `$.ui.invalidate`; visible pane and band redraw at most 30 times a second. Timers: `$.clock.every`, `after`, `sleep`, started from `session.start`. | confirmed |
| F6 | `$.fs` reads (with byte offset and length), lists and stats; 4 MiB per file read. `$.process.run` and `spawn` run a host command by argv; default timeout 30 s, maximum 10 min. | confirmed |
| F7 | `$.state` is per session and survives a module reload; `$.store` is shared by every session on the machine, saved as JSON under `~/.claude/plugins/store/`, 4 MiB total, get-then-set not atomic (one key per item recommended). | confirmed |
| F8 | `$.prompt.fill({text, mode})` writes the prompt box without sending; `$.ui.copy` copies to the surface's clipboard. | confirmed |
| F9 | `$.tool.register` gives the model a tool named `mcp__<plugin>__<name>`; a `tool.offer` hook can keep a tool from one loop's model (`isOffered: false`), and the hook input carries `agentId` and `subagentType` for subagent loops. Whether a mod's tools reach a headless `-p` or SDK session is not stated in the public pages; the build's reference says `ui.notify` reports `no-surface` in `-p`, SDK and desktop-hosted sessions. | supported |
| F10 | `$.ui.view({agentId})` can put a subagent's transcript in the main view, only on a person's action. tempergraph sessions are separate processes, not subagents of the person's session, so this does not apply to them. | confirmed |
| F11 | The API is early access and moves between builds; the declaration file of the running build is the authority. Many features need Claude Code 2.1.289 to 2.1.300 or later. | confirmed |
| F12 | A line typed into the prompt starting with `!` runs as a shell command in Claude Code. | supported (known product behaviour; not in the two pages read) |

## Conclusions

1. A mod can do everything the monitor needs: a pane with levels and keys, a band row, a status entry, toasts and notifications, file reads with offsets, host commands for read-only verbs and `ps`, session and cross-session state, and prompt fills.
2. The monitor must redraw from its own timers and state; reads belong in timers, never in a `ui.render` hook.
3. The monitor's model tool must be opt-in and refused to subagent loops (F9), because reach into headless sessions is not documented.
4. Drawing differs per surface; one tree using only elements common to terminal, desktop and VS Code, with `Progress` for bars, meets contract M5.

## Probes before building

| Id | Question | Blocks |
|---|---|---|
| P-MOD-1 | How does a mod tell at `session.start` that the session is headless (`-p`, SDK), so it registers no tool there? Answered from the API types of Claude Code 2.1.329 (2026-11-20): `session.start`'s input carries `isInteractive`, false under `-p` and the SDK. The monitor starts no timer and registers no command when it is false; a live check on a person's machine is still pending. | [MAC §2.2](../specs/05-actions-and-safety.spec.md) |
| P-MOD-2 | Does `$.fs` read paths outside the session's working directory (other state roots, `~/.tempergraph/`) on every surface without a permission prompt? | [MDS](../specs/01-data-sources.spec.md) |
| P-MOD-3 | Does `$.process.run` inherit the person's PATH, so the `tempergraph` shim is found, on desktop and VS Code? | [MDS](../specs/01-data-sources.spec.md) |
| P-MOD-4 | Does the release 1 mod load, draw and poll as its session tests say on a person's machine (terminal and desktop), against a real engine run? The session tests run under `claude plugin test` with the engine answered by fixtures; nothing has been run against a live Claude Code session yet. | [T10 plan](../../../tempergraph/docs/plans/t10-monitor.plan.md) |

## Open questions

| Question | Owner |
|---|---|
| Is the `mobile` surface drawn for a pane today? The build's types say so; the public page does not. | Monitor implementer |
