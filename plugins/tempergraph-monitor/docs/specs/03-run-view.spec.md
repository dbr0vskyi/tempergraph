---
title: Run list and run view
type: component
status: ready-for-implementation
prefix: MRV
adrs: [0001, 0004, 0006]
---

# Run list and run view

## 1. Overview

The monitor's pane: one pane, `tempergraph`, opened by the `/tg` command, by pressing the band row, or on its own when a run starts and the surface docks panes as sidebars. Inside it a person moves through levels with the same keys as Claude Code's dynamic workflows view ([R-002](../research/R-002-dynamic-workflows-view.rsrch.md)): the run list, a run, a unit, an attempt, a session. This spec owns the pane, the run list, the run view (the graph), the orchestration view and the key map; the levels below a run are [MDD](04-drill-down.spec.md). It also owns contract M5: one tree per view on every surface.

## 2. Contract

### 2.1 Pane

| Item | Rule |
|---|---|
| Id and title | `tempergraph`, title `tempergraph · <scope>` |
| Opened by | `/tg [label]` (opens on that run if given), a band press, a toast's link, or unasked at `run_started` only where the surface reports a docked sidebar layout ([R-001](../research/R-001-claude-code-mods.rsrch.md)) |
| Placement | `dock` and `inline`: full views; `widget` (desktop's minimized form): a glance of the band row's content and the oldest waiting gate |
| Header | Breadcrumb `Runs › auth-fix › code › attempt 2 › judge`, a freshness mark (`live`, `3 s`, `stale 1 m`), the scope |
| Footer | The keys valid at this level |

### 2.2 Keys

| Key | Action (borrowed from the workflows view unless marked) |
|---|---|
| `↑` `↓` | Select |
| `Enter` `→` | Drill in |
| `Esc` `←` | Back out |
| `j` `k` | Scroll the detail area |
| `f` | Filter by state (`all`, `live`, `waiting`, `failed`, `finished today`) |
| `g` | Jump to the run's open gate or pause (tempergraph) |
| `c` | Cost tab of the current run ([MCF](06-cost-and-fleet.spec.md)) (tempergraph) |
| `l` | Log tail of the selected session or check (tempergraph) |
| `a` | Actions menu for the selection ([MAC](05-actions-and-safety.spec.md)) |
| `x` | Fill the prompt with `stop` for the selected run, drain mode (workflows: stop; here it is a prompt fill) |
| `p` | Pin or unpin a run to the top of the list (tempergraph; workflows uses `p` for pause, which tempergraph has no verb for) |

Every key is also a `Button` in the footer, so a mouse, the desktop app and the VS Code panel reach every action.

### 2.3 Run list (level 0)

Rows grouped by origin: this repository first, then other repositories on this machine (`scope = machine`), then orchestrations, then the fleet tab ([MCF](06-cost-and-fleet.spec.md)). Within a group: waiting, running, failed or orphaned, finished in the last 24 h, older (folded).

| Column | From |
|---|---|
| Mark and label | §2.1 of [MBA](02-band-status-and-alerts.spec.md) |
| Workflow and version | status |
| Progress | `units passed / units in plan`, and the unit in flight with its S·C·J·G letter |
| Attempt | `attempt n` of the unit in flight, `↻` if n > 1 |
| Last verdict | status |
| Elapsed, or waiting time | status, health |
| Cost | estimated (and reported where every session reported), flag |
| Executors | first letters of executors used (`c` claude, `s` agent-sdk, `m` messages-api, `a` antigravity) |
| Supervision | the run's supervision level so far and who acted (`obs`, `appr`, `cons·agent`, `collab·person`, …) and, for a waiting run, whom it waits on (`person` or the supervising host), from the detail document's `supervision` block ([RDD §2.1](../../../tempergraph/docs/specs/31-run-detail-document.spec.md), [SUP §2.3](../../../tempergraph/docs/specs/86-supervision-metrics.spec.md)) |

### 2.4 Run view (level 1)

Above the tree, a **touch strip**: each touch so far in time order as one mark (class, decider, relay: `R·agent`, `A·person`, `S·person⇢relayed`), so a person sees at a glance whether a run went on alone or was babysat. Then up to five **narrator lines** from `events_tail` of the detail document, newest last (`12:04 gate plan PROCEED (6/6, 0.85)`, `12:19 code attempt 1 RETRY: c3 tests fail`), like a workflow's `log()` lines.

The tree is the declared plan in graph order ([RDD §2.1](../../../tempergraph/docs/specs/31-run-detail-document.spec.md)): one row per unit, unreached units dim.

| Part of a unit row | Shows |
|---|---|
| Mark | `✓` passed, `▶` running, `⏸` paused, `✗` failed, `·` not reached, `⊘` skipped by a switch |
| Name and kind | `code`, with `map ×5`, `fork ×3`, `switch→arm`, `human`, `sub-workflow` |
| Node strip | Four cells `S C J G` for the current or last attempt: done, running (highlighted), failed, not run, or `–` when the unit has no gate |
| Visits and attempts | `v2 a3` when a unit was visited twice and is on its third attempt; `←plan` when the last visit came from a trip back |
| Judge | `5/6 · 0.82` met over total and confidence of the last judgement; `UNVERIFIABLE` count when any |
| Cost share | A bar of the unit's share of the run's estimated cost, and its figure |
| Time | Wall time of the unit so far |

A map or fork row expands (`→`) into its items, each a row with its own node strip. A sub-workflow row expands into the child's own run view. A `back:` edge taken is drawn as an indented `↩ from code (gate BACK: c2 plan misses API)` line under the unit it returned to.

### 2.5 Orchestration view

Opened from an orchestration row; drawn from the orchestration status document ([ORC §2.7](../../../tempergraph/docs/specs/45-orchestration.spec.md)). Phases are groups, as phases group agents in the workflows view; each node row shows kind, label, state, the node run's label, its unit in flight and node strip (from that run's status row), cost, and attention marks; the attention list is pinned above the phases. `Enter` on a node opens that node's run view (level 1), so a person goes from an orchestration down to a live shell command with the same keys.

