# Observability and cost

## Purpose

What a run leaves behind so a person or a later analysis can see what it did, what it cost and where the time went, without changing the run. This spec owns two of the overview's contracts, that every model call is an executor run logged with its usage and that observability never changes a run or its exit code ([OVR](overview.spec.md)), and the cost rules that make four executors with different cost reporting comparable. Design notes and the release 1 build notes are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Depends on

- `budgets-and-failures.spec.md`: reservations are in the run log (BUD-B13); a wait is in the run log (BUD-B14); a refused reservation is in the run log (BUD-B15)
- `caller-provenance.spec.md`: caller provenance
- `central-run-stats.spec.md`: central run stats
- `check-contract-and-command-runs.spec.md`: check contract and command runs
- `compiler-and-flow.spec.md`: compiler and flow
- `complexity-routing.spec.md`: declaring a complexity switch (CXR-B7)
- `engine-cli.spec.md`: engine cli
- `finalizer-contract.spec.md`: finalizer contract
- `judge-and-verdict.spec.md`: judge and verdict
- `local-observability-store.spec.md`: local observability store
- `map-unit.spec.md`: map unit
- `measured-switches.spec.md`: measured switches
- `run-events.spec.md`: run events for observers
- `self-improvement.spec.md`: self-improvement loop
- `supervision-cost.spec.md`: supervision cost
- `supervision-metrics.spec.md`: supervision metrics
- `workflow-lessons.spec.md`: workflow lessons

## Does not own

- The record envelope and the observer record kinds: `run-events.spec.md`
- Where session logs live: `local-observability-store.spec.md`
- Export of run rows to a shared sink: `central-run-stats.spec.md`
- Export of telemetry: `telemetry-export.spec.md`

## Behaviours

### OBS-B1 Every call logged

