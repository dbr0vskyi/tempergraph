# Can the monitor give an at-a-glance home view of everything tempergraph is doing, and keep its drill-down?

## Problem statement

The owner saw another tool's terminal dashboard and liked the perspective it gives: one screen, dense, read in a few seconds, with small charts beside the figures. The owner asked whether the monitor can give tempergraph something in that spirit, under three conditions: it must not be the same (not the same fields, values or layout), it must stay interactive, and a person must still be able to go deeper into a run, a step and a session. tempergraph has much more to show than runs and cost: gates, judges, retries and their causes, supervision and babysitting, schedules, batches and the self-improvement loop.

This note answers four questions, so that a spec change does not rest on a guess:

1. What does the monitor show today, and where does an overview fall short?
2. Which of tempergraph's own data gives the best overview, and can the monitor read it under its read-only rule?
3. How is it drawn: inside the Claude Code mod, or as a separate terminal program, and at what dependency cost?
4. How does a person go from the overview down to a session?

The other tool is used only as a reference for information density. It is not named in this repository, and nothing below copies its fields or layout.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| The monitor's design set | specs, decision records, research | `docs/specs/*.spec.md`, `docs/adr/*.adr.md`, [research `claude-code-mods`](claude-code-mods.rsrch.md), [research `dynamic-workflows-view`](dynamic-workflows-view.rsrch.md) |
| The monitor's code | code | `hooks/register.tsx`, `hooks/lib/sources.ts`, `hooks/lib/fleet.ts`, `types/index.d.ts` |
| Engine documents the monitor reads or could read | specs | [DUR-B11](../../../tempergraph/docs/specs/durability-and-resume.spec.md), [RDD](../../../tempergraph/docs/specs/run-detail-document.spec.md), [CST-B9, CST-B14, CST-B16](../../../tempergraph/docs/specs/central-run-stats.spec.md), [CLI-B6, CLI-B20](../../../tempergraph/docs/specs/engine-cli.spec.md), [SCH](../../../tempergraph/docs/specs/schedules.spec.md), [JCL-B18](../../../tempergraph/docs/specs/judge-calibration.spec.md), [SIL-B22](../../../tempergraph/docs/specs/loop-summary-and-review-retries.spec.md), [SUP](../../../tempergraph/docs/specs/supervision-metrics.spec.md) |
| The engine's stats reader | code | `plugins/tempergraph/engine/src/tempergraph/observe/rows.py` (`BY`, `totals`, the run row builder) |
| The engine's CLI | code | `plugins/tempergraph/engine/src/tempergraph/cli/main.py`, `observe_cli.py`, `schedule_cli.py` |
| The mods API of Claude Code 2.1.332 | vendor reference shipped with the build | the `claude-code.d.ts` of the bundled plugin-authoring skill: the element table per surface, `ProgressProps`, `RasterProps` |
| Wheels of five Python terminal UI libraries and their dependencies, as `pip download --only-binary=:all:` fetched them on 2026-11-26 | measurement | PyPI |
| A screenshot of another tool's terminal dashboard, shared by the owner | image | the project thread; not stored in the repository |
| Open issues labelled `area: monitor` | issues | #39, #44, #141, #142, #145 |

## Key findings

### F1 The monitor has no overview level; its first screen is a list of runs `confirmed`

The pane opens on the run list (`MonitorView.level = 'runs'`, `types/index.d.ts`; [run-view](../specs/run-view.spec.md) §2.3): one row per run with mark, label, progress, attempt, last verdict, elapsed, cost, executors and supervision, grouped by origin. Figures across runs exist only in two places a person must open: the cost tab of one run and the fleet tab (`m`), which shows live runs and the month by machine and by workflow ([cost-and-fleet](../specs/cost-and-fleet.spec.md) §2.2). The band row above the prompt counts runs (`tg 4 ▶ 2 ⏸ 1 ✗ · $11.20 est`, [band-status-and-alerts](../specs/band-status-and-alerts.spec.md) §2.2). Nothing answers "is quality holding up", "are runs going on alone", "what fires next" or "what did the loop find" without opening a run.

### F2 The drill-down below the run list is complete and needs no change `confirmed`

