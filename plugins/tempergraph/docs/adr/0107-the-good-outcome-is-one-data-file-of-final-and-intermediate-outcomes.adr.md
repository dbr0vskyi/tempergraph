# ADR-0107 The good outcome is one data file of final and intermediate outcomes, each criterion classed by its verifier

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The concept's first line is "start from a definition of a good outcome", but criteria existed only per step ([R-011](../research/R-011-design-gap-review.rsrch.md) G1). The owner wants authoring to define the run-level outcome, find or create verifiable criteria including intermediate ones, and improve them later. People revise criteria after grading outputs ([R-105](../research/R-105-workflow-packages-authoring-and-good-outcomes.rsrch.md) B2).

## Decision

We will keep the good outcome in `outcome.json`: a statement, deliverables, final criteria, one intermediate outcome per unit with its criteria, and for each criterion `verified_by` (`check`, `judge`, `person`, `none` with a reason), its source and the final criteria it serves. Gates get their criteria from it at load. Details: [OUT §2.1 to §2.3](../specs/90-run-outcome.spec.md).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| One data file, gates derive from it (chosen) | One bar for gates, the outcome gate, the loop and evals; revisions are data diffs classified by rule; authoring writes it before any step exists | Criteria leave the declaration code |
| An `OutcomeSpec` in the Python declaration, criteria stay per gate | One place for everything | The final and intermediate outcomes and their links are scattered; a revision edits code |
| Outcome as Markdown in the docs | Readable | The engine would parse prose; drift between text and gates |

## Decision rationale

| Criterion | Data file | In Python | Markdown |
|---|---|---|---|
| Written first in authoring | yes | after the steps | yes |
| Traceability final ↔ intermediate | explicit | implicit | prose |
| Revision classified mechanically | yes | by syntax tree | no |
| No parsing of prose | yes | yes | no |

## Consequences

- Positive: every criterion has a verifier class, so the unverified part of a workflow is a number.
- Negative: older packages with inline criteria keep loading; a criterion id may not be in both places.
- Risk: `serves` links rot. Mitigation: validation and coverage (OUT §2.3, §4).

## Assumptions

- "Further improved" means revised by people first (release 1) and by measured proposals later (release 3).
