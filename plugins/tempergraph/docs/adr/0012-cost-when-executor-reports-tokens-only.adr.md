# ADR-0012 Cost is reported and estimated apart; an engine price table fills gaps; unknown is never zero

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Claude Code reports `total_cost_usd` in its result, a client-side estimate that may differ from the bill, notably through gateways ([R-001](../research/R-001-claude-code-cli-headless.rsrch.md)). Antigravity reports token usage and no cost ([R-002](../research/R-002-antigravity-cli-headless.rsrch.md)). Budgets, run summaries and self-improvement compare cost across steps and executors. A missing figure shown as zero hides spend.

## Decision

We will record two fields per session: `reported_cost_usd` (what the executor said, or null) and `estimated_cost_usd` (tokens times the binding table's per-model prices, or null when a price is missing). They are never summed into one figure. Reports and comparisons use the estimate when it exists, else the reported figure; a run with any session missing both is marked incomplete on its usage line. A per-session cost cap stays an executor option (`--max-budget-usd` on Claude Code); the engine does not emulate one. No code path writes zero for an unknown cost.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Reported and estimated apart, price table, unknown stays null (chosen) | Comparable across executors; honest about gaps | Operators maintain prices per model |
| Use whatever the executor reports | No price table | Antigravity shows nothing; budgets cannot work there |
| Engine estimate only | One figure | Discards Claude's own figure, useful to cross-check the table |
| Query the billing API | True cost | Delayed, per-provider, needs account access; out of scope |

## Decision rationale

| Criterion | Chosen | Reported only | Estimate only | Billing |
|---|---|---|---|---|
| Works on Antigravity | yes | no | yes | partly |
| Comparable across executors | yes | no | yes | yes |
| Shows a gap as a gap | yes | no | yes | yes |
| Operator effort | price table | none | price table | access |

## Consequences

- Positive: Antigravity steps appear in cost reports and run budgets beside Claude steps ([OBS](../specs/15-observability-and-cost.spec.md)).
- Negative: the estimate lags price changes. Mitigation: on Claude sessions both figures exist, so `report` can show how far they differ and the operator can correct the table.
- Risk: a step on Antigravity has no per-session cost cap, so one runaway session spends until its timeout. Mitigation: a workflow that sets `cost_cap_usd` on such a step is refused at preflight ([EXI](../specs/10-executor-interface.spec.md)); the timeout and idle watchdog bound the session.

## Revisit when

Antigravity reports cost, or a provider offers a timely per-request billing figure.
