---
title: Band, status line and alerts
type: component
status: ready-for-implementation
prefix: MBA
adrs: [0004]
---

# Band, status line and alerts

## 1. Overview

The surfaces that are always there, so a person never has to open anything to know a run needs them: one row in the band above the prompt, one status-line entry, toasts inside the session and native notifications outside it. They show run labels, not thread ids, because several live runs of one workflow look alike.

## 2. Contract

### 2.1 Run label

`alias` if set, else `label`, else `<repo>/<branch-or-worktree>·<4 hex of the thread id hash>`; a batch child adds its item id; an orchestration node run adds `<orchestration>/<node>`.

### 2.2 Band row (`AbovePrompt`)

One row for the mod, sized to the band's columns.

| Live runs | Row |
|---|---|
| 0 | No row (`next(e)`) unless a run ended in the last 10 min: `tg ✓ auth-fix finished · $3.10 est` |
| 1 | `tg ▶ auth-fix · code 2/5 · judge · attempt 2 · 14m · $2.40 est` |
| 2 to 3 | One segment per run, `▶ auth-fix code·J` `⏸ docs-sync waits 12m`, waiting runs first; when they do not fit, the row of the next line |
| more | `tg 4 ▶ 2 ⏸ 1 ✗ · $11.20 est`; from 80 columns the longest-waiting run's segment follows the counts, with its wait time |

Marks: `▶` running, `⏸` waiting for a person, `✗` failed or orphaned in the last hour, `✓` finished, `⚠` suspect stall or cap ETA under 10 min. The node in flight is one letter: `S` step, `C` check, `J` judge, `G` gate. Pressing the row (or its hotkey once the band holds focus) opens the pane on the run it names, or on the run list.

### 2.3 Status line

`$.ui.status` holds a short form whenever any run is live or waiting: `tg 2▶ 1⏸`. Cleared when nothing is live or waiting.

### 2.4 Alerts

| Event read | Toast (in session) | Native notification (`$.ui.notify`) |
|---|---|---|
| `pause` record (a gate waits for a person) | yes | yes: title the run label, body `<unit> waits: <question, 80 chars>` |
| `run_exit` with code 4 or 5, or an orchestration attention item | yes | yes |
| `run_exit` code 0 | yes | only with `alerts.finished = on` |
| `health.suspect_stall` became true | yes | no |
| `health.cap_eta_min` under 10 | yes | yes |
| A fleet heartbeat shows a run waiting over 30 min on another machine | no | only with `alerts.fleet = on` |

Each alert is raised once per `(thread, seq)`: the last alerted `seq` per thread is kept in `$.store`, so a new session, a reload or a second Claude Code window on the same machine does not raise it again. Notifications are not raised for runs outside the mod's scope.

## 3. Behaviours

**MBA-B1 Waiting first.** Given four live runs of which one waits at a gate, when the band is drawn in 60 columns, then the row reads `tg 3 ▶ 1 ⏸ · $8.10 est`, and in 120 columns the waiting run's segment comes first with its wait time.

**MBA-B2 One alert per pause.** Given a pause alerted in session A, when session B starts on the same machine a minute later, then B shows the run as waiting in its band and raises no toast or notification for it.

**MBA-B3 Estimated, not reported.** Given a run whose sessions ran on `antigravity` only, when the band shows cost, then it reads `$… est`, never a bare dollar figure ([MCF](06-cost-and-fleet.spec.md)).

**MBA-B4 Notification channel off.** Given a person whose notifications are disabled, when a pause is read, then `$.ui.notify` resolves not sent and the toast still shows; nothing is retried.

## 4. Error conditions

| Condition | Result |
|---|---|
| The band has fewer than 20 columns | Row is `tg ⏸1` or `tg ▶n` only |
| Status verb stale for over 60 s | The band row ends with `· stale` |

## 5. Design notes

- Labels first: without them, several live runs of one workflow draw near-identical band lines ([MADR-0004](../adr/0004-borrow-the-workflows-view-and-add-gates.adr.md)).
- Alert de-duplication lives in the plugin store because a person often has several Claude Code sessions open on one repository.
- Release 1 build ([T10 plan](../../../tempergraph/docs/plans/t10-monitor.plan.md)): the rows of §2.2, the status line, the alerts of §2.4 but the fleet row, and both error rows of §4 are built. `alerts.finished` is the setting `alerts_finished`; `alerts.fleet` is the setting `alerts_fleet`: a toast once per run and pause for a wait over 30 min on another machine, remembered in `$.store`; no native notification.
- A notification is the one way the monitor reaches a person who is not looking; it carries the question so the person can decide whether to come back now.

## 6. Acceptance criteria

- [ ] MBA-AC-1 Each row of §2.2 is produced by a test mount on the terminal and desktop surfaces.
- [ ] MBA-AC-2 MBA-B2 passes with two simulated sessions sharing one plugin store.
- [ ] MBA-AC-3 No band, status or alert text shows a cost without `est` when the run's figure is estimated or incomplete.

## Open questions

None.

## References

[MDS](01-data-sources.spec.md) · [MRV](03-run-view.spec.md) · [EVT](../../../tempergraph/docs/specs/30-run-events.spec.md) · [R-001](../research/R-001-claude-code-mods.rsrch.md)
