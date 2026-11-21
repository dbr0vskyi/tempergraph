---
title: Gate and human nodes
type: component
status: ready-for-implementation
prefix: HUM
adrs: [0004, 0015, 0065, 0066, 0073, 0074, 0085, 0086]
---

# Gate and human nodes

## 1. Overview

The gate only routes. The human node is the single place a run pauses, and only a person answers it (contract C6). Escalations, spent budgets that ask, approval pauses after a pass, event waits and asks for a person's input all pause in the same node, so a resume replays only that node. The one other pause is an operator's breakpoint before a step node, which runs nothing of the unit before it ([FLX §2.5](74-flow-extensions.spec.md)).

## 2. Contract

```python
def gate_node(unit: UnitSpec, state: RunState) -> GateWrite: ...      # pure; never pauses
def human_node(unit: UnitSpec, state: RunState) -> HumanWrite: ...    # first statement: interrupt(payload)
class PausePayload: kind: Literal["escalation", "budget", "approval", "event_wait", "input", "breakpoint"]
                    unit: str; item: str | None; reason: str; artifacts: list[str]
                    rubric: list[CriterionView]; decisions: list[str]; resume_command: str
```

### 2.1 What sends a run to a person

| Cause | Pause kind |
|---|---|
| Unresolved gap (blocker UNVERIFIABLE, gap flag, unparsed or discarded judgement) | escalation |
| A workflow escalation rule | escalation |
| Retry or loop budget spent on a gate set to `ask` | budget |
| A model escalation whose conditions hold at a stage that offers it; the payload carries the evidence and `resume --escalate` ([LAD §2.4](92-effort-ladder-and-model-escalation.spec.md)) | budget |
| A check FAIL marked environmental (no retry can fix it) | escalation |
| A failed or blocked attempt that could not reach a tool, skill, MCP server or command (cause `tool_access`); the payload lists the refused names and the `--grant` or `--allow-command` that fixes each ([RST §2.8](80-run-settings-and-overrides.spec.md)) | escalation |
| An upstream claim the judge could neither confirm nor refute ([JDG-B9](05-judge-and-verdict.spec.md)), or one on a gate with no judge; a defect attributed outside the allowed targets | escalation |
| A pass on a gate with `approval`, or a step named by the operator's approval option | approval |
| A pass on a gate with criteria verified by `person` (a sign-off); the payload's `rubric` lists them with each `role` and `question`, and `resume --criterion <id>=signed\|declined` records a status per criterion ([OUT §2.2](90-run-outcome.spec.md)) | approval |
| A `wait` unit | event_wait |
| An `ask` unit ([ASK](73-ask-unit.spec.md)) | input |
| A council with no decision and `on_no_decision: escalate` ([CNL §2.4](71-council-unit.spec.md)) | escalation |
| An operator's `--pause-before` ([FLX §2.5](74-flow-extensions.spec.md)) | breakpoint |
| A wait or ask past its deadline, applied with `escalate` ([FLX §2.3](74-flow-extensions.spec.md)) | escalation |

An infra failure never pauses ([BUD](08-budgets-and-failures.spec.md)). The self-improvement workflow never pauses.

### 2.2 Decisions

| Decision | Effect |
|---|---|
| proceed [feedback] | Accept the work and go on; the step, judge and gate do not run again; feedback reaches the next unit once as notes |
| retry [feedback] | The step runs again with a fresh retry budget; feedback reaches the step and its judge once |
| back:<unit> [feedback] | To a listed earlier unit; feedback becomes that visit's reason; the pair's loop budget resets |
| rewind:<unit> [feedback] | To any unit completed on the path; cleared as a trip back; no loop budget charged; counts against the human cap ([RRN §2.3](81-reruns-and-feedback.spec.md)) |
| stop [feedback] | Ends the run (exit 4); feedback is recorded locally as the cause |
| event:<name>=<value> | Only at a wait; accepted only if the unit's pure check passes the value |
| answer:<name>=<value> | Only at an ask, or at a council's no-decision pause (`decision`); validated by the question's kind ([ASK §2.3](73-ask-unit.spec.md)) |

Any feedback may be given as a **ruling** (`--ruling`): it is then shown to every later attempt of the units it applies to and to their judges until a person revokes it ([RRN §2.2](81-reruns-and-feedback.spec.md)). A resume may also change run settings ([RST §2.6](80-run-settings-and-overrides.spec.md)).

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

**HUM-B6 Intervention row.** Given an accepted resume, when it is applied, then one ledger row is appended before the graph runs: a random id, the `Caller` of the resume with its kind, decider and relay evidence ([PRV §2.5](85-caller-provenance.spec.md); an infra re-open is `engine`, an event value or an applied deadline carries the caller that delivered it), the touch classes it counts as ([SUP §2.1](86-supervision-metrics.spec.md)), the pause kind, the decision, the seconds the pause waited, whether feedback was given and whether as a ruling, the setting keys changed, the grants given (unit and capability names), and a cause word from metadata only.

## 4. Error conditions

| Condition | Result |
|---|---|
| Decision not valid for the thread state | Exit 2, nothing written ([DUR](09-durability-and-resume.spec.md)) |
| `back` to a unit the gate does not list | Exit 2 |
| Human retries and rewinds above the human cap (default 100) | Exit 2 |
| `rewind` to a unit not completed on the path | Exit 2 ([RRN §4](81-reruns-and-feedback.spec.md)) |

## 5. Design notes

- One interrupt per gate keeps resume cheap and correct under LangGraph's replay-from-top rule ([ADR-0004](../adr/0004-four-nodes-per-unit.adr.md)).
- Exit 3 means "a person is needed", never failure; callers tell it from 4 and 5 by code alone ([ADR-0015](../adr/0015-exit-codes-as-caller-contract.adr.md)).

## 6. Acceptance criteria

- [ ] HUM-AC-1 A source test asserts `interrupt` is the first statement of the human node.
- [ ] HUM-AC-2 Each pause kind of §2.1 exits 3 with a payload holding a working resume command.
- [ ] HUM-AC-3 Every row of the HUM-B4 table holds.
- [ ] HUM-AC-4 Agent resumes, by caller kind and decider, are counted apart from a person's in every report ([SUP §2.2](86-supervision-metrics.spec.md)).

## Open questions

None.

## References