WHEN any model session ends, a step, retry, judge, judge re-ask or grouping call THE engine SHALL write one `agent_run` record of that kind with its own `Usage`, the tool call names, `cli_version`, `session_id`, isolation mode, the outcome fields of `SessionResult`, `unknown_tools` (names the executor's view catalog does not map, [SIL](self-improvement.spec.md)), `lessons_digest` on a step or retry whose unit has lessons ([LSN](workflow-lessons.spec.md)), `duration_s`, `tool_wall_share` and `slow_host`; and count only `agent_run` records as model calls.

- GIVEN a judge re-ask WHEN it runs THEN it is an `agent_run` record of kind `judge_reask` with its own usage
- GIVEN a run log with route, gate and agent_run records WHEN the analyzer counts model calls THEN only the agent_run records count

### OBS-B2 Mixed-executor run line

WHEN a run's usage line is printed THE engine SHALL show the reported total and the estimated total apart, never summed into one figure, and end the line `complete`, `estimated` (some sessions only estimated) or `incomplete` (some unmeasured).

- GIVEN steps a and b on `antigravity` (reported null, estimated 0.31 and 0.44) and judge a on `claude` (reported 0.22, estimated 0.20) WHEN the run line is printed THEN it shows 0.22 reported (partial), 0.95 estimated and the flag `estimated`

### OBS-B3 Logging fails safely

WHEN writing any record, ledger row, live file or report input fails THE engine SHALL end the run with the exit code it would have had and attempt one record of the failure.

- GIVEN a full disk when the ledger row is written WHEN the run ends THEN its exit code is the one it would have had and one record of the failure is attempted

### OBS-B4 Session metrics

WHEN a session finishes THE engine SHALL compute turns, peak context, turns above 200k context, tokens before the first write and files read again from normalized events, numbers only, and record null for a metric an executor's stream cannot yield.

- GIVEN a stream that carries no context size WHEN its metrics are recorded THEN peak context is null, not 0

### OBS-B5 Time profile

WHEN a session's events with receive times end THE engine SHALL attribute wall time to the model and to each tool name and shell program word, and keep no command, path or output.

- GIVEN a session that ran `pytest` twice through the shell tool WHEN profiled THEN the time is counted under the program word `pytest` and no argument is kept

### OBS-B6 Timeouts sorted

WHEN the report reads a timed-out session THE report SHALL give it one class: `slow_host` when the host-speed warning was set (the session timed out with at least 60% of its wall time inside tool calls), else `hung` when the last line was at least the idle limit old at the kill, else `model_silent` when lines arrived and no `result` did.

- GIVEN three timed-out sessions, one with no line for the idle limit, one with the host-speed warning and one with lines but no result WHEN the report runs THEN they are `hung`, `slow_host` and `model_silent`

### OBS-B7 Run log record kinds

WHEN a run reaches each of these points THE engine SHALL write the record named: `task` at start and at a resume with inputs (scrubbed, clipped request); `attempt_start` before every step or judge session (unit, item, attempt, kind, executor, alias and source, timeout and source, `prompt_digest`); `attempt_interrupted` on resume for an unclosed start; `route` when a route or switch picks a target; `audit_judge` when a sampled audit judge ran ([JDG](judge-and-verdict.spec.md)); `gate` when a gate routes (verdict, judgement view, confidence and source, guard status, view set); `human` when a resume is applied; `map_items` when a map fans out ([MAP](map-unit.spec.md)); `self_check` when a step ran its check preview ([CHK](check-contract-and-command-runs.spec.md)); `answers` when an ask took answers; `finalize` when the finalizer returned, raised or timed out ([FIN](finalizer-contract.spec.md)); `reservation` when a session takes a cost reservation, waits for room under the run cost cap or is refused ([BUD-B13, BUD-B14, BUD-B15](budgets-and-failures.spec.md)); and `wait`, `auto_resume` and `engine_error` as named. Every reader SHALL skip a record kind it does not know.

- GIVEN a log line of an unknown kind WHEN any reader folds the log THEN the line is skipped and the rest is read

### OBS-B8 Route record

WHEN a route or switch picks a target THE engine SHALL record the unit, the arm and `chosen_by` (`predicate`, `default`, `operator` or `rearm`); for a switch also `shadow`, `would_choose` and `signals`; for a step's route the step values it read in `signals` (at most 10, as [SWM](measured-switches.spec.md)); and for a complexity switch `zone`, `measures`, `rules_digest` and `rules_source` ([CMP](compiler-and-flow.spec.md), [CXR-B7](complexity-routing.spec.md)).

- GIVEN a complexity switch that picks its detailed arm WHEN the route record is written THEN it carries the zone, the measures and the rules digest

### OBS-B9 Human and audit records

WHEN a resume is applied THE engine SHALL record in `human` the decision, `caller` (kind, decider, relay; [PRV](caller-provenance.spec.md)), touch classes ([SUP](supervision-metrics.spec.md)), wait seconds and the feedback id; WHEN a sampled audit judge runs it SHALL record in `audit_judge` the executor, alias, per-criterion agreement with the gate's judge and `Usage`; and WHEN an ask takes answers it SHALL record the unit, the names answered, the names still open, whether the check passed and the caller, never the values.

- GIVEN an ask answered in part WHEN the `answers` record is written THEN it lists the answered and open names and holds no answer value

### OBS-B10 Unmeasured is never zero

WHEN a usage field is not measured THE engine SHALL record it as null in every record, line and report, never 0; and WHEN a model has no price SHALL leave that session's estimate null and mark the run line `incomplete`.

- GIVEN a session on a model missing from the price table WHEN the run line is printed THEN that session's estimate is null and the line ends `incomplete`

### OBS-B11 Reported and estimated cost

WHEN a session has tokens THE engine SHALL compute `estimated_cost_usd` from its price table and keep `reported_cost_usd` from the executor beside it: `claude` and `agent-sdk` report a client-side estimate, `messages-api` and `antigravity` report tokens only so their reported figure is null; and reports SHALL compare executors on the estimated figure and show the reported one where present.

- GIVEN a `messages-api` session with tokens WHEN recorded THEN `reported_cost_usd` is null and `estimated_cost_usd` is set

### OBS-B12 Price table

WHEN the estimate is computed THE engine SHALL use the defaults per model family shipped with the engine, overridden per model by the operator's binding table; the release 1 defaults are the first-party list prices of the generation the tier aliases resolve to, USD per million tokens as of 2026-11: haiku 0.10 in and 0.50 out; sonnet 2 in, 10 out and 0.10 cache read; opus 4 in, 20 out and 0.20 cache read; a family without a cache read price uses 0.1× input, cache writes are 1.25× input, and cache tokens are priced at their own rates.

- GIVEN a sonnet session of 1M input and 100k output tokens and no binding override WHEN estimated THEN the estimate is 3.00 USD

### OBS-B13 Child and supervision spend apart

WHEN a run has self-improvement children or sub-workflows THE reports SHALL join their usage to the parent's run line as a separate figure, never summed into the parent's own, a daily cap summing the children; and WHEN supervising sessions spent on a run outside the engine they SHALL show that as a third figure, marginal and turn apart, with its own completeness ([SCO](supervision-cost.spec.md)), never summed into the run's cost.

- GIVEN a run whose self-improvement child cost 0.40 WHEN the report shows the parent's line THEN 0.40 is shown as child spend beside, not inside, the parent's cost

### OBS-B14 Live progress file

WHEN a session is running THE engine SHALL keep `sessions/<session_key>/live.json` ([LOS](local-observability-store.spec.md)) with the open tool and its input summary, the last ten tool names with summaries and the last text line (scrubbed, clipped), replaced atomically at most once a second by a writer thread fed from the normalized event stream, not a run-log record; the same writer SHALL append the session's activity journal ([EVT](run-events.spec.md)).

- GIVEN a session emitting ten tool calls in one second WHEN the live file is read THEN it was replaced at most once in that second and lists the last ten tools

### OBS-B15 Model-free reports

WHEN an operator runs `report [30d|7d|24h|all] [--by unit|executor|version] [--json]` THE engine SHALL read the ledger and logs only, use no model and show: cost per unit with `agent_s`, the sum of its sessions' `duration_s`; first visits against repeats, the first visit being the first started attempt of a unit and a cut-off attempt counting with its partial usage, each repeat naming one cause (the visit's `entered_from`, `back:<unit>` or `proceed`, or `retry: judge` or `retry: check` from the gate that sent it back); cost and pass rate per route and switch arm; pass, fail and `UNVERIFIABLE` rates per criterion id with gate escapes (a criterion passed at a gate and failed by a later gate or a person); each step prompt's digest per unit (the first 16 hex of the SHA-256 of the rendered prompt) with its sessions, threads, repeat rate, timeouts and cost; stalled sessions as their own class and timeouts sorted as OBS-B6; the time profile of OBS-B5 from the activity journals; and judges against steps, per executor and per workflow version.

