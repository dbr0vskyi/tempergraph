# Budgets, failures and timeouts

## Purpose

Every way a run can repeat has a counter with a default, and the cause of a failure decides which counter it spends: the model's failure costs a retry, the machine's an infra try, a person's direction the human cap. Budgets are decided in the gate node, which stays pure. Timeouts are engine-owned and resolved per step and per judge, so they behave the same on every executor. Every default is a run setting an operator may override per run, per unit or per machine within the catalog's ranges ([RST-B18](80-run-settings-and-overrides.spec.md)). The gate, pauses ([HUM](07-gate-and-human.spec.md)), executors ([EXI](10-executor-interface.spec.md)) and ladders ([LAD](92-effort-ladder-and-model-escalation.spec.md)) depend on it; design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### BUD-B1 Cause picks the counter

WHEN a session ends with an `infra_cause` in `spawn_failed`, `prompt_not_delivered`, `no_output`, `no_result`, `broken_pipe`, `connection`, `out_of_memory`, `request_timed_out` or `throttled`, or a step times out with at least 60% of wall time in tool calls (`slow_host`) THE gate SHALL spend an infra try, leave the retry budget unchanged and rerun the attempt on the same ladder rung after the backoff; and SHALL spend the retry budget on any other `timed_out`, a `stalled` session and `error_kind` `cap_reached`, `turn_cap` or `model`.

- GIVEN a step attempt that ends with `broken_pipe` WHEN the gate decides THEN the retry budget is unchanged and the infra counter rises

### BUD-B2 Same rules on every executor

WHEN the same failure shape occurs on any executor THE engine SHALL spend the same counter, classifying no result, throttling and its executor signals as infra, a turn cap, a cost cap and a stall as retry, and auth and refusal as escalate.

- GIVEN a stream that ends with no result (`claude` no `result`, `agent-sdk` no `ResultMessage`, `messages-api` worker with no `result` line, `antigravity` `init` with no `result`) WHEN classified THEN each spends an infra try
- GIVEN a turn cap (`error_max_turns` on `claude` and `agent-sdk`, the engine turn count on `messages-api`) or a cost cap (`--max-budget-usd` end per P-CC-3, `error_max_budget_usd`, the engine estimate) WHEN classified THEN each spends the retry budget
- GIVEN throttling (retry category `rate_limit`, `AssistantMessage.error = rate_limit`, HTTP 429 with `retry-after` or 529, per P-AG-7 on `antigravity`) WHEN classified THEN each spends an infra try
- GIVEN an auth failure (`authentication_failed`, HTTP 401, 403 or 402, `result.error.type` per P-AG-7) or a `messages-api` `stop_reason = refusal` WHEN classified THEN each escalates

### BUD-B3 Visit budgets

WHEN a unit entered by a back-edge fails THE engine SHALL count its retry budget from the later of the visit's start and the last human retry, attempt numbers rising across visits.

- GIVEN a unit's second visit after a human retry WHEN it fails twice THEN its budget counts from the human retry

### BUD-B4 Trip back clears

WHEN a BACK from one unit to an earlier one is applied THE engine SHALL delete from state the verdicts, judgements and artifacts of the target and every unit after it on the path, leaving workspace files untouched, and give the target's prompt and judge the reason under their own heading.

- GIVEN BACK from `c` to `a` WHEN it is applied THEN `a`, `b` and `c` have no verdicts in state and `a`'s prompt carries the reason

### BUD-B5 Slow is not failed

WHEN an attempt that used at least 0.85 of its limit passes THE engine SHALL flag it slow and spend nothing.

- GIVEN an attempt that used 0.85 of its limit and passed WHEN recorded THEN it is flagged slow

### BUD-B6 Automatic re-open

WHEN the operator enabled automatic re-open with N and a run ends with spent retries, a step timeout or an infra failure with exactly one top-level unit stopped THE engine SHALL re-open it at most N times per thread as that person's retry given in advance, recorded as ledger rows with cause `auto_reopen` and caller kind `engine`, a person's retry not resetting the count, and never answer a pause, undo a stop or re-open a `cost_cap` drain.

- GIVEN `run.auto_reopen` 2 WHEN a run ends on spent retries three times THEN it is re-opened twice and then stays stopped

### BUD-B7 One alias per step

