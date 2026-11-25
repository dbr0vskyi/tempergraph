# Judged criteria carry a scoring scale with seeds; authoring guides the person until every criterion is clear

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner wrote on 2026-11-20: "We need also to check if judges define clear criteria and scoring system when the workflow is created based on the definition of good outcome. In case the definition from the user is not enough to extract criteria, we should guide the user, provide examples, clarifying questions to be able to extract criteria." The engine fixes the statuses and the verdict rule ([JDG-B13](../specs/judge-and-verdict.spec.md)), but a criterion's text and check method alone leave the line between MET, PARTIAL and UNMET to the judge, and a judge left to draw that line tends to report a confidence that only mirrors its verdict. People find criteria by grading outputs ([research `workflow-packages-authoring-and-good-outcomes`](../research/workflow-packages-authoring-and-good-outcomes.rsrch.md) B2).

## Decision

We will:
- require every judged criterion to carry a **scale**: what `met`, `partial` and `unmet` look like for that criterion, the evidence `met` needs, when N/A applies, and seed fixtures for at least one passing and one failing grade ([OUT-B11](../specs/run-outcome.spec.md));
- run a model-free **criteria lint** and an outcome **sufficiency check** during authoring, and keep a phase open until they pass ([AUT-B19, AUT-B20, AUT-B21](../specs/workflow-authoring.spec.md));
- answer every lint finding with a fixed **guidance ladder**: clarifying questions, examples of criteria for the task kind, a contrast pair, a graded draft, then a recorded decision;
- check, before the first trial, that each judge grades its seeds as expected twice in a row ([SCF-B18, SCF-B19, SCF-B20, SCF-B21, SCF-B22](../specs/blueprint-and-scaffold.spec.md) rung 8).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Per-criterion scale, lint, guidance ladder, seed check (chosen) | The scoring line is the author's, written once; unclear criteria are caught before a run and fixed with the person | More for the person to confirm per judged criterion |
| A numeric score per criterion (1 to 5) | Finer grades | The engine derives verdicts from statuses, not numbers; numeric scales drift between judges |
| Trust the judge to infer the line from the text | Nothing to write | Two judges grade the same output differently; the first trial is the first evidence |
| Generate criteria from the description with a model and accept them | Fast | Criteria the person never confirmed; the drift appears in production |

## Decision rationale

| Criterion | Scale and ladder | Numeric | Judge infers | Generated |
|---|---|---|---|---|
| Same output graded the same | yes, checked by seeds | partly | no | no |
| Fits the engine's verdict rule | yes | no | yes | yes |
| Thin definitions get help, not guesses | yes | no | no | no |
| Cost before the first run | judge calls on seeds | none | none | one model call |

## Consequences

- Positive: every judged criterion arrives at its first run with a stated line and two labelled examples, which are also its first calibration cases ([JCL](../specs/judge-calibration.spec.md)).
- Negative: authoring takes longer for workflows with many judged criteria. Mitigation: the skill drafts scales from the examples and the person edits.
- Risk: the vague-word list flags fine text. Mitigation: a finding the person overrides is a recorded decision and is not raised again.

## Assumptions

- "Scoring system" means the per-criterion meaning of the engine's fixed statuses, not a new numeric score.
- An example library of criteria per task kind ships with the authoring skill as reference files.
