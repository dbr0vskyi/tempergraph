---
title: Observability and cost
type: component
status: ready-for-implementation
prefix: OBS
adrs: [0009, 0012, 0018, 0021, 0023, 0025]
---

# Observability and cost

## 1. Overview

What a run leaves behind so a person or a later analysis can see what it did, what it cost and where the time went, without changing the run. This spec owns contracts C1 (every model call is an executor run, logged with its usage) and C2 (observability never changes a run or its exit code), and the cost rules that make four executors with different cost reporting comparable.

## 2. Contract

### 2.1 Run log events

| Kind | Written when | Key fields |
|---|---|---|
| `task` | Start, and resume with inputs | scrubbed, clipped request |
| `attempt_start` | Before every step or judge session | unit, item, attempt, kind, executor, alias and source, timeout and source |
| `agent_run` | After every session | kind (`step`, `retry`, `judge`, `judge_reask`, `grouping`), `Usage`, tool call names, `cli_version`, `session_id`, isolation mode, outcome fields of `SessionResult` |
| `attempt_interrupted` | On resume, for an unclosed start | |
| `route` | A route or switch picks a target | unit, arm, `chosen_by` (`predicate`, `default`, `operator`, `rearm`), and for a switch `shadow`, `would_choose` and `signals` ([CMP](03-compiler-and-flow.spec.md), [SWM](79-measured-switches.spec.md)) |
| `audit_judge` | A sampled audit judge ran ([JDG](05-judge-and-verdict.spec.md)) | executor, alias, per-criterion agreement with the gate's judge, `Usage` |
| `gate` | Gate routes | verdict, judgement view, confidence and source, guard status, view set |
| `human` | Resume applied | decision, `caller` (kind, decider, relay; [PRV §2.5](85-caller-provenance.spec.md)), touch classes ([SUP §2.1](86-supervision-metrics.spec.md)), wait seconds, feedback id |
| `map_items` | A map fans out | unit, item ids, count ([MAP](77-map-unit.spec.md)) |
| `self_check` | A step ran its check preview | unit, item, attempt, result, finding counts, duration ([CHK §2.5](75-check-contract-and-command-runs.spec.md)) |
| `finalize` | The finalizer returned, raised or timed out | outcome, reason, url, duration, manual step count ([FIN §2.3](78-finalizer-contract.spec.md)) |
| `wait`, `auto_resume`, `engine_error` | As named | |

### 2.2 Cost rules

| Rule | Detail |
|---|---|
| Unmeasured is never zero | Unknown fields are null |
| Reported and estimated stay apart | `reported_cost_usd` from the executor; `estimated_cost_usd` from the engine's price table for every session with tokens; never summed into one figure |
| Price table | Defaults per model family shipped with the engine; the operator's binding table overrides per model. Release 1 ships the first-party list prices of the generation the tier aliases resolve to, USD per million tokens as of 2026-11: haiku 0.10 in, 0.50 out; sonnet 2 in, 10 out, 0.10 cache read; opus 4 in, 20 out, 0.20 cache read. A family without a cache read price uses 0.1× input; cache writes are 1.25× input |
| Completeness flag | A run's usage line ends `complete`, `estimated` (some sessions only estimated) or `incomplete` (some unmeasured) |
| Executor comparison | Reports compare executors on estimated cost, the one figure all have, and show reported cost where present |
| Per executor | `claude` and `agent-sdk` report a client-side estimate; `messages-api` and `antigravity` report tokens only, so their `reported_cost_usd` is null and the estimate is the figure. Cache read and write tokens are priced at their own rates |
| Child spend | A self-improvement child's or sub-workflow's usage is joined to its parent's run line in reports, shown as a separate figure, never summed into the parent's own |
| Supervision spend | What supervising sessions spent on a run outside the engine is a third figure, marginal and turn apart, with its own completeness ([SCO](87-supervision-cost.spec.md)); never summed into the run's cost |

### 2.3 Live progress file

Per running session, at `sessions/<session_key>/live.json` ([LOS §2.1](33-local-observability-store.spec.md)): open tool with its input summary, last ten tool names with summaries, last text line (scrubbed, clipped), replaced atomically at most once a second by a writer thread fed from the normalized event stream. It is not a run-log record. The same writer appends the session's activity journal ([EVT §2.3](30-run-events.spec.md)).

