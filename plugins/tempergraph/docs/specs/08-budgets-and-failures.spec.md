---
title: Budgets, failures and timeouts
type: component
status: ready-for-implementation
prefix: BUD
adrs: [0004, 0006, 0021, 0070]
---

# Budgets, failures and timeouts

## 1. Overview

Every way a run can repeat has a counter with a default, and the **cause** of a failure decides which counter it spends: the model's failure costs a retry, the machine's an infra try, a person's direction the human cap. Budgets are decided in the gate node, which stays pure. Timeouts are engine-owned and resolved per step and per judge, so they behave the same on every executor. Every default below is a run setting an operator may override per run, per unit or per machine within the catalog's ranges ([RST §2.2](80-run-settings-and-overrides.spec.md)).

## 2. Contract

| Counter | Spent by | Default | When spent |
|---|---|---|---|
| Retry budget (per visit) | Check FAIL, judge RETRY, failed step, engine timeout or stall | 2 retries | Gate `on_budget_spent`: `stop` (exit 5) or `ask` (pause) |
| Loop budget (per unit, target) | Route, upstream claim or attribution sending the run back | 1 trip | Same stop-or-ask setting |
| Human cap | A person's retry | 100 | Resume refused (exit 2) |
| Infra tries (in a row) | `infra_cause` set on a step or judge session | 3 (max 10), backoff 10, 20, 40 s up to 300 s | Run ends with an infra exit (5); never a pause |
| Attempt cap (per invocation) | Any step attempt | 15 | Clean stop; a resume gets a fresh allowance |
| Run cost cap (`run_cost_cap_usd`) | Every session's cost, reported where present else estimated, children included | none | Checked before each attempt starts: a run at or over the cap drains cleanly with exit 5 reason `cost_cap`; re-openable after the operator raises it with `resume --set run.run_cost_cap_usd=…` ([RST §2.6](80-run-settings-and-overrides.spec.md)) |

### 2.1 Timeout resolution

Step: the operator layers of [RST §2.3](80-run-settings-and-overrides.spec.md) (flags per unit then per run, profiles, project and user overrides), the step's `timeout_s`, workflow default, project and user defaults, engine default (600 s). Judge: the same operator layers on the judge scopes only, the gate's judge `timeout_s`, workflow default, project and user defaults, engine default (600 s); a judge never reads a step's value. Council members, the chair, contest slots and scripts resolve on their own scopes the same way. `idle_s` follows the same order. Every record carries the number and its source layer.

### 2.2 Cause to counter

| Executor result | Counter |
|---|---|
| `infra_cause` ∈ {`spawn_failed`, `prompt_not_delivered`, `no_output`, `no_result`, `broken_pipe`, `connection`, `out_of_memory`, `request_timed_out`, `throttled`} | infra tries |
| `timed_out` with ≥ 60% of wall time in tool calls (step only) | infra tries (`slow_host`) |
| `timed_out` otherwise, `stalled` | retry budget |
| `error_kind` `cap_reached`, `turn_cap`, `model` | retry budget |
| `error_kind` `auth` | none: escalate at once; no retry can fix it |
| `error_kind` `refused` | none: escalate with the refusal recorded; the same prompt would be refused again |
| Judge RETRY whose every unmet blocker is `no_change` | none: escalate ([JDG](05-judge-and-verdict.spec.md)) |
| Check FAIL marked environmental | none: escalate with no judge and no new attempt |
| A failed or blocked attempt whose session recorded a `denied` event or lacked a declared tool at start | none: escalate with cause `tool_access`; the payload offers the grants that fix it ([RST §2.8](80-run-settings-and-overrides.spec.md)) |

## 3. Behaviours

**BUD-B1 Cause picks the counter.** Given a step attempt that ends with `broken_pipe`, when the gate decides, then the retry budget is unchanged, the infra counter rises, and the attempt reruns on the same ladder rung after the backoff.

**BUD-B2 Same rules on every executor.** Given the same failure shape on each executor, when classified, then the counter spent is the same.