Runs → run → unit → attempt (step, check, judge, gate tabs) → session (now, calls, processes, log, info), with a breadcrumb and a back button, is specified and built ([MOV-B1](../specs/overview.spec.md), [drill-down](../specs/drill-down.spec.md), `hooks/register.tsx`). An overview only has to land a person on the right row of a level that already exists.

### F3 The monitor draws with three elements and reads three verbs `confirmed`

`hooks/register.tsx` uses `Box`, `Text` and `Button` only; no `Progress`, `Raster` or `Svg`. `hooks/lib/sources.ts` allows `status`, `events` and `stats` (`READ_ONLY_VERBS`) and refuses every argv whose verb is in `WRITING_VERBS`, which lists `schedule`, `improve`, `supervision` and others as whole verbs, so read-only subcommands such as `schedule list` are refused too. `evals`, `labels` and `attention` are in neither list and are not called.

### F4 The data for a rich overview exists in engine documents today `confirmed`

| Question a person asks at a glance | Engine source | Read by the monitor today |
|---|---|---|
| Does anything wait on me, and for how long? | `pending_gates` in status rows ([DUR-B11](../../../tempergraph/docs/specs/durability-and-resume.spec.md)); `attention --json` ([CLI-B6](../../../tempergraph/docs/specs/engine-cli.spec.md)) adds orchestration and schedule items and, with CLI-B20, loop summaries | status: yes; attention: no |
| Is each live run moving, and where? | status rows (`attempt_in_flight`, `alive`), the detail document's node strip and `live` block ([RDD](../../../tempergraph/docs/specs/run-detail-document.spec.md)) | yes |
| Is quality holding? | run rows: `repeats` by cause, `gate_verdicts` counts, `units_run`, `exit` ([CST-B9](../../../tempergraph/docs/specs/central-run-stats.spec.md)); judge met/total and confidence per attempt (RDD); gate acceptance state `accepted`, `below_bar`, `stale`, `contradicted` from `evals bar --json` ([JCL-B18](../../../tempergraph/docs/specs/judge-calibration.spec.md)) | rows only through `stats` totals, which do not carry these fields (F5); `evals bar`: no |
| Do runs go on alone, or are they babysat? | run rows: `level`, `level_by`, `touches_undesigned`, `touches_by_decider`, `agent_own_rescues`, `person_wait_s` ([SUP](../../../tempergraph/docs/specs/supervision-metrics.spec.md)); supervision cost rows ([SCO](../../../tempergraph/docs/specs/supervision-cost.spec.md)) | per run in the run list and cost tab; not across runs |
| What does it cost, honestly? | reported and estimated apart with completeness (`totals` in `rows.py`), projection median and p90 per workflow (CST-B15), cap ETA per live run (`health.cap_eta_min`) | yes |
| What happens next without me? | `schedule list --json`: next slot, last fire, live runs, failures, period spend per schedule ([SCH](../../../tempergraph/docs/specs/schedules.spec.md), "writing nothing and starting no process"); batch children are status rows with `origin: batch` | schedules: no; batch: rows only |
| What did the loop learn? | `loop_summary` (`recorded`, `filed`, `top[]`) ([SIL-B22](../../../tempergraph/docs/specs/loop-summary-and-review-retries.spec.md)), surfaced by `attention` (CLI-B20) | no |
| Other machines | `stats --live` heartbeats, month rollup (CST-B16) | yes, in the fleet tab |

### F5 The stats reader totals money and exits, not quality or autonomy, and has no day grouping `confirmed`

`totals()` in `rows.py` returns `runs`, `threads`, `reported_usd`, `estimated_usd`, `completeness`, `lower_bound` and `exits`. The run rows hold `repeats`, `gate_verdicts`, `person_wait_s`, `level` and `touches_undesigned`, but no reader adds them up. `BY` offers `month` and no `day` or `hour`, so a chart of the last seven days needs seven `stats --since` calls or an engine change. `escapes` is written `None` in local rows (`rows.py` line 235), so an escape count cannot be shown yet.

### F6 `attention` is not strictly read-only `confirmed`