### 2.6 Surfaces (contract M5)

| Surface | Difference |
|---|---|
| Terminal | Full tree; cost bars as text blocks; narrow width (< 80) drops the executor and time columns |
| Desktop | Same tree; bars as `Progress`; links open files; `widget` glance |
| VS Code | Same tree; no `Client` elements are used anywhere |
| Mobile (where drawn) | The run list and the run view only, one column; drill-down and actions say "open on your computer" |

## 3. Behaviours

**MRV-B1 Retry visible while it happens.** Given unit `code` whose first attempt's judge returned 4/6 and whose gate sent it back, when the second attempt's step is running, then the row reads `▶ code · S C J G` with S highlighted, `a2 ↻`, judge `4/6 · 0.70` (last), and a narrator line `code attempt 1 RETRY: c3, c5`.

**MRV-B2 Map items.** Given a map unit of five items, two passed, one running its judge, two not started, when the row is expanded, then five item rows show `✓ ✓ ▶(J) · ·` and the collapsed row reads `map ×5 2✓ 1▶ 2·`.

**MRV-B3 Trip back.** Given gate `code` routed `back:plan`, when the run view is drawn, then `plan` is `▶ v2` with an `↩ from code` line beneath it, and `code` shows `v1` ended `BACK`.

**MRV-B4 Orchestration to session.** Given an orchestration with a live node, when the person presses Enter on the node, its run's running unit, the attempt and the step, then the session view of [MDD](04-drill-down.spec.md) opens with the breadcrumb `Orchestrations › nightly › n3 › code › attempt 1 › step`.

**MRV-B5 Pane opens itself only where it fits.** Given a terminal 100 columns wide, when a run starts, then the pane does not open on its own; the band row appears and `/tg` opens the pane inline.

## 4. Error conditions

| Condition | Result |
|---|---|
| Detail document cut (`truncated`) | Rows for passed units show summary only; drilling into one asks `--unit` |
| `plan_stale` | Header shows "plan changed since this run started" |
| A level's source is stale | The level draws its last copy with the stale mark |

## 5. Design notes

- The key map keeps the workflows view's muscle memory; where tempergraph has no matching verb (pause, restart, skip) the key is reused or absent rather than faked ([MADR-0004](../adr/0004-borrow-the-workflows-view-and-add-gates.adr.md)).
- The node strip is the one new visual idea: it makes "which of step, check, judge, gate is running" readable at a glance, which a workflow's agent rows cannot say because a workflow has no gates.
- Release 1 build ([T10 plan](../../../tempergraph/docs/plans/t10-monitor.plan.md)): the run list (filter on `f`, a pin button per run, pins kept in `$.store` across sessions) and the run view (unit rows with the node strip, trip-back lines, narrator, touch strip, the cut note, pause question; `g` opens the pause view, `c` the cost tab, `x` fills stop) are drawn from the status and detail documents. Every row is a `Button`, so arrows and Enter are the surface's own focus keys. Deviations: back out is a footer `Button` with hotkey `b`, since a mod's `Button` hotkey is one letter or digit and `Esc` is the surface's own; `j` and `k` are not bound because the pane's scroll is the surface's; `l` and `a` are not bound, as the log tail is a session tab and every action is its own button. Map item rows, the orchestration view and the mobile reduction are not built (maps and orchestration are release 2).
- One pane with levels, rather than one pane per run, keeps the band and the pane in step and matches the workflows view's single entry point ([MADR-0006](../adr/0006-one-pane-many-levels.adr.md)).

## 6. Acceptance criteria

- [ ] MRV-AC-1 MRV-B1 to MRV-B4 pass as UI tests on the terminal and desktop surfaces from fixture detail documents.
- [ ] MRV-AC-2 Every key of §2.2 has a footer Button with the same action (test presses both).
- [ ] MRV-AC-3 A run view of 40 units and a map of 50 items draws within the surface's room without a refused tree.

## Open questions

| Question | Owner |
|---|---|
| Should a closed pane reopen itself on a pause? Today a pause raises a notification and a toast, and does not move the person's layout. Default for release 1: no. | Owner |

## References

[MDD](04-drill-down.spec.md) · [MBA](02-band-status-and-alerts.spec.md) · [RDD](../../../tempergraph/docs/specs/31-run-detail-document.spec.md) · [R-002](../research/R-002-dynamic-workflows-view.rsrch.md)