- GIVEN a unit whose first attempt was cut off and whose second passed WHEN the report runs THEN the first visit carries the cut-off attempt's partial usage and the repeat names its cause
- GIVEN a criterion passed at a gate and failed at a later gate WHEN the report runs THEN it is counted as a gate escape

### OBS-B16 Loop signal

WHEN one session repeats the same tool with the same input five times in a row THE report SHALL list it as a loop signal, record-only, and never stop the session.

- GIVEN a session that called Read on one file five times running WHEN the report runs THEN the loop list names that session and the session was not stopped

### OBS-B17 Run overlay

WHEN an operator runs `graph <workflow> --overlay <thread> [--format mermaid|md|json|svg]` THE engine SHALL draw on the workflow diagram, per unit, its visits, sessions, repeats, gate verdicts and money, and each routing edge with the times it was taken (`retry`, `back`, `proceed`), counts and words only; routes into a human node SHALL be counted in JSON and not drawn.

- GIVEN a thread whose unit was retried twice WHEN the overlay is drawn as md THEN that unit's retry edge shows 2
- GIVEN the same thread WHEN the overlay is drawn as svg THEN one standalone SVG document holds each unit's box with the counts the mermaid overlay shows for it

### OBS-B18 Stats rows

WHEN a run segment exits THE engine SHALL write one stats row per run with user, workflow, ticket, executor, cost figures and outcome, kept per month on the operator's machine by `observe.rows.run_row`, the one function the sink copy also uses; copy its supervision fields from the segment's `supervision` record; take `user` from the repository's git `user.name`, kept on this machine only; and send nothing anywhere unless the operator configures a sink ([CST](central-run-stats.spec.md)); `stats` ([CLI](engine-cli.spec.md)) reads these rows.

- GIVEN no configured sink WHEN a run exits THEN its row is written under the home stats folder and no network call is made

## Acceptance criteria

- OBS-AC1 (OBS-B3): A failure injected into each recording step leaves the run and its exit code unchanged
- OBS-AC2 (OBS-B2, OBS-B10, OBS-B11): No record anywhere shows a cost of 0 for an unmeasured session
- OBS-AC3 (OBS-B2, OBS-B11, OBS-B12, OBS-B13): The cost report reproduces a hand-computed fixture of mixed-executor sessions exactly
- OBS-AC4 (OBS-B1, OBS-B7, OBS-B8, OBS-B9): The analyzer counts only `agent_run` records as model calls, and each record kind is written with its fields by a fixture run
- OBS-AC5 (OBS-B4, OBS-B5, OBS-B6, OBS-B14, OBS-B15, OBS-B16, OBS-B17, OBS-B18): Each report row reproduces a hand-computed fixture, including a cut-off first attempt and a gate escape
