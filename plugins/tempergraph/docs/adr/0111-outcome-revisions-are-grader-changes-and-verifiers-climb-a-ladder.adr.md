# ADR-0111 Outcome revisions are grader-side changes; weakening is a person's act and verifiers climb a measured ladder

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The good outcome must improve after authoring. Grader changes are already apart from producer changes, and weakening is person-only ([ADR-0031](0031-steps-and-their-graders-change-apart.adr.md)). Judges are trusted only when accepted on labels ([ADR-0045](0045-judges-accepted-on-labelled-error-rates.adr.md)). The owner's lifecycle is less human-in-the-loop over time ([ADR-0089](0089-supervision-is-a-promotion-and-improvement-measure.adr.md)).

## Decision

We will revise `outcome.json` only as a recorded revision with origin and evidence, classed from parsed files as strengthening, weakening or neutral. A weakening, including moving a verifier down, needs a person. A verifier moves up from `none` to `person` to `judge` to `check` only with evidence: an accepted judge for `person → judge`, fixtures and replayed agreement for `judge → check`. Candidates are read model-free from rulings, escapes, declined sign-offs, unverified rates and sign-offs that always pass. Release 1 revises through the authoring skill; the improvement loop proposes class `outcome` from release 3. Details: [OUT-B20, OUT-B21](../specs/90-run-outcome.spec.md).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Recorded revisions, person-only weakening, measured ladder (chosen) | No gaming path; supervision falls as verifiers move up on evidence | Slower than letting the loop edit criteria |
| Free edits by the owner | Simple | Measures compare across silent changes |
| Loop rewrites criteria from failures | Fast | Fits the bar to the failing runs; weakening by the back door |

## Decision rationale

| Criterion | Ladder | Free edits | Loop rewrites |
|---|---|---|---|
| Measures comparable across revisions | yes | no | no |
| Weakening visible | yes | no | no |
| Lowers supervision over time | by evidence | by hand | unsafely |

## Consequences

- Positive: "less human-in-the-loop" becomes person criteria moving to judges and checks, each step backed by data.
- Negative: a reworded criterion stales its calibration score.
- Risk: thresholds (20 runs, 10 replays) are guesses. Mitigation: they are recorded loop parameters ([IMD](../specs/43-improvement-data.spec.md)).

## Assumptions

- The thresholds are defaults with no data behind them.
