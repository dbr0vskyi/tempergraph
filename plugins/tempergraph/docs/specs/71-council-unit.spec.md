---
title: Council unit
type: component
status: review
prefix: CNL
adrs: [0062, 0063]
---

# Council unit

## 1. Overview

A **council** puts one question to several model sessions, its **members**, and combines what they say into one artifact: a synthesis written by a **chair**, a decision tallied by the engine from votes, or a ranking aggregated from peer ranks. It suits questions with no single checkable answer where several perspectives help: a design choice, a risk call, a go or no-go, a review through several lenses. Members answer blind first; deliberation rounds are opt-in and anonymized; every outcome is derived by rule; and the council's output goes to the gate's one independent judge like any step's ([ADR-0063](../adr/0063-council-is-a-gated-step-with-engine-tallied-outcomes.adr.md), [R-061](../research/R-061-councils-debate-and-voting.rsrch.md)). A council is a step, never a judge.

## 2. Contract

### 2.1 Declaration

| Type | Field | Kind | Meaning |
|---|---|---|---|
| `UnitSpec` (CON §2.1) | `council` | `CouncilSpec`, for kind `council` | |
| `CouncilSpec` | `question` | template (CON §2.2) | The brief every member gets; the inputs and references are the same for all. |
| | `members` | list of 2–7 `MemberSpec` | |
| | `mode` | `synthesize` \| `vote` \| `rank` | §2.3 |
| | `options` | list of slugs, or an artifact key of a list | `vote` only: what members choose among (2–10). |
| | `rule` | `majority` \| `supermajority` \| `unanimous` \| `plurality`, default `majority` | `vote` only. `supermajority` is at least two thirds of valid ballots. |
| | `rounds` | int 0–3, default 0 | Deliberation rounds after the blind round 0. |
| | `anonymize` | bool, default true | Peers are shown as `Member A`, `Member B`… in an order fixed per attempt and recorded. |
| | `chair` | `ChairSpec`, required for `synthesize`, optional otherwise | |
| | `quorum` | int, default all members | Valid answers a round needs to count. |
| | `on_no_decision` | `escalate` \| `retry` \| `stop`, default `escalate` | §2.4 |
| | `retry_scope` | `all` \| `chair`, default `all` | `chair` keeps the members' final positions and re-runs only the chair (`synthesize`, `rank`). |
| | `cost_cap_usd` | float, optional | Per attempt; the remaining sessions of the attempt are drained when reached. |
| `MemberSpec` | `name` | slug | Unique in the council. |
| | `executor`, `model` | executor name, alias (CON §2.4) | Resolved per member on the step layer. |
| | `stance` | text ≤ 400 chars | The member's lens or role ("security reviewer", "argue against the change"). |
| | `tools` | read-only `ToolCapability` list | Never `edit`, `write`, `shell` or a writing MCP tool. |
| | `timeout_s`, `idle_s` | positive int, optional | |
| `ChairSpec` | `executor`, `model`, `prompt` | optional | The chair sees the question, every member's final answer under its label, and the tally if any. |

The council produces three artifacts, keyed by the unit: `decision` (the chair's answer, or for a chairless `vote` or `rank` the engine-written outcome), `positions` (each member's final answer and its round history, under labels) and `tally` (`vote` and `rank`: the counts, the rule and the outcome).

### 2.2 Member answer block

A member's answer is free text ending in one fenced JSON block, which the engine parses, like a judgement block (CON §2.8).

| Field | Modes | Meaning |
|---|---|---|
| `position` | all | One line: the member's answer. |
| `choice` | `vote` | One of `options`, or `abstain`. |
| `ranking` | `rank`, from round 0's ranking pass | Peer labels best first; the member's own label is never listed. |
| `confidence` | all | Float in [0,1]. |
| `changed`, `why_changed` | rounds ≥ 1 | Whether the position moved since the last round, and why. |
| `dissent` | rounds ≥ 1, chair | Where the author still disagrees with the others; empty only if it does not. |

A block that does not parse is re-asked once; a second failure is a **spoiled** answer and counts against the quorum.

### 2.3 Modes and outcome

| Mode | Sessions per attempt (n members, r rounds) | Outcome by |
|---|---|---|
| `synthesize` | n × (r + 1) + 1 chair | The chair's answer; its `dissent` section is required when any member's final position differs |
| `vote` | n × (r + 1) (+ 1 if a chair writes the rationale) | Engine tally of final-round `choice`s by `rule`; abstentions and spoiled ballots do not count as votes |
| `rank` | n × (r + 1) + n ranking passes (+ 1 chair) | Engine Borda count over peer rankings (k−1 points for first of k); ties broken by mean member confidence, then label order |

### 2.4 No decision

A `vote` whose rule is not met, a quorum not reached, or a `rank` with an exact tie after both breaks has outcome `no_decision`. With `on_no_decision: escalate` the gate pauses with kind `escalation`, shows `positions` and `tally`, and accepts `answer:decision=<option>` from a person ([ASK §2.3](73-ask-unit.spec.md) decision grammar), recorded as `chosen_by = person`. `retry` charges the retry budget and runs the council again; `stop` stops.

### 2.5 Compilation

The council's step node is a subgraph: one member node dispatch per (round, member), an engine-owned round barrier that waits for every member's answer, failure or spoil, a pure tally node, and the chair node. Each member session is checkpointed on its own, so a crash resumes only unfinished sessions. The judge, gate and human nodes are the unit's usual ones ([CMP §2.1](03-compiler-and-flow.spec.md)). Members run in the run's worktree read-only, fingerprinted before and after like parallel branches ([WSP §2.1](13-workspace-and-concurrency.spec.md)); a member that changed the workspace fails.

