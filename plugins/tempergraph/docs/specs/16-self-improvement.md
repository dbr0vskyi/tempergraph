---
title: Self-improvement loop
type: component
status: review
prefix: SIL
adrs: [0003, 0005]
---

# Self-improvement loop

## 1. Overview

A built-in workflow that reads every finished run's record, judges it with an independent judge, and files, comments on or only records a finding in the repository that owns the fault: the engine's or the workflow's. It runs as a detached child, is gated and judged like any workflow, and never pauses. The loop closes through people: an issue is evidence, not an order. This spec owns contract C14 (a measurement call never writes code).

## 2. Contract

### 2.1 Records on every exit (both modes, no model call)

| Record | Holds | Published |
|---|---|---|
| Findings | Signal and step names, cause codes, counts, executor names | Yes, as metadata |
| Evidence | Request, outputs, scrubbed feedback | Never; local only |
| Ledger row | Names, counts, hashes, executor and CLI versions; no text | Never as text |

### 2.2 Lenses

| Lens | Question | Dev mode trigger | Stable mode trigger |
|---|---|---|---|
| Friction | Where did the process hurt, and whose fault? | Every flagged final exit | Spent retries or a stop; an uncleared failed step; a gap escalation; repeated blockers; cost well above median; a new version's first five runs; a person pushing back |
| Outcome | Did the result meet the request? | Every final exit | A person pushing back; a pass at judge confidence ≤ 0.5; every 20th clean run |
| Cost | Where does money repeat? | Every 10th final exit of a version | Same |

### 2.3 Fault sides

Cause codes come from run-log names and numbers only, each classed `fault`, `infra` or `designed`. A fault is attributed to `engine`, `workflow`, or, new in tempergraph, `executor:<name>` when the cause is a CLI behaviour (an unknown event shape, a tool name outside the catalog, a refused flag). Executor-side issues go to the engine's repository with an executor label.

## 3. Behaviours

**SIL-B1 Detached and best effort.** Given a run that exits, when recording finishes, then the self-improvement child starts detached through a hand-off ticket; its failure never changes the parent's exit code.

**SIL-B2 De-duplication by cause.** Given a finding whose fingerprint (side, workflow, leading cause, step) matches an open issue, when filed, then a "seen again" comment is added instead of a new issue; a failed search is retried once, then files anyway and records why.

**SIL-B3 Pattern rule.** Given an outcome gap on the workflow side, when deciding to file, then at least three runs with three distinct requests in 30 days are required; one clear engine fault is enough.

**SIL-B4 Executor drift is visible.** Given runs on `antigravity` whose sessions show a tool name absent from the view catalog after a CLI update, when friction is judged, then the cause `unknown_tool_name` is attributed to `executor:antigravity` with the CLI version, and the workflow is not blamed.

**SIL-B5 Measurement writes nothing.** Given a cost-fix comparison between two workflow versions, when it runs, then it makes no model call, writes no file, ledger row or code, and its only writes are one issue comment and, after a regression, one reopen.

**SIL-B6 Dry run files nothing.** Given the operator's dry-run switch, when the child runs, then it shows what it would file and files nothing; every step of the parent still ran and spent.

## 4. Error conditions

| Condition | Result |
|---|---|
| Code host unreachable | Payload kept and redelivered by the next filing |
| Daily cap reached (stable mode, default $50) | Judges skipped; records still written |
| Evidence file opened by filing code | Source test fails |

## 5. Design notes

- The loop is a workflow inside the engine so every run is analyzed without an optional install ([ADR-0003](../adr/0003-workflows-as-data.md)).
- Its friction and outcome judges follow the same executor selection as any gate ([JDG](05-judge-and-verdict.md)); by default they run on a mid-tier alias for 1800 s.
- Thresholds (audit 1 in 20, 30-day pattern window, confidence floor) are defaults with no data behind them; they are recorded as such and revisited with real runs.

## 6. Acceptance criteria

- [ ] SIL-AC-1 Every exit writes findings, evidence and one ledger row, with no model call.
- [ ] SIL-AC-2 The canary test shows no request text in any issue, comment or ledger row.
- [ ] SIL-AC-3 A repeated cause produces one issue and comments, never a duplicate issue.
- [ ] SIL-AC-4 An executor-attributed cause is filed with the executor label and CLI version, never against the workflow.

## Open questions

| Question | Owner |
|---|---|

## References

