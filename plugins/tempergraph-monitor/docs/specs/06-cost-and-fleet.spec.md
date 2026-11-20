---
title: Cost and fleet
type: component
status: ready-for-implementation
prefix: MCF
adrs: [0005]
---

# Cost and fleet

## 1. Overview

Two tabs that look past one attempt: a run's **cost** as it accrues, and the **fleet**, every live and recent run on every machine that pushes to a shared sink. This spec owns contract M4: an unmeasured, estimated or incomplete figure is shown so, never as 0 or as reported, following the engine's cost rules ([OBS §2.2](../../../tempergraph/docs/specs/15-observability-and-cost.spec.md)).

## 2. Contract

### 2.1 Cost tab of a run

| Part | Content |
|---|---|
| Totals | Estimated total; reported total with `(n of m sessions)` when partial; completeness flag; child spend (self-improvement, sub-workflows) as a separate line |
| By unit | Bars of estimated cost per unit, split first visit against repeats, each repeat with its cause |
| By kind | Steps against judges and re-asks |
| By executor and model | Estimated cost and tokens (input, output, cache read, cache write, thinking) |
| Budget | Run cost cap, what is left, burn rate per hour, minutes to the cap at that rate |
| Supervision | What supervising sessions spent on this run, as its own figure beside the run's: marginal and turn apart, by category (start, watch, diagnose, decide, steer, relay, rewake), with completeness, and the supervision share ([SCO](../../../tempergraph/docs/specs/87-supervision-cost.spec.md)); `open` while a supervising session is still live, never `0` when unmeasured |
| Projection | For this workflow: median and 90th percentile cost per finished run and the sample size, marked `thin` under 5 runs, from `stats --projection` |

Every figure carries `est` when estimated, `rep` when reported, and `≥` when a part is unmeasured.

### 2.2 Fleet tab

Built from the fleet copy in the home folder, `~/.tempergraph/fleet/<fleet_sink>/`, through `stats --live` and the month's rollup ([CST](../../../tempergraph/docs/specs/34-central-run-stats.spec.md)); the header shows when it was last synced.

| Part | Content |
|---|---|
| Live now | One row per live run on any machine: machine label, repository (name or hash, as the sink stores it), workflow, label, state, unit in flight, waiting time, estimated cost so far; a heartbeat older than 5 min is `stale` |
| This month | Totals by machine, user, workflow and executor: runs, exit reasons, estimated and reported cost apart, completeness; per workflow the share of runs by supervision level, undesigned touches per run by decider, and the median supervision share ([SUP §2.4](../../../tempergraph/docs/specs/86-supervision-metrics.spec.md)) |
| Drill | A row of this machine opens its run view; a row of another machine opens a read-only card of its numbers ("logs are on <machine label>") |

## 3. Behaviours

**MCF-B1 Never zero.** Given a run with one session that was cut off before reporting usage, when the cost tab draws, then that session's cost is `—`, the totals read `≥ $4.10 est`, and the flag reads `incomplete`.

**MCF-B2 Mixed executors.** Given the engine's mixed-executor example ([OBS-B2](../../../tempergraph/docs/specs/15-observability-and-cost.spec.md)), when the tab draws, then it shows `$0.95 est` and `$0.22 rep (1 of 3 sessions)` on separate lines, never summed.

**MCF-B3 Cap warning.** Given a run cost cap of $20, $17 spent and a burn of $9 per hour, when the tab draws, then the budget line shows `$3.00 left · ~20 min at $9/h`; under 10 min it also raises the alert of [MBA §2.4](02-band-status-and-alerts.spec.md).

**MCF-B4 Waiting on another machine.** Given a run paused for 40 min on machine B, when machine A's fleet tab is open, then the run is listed under Live now with `⏸ 40m` and B's label, and pressing it opens a card, not a run view.

**MCF-B5 No sink.** Given `fleet_sink` empty, when the fleet tab opens, then it explains how to configure a sink in the engine and shows this machine's month from local stats only.

## 4. Error conditions

| Condition | Result |
|---|---|
| Projection verb fails | Projection line omitted, marked unavailable |
| Sink unreadable | Fleet tab shows its last copy, marked stale, and the sink's name |

## 5. Design notes

- Cost honesty is copied, not reinvented: the engine already keeps reported and estimated apart; the monitor only refuses to blur them on screen ([engine ADR-0012](../../../tempergraph/docs/adr/0012-cost-when-executor-reports-tokens-only.adr.md)).
- The fleet tab is the "single place" for numbers from all machines inside Claude Code; the same rows can be read by `stats --source` in a shell or sent to an OTLP backend ([MADR-0005](../adr/0005-three-scopes-repo-machine-fleet.adr.md)).
- Release 1 build ([T10 plan](../../../tempergraph/docs/plans/t10-monitor.plan.md)): the cost tab is drawn from the detail document: the total and the completeness flag, by unit (first visit, then each repeat with the engine's `repeat_cause`, else `retry` or `visit n (<entered_from>)`), by kind (`step`, `judge`, and `re-ask` for a judge's re-ask sessions), by executor and model with the five token counts (`—` where the executor gave none), and the budget line. Deviations: reported and estimated money are summed per session (a session's reported figure wins over its estimate), never across the two; child spend has no field in the detail document yet and is not shown; supervision reads `not recorded` until SCO's journal (T7.6), and projection reads `unavailable` until `stats --projection` (T7.4). The fleet tab is not built: it needs the fleet copy and `stats --live` of T10.1.
- A workflows view shows tokens per agent; tempergraph shows money per unit, because money per repeat cause is what is worth ranking.

## 6. Acceptance criteria

- [ ] MCF-AC-1 MCF-B1 to MCF-B5 pass as UI tests from fixture documents.
- [ ] MCF-AC-2 A test over every drawn tree finds no cost figure without `est`, `rep` or `≥` where the engine's figure is not a complete reported total.

## Open questions

None.

## References

[MBA](02-band-status-and-alerts.spec.md) · [CST](../../../tempergraph/docs/specs/34-central-run-stats.spec.md) · [OBS](../../../tempergraph/docs/specs/15-observability-and-cost.spec.md)