CLI-B6 says `attention` "create[s] nothing but the hand-off of a lost runner" ([SIL-B29](../../../tempergraph/docs/specs/runs-without-a-final-exit.spec.md)). The monitor's contract M1 says it never writes under a state root ([data-sources](../specs/data-sources.spec.md)). The monitor can build "needs you" from status rows alone (it does today) and add schedule items from `schedule list`; it cannot call `attention` until the engine offers a form that writes nothing.

### F7 A mod can draw small charts on every surface, and denser ones per surface `confirmed`

In Claude Code 2.1.332 every surface has `Box`, `Text`, `Button`, `Link`, `Markdown` and `Progress`. The terminal alone has `Raster`, a cell grid of up to 512 × 256 cells, each a glyph with a foreground and background colour, repainted in place by `$.ui.blit`; desktop, VS Code and mobile have `Svg` instead. So a strip of glyphs in `Text` (block elements `▁▂▃▄▅▆▇█`, or one mark per run) draws everywhere, which contract M5 asks for, while `Raster` and `Svg` are the richer forms of the same tree. Redraws are capped at 30 a second ([research `claude-code-mods`](claude-code-mods.rsrch.md) F5), far above a 2 s poll.

### F8 Room is the hard limit, not the elements `confirmed`

A pane opened unasked docks only from about 144 columns; below that it is drawn inline above the prompt ([research `claude-code-mods`](claude-code-mods.rsrch.md) F4, [MRV-B5](../specs/run-view.spec.md)). An overview must read well at 80 columns inline and may use a second column only when docked wide. `Button` hotkeys are one letter or digit and `Esc` belongs to the surface (run-view design notes), so tiles are reached by digits or letters, not by arbitrary keys.

### F9 A separate terminal program would add the engine's first UI dependency `confirmed`

The engine depends on `langgraph`, `langgraph-checkpoint-sqlite` and `tzdata` (`pyproject.toml`). Measured wheels with their own dependencies, 2026-11-26:

| Library | Wheels pulled | Size | Interactive widgets | Notes |
|---|---|---|---|---|
| `rich` | 4 (`rich`, `markdown-it-py`, `mdurl`, `pygments`) | 1.7 MB | no: live rendering, tables, bars, no input | enough for a refreshing, non-interactive watch |
| `textual` | 9 (`rich` and its four, `mdit-py-plugins`, `linkify-it-py`, `platformdirs`, `typing-extensions`) | 2.6 MB | yes: focus, keys, mouse, layout, scrolling | the full application framework; fastest to build tabs and drill-down |
| `prompt_toolkit` | 2 (`wcwidth`) | 1.2 MB | yes, lower level | layout and keys by hand |
| `urwid` | 2 (`wcwidth`) | 1.6 MB | yes, widget tree | older API; Windows support is newer |
| `blessed` | 3 (`jinxed`, `wcwidth`) | 1.1 MB | no widgets: terminal primitives | everything drawn by hand |
| `curses` | 0 (standard library) | 0 | primitives | not shipped with CPython on Windows, a platform release 2 lists ([engine research `running-on-windows`](../../../tempergraph/docs/research/running-on-windows.rsrch.md)) |

A mod costs no dependency at all: the drawing is Claude Code's.

### F10 A program outside Claude Code would duplicate what the mod already owns `inferred`

The monitor was chosen as a mod because the person already works in Claude Code ([MADR `a-claude-code-mod-that-observes`](../adr/a-claude-code-mod-that-observes.adr.md)). A separate program would need its own copy of the sources layer, the levels, the cost honesty rules (M4) and the alerts, and would be tested apart. Its one gain is reach: a terminal over SSH, a machine without Claude Code, or a screen left on beside the work. Whether that reach is wanted is the owner's call (Open questions).

### F11 What makes the reference dense, and what tempergraph must not lose `inferred`

The reference reaches its density with four devices: a single screen with no navigation, figures grouped into a few boxed tiles, a tiny chart next to every figure, and lists where each row carries an inline bar and a relative time. Those devices are generic and are what this note borrows. Its fields, its tile set, its list sections and their order are not borrowed. Two of its habits conflict with tempergraph's rules: a total token figure across executors hides that some executors do not report tokens, and a bare money figure loses the `est`, `rep` and `≥` marks contract M4 requires. A tempergraph overview leads with what waits on a person and with whether gates are passing, because those are the figures only tempergraph has.