WHEN a step's attempts and infra reruns run THE engine SHALL use the step's one alias for every attempt and the judge's alias by the judge order ([CON-B3](01-contracts.spec.md)), no retry changing the model; refuse release 1's retry-count list in `model` with `model-ladder-retired`, rewritten by rule ([LAD-B18](92-effort-ladder-and-model-escalation.spec.md)); and leave raising effort or the model to LAD's evidence-gated ladder and one-step escalation ([ADR-0121](../adr/0121-ladders-climb-only-on-trusted-substantive-evidence.adr.md)).

- GIVEN `model: small` and retry budget 3 WHEN four attempts and an infra rerun run THEN every one uses `small`

### BUD-B8 Counters

WHEN a run repeats THE engine SHALL keep the retry budget per visit (check FAIL, judge RETRY, failed step, engine timeout or stall; default 2), the loop budget per unit and target (a route, upstream claim or attribution sending the run back; default 1), both ending at the gate's `on_budget_spent` (`stop` with exit 5, re-openable by a person's retry, or `ask` with exit 3 and a budget payload); the human cap (a person's retry; default 100, a resume beyond it refused with exit 2); infra tries in a row (default 3, at most 10, backoff 10, 20, 40 s up to 300 s, ending with exit 5 reason `infra`, re-openable, never a pause); and the attempt cap per invocation (default 15, a clean stop, a resume getting a fresh allowance, the chain length recorded on the status row).

- GIVEN infra tries spent WHEN the run ends THEN it exits 5 with reason `infra` and no pause

### BUD-B9 Run cost cap

WHEN `run_cost_cap_usd` is set THE engine SHALL check before each attempt starts the run's spend, every session's reported cost where present else estimated, children included, and drain a run at or over the cap cleanly with exit 5 reason `cost_cap`, re-openable after the operator raises it with `resume --set run.run_cost_cap_usd=…` ([RST-B26](80-run-settings-and-overrides.spec.md)), the figure being the one the run line shows, and a per-session `cost_cap_usd` still applying inside each session where the executor declares it.

- GIVEN a cap of 5 USD and 5.10 USD spent WHEN the next attempt would start THEN the run drains with exit 5 `cost_cap`

### BUD-B10 Timeout resolution

WHEN a timeout is resolved THE engine SHALL take a step's from the operator layers ([RST-B22](80-run-settings-and-overrides.spec.md): flags per unit then per run, profiles, project and user overrides), the step's `timeout_s`, the workflow default, project and user defaults and the engine default 600 s; a judge's from the same operator layers on the judge scopes only, the gate's judge `timeout_s`, the workflow, project and user defaults and 600 s, never a step's value; council members, the chair, contest slots and scripts on their own scopes the same way; `idle_s` in the same order; and record on every step and judge record the number and its source layer.

- GIVEN a step `timeout_s` of 1800 and no judge timeout WHEN the judge resolves THEN it gets 600 s from the engine default, recorded as such

### BUD-B11 Causes that escalate at once

WHEN a session ends with `error_kind` `auth` or `refused`, a judge RETRY whose every unmet blocker is `no_change` ([JDG-B8](05-judge-and-verdict.spec.md)), a check FAIL marked environmental, or a failed or blocked attempt whose session recorded a `denied` event or lacked a declared tool at start THE engine SHALL spend no counter and escalate at once: auth because no retry can fix it, a refusal with the refusal recorded, an environmental FAIL with no judge and no new attempt, and the tool case with cause `tool_access` and a payload offering the grants that fix it ([RST-B28](80-run-settings-and-overrides.spec.md)).

- GIVEN a step whose session recorded a `denied` event WHEN the gate decides THEN the run pauses with cause `tool_access` and the payload lists the grants

### BUD-B16 The same check failure twice

WHEN a unit's check fails on two attempts in a row of one visit and item with the same evidence (the same failing findings by criterion, place and message, or the same scrubbed evidence text when it returns no findings) although the later attempt's step changed files in the workspace THE gate SHALL escalate at once with cause `check_repeat`, spend no further retry, infra try or ladder step, and show the repeated failing findings in the pause payload.

- GIVEN a retry budget of 3 and a check that fails with the same finding on attempts 1 and 2, attempt 2's step having changed files WHEN the gate decides after attempt 2 THEN the run pauses with kind `escalation` and cause `check_repeat`, the payload lists the finding, no third attempt starts and no further retry is spent
- GIVEN a check that fails with one finding on attempt 1 and with another on attempt 2 WHEN the gate decides after attempt 2 THEN the unit is retried as BUD-B8 says
- GIVEN the same failing finding on attempts 1 and 2 and a step that changed no file on attempt 2 WHEN the gate decides THEN the unit is retried as BUD-B8 says
- GIVEN an `effort_ladder` and the same failing finding on two attempts in a row with changed files WHEN the gate decides THEN the ladder does not climb and the run pauses with cause `check_repeat`

### BUD-B12 Concurrent sessions under one cap

WHEN sessions of one run can be in flight together (parallel branches, a parallel map, contest slots, council members) THE engine SHALL count what is in flight in the check before each attempt, a starting session reserving its per-session cap, or the projection of its unit from the stats ([CST](34-central-run-stats.spec.md)), or the run's remaining cap divided by the sessions that may run at once, the reservation becoming its real cost when it ends; make an attempt whose reservation would cross the cap wait for a running session, and start none when nothing is running, then drain with `cost_cap`.

- GIVEN two parallel branches whose reservations together cross the cap WHEN both are due THEN one starts and the other waits
- GIVEN a cap of 5.00 USD, 1.00 USD spent and a concurrent map of three items that each reserve 2.50 USD WHEN the items are due THEN one starts and the other two wait for a running item
- GIVEN a cap of 5.00 USD, 1.00 USD spent and a council of three members whose sessions each reserve 2.50 USD WHEN round 0 is due THEN one member session starts and the other two wait for a running member session

### BUD-B13 Reservations are in the run log

WHEN a session of a run with a cost cap takes its reservation (BUD-B12) THE engine SHALL write a `reservation` record with `action` `held` before the session starts, giving the amount reserved (`reserved_usd`), where that figure came from (`source`: `session_cap`, `projection` or `share`), the run's spend as BUD-B9 counts it (`spent_usd`), what the other running sessions hold (`in_flight_usd`) and the run's cap (`cap_usd`).

- GIVEN a cap of 5.00 USD, 1.00 USD spent, nothing running and a branch with a per-session cost cap of 2.50 USD WHEN its session is due THEN a `reservation` record with `action` `held`, `reserved_usd` 2.50, `source` `session_cap`, `spent_usd` 1.00, `in_flight_usd` 0 and `cap_usd` 5.00 comes before that session's `attempt_start` record
- GIVEN a cap of 5.00 USD, 1.00 USD spent, two parallel branches and no per-session cap or projection WHEN both are due THEN each branch's `held` record has `source` `share` and `reserved_usd` 2.00, the remaining 4.00 USD divided by the 2 branches
- GIVEN two parallel branches whose reservations fit together under the cap WHEN both are due THEN each has a `held` record and no `reservation` record has `action` `waiting`
- GIVEN a cap of 7.00 USD, 1.00 USD spent, a council of three members and no per-session cap or projection WHEN round 0 is due THEN each member's `held` record has `source` `share` and `reserved_usd` 2.00, the remaining 6.00 USD divided by the 3 members

### BUD-B14 A wait is in the run log

WHEN a session must wait for a running session to end because its reservation would take spend plus reservations over the run cost cap (BUD-B12) THE engine SHALL write once, when the wait begins, a `reservation` record with `action` `waiting` that gives the figures of BUD-B13 and lists the running sessions' `session_key` values ([EVT-B8](30-run-events.spec.md)) in `waiting_for`.

- GIVEN a cap of 5.00 USD, 1.00 USD spent and two parallel branches that each reserve 2.50 USD WHEN both are due THEN the branch that does not start has a `waiting` record with `reserved_usd` 2.50, `in_flight_usd` 2.50 and `waiting_for` listing the `session_key` of the branch that started
- GIVEN a cap of 5.00 USD, 1.00 USD spent, a running session that holds 2.50 USD and a branch waiting to reserve 2.50 USD WHEN the running session ends with a real cost of 0.40 USD THEN the branch's `held` record follows that session's `agent_run` record with `spent_usd` 1.40 and `in_flight_usd` 0, and the branch wrote no second `waiting` record

### BUD-B15 A refused reservation is in the run log

WHEN a session's reservation would take spend plus reservations over the run cost cap and no session is running (BUD-B12) THE engine SHALL write a `reservation` record with `action` `refused` that gives the figures of BUD-B13, before the run drains with `cost_cap`.

- GIVEN a cap of 5.00 USD, 3.00 USD spent, nothing running and a branch that reserves 2.50 USD WHEN its session is due THEN its `reservation` record has `action` `refused`, no session of the branch starts and the `run_exit` record that follows carries exit code 5 and reason `cost_cap`
- GIVEN a cap of 5.00 USD, 1.00 USD spent, a running session that holds 2.50 USD and a branch waiting to reserve 2.50 USD WHEN the running session ends with a real cost of 2.40 USD THEN the branch's `reservation` record has `action` `refused`, after its `waiting` record, and the run drains with `cost_cap`
- GIVEN a cap of 5.00 USD, 1.00 USD spent and a council of two members whose sessions each reserve 2.50 USD WHEN the first member's session ends with a real cost of 2.40 USD while the second waits THEN the second member's `reservation` record has `action` `refused`, after its `waiting` record, no further session of the council starts and the run drains with `cost_cap`

## Acceptance criteria

- BUD-AC1 (BUD-B1, BUD-B2, BUD-B11): Each cause rule is tested on every executor's fixtures
- BUD-AC2 (BUD-B3, BUD-B4, BUD-B6, BUD-B7, BUD-B8, BUD-B9, BUD-B12): Every loop in a run has a counter with a default; a test drives each to its limit
- BUD-AC3 (BUD-B1, BUD-B8): An infra failure never produces a pause
- BUD-AC4 (BUD-B5, BUD-B10): Every step and judge record carries its timeout and source layer
- BUD-AC5 (BUD-B13): A fixture run of two parallel branches whose reservations fit together under the cap writes a `reservation` record with `action` `held` before each branch's first `attempt_start` record and writes no `reservation` record with another action
- BUD-AC6 (BUD-B14): A fixture run of two parallel branches whose reservations together cross the cap writes, for the branch that waited, one `waiting` record that lists the other branch's `session_key` in `waiting_for` and, after that session's `agent_run` record, a `held` record
- BUD-AC7 (BUD-B15): A fixture run whose next reservation does not fit while nothing is running writes a `reservation` record with `action` `refused` before the `run_exit` record, which carries exit code 5 and reason `cost_cap`
- BUD-AC8 (BUD-B16): A fixture check that fails with the same finding on two attempts in a row, the second attempt's step having changed a file, pauses the run with kind `escalation` and cause `check_repeat` and starts no third attempt, while a fixture check that fails with a different finding on the second attempt, or whose second step changed no file, is retried as BUD-B8 says
- BUD-AC9 (BUD-B12, BUD-B14): A fixture run of a concurrent map whose items' reservations together cross the cap writes, for an item that waited, one `waiting` record that lists a running item's `session_key` in `waiting_for` and, after that session's `agent_run` record, a `held` record, and no `held` record of the run has `spent_usd`, `in_flight_usd` and `reserved_usd` adding up to more than `cap_usd`
- BUD-AC12 (BUD-B13): A fixture run of a council whose members have no per-session cost cap writes, before each member's first `attempt_start` record, a `reservation` record with `action` `held` and `source` `share` whose `reserved_usd` is the run's remaining cap divided by the number of members
- BUD-AC13 (BUD-B12, BUD-B14): A fixture run of a council whose members' reservations together cross the cap writes, for a member that waited, one `waiting` record that lists a running member's `session_key` in `waiting_for` and, after that session's `agent_run` record, a `held` record, and no `held` record of the run has `spent_usd`, `in_flight_usd` and `reserved_usd` adding up to more than `cap_usd`
- BUD-AC14 (BUD-B15): A fixture run of a council whose next member reservation does not fit while no member session is running writes a `reservation` record with `action` `refused` before the `run_exit` record, which carries exit code 5 and reason `cost_cap`, and starts no later session of the council

## Open questions

- Should a `throttled` session wait longer than the standard backoff? Until answered: no, the standard 10, 20, 40 s backoff; it needs a live concurrency measurement per executor. Owner: operator.
- Do repeated resumes of one thread each get a fresh attempt allowance without bound, or should a thread carry a lifetime cap? Until answered: the per-invocation cap of 15 only, with the chain length on the status row. Owner: engine owner.
- Should the comparison of BUD-B16 ignore durations and temporary paths in a check's message? Until answered: no, the scrubbed text must be identical, so a check whose message carries a changing duration never repeats and the check's author keeps its messages stable; a repeat is never taken from a failure that changed. Owner: engine owner.
- Not built yet: the reservations of BUD-B12 to BUD-B15 are built for a run's parallel branches, writer branches included, for the items of a concurrent map and for the member and chair sessions of a council; they are not built for contests (release 3, track R3-T4 of the third-release plan), which reuse them when they run sessions at once. The `projection` source is not taken, because the central run stats hold no per-unit projection ([CST-B15](34-central-run-stats.spec.md) projects per workflow); a reservation is the per-session cap or the share ([R-140](../research/R-140-release-three-readiness-and-gaps.rsrch.md) F5). Owner: engine owner.