Session kinds: `member`, `member_reask`, `chair` (CON §2.6); session keys `<unit>.<attempt>.member.<name>.<round>`, `<unit>.<attempt>.chair`.

### 2.6 What is refused

| Refused before a run (`error`) |
|---|
| Fewer than 2 or more than 7 members; two members with one name |
| A member tool that is not read-only by the engine catalog ([GRD](06-independence-guard.spec.md)) |
| `synthesize` without a chair; `vote` without options or with fewer than 2; `options` from an artifact no earlier unit produces |
| `rule` or `options` outside `vote`; `retry_scope: chair` with `vote` |
| A council in a map item or a parallel branch whose block is a writer |
| No judge on the council's gate (contract C4 applies to model work) |

Warnings: every member bound to one model family (audit `council-one-family`); `rule: majority` with an even member count; `rounds > 0` with `anonymize: false`.

## 3. Behaviours

**CNL-B1 Blind first round.** Given a council of three members, when round 0 runs, then each member's prompt contains the question and its stance and no other member's text, label, executor or model.

**CNL-B2 Anonymized rounds.** Given `rounds: 1` and `anonymize: true`, when round 1 runs, then each member sees the others' round-0 answers as `Member A`, `Member B` (its own omitted), in the order recorded for the attempt, and must fill `changed`, `why_changed` and `dissent`.

**CNL-B3 Tally by rule.** Given a `vote` council of five members with options `ship`, `hold`, when the final ballots are counted, then the engine writes `tally` and the outcome; no model reads the ballots to decide.

| Ballots | Rule | Outcome |
|---|---|---|
| 3 ship, 2 hold | majority | ship |
| 3 ship, 2 hold | supermajority | no_decision |
| 2 ship, 2 hold, 1 spoiled, quorum 4 | majority | no_decision (tie) |
| 2 ship, 1 hold, 2 abstain | plurality | ship |
| 4 ship, 1 spoiled, quorum 5 | majority | no_decision (quorum) |

**CNL-B4 Judge grades the council.** Given a `synthesize` council, when its gate runs, then the judge's subject is `decision` and its references include `positions`, so a criterion such as "the decision states every dissent" is gradable; the judge session is fresh, read-only and none of the members.

**CNL-B5 Route on a decision.** Given a council followed by a switch whose predicate reads `tally.outcome`, when the gate passes, then the switch picks the arm by that value with no model call ([CMP §2.2](03-compiler-and-flow.spec.md)).

**CNL-B6 Mixed executors.** Given members on `claude`, `antigravity` and `messages-api`, when preflight runs, then each member's alias and tools are checked against its own executor and any gap refuses the start with exit 2; the chair and the judge are resolved on their own layers.

**CNL-B7 Chair-only retry.** Given `retry_scope: chair` and a judge RETRY whose unmet blockers concern the synthesis, when the retry runs, then only the chair session runs, with the judge's notes, and the members' recorded positions are reused.

**CNL-B8 Cost cap.** Given `cost_cap_usd: 2` and members whose reported cost reaches 2 during round 1, when the cap is reached, then no new member session starts, running ones finish, and the attempt ends `cap_reached` ([BUD](08-budgets-and-failures.spec.md)).

## 4. Error conditions

| Type | Result |
|---|---|
| A member session fails (infra) | Counted as missing for the round; the round still closes; below quorum → `no_decision` |
| Every member fails on infra | Infra failure of the attempt ([BUD](08-budgets-and-failures.spec.md)), never a pause |
| A member writes to the workspace | Member failed; the write is reported with paths |
| Chair answer has no dissent section when positions differ | Built-in check FAIL, retryable |

## 5. Design notes

- Round 0 blind and rounds opt-in follow R-061 K2 and K4: most of the benefit of debate comes from independent answers combined, and rounds invite conformity.
- Members ask for dissent explicitly because withheld dissent removes the gain of discussion (R-061 K5).
- The engine records per round how many members changed position, so the audit can show whether rounds pay ([ARC](56-audit-rule-catalog.spec.md) `council-rounds-no-gain`).
- Judge panels stay deferred ([JCL §5](50-judge-calibration.spec.md)); a council feeds one calibratable judge.
- Any of the four executors can host members, chairs and the judge; nothing in a council needs a capability a plain step does not.

## 6. Acceptance criteria

- [ ] CNL-AC-1 Every row of §2.6 has a fixture workflow that fails validation with its own finding code.
- [ ] CNL-AC-2 A source test shows no model call in the tally or Borda code.
- [ ] CNL-AC-3 Every row of the CNL-B3 table holds offline with scripted members.
- [ ] CNL-AC-4 A crash after two of three round-0 members finish resumes with one member session, not three.
- [ ] CNL-AC-5 No round-0 prompt contains another member's text (prompt-capture test).
- [ ] CNL-AC-6 The run detail shows members, rounds, changes per round, the tally and the outcome ([RDD](31-run-detail-document.spec.md)).

## Open questions

| Question | Owner |
|---|---|
| Should a person's `answer:decision` at a no-decision pause count as a label for calibrating the council's judge? | Owner, with [FBK](41-feedback-and-judge-reliability.spec.md) |

## References

[CON](01-contracts.spec.md) · [CMP](03-compiler-and-flow.spec.md) · [JDG](05-judge-and-verdict.spec.md) · [ADR-0063](../adr/0063-council-is-a-gated-step-with-engine-tallied-outcomes.adr.md) · [R-061](../research/R-061-councils-debate-and-voting.rsrch.md)
