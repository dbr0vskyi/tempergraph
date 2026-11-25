---
title: Actions and safety
type: component
status: ready-for-implementation
prefix: MAC
adrs: [0003]
---

# Actions and safety

## 1. Overview

What a person can do from the monitor, and the rules that keep the monitor an observer. This spec owns contract M2 (every action that would change a run is a prompt fill the person sends) and contract M3 (the mod offers no tool to a headless session or a subagent). It also lists the mod's settings.

## 2. Contract

### 2.1 Actions

| Action | Where | Does |
|---|---|---|
| Resume with a decision | Pause view, one per decision word | Fills the prompt with the resume line the engine printed (`!tempergraph resume <workflow> <task> --decision <word>`); feedback, when the gate takes it, is left for the person to type after `--feedback` |
| Stop | `x` on a run, or the actions menu | Fills `!tempergraph stop <selector>` (drain); a second choice fills `--now` |
| Ask the run driver | Pause view | Fills `/tempergraph:run …` with the resume context, so the run driver skill walks the person through the pause ([SHL](../../../tempergraph/docs/specs/plugin-shell.spec.md)) |
| Ask Claude about a session | Session view | Fills a prompt naming the session's `raw.jsonl` path and the attempt's gate result, e.g. "Read <path> and explain why the judge of code attempt 1 returned RETRY" |
| Copy | Any id, path or command | `$.ui.copy` |
| Open | A path (desktop, VS Code) | A `file:` link the surface opens |
| Pin, filter | Run list | Session state and `$.store` |

`!` at the start of the prompt runs the line as a shell command in Claude Code when the person presses Enter ([research `claude-code-mods`](../research/claude-code-mods.rsrch.md)). Every filled command is built from values the engine printed (workflow, thread id, decision words) and the mod's constants; nothing a person typed into the pane reaches it.

### 2.2 Model tool

| Setting `model_tool` | Behaviour |
|---|---|
| `off` (default) | The mod registers no tool |
| `interactive` | The mod registers one read-only tool, `runs`, that returns the status rows and, given a label, the run's detail summary; it registers it only in a session that has a drawing surface, and answers `tool.offer` with `isOffered: false` for every loop that carries an agent id or subagent type |

The tool never runs a writing verb and returns no tool input summaries or log text.

### 2.3 Settings (`userConfig`)

| Key | Values | Default |
|---|---|---|
| `scope` | `repo`, `machine` | `repo` |
| `fleet_sink` | a sink name from the engine config, or empty | empty |
| `open_pane` | `auto` (sidebar layouts only), `never` | `auto` |
| `alerts_finished`, `alerts_fleet` | `true`, `false` | `false` |
| `show_tool_inputs`, `show_log_tails` | `true`, `false` | `true` |
| `model_tool` | `off`, `interactive` | `off` |
| `engine_path` | path to the `tempergraph` shim, or empty (the places the monitor looks for the engine: MAC-B5) | empty |

## 3. Behaviours

**MAC-B1 The person sends.** Given a pause with decisions `proceed`, `retry`, `stop`, when the person presses the `retry` action, then the prompt box holds `!tempergraph resume delivery PROJ-12 --decision retry`, nothing has run, and the run is still paused until the person presses Enter.

**MAC-B2 No tool by default.** Given the default settings, when any session, interactive or headless, lists its tools, then no tool of this mod is listed.

**MAC-B3 No tool for a judge.** Given `model_tool = interactive` and an engine judge session on `claude` that loads user plugins against the engine's isolation intent, when its loop starts, then the tool is not offered to it (it has no drawing surface, or it carries an agent id), so no judge's verdict is voided through this mod.

**MAC-B4 Typed text never reaches a command.** Given a person who types into the pane's filter field `; rm -rf ~`, when they then press a stop action, then the filled command holds only the selected run's thread id, and the filter text appears nowhere in it.

**MAC-B5 The engine is looked for in three places, in order.** Given the monitor has not found the engine yet, or the program it found exits 127, when it is to run an engine verb, then it tries the path in the `engine_path` setting (unless MAC-B7 ignores it), then `tempergraph` on PATH, then the shim in the engine home (MAC-B6), and runs the verb, and the verbs after it, through the first program that does not exit 127. A program exits 127 when it does not exist, or when it is the shim of an engine that is not installed ([CLI-B18](../../../tempergraph/docs/specs/engine-cli.spec.md)).