## Conclusions

1. An overview fits the existing design as a new top level of the one pane, above the run list, not as a second pane: [MADR `one-pane-many-levels`](../adr/one-pane-many-levels.adr.md) holds, and every tile lands on a level that exists (F1, F2).
2. The overview is best built from seven questions in this order: needs you, moving, gates, alone, spend, next, loop (F4). Tokens are left to the cost tab, where they sit per executor and model.
3. Four of the seven read data the monitor already polls. Gates, alone and loop need an engine reader that totals `repeats`, `gate_verdicts`, `level`, `touches_undesigned` and `person_wait_s` and groups by day (F5); next needs `schedule list --json` allowed by subcommand (F3); calibration state needs `evals bar --json` (F4); attention needs a form that writes nothing (F6).
4. Drawing stays inside the mod with `Text` glyph strips everywhere and `Progress` for bars, at no dependency cost; `Raster` (terminal) and `Svg` (desktop) can replace a strip later as the richer form of the same element (F7, F9).
5. A separate terminal program is not needed for the overview; if the owner wants reach outside Claude Code, `textual` as an optional extra of the engine is the cheapest path to keys and drill-down (F9, F10).

### Options

| Option | What | Cost | Verdict |
|---|---|---|---|
| A. Home level in the mod, glyph strips | A new `home` level drawn with `Box`, `Text`, `Button`, `Progress`; strips of glyphs for history | No dependency; engine reader changes of conclusion 3 | Recommended |
| B. A, plus `Raster` and `Svg` charts | Same level; on the terminal a `Raster` per chart, on desktop an `Svg`, the glyph strip as the plain form | More code per surface; tests per surface | Later, for one or two charts once A is used |
| C. `tempergraph top` in the engine with `textual` | A full-screen program reading the same documents | 9 wheels, 2.6 MB as an optional extra `[tui]`; a second UI to keep in step | Only if the owner wants reach outside Claude Code |
| D. `tempergraph status --watch` with `rich` | A refreshing, non-interactive summary in a shell | 4 wheels, 1.7 MB; no drill-down | Rejected: fails the owner's interactivity condition |

### Sketch 1: Home, inline at 80 columns

Original layout: a "needs you" box first, a "moving" list where each run is a rail of its plan's units, then four question tiles in one row and a loop line. Every number carries `est`, `rep` or `≥` where M4 asks.

```text
tempergraph · this repo · live 2s                        h home · r runs · m fleet
╭ needs you ──────────────────────────────────────────────────────────────────╮
│ ⏸ 41m docs-sync · plan · human gate "Approve the plan?"          1 open     │
│ ⏸  6m schedule nightly-deps paused after 3 failures              2 open     │
╰─────────────────────────────────────────────────────────────────────────────╯
moving
 ▶ auth-fix    ✓✓▶··  code   S C [J] G  a2 ↻ 4/6 0.70     14m   $2.40 est
 ▶ api-bump    ✓▶···  plan  [S] C  J  G  a1                3m   $0.31 est
 ▶ batch q7    items ✓✓▶▶· · 2 live · 1 queued                21m   $4.90 est ≥

 3 gates · 7d          4 alone · 7d          5 spend · today       6 next
 ✓✓↻✓↩✓✓✗✓↻✓✓          obs ▮▮▮▮▮▮ 9          $18.40 est ≥          08:00 nightly-deps
 first try 71%         appr ▮▮▮▮ 4           $6.10 rep (3/7)       Mon release-notes
 retry: tests 5 lint 2 steer ▮▮ 2            cap: auth-fix 22m     2 more this week
 back: plan 3          0.6 unplanned/run     p90 feature $7.90
 judges 0.81 · 1 stale person wait 1h12m

 7 loop · 14 found · 2 filed · top: prompt in plan 0.70
```

The gate strip draws one glyph per finished run, newest right: `✓` passed every gate first time, `↻` retried, `↩` sent back to an earlier unit, `✗` failed. The alone tile counts runs by supervision level. The run rail draws one cell per planned unit with the node in flight bracketed.

### Sketch 2: Home and preview, docked from 144 columns

