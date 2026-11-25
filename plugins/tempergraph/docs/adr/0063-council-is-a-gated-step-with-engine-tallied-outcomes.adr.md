# ADR-0063 A council is a gated step: blind members, opt-in anonymized rounds, an engine tally or a chair, one independent judge

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner asked for a council node. A council puts one question to several model sessions and combines what they say. Public work ([R-061](../research/R-061-councils-debate-and-voting.rsrch.md)) finds that independent answers plus a vote give most of the benefit of debate (K2), that diversity matters (K3), that members conform to majorities (K4) and withhold dissent (K5), and that agreement is not correctness (K6). The design already defers a panel of voting **judges** until single judges are calibrated ([JCL-B9](../specs/judge-calibration.spec.md)).

## Decision

We will add a unit kind **`council`** ([CNL](../specs/council-unit.spec.md)):

1. **Members** (2 to 7) are fresh, read-only sessions, each with its own executor, model alias and stance. Round 0 is blind: no member sees another's answer.
2. **Modes.** `synthesize` (a chair session writes one answer and a dissent section), `vote` (members choose among declared options; the engine tallies by a declared rule) and `rank` (members rank each other's anonymized answers; the engine aggregates by Borda count; a chair may write from the top answer).
3. **Rounds** of deliberation are opt-in (`rounds` 0 to 3, default 0). In a round, peers are shown under neutral labels, and each member states whether it changed position, why, and where it still disagrees.
4. **Outcomes by rule.** A tie or a missed rule is `no_decision`: by default a pause for a person, who answers with an option.
5. **The gate is unchanged.** The council's output goes to the gate's check and its one independent judge, which is not a member. A council is never a judge, and a judge panel stays deferred.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Council as a gated step (chosen) | Combines perspectives where the work needs it; keeps one calibratable judge; works with routes (a route reads the tally) | N+1 sessions per attempt |
| Council as a judge panel | Directly "more reliable judging" | Agreement is not correctness (K6); defeats per-judge calibration; JCL deferred it |
| Debate by default (several rounds) | Matches "deliberation" | Most gain is from the vote (K2); conformity (K4) can make it worse; cost grows per round |
| Model aggregator for votes | Handles free-text ballots | A model would decide an outcome, against C4's rule |
| Hand-wired parallel branches plus a synthesis step | No new kind | Branches cannot see each other for rounds; tally, anonymity and quorum must be rebuilt per workflow |

## Decision rationale

| Criterion | Gated step | Judge panel | Debate default | Model tally | Hand-wired |
|---|---|---|---|---|---|
| Outcome by rule | yes | partly | yes | no | per author |
| Keeps judge calibration meaningful | yes | no | yes | yes | yes |
| Cost at default | N+1 sessions | N judges per gate | N×(r+1)+1 | N+2 | N+1 |
| Evidence base (R-061) | K2, K3, K7 | K6 against | K2, K4 against | — | — |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| C1 | "Council" means several members deliberating or voting on one question, with a combined verdict out, as the coordinator read the owner's ask. | CNL |
| C2 | Members need read access only; work that changes files is a contest, not a council. | CNL-B9, CNL-B10, WSP |
| C3 | Model family can be read from each executor's binding table (a `family` label per bound alias). | CNL-B9 to CNL-B16, audit rule `council-one-family` |

## Consequences

- Positive: design reviews, risk calls, go/no-go decisions and multi-lens reviews become one declared unit with recorded positions, tallies and dissent. A route can branch on a council's decision with no model in the edge.
- Negative: a council costs members × (rounds + 1) + chair sessions per attempt; cost projection and a per-attempt cap are required.
- Risk: a confident but wrong majority. Mitigation: blind round 0, anonymity, diversity warning, the independent judge, and the audit's measurement of whether rounds change outcomes.

## Revisit when

Judge calibration data show a gate that one judge cannot pass on any model (then a judge panel is reconsidered), or the audit shows rounds never change a tally.