| Failure | claude | agent-sdk | messages-api | antigravity | Counter |
|---|---|---|---|---|---|
| No result | stream ends with no `result` | no `ResultMessage` | worker ends with no `result` line | `init` seen, no `result` | infra |
| Turn cap | `subtype = error_max_turns` | `subtype = error_max_turns` | engine turn count | n/a (no turn cap) | retry |
| Cost cap | `--max-budget-usd` end (P-CC-3) | `subtype = error_max_budget_usd` | engine estimate between responses | n/a | retry |
| Throttled | last retry category `rate_limit` | `AssistantMessage.error = rate_limit` | 429 with `retry-after`, 529 | per P-AG-7 | infra |
| Stall | engine idle kill | engine idle kill | engine idle kill | engine idle kill | retry |
| Auth | `api_retry` category `authentication_failed` | `error = authentication_failed` | 401, 403, 402 | `result.error.type` per P-AG-7 | escalate |
| Refusal | n/a | n/a | `stop_reason = refusal` | n/a | escalate |

**BUD-B3 Visit budgets.** Given a unit entered by a back-edge, when it fails, then its retry budget counts from the later of the visit's start and the last human retry; attempt numbers keep rising across visits.

**BUD-B4 Trip back clears.** Given BACK from unit c to unit a, when it is applied, then the verdicts, judgements and artifacts of a and every unit after it on the path are deleted from state (files in the workspace are untouched), and a's prompt and judge carry the reason under their own heading.

**BUD-B5 Slow is not failed.** Given an attempt that used 0.85 of its limit and passed, when recorded, then it is flagged slow; it spends nothing.

**BUD-B6 Automatic re-open.** Given the operator enabled automatic re-open with N = 2, when a run ends with spent retries, a step timeout or an infra failure and exactly one top-level unit stopped, then the engine re-opens it at most twice as that person's retry given in advance; it never answers a pause or undoes a stop.

**BUD-B7 Ladder.** Given a ladder `[small, medium, large]`, when attempts 1, 2, 3 and 4 run, then they use `small`, `medium`, `large`, `large`; a person's retry, a re-open or a trip back starts at `small`; an infra rerun repeats its rung; the judge uses `large` on every attempt. This retry-count ladder is release 1's; release 2 retires it for the evidence-gated effort ladder and one-step model escalation of [LAD](92-effort-ladder-and-model-escalation.spec.md) ([ADR-0121](../adr/0121-ladders-climb-only-on-trusted-substantive-evidence.adr.md)), and its `model` lists are rewritten by an upgrade transform (LAD §2.8).

## 4. Error conditions

| Condition | Result |
|---|---|
| Infra tries spent | Exit 5 with reason `infra`; re-openable |
| Retry budget spent, gate `stop` | Exit 5; re-openable by a person's retry |
| Retry budget spent, gate `ask` | Exit 3 with a budget payload |

## 5. Design notes

- The idle watchdog is executor-neutral because it reads normalized events ([EXI](10-executor-interface.spec.md)); Antigravity has no turn cap, so the engine's limits are its only bounds ([R-003](../research/R-003-executor-capability-matrix.rsrch.md)).
- Text is never classified, except the one exact-equality match each executor spec lists.
- The run cost cap reads the same figure the run line shows, so an operator sees why a run drained. A per-session cap (`cost_cap_usd`) still applies inside each session where the executor declares it.

## 6. Acceptance criteria

- [ ] BUD-AC-1 Each row of §2.2 is tested on every executor's fixtures.
- [ ] BUD-AC-2 Every loop in a run has a counter with a default; a test drives each to its limit.
- [ ] BUD-AC-3 An infra failure never produces a pause.
- [ ] BUD-AC-4 Every step and judge record carries its timeout and source layer.

## Open questions

| Question | Owner | Release 1 default |
|---|---|---|
| Should a `throttled` session wait longer than the standard backoff? Needs a live concurrency measurement per executor. | Operator | No: the standard 10, 20, 40 s backoff |
| Do repeated resumes of one thread (a resume chain) each get a fresh attempt allowance without bound, or should a thread carry a lifetime cap? First release keeps the per-invocation cap and records the chain length on the status row. | Engine owner | The per-invocation cap of 15 only |
| Does `run.auto_reopen` count per segment or per thread? Assumed per thread: every automatic re-open of the thread counts toward N (ledger rows with cause `auto_reopen`, caller kind `engine`), and a person's retry does not reset it. A `cost_cap` drain and a person's stop are never re-opened. | Engine owner | Per thread |

## References

