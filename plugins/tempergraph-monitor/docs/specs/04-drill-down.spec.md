---
title: Drill-down
type: component
status: ready-for-implementation
prefix: MDD
adrs: [0004, 0005]
---

# Drill-down

## 1. Overview

The levels below a run: a unit with its visits and attempts, an attempt with its four nodes, and a session, live or finished. This is where a person "goes inside" a run: reads why a judge sent work back, sees the check's failing output, and watches the shell command a step is running now with the processes under it. Every view is drawn from engine documents ([RDD](../../../tempergraph/docs/specs/31-run-detail-document.spec.md), [EVT](../../../tempergraph/docs/specs/30-run-events.spec.md), [LOS](../../../tempergraph/docs/specs/33-local-observability-store.spec.md)); the monitor derives no verdict and parses no executor stream for meaning.

## 2. Contract

### 2.1 Unit view (level 2)

| Part | Content |
|---|---|
| Header | Unit name, kind, declared executor and judge executor, alias, gate policy (budget left per counter) |
| Visits | Each visit with `entered_from`; inside, each attempt as one row: number, node strip, check result, judge met/total and confidence, gate verdict and route, `repeat_cause`, cost, duration |
| Items | For a map or fork, the items, each drilling into its own attempts |

### 2.2 Attempt view (level 3)

Four tabs, one per node, opened on the node in flight or, when finished, on the node that decided the route.

| Tab | Content |
|---|---|
| Step | The step session's summary (§2.4), output artifact keys with local paths |
| Check | Result, duration, `environmental` and `untracked_only` flags, the clipped evidence, and `l` for the tail of the check's stdout and stderr |
| Judge | Criteria table: n, id, status (MET, PARTIAL, UNMET, N/A, UNVERIFIABLE), and for each blocker its clipped evidence, place and fix from the local evidence file; `gap`; confidence with its source; the judge session's summary; re-asks as their own rows |
| Gate | Verdict, the rule that derived it (blockers, confidence threshold, check), route target, guard status and any discarded judgement with the call that voided it, budget counters charged |

### 2.3 Pause view

When the run waits for a person, the run view opens here with `g`: the pause kind, the question, the artifacts to review with their paths (each a link or a copy action), the decision words with their consequences, how long it has waited, and one action per decision that fills the prompt with the resume command ([MAC](05-actions-and-safety.spec.md)). The monitor never picks a decision.

### 2.4 Session view (level 4)

| Tab | Live session | Finished session |
|---|---|---|
| Now | Open tool: name, capability, `input_summary`, elapsed; last text line; tokens and turns so far; `last_event_age_s` against the idle limit as a bar | Outcome: ok, timed out, stalled, partial, infra cause, error kind |
| Calls | Every tool call from the activity journal: time, name, summary, ok, duration; subagent calls indented; denied calls marked | Same, complete |
| Processes | The session's process group from `ps`: pid, parent, elapsed, program name (never arguments), as a tree | Not shown |
| Log | Tail of `raw.jsonl` as plain text lines, of `stderr.log`, and for `messages-api` of `tools.jsonl` | Same |
| Info | Executor and CLI version, alias and bound model, session id, `session_key`, transcript locator (engine copy and native), activity and live paths, isolation mode, usage with reported and estimated cost | Same |

**"Which shell is it running"** is answered by two views together: the Now tab's open tool, when it is a shell tool, shows the command line as the engine summarised it ([EVT §2.5](../../../tempergraph/docs/specs/30-run-events.spec.md)) with its elapsed time, and the Processes tab shows which programs that command started and how long each has run (for example `bash → make → pytest → python`).

### 2.5 Settings that hide data

| Setting | Effect |
|---|---|
| `show.tool_inputs` (`on` default) | `off` hides every `input_summary` in the pane, whatever the engine wrote |
| `show.log_tails` (`on` default) | `off` hides the Log tab and check output tails |
| Engine `observe.tool_inputs = off` | Summaries are null at the source; the pane shows names only |

## 3. Behaviours

**MDD-B1 Why it was sent back.** Given attempt 1 of `code` with gate RETRY, when the Judge tab opens, then it lists six criteria with statuses, and the two blockers show their evidence, place and fix lines, so the person reads the reason without opening a file.