### 2.4 Reports


| Report | Content |
|---|---|
| First visit and repeats | The first visit is the first *started* attempt of a unit; a cut-off attempt counts with its partial usage. Each repeat names one cause |
| Per arm | Cost and pass rate per route and switch arm |
| Per criterion | Pass, fail and `UNVERIFIABLE` rates per criterion id, and **gate escapes**: a criterion passed at a gate and failed by a later gate or a person |
| Prompt digests | The digest of each rendered template beside its rates, so a prompt change is visible |
| Stalls and timeouts | `stalled` sessions as their own class; each timeout sorted into `hung` (no line for the idle limit), `slow_host` (host-speed preflight warned) or `model_silent` (lines arrived, no `result`) |
| Loop signal | Record-only: the same tool and input repeated five times in a row in one session; it never stops a session |
| Stats | `stats` ([CLI](17-engine-cli.spec.md)): one row per run with user, workflow, ticket, executor, cost figures and outcome, kept per month on the operator's machine; nothing is sent anywhere unless the operator configures a sink ([CST](34-central-run-stats.spec.md)) |

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

**OBS-B6 Timeout sorted.** Given three timed-out sessions, when the report runs, then each gets one class.

| Last line age at kill | Host-speed warning | Class |
|---|---|---|
| ≥ idle limit | no | `hung` |
| any | yes | `slow_host` |
| < idle limit, no `result` | no | `model_silent` |

## 4. Error conditions

| Condition | Result |
|---|---|
| A price missing for a model | Estimate null for that session; the run line is `incomplete` |
| An unknown event kind in a log | Skipped by every reader |

## 5. Design notes

- Antigravity and the Messages API report no cost; Claude Code and the Agent SDK report a client-side estimate. One engine price table gives every executor a comparable estimate without trusting any as billing truth ([ADR-0012](../adr/0012-cost-when-executor-reports-tokens-only.adr.md)).
- The live file and metrics come from normalized events, so they work the same on every executor ([ADR-0009](../adr/0009-normalized-session-event-stream.adr.md)).
- Self-improvement children log to their own run logs; a daily cap sums them, and reports join them to the parent's line as a separate figure.
- Export is off by default. An operator may configure sinks of metadata-only rows and OTLP telemetry ([CST](34-central-run-stats.spec.md), [TEL](35-telemetry-export.spec.md)); content never leaves the machine.
- Release 1 build ([T7 plan](../plans/t7-observability.plan.md) T7.4): `report [30d|7d|24h|all] [--by unit|executor|version] [--json]` and `stats` read the run logs and the home stats rows. Deviations: `agent_run` carries no `duration_s` or host-speed warning yet, so a timeout is sorted into `hung` or `model_silent` from the `stalled` flag and `slow_host` is never emitted; the time profile counts the activity journal's `duration_s` per tool name and program word. A repeat's cause is the `entered_from` of its visit (`back:<unit>`, `proceed`) or `retry: judge` / `retry: check` from the gate that sent it back. Prompt digests and the diagram overlay wait for the rendered-template digest on `attempt_start` (T5). The per-user stats row is written at each `run_exit` from the run log by `observe.rows.run_row`, the one function the sink copy will also use (T10.1); its supervision fields are copied from the segment's `supervision` record (T7.5), and `user` is the repository's git `user.name`, kept on this machine only.
- Observer record kinds added for live followers (`run_started`, `unit_entered`, `session_opened`, `check`, `judgement`, `budget`, `pause`, `stop_requested`, `run_exit`) and the record envelope are owned by [EVT](30-run-events.spec.md); where the session logs live is owned by [LOS](33-local-observability-store.spec.md).

## 6. Acceptance criteria

- [ ] OBS-AC-1 A failure injected into each recording step leaves the run and its exit code unchanged.
- [ ] OBS-AC-2 No record anywhere shows a cost of 0 for an unmeasured session.
- [ ] OBS-AC-3 The cost report reproduces a hand-computed fixture of mixed-executor sessions exactly.
- [ ] OBS-AC-4 The analyzer counts only `agent_run` records as model calls.
- [ ] OBS-AC-5 Each report row of §2.4 reproduces a hand-computed fixture, including a cut-off first attempt and a gate escape.

## Open questions

None.

## References