**MAC-B6 The engine home.** Given the monitor looks in the engine home, when `TEMPERGRAPH_HOME` names a folder, then it looks for the shim in that folder's `bin` folder (`bin/tempergraph`), and when the variable is unset or empty, in `~/.tempergraph/bin` (`~/.tempergraph/bin/tempergraph`). The home folder is that of [LOS-B10](../../../tempergraph/docs/specs/local-observability-store.spec.md), and the shim and its Windows wrapper are those of [UPD-B12](../../../tempergraph/docs/specs/engine-update.spec.md) and [WIN-B5](../../../tempergraph/docs/specs/windows-support.spec.md).

**MAC-B7 A setting that is not the shim is ignored.** Given the value of the `engine_path` setting, trimmed of white space at both ends, is anything but an absolute path (one that starts with `/`, or with a drive letter, `:` and `/` or `\`) whose last segment is `tempergraph`, `tempergraph.exe` or `tempergraph.cmd`, when the monitor looks for the engine, then it takes the setting as empty and runs no program the setting names.

## 4. Error conditions

| Condition | Result |
|---|---|
| `$.prompt.fill` reports no composer | The command is copied instead, with a toast saying so |
| The prompt already holds a draft | The fill is appended on a new line (`append` mode); the draft is kept |

## 5. Design notes

- Prompt fills keep the person as the one who acts, give them a chance to edit, and leave a record in the conversation of what was run ([MADR `actions-fill-the-prompt`](../adr/actions-fill-the-prompt.adr.md)).
- The model tool is off by default because a monitor tool registered in every session, headless ones included, can be called by a judge, which voids its verdict and pauses the run. The engine's own judge isolation is the main control ([engine SEC-B3](../../../tempergraph/docs/specs/security.spec.md)); this is the mod's part.
- Release 1 build ([T10 plan](../../../tempergraph/docs/plans/t10-monitor.plan.md)): resume with a decision, stop (drain and `--now`), ask the run driver, ask Claude about a session, and copy are built; each fill is checked token by token against what the engine printed and refused otherwise. Settings are the manifest's `userConfig` fields; Claude Code names fields with letters, digits and `_`, so the dotted names of the design became `alerts_finished`, `show_tool_inputs` and so on. Deviations: `Open` (a `file:` link) is not built; `model_tool = interactive` is accepted and registers nothing yet, so MAC-B2 and MAC-B3 hold for every value; `open_pane = auto` behaves as `never`, because `$.ui.open` gives no way to ask for a sidebar only, and MRV-B5 forbids opening inline on its own; `scope = machine` lists other repositories' runs as read-only cards with no fill; `fleet_sink` must be a sink name (`[a-z0-9-]{1,40}`), and the fleet tab is read only when it is set.
- "Ask Claude about a session" turns the monitor into an entry point for diagnosis without the monitor calling a model itself.

## 6. Acceptance criteria

- [ ] MAC-AC-1 A source-scan test finds no `$.prompt.submit`, `$.command.run` or writing `$.process.run` call in the mod.
- [ ] MAC-AC-2 MAC-B2 and MAC-B3 pass in the plugin test kit with a simulated headless session and a subagent loop.
- [ ] MAC-AC-3 Every action's filled text matches a fixture for each decision kind of [HUM](../../../tempergraph/docs/specs/gate-and-human.spec.md).
- [ ] MAC-AC-4 MAC-B5 passes in a session test run once for each place: every program exits 127 except the one in the `engine_path` setting, then except `tempergraph` on PATH, then except the shim of the engine home; each time the band row shows the runs.
- [ ] MAC-AC-5 MAC-B5 passes in a session test where only the shim of the engine home answers: once it has answered, no later engine verb of the session is run through `tempergraph` or through the path in the setting.
- [ ] MAC-AC-6 MAC-B6 passes in a session test where only the shim of the engine home answers: the band row shows the runs with `TEMPERGRAPH_HOME` set to a folder that holds the shim, and with it unset and the shim in `~/.tempergraph/bin`.
- [ ] MAC-AC-7 MAC-B7 passes in a session test where the `engine_path` setting holds a relative path, then a path ending in another name: no program the setting names is run.

## Open questions

| Question | Owner |
|---|---|
| Probe P-MOD-1: how a mod tells, at `session.start`, that the session is headless (`-p`, SDK). Default taken: the 2.1.329 API types give `isInteractive` on `session.start`, and the mod registers nothing when it is false; a live check on the owner's machine is pending ([research `claude-code-mods`](../research/claude-code-mods.rsrch.md)). | Monitor implementer |

## References

[MDD](drill-down.spec.md) · [RCT](../../../tempergraph/docs/specs/run-control.spec.md) · [DUR](../../../tempergraph/docs/specs/durability-and-resume.spec.md) · [research `claude-code-mods`](../research/claude-code-mods.rsrch.md)
