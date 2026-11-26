# Council unit

## Purpose

A council puts one question to several model sessions, its members, and combines what they say into one artifact: a synthesis written by a chair, a decision tallied by the engine from votes, or a ranking aggregated from peer ranks. It suits questions with no single checkable answer where several perspectives help: a design choice, a risk call, a go or no-go, a review through several lenses. Members answer blind first; deliberation rounds are opt-in and anonymized; every outcome is derived by rule; and the council's output goes to the gate's one independent judge like any step's ([ADR `council-is-a-gated-step-with-engine-tallied-outcomes`](../adr/council-is-a-gated-step-with-engine-tallied-outcomes.adr.md), [ADR `new-node-kinds-keep-the-gated-unit`](../adr/new-node-kinds-keep-the-gated-unit.adr.md), [research `councils-debate-and-voting`](../research/councils-debate-and-voting.rsrch.md)). A council is a step, never a judge, and any executor can host its members, chair and judge. Workflow authors and the compiler depend on it; design notes are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Depends on

- `ask-unit.spec.md`: ask unit
- `budgets-and-failures.spec.md`: budgets, failures and timeouts
- `compiler-and-flow.spec.md`: what each node does (CMP-B9); order and routes (CMP-B10)
- `contracts.spec.md`: shared contracts
- `independence-guard.spec.md`: independence guard and judge views
- `overview.spec.md`: a step never grades itself (OVR-B6)
- `run-detail-document.spec.md`: run detail document
- `workspace-and-concurrency.spec.md`: shapes of parallel work (WSP-B11)

## Behaviours

### CNL-B9 Declaration

