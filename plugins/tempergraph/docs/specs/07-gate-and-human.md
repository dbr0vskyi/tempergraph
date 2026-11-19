---
title: Gate and human nodes
type: component
status: review
prefix: HUM
adrs: [0004, 0015]
---

# Gate and human nodes

## 1. Overview

The gate only routes. The human node is the single place a run pauses, and only a person answers it (contract C6). Escalations, spent budgets that ask, approval pauses after a pass and event waits all pause in the same node, so a resume replays only that node.

## 2. Contract

```python
def gate_node(unit: UnitSpec, state: RunState) -> GateWrite: ...      # pure; never pauses
def human_node(unit: UnitSpec, state: RunState) -> HumanWrite: ...    # first statement: interrupt(payload)
class PausePayload: kind: Literal["escalation", "budget", "approval", "event_wait"]
                    unit: str; item: str | None; reason: str; artifacts: list[str]
                    rubric: list[CriterionView]; decisions: list[str]; resume_command: str
```

### 2.1 What sends a run to a person

| Cause | Pause kind |
|---|---|
| Unresolved gap (blocker UNVERIFIABLE, gap flag, unparsed or discarded judgement) | escalation |
| A workflow escalation rule | escalation |
| Retry or loop budget spent on a gate set to `ask` | budget |
| A check FAIL marked environmental (no retry can fix it) | escalation |
| An upstream claim the judge could not confirm; a defect attributed outside the allowed targets | escalation |
| A pass on a gate with `approval`, or a step named by the operator's approval option | approval |
| A `wait` unit | event_wait |

An infra failure never pauses ([BUD](08-budgets-and-failures.md)). The self-improvement workflow never pauses.

### 2.2 Decisions

| Decision | Effect |
|---|---|
| proceed | Accept the work and go on; the step, judge and gate do not run again |
| retry [feedback] | The step runs again with a fresh retry budget; feedback reaches the step and its judge once |
| back:<unit> [feedback] | To a listed earlier unit; feedback becomes that visit's reason; the pair's loop budget resets |
| stop | Ends the run (exit 4) |
| event:<name>=<value> | Only at a wait; accepted only if the unit's pure check passes the value |

## 3. Behaviours

**HUM-B1 Interrupt first.** Given a paused run, when it is resumed, then the human node re-executes from its top and nothing before `interrupt` logs, spends or writes.

**HUM-B2 Exit 3 with payload.** Given an escalation, when the human node interrupts, then the process prints the payload (produced output, missing artifacts, rubric, exact resume command) and exits 3.

**HUM-B3 Several pending gates.** Given two pending gates from parallel branches, when a resume names neither, then it is refused with exit 2 listing each gate and its exact command; each gate is answered by unit and item.

**HUM-B4 Wait is not passable by word.** Given a run paused at a wait unit, when a person sends `proceed`, then it is refused with exit 2; when an event value fails the check, it is refused with exit 2, nothing is written and the run still waits.

| Resume at a wait | Check | Result |
|---|---|---|
| `proceed` | — | exit 2, still waiting |
| `event:approved=yes` | passes | value stored as an artifact; run continues |
| `event:approved=maybe` | fails | exit 2, still waiting |
| `stop` | — | exit 4 |

**HUM-B5 Approval is not friction.** Given a passing gate with `approval`, when the run pauses, then the recorded verdict stays PROCEED, the pause is not counted as an escalation, and a rework there is not a retry burst for self-improvement.

**HUM-B6 Intervention row.** Given an accepted resume, when it is applied, then one ledger row is appended before the graph runs: a random id, who resumed (`person`, `auto_reopen`, `event`, or `agent` when the caller declares itself one), the pause kind, the decision, whether feedback was given, and a cause word from metadata only.

## 4. Error conditions

| Condition | Result |
|---|---|
| Decision not valid for the thread state | Exit 2, nothing written ([DUR](09-durability-and-resume.md)) |
| `back` to a unit the gate does not list | Exit 2 |
| Human retries above the human cap (default 100) | Exit 2 |

## 5. Design notes

- One interrupt per gate keeps resume cheap and correct under LangGraph's replay-from-top rule ([ADR-0004](../adr/0004-four-nodes-per-unit.md)).
- Exit 3 means "a person is needed", never failure; callers tell it from 4 and 5 by code alone ([ADR-0015](../adr/0015-exit-codes-as-caller-contract.md)).

## 6. Acceptance criteria

- [ ] HUM-AC-1 A source test asserts `interrupt` is the first statement of the human node.
- [ ] HUM-AC-2 Each pause kind of §2.1 exits 3 with a payload holding a working resume command.
- [ ] HUM-AC-3 Every row of the HUM-B4 table holds.
- [ ] HUM-AC-4 Agent resumes are counted apart from a person's in every report.

## Open questions

None.

## References