Original layout: two columns. The left keeps Sketch 1's first column (needs you, moving, the tiles stacked). The right is a preview of whatever is selected on the left, so a person reads one level down without leaving home; Enter opens that level for real.

```text
tempergraph · machine · live 2s                                 │ auth-fix · feature 0.4 · code · attempt 2
╭ needs you ─────────────────────────────────────────────────╮   │ touches  A·person  S·agent
│ ⏸ 41m docs-sync · plan · "Approve the plan?"      1 open   │   │ 12:04 gate plan PROCEED (6/6, 0.85)
╰────────────────────────────────────────────────────────────╯   │ 12:19 code attempt 1 RETRY: c3 tests fail
moving                                                          │
›▶ auth-fix    ✓✓▶··  code  S C [J] G  a2 ↻  14m  $2.40 est    │  ✓ triage    S C J G   ▇            1m
 ▶ api-bump    ✓▶···  plan [S] C J G   a1     3m  $0.31 est    │  ✓ plan      S C J G   ▇▇▇          6m
                                                                │  ▶ code      S C J G   ▇▇▇▇▇▇  a2 ↻ 7m
gates 7d   ✓✓↻✓↩✓✓✗✓↻✓✓  first try 71% · judges 0.81          │  · review    – – – –
alone 7d   obs 9 · appr 4 · steer 2 · 0.6 unplanned/run         │  · deliver   – – – –
spend      $18.40 est ≥ · $6.10 rep (3/7) · cap 22m             │
next       08:00 nightly-deps · Mon release-notes               │ judge now: 4/6 · 0.70 · blockers c3 c5
loop       14 found · 2 filed                                   │ Enter run view · g gate · c cost
```

### Drill-down from home

| Pressed on home | Lands on |
|---|---|
| A "needs you" row | The pause view of that run ([drill-down](../specs/drill-down.spec.md) §2.3), or the schedule's card for a paused schedule |
| A "moving" row | The run view at the unit in flight; Enter again walks unit → attempt → session as today |
| A cell of a run rail | The unit view of that unit |
| The gates tile, or one glyph of its strip | The run list filtered to runs with a repeat or a send-back in the window, or that run's run view |
| The alone tile | The run list filtered by supervision level, sorted by unplanned touches |
| The spend tile | The cost tab of the run nearest its cap, or the fleet month when nothing is live |
| The next tile | A read-only card of the schedule: sentence, next slots, last fires, failures, period spend |
| The loop line | A card of the latest loop summaries, each linking to its run |

Digits `1` to `7` pick a section, `h` returns home from any level, and the breadcrumb starts at `Home`.

### Recommendation

Build option A. Order of work:

1. Engine: a stats total for quality and autonomy (`repeats` by cause, `gate_verdicts`, supervision level counts, unplanned touches per run, person wait) and a `--by day` grouping, read-only and model-free like the rest of `stats` (F5).
2. Engine: a form of `attention --json` that writes nothing, or a statement in CLI-B6 that observers derive needs-you from status rows (F6).
3. Monitor: allow read-only subcommands by name (`schedule list --json`, `evals bar --json`) instead of refusing whole verbs; spec change in [data-sources](../specs/data-sources.spec.md) first (F3).
4. Monitor: the home level, spec first (a new monitor spec for the home view, and a row in [run-view](../specs/run-view.spec.md) for the new level and the `h` key), then code and UI tests from fixtures, glyph strips only.
5. Monitor, later: `Raster` and `Svg` charts for the gate strip and the spend tile (option B).
6. Only on the owner's word: `tempergraph top` with `textual` as an optional extra (option C).

## Open questions

| Question | Default until answered |
|---|---|
| Does the owner want the overview outside Claude Code too (SSH, a machine without Claude Code, a screen left on)? | No: the mod only (option A) |
| Should home replace the run list as the pane's first screen, or open with `h`? | Home is the first screen; the run list is one key away |
| Which window do the gate and alone tiles cover: today, 7 days or the last N runs? | 7 days, falling back to the last 20 runs when there are fewer than 5 in the window |
| Do the `escapes` of a run (a defect found after a pass) belong on home once the engine fills them? | Yes, on the gates tile, once rows carry a figure (F5) |
