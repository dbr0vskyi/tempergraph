# Check an authored workflow model-free first, then by one consented, capped trial graded by the person

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Blueprint comparison, a literal check, generated tests and a stamp verify an authored workflow without a model; a live run needs the person's consent. The audit exists ([AUD](../specs/workflow-audit.spec.md)). Model-free checks cannot show whether the outcome and its verifications grade the way the person grades.

## Decision

We will check an authored workflow by a ladder that stops at the first failing rung: load and validate, blueprint comparison, literal check, generated tests on stand-ins, coverage and trust, audit, register; then, with the person's yes on the stated cost, each judge graded twice on its criteria's seed examples (a wrong or flipping grade sends the criterion back to the person as unclear, [ADR `judged-criteria-carry-a-scale-and-authoring-guides-to-clarity`](judged-criteria-carry-a-scale-and-authoring-guides-to-clarity.adr.md)), then one capped dry-run trial on a real case whose output the person grades per criterion; then the stamp. The person's grades become labels and calibration cases. The workflow stays in `dev`. Details: [SCF-B18, SCF-B19, SCF-B20, SCF-B21, SCF-B22](../specs/blueprint-and-scaffold.spec.md).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Model-free ladder, then one graded trial (chosen) | Cheap failures first; the first labels arrive on day one | A trial costs money and the person's time |
| Model-free only | Free | Judges and criteria untested against the person |
| A full eval suite before first use | Strong evidence | Needs cases the person does not have yet |

## Decision rationale

| Criterion | Ladder and trial | Model-free only | Full suite |
|---|---|---|---|
| Spend before the first finding | none | none | high |
| Tests grading against the person | once | no | yes |
| Feasible on the day of authoring | yes | yes | no |

## Consequences

- Positive: disagreements between the person and a verifier show up before any real run.
- Negative: one trial is one data point; it is labelled as such.
- Risk: a trial writes outside its worktree. Mitigation: dry run, fresh worktree, cap ([WSP](../specs/workspace-and-concurrency.spec.md)).

## Assumptions

- A $5 default cap fits a first trial of a simple workflow; no data yet.
