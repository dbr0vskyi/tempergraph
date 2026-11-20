---
title: Ask unit
type: component
status: review
prefix: ASK
adrs: [0062, 0065]
---

# Ask unit

## 1. Overview

An **ask** unit pauses a run to take input from a person and stores the answers as an artifact later steps read ([ADR-0065](../adr/0065-ask-unit-takes-a-persons-input-as-an-artifact.adr.md)). It is LangGraph's `interrupt()` for human input, in this engine's form: the pause is in the unit's human node, the answers are validated by rule, and there is no model and no judge, since the person's input is the bar ([R-060](../research/R-060-node-types-against-langgraph.rsrch.md) L11). Questions are declared, or taken from a list an earlier step wrote, such as a discovery step's open questions.

## 2. Contract

### 2.1 Declaration

| Type | Field | Kind | Meaning |
|---|---|---|---|
| `UnitSpec` (CON §2.1) | `ask` | `AskSpec`, for kind `ask` | |
| `AskSpec` | `questions` | list of 1–20 `Question`, optional | |
| | `from` | artifact key, optional | A list artifact of questions in the `Question` shape (JSON or a Markdown list with one `name: question` per item). Exactly one of `questions` and `from`. |
| | `context` | list of artifact keys | Shown with the questions, by pointer. |
| | `check` | callable ref, optional | Pure check over the answers. |
| | `deadline_s`, `on_deadline` | optional | [FLX §2.3](74-flow-extensions.spec.md) |
| `Question` | `name` | slug | Key in the answers. |
| | `text` | template ≤ 500 chars | |
| | `kind` | `text` \| `choice` \| `choices` \| `number` \| `bool` \| `file` \| `url` | `choices` allows several. |
| | `choices` | list of slugs | `choice`, `choices` only. |
| | `required` | bool, default true | |
| | `default` | value of `kind`, optional | Used when the person leaves it out. |

The unit produces one artifact, `answers` (kind `file`, JSON under the thread's folder), which a later step names as a judge reference or a prompt input like any artifact. The gate holds only the built-in answer check and the author's `check`.

### 2.2 Placement

An ask runs on the main chain or inside a sub-workflow child (the child's pause is the parent's). It may not be a parallel branch, a map item, a contest slot or a council member.

### 2.3 Answering

| Decision (CON §2.9) | Effect |
|---|---|
| `answer:<name>=<value>` (repeatable) | Sets one answer; validated by kind |
| `--answers <file>` | A JSON or YAML map of answers |
| `proceed` | Accepted only when every required answer has a value or a default |
| `stop` | Ends the run (exit 4) |

The pause payload ([HUM](07-gate-and-human.spec.md), kind `input`) lists each question with its kind, choices, default and whether it is answered, and the exact resume command. Answers can be given over several resumes; each accepted resume writes what it set and stays paused until the set is complete and the check passes. The intervention row records who answered (`person` or `agent`, [HUM-B6](07-gate-and-human.spec.md)).

## 3. Behaviours

**ASK-B1 Typed answers.** Given an ask with `env` of kind `choice` (`staging`, `prod`) and `ticket` of kind `text`, when a resume sends `answer:env=dev`, then it is refused with exit 2 naming the allowed choices, nothing is written, and the run stays paused.

| Resume | Result |
|---|---|
| `answer:env=staging` | stored; still paused (`ticket` missing) |
| `answer:ticket=PRJ-12` then `proceed` | stored; check runs; run continues |
| `proceed` with `ticket` missing and no default | exit 2, still paused |
| `stop` | exit 4 |

**ASK-B2 Questions from a step.** Given a discovery step that produced `open_questions` and an ask with `from: open_questions`, when the ask is entered, then the list is validated against the `Question` shape; a malformed list stops the unit before the pause with a finding naming the item, as a bad map list does.

**ASK-B3 Answers reach later steps.** Given a plan step whose prompt names `{answers}` and whose judge references `answers`, when it runs, then the step reads the answers file and the judge grades against it.

**ASK-B4 Listed for attention.** Given a paused ask, when `attention` runs, then the item shows kind `input`, the count of unanswered required questions, and the resume command.

## 4. Error conditions

| Type | Result |
|---|---|
| `from` artifact missing at entry | Unit stops; run exit 4 naming the key |
| More than 20 questions in a `from` list | Unit stops before the pause, as a too-long map list |
| A `file` answer outside the workspace | Exit 2 (contract C10) |

## 5. Design notes

- One interrupt per gate holds: the ask's only pause is its human node, and a partial answer re-enters the same node.
- An ask differs from an approval (a decision on work) and from a wait (a value from an outside system, checked); its answers are data for later steps.
- No executor is involved, so an ask behaves the same on all four executors.

## 6. Acceptance criteria

- [ ] ASK-AC-1 Every row of the ASK-B1 table holds offline.
- [ ] ASK-AC-2 A partial answer, a crash and a resume keep the answers already accepted.
- [ ] ASK-AC-3 Validation refuses an ask in every placement §2.2 forbids.
- [ ] ASK-AC-4 The monitor's documents show kind `input` with question counts ([RDD](31-run-detail-document.spec.md)).

## Open questions

None.

## References

[CON](01-contracts.spec.md) · [HUM](07-gate-and-human.spec.md) · [ADR-0065](../adr/0065-ask-unit-takes-a-persons-input-as-an-artifact.adr.md)