WHEN a unit of kind `council` is declared THE engine SHALL read its `council` field ([CON](contracts.spec.md)) as `CouncilSpec`: `question` (a template, the brief every member gets with the same inputs and references), `members` (2 to 7 `MemberSpec`), `mode` (`synthesize`, `vote` or `rank`), `options` (`vote` only: 2 to 10 slugs, or an artifact key of a list), `rule` (`vote` only: `majority`, `supermajority` of at least two thirds of valid ballots, `unanimous` or `plurality`, default `majority`), `rounds` (0 to 3 deliberation rounds after the blind round 0, default 0), `anonymize` (default true: peers shown as `Member A`, `Member B` in an order fixed per attempt and recorded), `chair` (`ChairSpec` of optional `executor`, `model` and `prompt`, required for `synthesize`), `quorum` (valid answers a round needs, default all members), `on_no_decision` (`escalate`, `retry` or `stop`, default `escalate`), `retry_scope` (`all`, or `chair` keeping members' final positions in `synthesize` and `rank`) and `cost_cap_usd` (per attempt); each `MemberSpec` having a unique slug `name`, `executor` and `model` resolved on the step layer, a `stance` of at most 400 characters, read-only `tools` (never `edit`, `write`, `shell` or a writing MCP tool), and optional `timeout_s` and `idle_s`.

- GIVEN a `synthesize` council of two members with a chair, a question and a judged gate WHEN validated THEN it validates with no `error` finding
- GIVEN a council with a member granted `edit` WHEN validated THEN it is refused

### CNL-B10 Produced artifacts

WHEN a council attempt ends THE engine SHALL produce, keyed by the unit, `decision` (the chair's answer, or for a chairless `vote` or `rank` the engine-written outcome), `positions` (each member's final answer and its round history, under labels) and `tally` (`vote` and `rank`: the counts, the rule and the outcome).

- GIVEN a chairless `vote` council WHEN it ends THEN `decision` is the engine-written outcome

### CNL-B11 Member answer block

WHEN a member answers THE engine SHALL parse the fenced JSON block that ends its free text, like a judgement block ([CON](contracts.spec.md)), with `position` (one line), `choice` (`vote`: one of `options` or `abstain`), `ranking` (`rank`: peer labels best first, never its own), `confidence` (in [0,1]), `changed` and `why_changed` (rounds 1 and later), and `dissent` (rounds 1 and later and the chair: where the author still disagrees, empty only if it does not), re-ask once on a block that does not parse and count a second failure as a spoiled answer against the quorum.

- GIVEN a block that fails to parse twice WHEN the round closes THEN the answer is spoiled and counts against the quorum

### CNL-B1 Blind first round

WHEN round 0 runs THE engine SHALL give each member the question and its own stance and no other member's text, label, executor or model.

- GIVEN a council of three members WHEN round 0 runs THEN no prompt contains another member's text

### CNL-B2 Anonymized rounds

WHEN a deliberation round runs with `anonymize: true` THE engine SHALL show each member the others' previous answers as `Member A`, `Member B` (its own omitted) in the order recorded for the attempt, and require `changed`, `why_changed` and `dissent`.

- GIVEN `rounds: 1` WHEN round 1 runs THEN each member sees the others' round-0 answers under labels and must fill `changed`, `why_changed` and `dissent`

### CNL-B12 Modes and outcome

WHEN a council's outcome is derived THE engine SHALL derive it as follows: for `synthesize` (n × (r + 1) member sessions and 1 chair), take the chair's answer, its dissent section required when any member's final position differs and its absence a retryable built-in check FAIL; for `vote` (n × (r + 1), plus 1 if a chair writes the rationale), tally final-round `choice`s by `rule`, abstentions and spoiled ballots not counting as votes; and for `rank` (n × (r + 1) plus n ranking passes, plus 1 chair), take a Borda count over peer rankings (k−1 points for first of k), ties broken by mean member confidence then label order; and record per round how many members changed position.

- GIVEN a chair answer without dissent while positions differ WHEN checked THEN the built-in check fails and the attempt may retry

### CNL-B3 Tally by rule

WHEN a `vote` council's final ballots are counted THE engine SHALL write `tally` and the outcome, no model reading the ballots to decide.

- GIVEN options `ship`, `hold` and 3 ship, 2 hold under `majority` WHEN tallied THEN the outcome is `ship`
- GIVEN 3 ship, 2 hold under `supermajority` WHEN tallied THEN the outcome is `no_decision`
- GIVEN 2 ship, 2 hold, 1 spoiled, quorum 4, under `majority` WHEN tallied THEN the outcome is `no_decision` (tie)
- GIVEN 2 ship, 1 hold, 2 abstain under `plurality` WHEN tallied THEN the outcome is `ship`
- GIVEN 4 ship, 1 spoiled, quorum 5, under `majority` WHEN tallied THEN the outcome is `no_decision` (quorum)

### CNL-B13 No decision

WHEN a `vote` misses its rule, a round misses its quorum, or a `rank` ties exactly after both breaks THE engine SHALL give outcome `no_decision` and, with `on_no_decision: escalate`, pause with kind `escalation` showing `positions` and `tally` and accept `answer:decision=<option>` from a person ([ASK](ask-unit.spec.md) decision grammar), recorded as `chosen_by = person`; with `retry` charge the retry budget and run the council again; with `stop` stop.

- GIVEN `no_decision` and `escalate` WHEN a person answers `answer:decision=hold` THEN the decision is `hold` with `chosen_by = person`

### CNL-B14 Compilation

WHEN a council compiles THE compiler SHALL make its step node a subgraph of one member node dispatch per round and member, an engine-owned round barrier that waits for every member's answer, failure or spoil, a pure tally node and the chair node, checkpoint each member session on its own so a crash resumes only unfinished sessions, use the unit's usual judge, gate and human nodes ([CMP-B9](compiler-and-flow.spec.md)), use session kinds `member`, `member_reask` and `chair` with keys `<unit>.<attempt>.member.<name>.<round>` and `<unit>.<attempt>.chair`, and run members in the run's worktree read-only, fingerprinted before and after like parallel branches ([WSP-B11](workspace-and-concurrency.spec.md)), a member that changed the workspace failing with the written paths reported.

- GIVEN a crash after two of three round-0 members finish WHEN resumed THEN one member session runs

### CNL-B15 Member failures

WHEN a member session fails on infrastructure THE engine SHALL count it missing for the round and still close the round, below quorum giving `no_decision`, and when every member fails on infrastructure end the attempt as an infra failure ([BUD](budgets-and-failures.spec.md)), never a pause.

- GIVEN every member failing on infrastructure WHEN the round closes THEN the attempt is an infra failure and no pause is raised

### CNL-B16 What is refused

WHEN a workflow with a council is validated THE engine SHALL refuse with an `error` fewer than 2 or more than 7 members or two with one name; a member tool the engine catalog does not hold read-only ([GRD](independence-guard.spec.md)); `synthesize` without a chair; `vote` without options or with fewer than 2; `options` from an artifact no earlier unit produces; `rule` or `options` outside `vote`; `retry_scope: chair` with `vote`; a council in a map item or in a parallel branch whose block is a writer; and no judge on the council's gate (OVR-B6); and SHALL warn on every member bound to one model family (audit `council-one-family`), `rule: majority` with an even member count, and `rounds > 0` with `anonymize: false`.

- GIVEN `synthesize` without a chair WHEN validated THEN it is refused with its own finding code

### CNL-B4 Judge grades the council

WHEN a council's gate runs THE gate SHALL judge `decision` as the subject with `positions` among the references, in a fresh read-only judge session that is none of the members.

- GIVEN a `synthesize` council WHEN its gate runs THEN a criterion such as "the decision states every dissent" is gradable

### CNL-B5 Route on a decision

WHEN a switch after a council reads `tally.outcome` THE engine SHALL pick the arm by that value with no model call ([CMP-B10](compiler-and-flow.spec.md)).

- GIVEN a switch on `tally.outcome` WHEN the gate passes THEN the arm is picked with no model call

### CNL-B6 Mixed executors

WHEN a council's members name different executors THE preflight SHALL check each member's alias and tools against its own executor, refuse any gap with exit 2, and resolve the chair and the judge on their own layers.

- GIVEN members on `claude`, `antigravity` and `messages-api` WHEN preflighted THEN each is checked against its own executor

### CNL-B7 Chair-only retry

WHEN a judge RETRY's unmet blockers concern the synthesis under `retry_scope: chair` THE engine SHALL run only the chair session, with the judge's notes, reusing the members' recorded positions.

- GIVEN `retry_scope: chair` and a RETRY WHEN the retry runs THEN only the chair session runs

### CNL-B8 Cost cap

WHEN the members' reported cost reaches `cost_cap_usd` during an attempt THE engine SHALL start no new member session, let running ones finish, and end the attempt `cap_reached` ([BUD](budgets-and-failures.spec.md)).

- GIVEN `cost_cap_usd: 2` reached during round 1 WHEN capped THEN no new session starts and the attempt ends `cap_reached`

## Acceptance criteria

- CNL-AC1 (CNL-B16, CNL-B9): A well-formed council validates with no `error` finding, and every refusal of CNL-B16 has a fixture workflow that fails validation with its own finding code
- CNL-AC2 (CNL-B3, CNL-B12, CNL-B5): A source test shows no model call in the tally or Borda code
- CNL-AC3 (CNL-B3, CNL-B13, CNL-B11, CNL-B15): Every scenario of CNL-B3 holds offline with scripted members
- CNL-AC4 (CNL-B14): A crash after two of three round-0 members finish resumes with one member session, not three
- CNL-AC5 (CNL-B1, CNL-B2): No round-0 prompt contains another member's text (prompt-capture test)
- CNL-AC6 (CNL-B10, CNL-B12): The run detail shows members, rounds, changes per round, the tally and the outcome ([RDD](run-detail-document.spec.md))
- CNL-AC7 (CNL-B4, CNL-B6, CNL-B7, CNL-B8): Fixtures cover the judge's subject and references, a mixed-executor preflight refusal, a chair-only retry and a cost cap mid-round, both the council's own `cost_cap_usd` and the run's cost cap through the reservations of [BUD-AC13](budgets-and-failures.spec.md) and BUD-AC14

## Open questions

- Should a person's `answer:decision` at a no-decision pause count as a label for calibrating the council's judge? Owner: owner, with [FBK](feedback-and-judge-reliability.spec.md).
