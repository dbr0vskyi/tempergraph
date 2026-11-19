---
title: Observability and cost
type: component
status: review
prefix: OBS
adrs: [0009, 0012]
---

# Observability and cost

## 1. Overview

What a run leaves behind so a person or a later analysis can see what it did, what it cost and where the time went, without changing the run. This spec owns contracts C1 (every model call is an executor run, logged with its usage) and C2 (observability never changes a run or its exit code), and the cost rules that make two executors with different cost reporting comparable.

## 2. Contract

### 2.1 Run log events

| Kind | Written when | Key fields |
|---|---|---|
| `task` | Start, and resume with inputs | scrubbed, clipped request |
| `attempt_start` | Before every step or judge session | unit, item, attempt, kind, executor, alias and source, timeout and source |
| `agent_run` | After every session | kind (`step`, `retry`, `judge`, `judge_reask`, `grouping`), `Usage`, tool call names, `cli_version`, `session_id`, isolation mode, outcome fields of `SessionResult` |
| `attempt_interrupted` | On resume, for an unclosed start | |
| `gate` | Gate routes | verdict, judgement view, confidence and source, guard status, view set |
| `human` | Resume applied | decision, who, feedback id |
| `wait`, `auto_resume`, `finalize`, `engine_error` | As named | |

### 2.2 Cost rules

| Rule | Detail |
|---|---|
| Unmeasured is never zero | Unknown fields are null |
| Reported and estimated stay apart | `reported_cost_usd` from the executor; `estimated_cost_usd` from the engine's price table for every session with tokens; never summed into one figure |
| Price table | Defaults per model family shipped with the engine; the operator's binding table overrides per model |
| Completeness flag | A run's usage line ends `complete`, `estimated` (some sessions only estimated) or `incomplete` (some unmeasured) |
| Executor comparison | Reports compare executors on estimated cost, the one figure both have, and show reported cost where present |

### 2.3 Live progress file

Per running session, beside the run log: open tool, last ten tool names, last text line (scrubbed, clipped), replaced atomically at most once a second by a writer thread fed from the normalized event stream. It is not a run-log record.

### 2.4 Reports

Read-only, model-free verbs over the ledger and logs: cost per unit, first visits against repeats with one cause per repeat, judges against steps, per executor and per workflow version, time profile (wall time per tool name and program word), and the run overlay on the workflow diagram (counts and words only).

## 3. Behaviours

**OBS-B1 Every call logged.** Given a judge re-ask, when it runs, then it is an `agent_run` record of kind `judge_reask` with its own usage.

**OBS-B2 Mixed-executor run.** Given a run with three steps on `antigravity` and their judges on `claude`, when its usage line is printed, then it shows the reported total (judges only), the estimated total (all sessions) and the flag `estimated`.

| Session | Executor | Reported | Estimated |
|---|---|---|---|
| step a | antigravity | null | 0.31 |
| judge a | claude | 0.22 | 0.20 |
| step b | antigravity | null | 0.44 |
| **Run line** | | 0.22 (partial) | 0.95 · `estimated` |

**OBS-B3 Logging fails safely.** Given a full disk when the ledger row is written, when the run ends, then its exit code is the one it would have had and one record of the failure is attempted.

**OBS-B4 Session metrics.** Given a finished session, when recorded, then turns, peak context, turns above 200k context, tokens before the first write and files read again are computed from normalized events, numbers only; a metric an executor's stream cannot yield is null.

**OBS-B5 Time profile.** Given a session's events with receive times, when it ends, then wall time is attributed to the model and to each tool name and shell program word; no command, path or output is kept.

## 4. Error conditions

| Condition | Result |
|---|---|
| A price missing for a model | Estimate null for that session; the run line is `incomplete` |
| An unknown event kind in a log | Skipped by every reader |

## 5. Design notes

- Antigravity reports no cost; Claude Code reports a client-side estimate. One engine price table gives both a comparable estimate without trusting either as billing truth ([ADR-0012](../adr/0012-cost-when-executor-reports-tokens-only.adr.md)).
- The live file and metrics come from normalized events, so they work the same on both executors ([ADR-0009](../adr/0009-normalized-session-event-stream.adr.md)).
- Self-improvement children log to their own run logs; a daily cap sums them. Showing them in the parent's total is a known gap.
- Tracing to an external service is off and not designed; any destination is a governance decision.

## 6. Acceptance criteria

- [ ] OBS-AC-1 A failure injected into each recording step leaves the run and its exit code unchanged.
- [ ] OBS-AC-2 No record anywhere shows a cost of 0 for an unmeasured session.
- [ ] OBS-AC-3 The cost report reproduces a hand-computed fixture of mixed-executor sessions exactly.
- [ ] OBS-AC-4 The analyzer counts only `agent_run` records as model calls.

## Open questions

None.

## References