| n | id | Status | Evidence (clipped) | Fix |
|---|---|---|---|---|
| 3 | tests-pass | UNMET | `pytest: 3 failed in tests/api` | fix the failing API tests |
| 5 | api-doc | PARTIAL | `two endpoints undocumented` | document POST /tokens and DELETE /tokens |

**MDD-B2 Live shell.** Given a step whose shell tool has run `make test` for 7 minutes, when the session's Now and Processes tabs are open, then Now shows `Bash · make test · 7m 02s` and Processes shows the tree under the session's process group with elapsed times, refreshed every 2 s.

**MDD-B3 Long silent tool.** Given an open tool whose last event is 13 minutes old with a 15-minute idle limit, when Now is drawn, then the idle bar is at 87 % and marked, matching the detail document's `suspect_stall`.

**MDD-B4 Judge voided by the guard.** Given a judgement discarded because the judge called a tool outside its view set, when the Gate tab opens, then it shows the discarded judgement, the call that voided it, and the gate's resulting verdict, so a case such as a judge calling a monitor's tool is visible as what it was.

**MDD-B5 Hidden inputs.** Given `show.tool_inputs = off`, when any session view draws, then no command line or path appears; names, durations and outcomes do.

**MDD-B6 Finished session.** Given a session that ended 3 days ago and was pruned, when its view opens, then Info shows paths marked `pruned` and Calls and Log say the logs were removed by `store prune`.

## 4. Error conditions

| Condition | Result |
|---|---|
| Activity journal missing (older engine) | Calls tab built from the live file's last ten names; marked partial |
| Evidence file unreadable | Judge tab shows statuses only |
| Session process group gone | Processes says "ended" |

## 5. Design notes

- Judge first: much of repeat cost is a judge sending work back, so the reason a judge gave is the most useful line in an attempt ([MADR-0004](../adr/0004-borrow-the-workflows-view-and-add-gates.adr.md)).
- Release 1 build ([T10 plan](../../../tempergraph/docs/plans/t10-monitor.plan.md)): the unit view (header with gate budget left, visits and attempt rows), the attempt view's four tabs (hotkeys `1` to `4`; it opens on the node in flight, else on the judge when it named blockers, else on the gate), the pause view of §2.3 with one prompt fill per decision ([MAC](05-actions-and-safety.spec.md)), and the session view's five tabs are drawn. Settings are `show_tool_inputs` and `show_log_tails`. Deviations: the check tab shows the clipped evidence only, as the check's stdout and stderr tails are not in the detail document yet; the guard's discarded judgement (MDD-B4) shows as the gate's `guard` value until the detail document carries the voided call; the Log tab reads `raw.jsonl` and `stderr.log` beside the engine transcript and says "not found (pruned, or never written)" when they are gone (MDD-B6); a Calls tab with no journal says so rather than rebuilding from the live file.
- Program names only in the process tree: arguments of child processes are what the engine's scrubber never saw.
- Raw log lines are shown as text, never interpreted; the meaning comes from normalized records only ([engine ADR-0009](../../../tempergraph/docs/adr/0009-normalized-session-event-stream.adr.md)).

## 6. Acceptance criteria

- [ ] MDD-AC-1 MDD-B1 to MDD-B6 pass as UI tests from fixture documents on terminal and desktop.
- [ ] MDD-AC-2 With both hide settings off, a canary planted in a tool input appears in no drawn tree (test reads every tree's text).
- [ ] MDD-AC-3 The Processes tab never shows a process outside the session's process group (test with a decoy process).

## Open questions

| Question | Owner |
|---|---|
| Should the Calls tab offer "open in Claude": filling the prompt with a request to explain the selected session from its `raw.jsonl`? It costs the person's model usage; it is offered as an action, not automatic ([MAC](05-actions-and-safety.spec.md)). Default for release 1: yes, as the session view's "ask Claude about this session" fill, which names the session's transcript and the attempt's gate verdict. | Owner |

## References

[MRV](03-run-view.spec.md) · [MAC](05-actions-and-safety.spec.md) · [RDD](../../../tempergraph/docs/specs/31-run-detail-document.spec.md) · [EVT](../../../tempergraph/docs/specs/30-run-events.spec.md) · [engine ADR-0023](../../../tempergraph/docs/adr/0023-local-activity-journal-with-tool-input-summaries.adr.md)
