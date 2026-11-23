# ADR-0058 Upgrade a workflow by deterministic transforms first, and a built-in gated workflow for what needs judgement

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner asked for a command that upgrades a workflow and noted it needs a model. Some breaking changes need answers only the owner has, such as a new judge brief or criterion, and a guessed one passes the check and judges badly ([R-056](../research/R-056-automated-and-model-assisted-migrations.rsrch.md) M10). Public practice shows a model can do most migration edits when locations are found deterministically and every edit passes validators in a fixed order, with a person reviewing (M3 to M7). tempergraph already has the rails for a model edit: a step, a check, an independent judge, a derived verdict, budgets and pauses.

## Decision

We will add `tempergraph upgrade <workflow>` ([WUP](../specs/63-workflow-upgrade.spec.md)) that, on a branch of the workflow's source:

1. Plans by detect rules, model-free.
2. Applies engine-shipped transforms, model-free, one commit per changelog entry, oldest release first.
3. Hands the remaining items to a built-in **upgrade workflow** ([UWF](../specs/64-upgrade-workflow.spec.md)): each assisted edit is a gated step; each owner question is a drafted change behind an approval pause; protected paths (criteria, checks, stances) change only through the owner.
4. Never writes an installed copy and never merges.

`upgrade-check` remains as the read-only planning form.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Transforms, then a gated built-in workflow (chosen) | Spends only where judgement is needed; every model edit is checked and independently judged; owner questions stay pauses; visible in status and cost | A built-in workflow to maintain and calibrate |
| Keep detect-and-explain only | No spend; edits nothing | Not what the owner asked; a person makes every edit by hand |
| One unstructured model session edits the package | Least engine work | Self-graded; no deterministic check per edit; drifts into unrelated edits, a measured failure mode (M8) |
| Model edits everything, transforms unused | One path | Spends on renames a rule does exactly; less reproducible |

## Decision rationale

| Criterion | Transforms + gated workflow | Detect and explain | One session | Model for all |
|---|---|---|---|---|
| Does the edits | yes | no | yes | yes |
| No self-grading (C4) | yes | n/a | no | depends |
| Spend only where needed | yes | none | no | no |
| Owner keeps the owner's answers | yes | yes | no | no |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | "Adjust it" means produce the changes for the owner to review and merge, not change what runs on other machines without review. | WUP-B20, WUP-B21 |
| A2 | A default cap of $10 per upgrade's assist run is acceptable; the owner can raise it per call. | UWF-B6, UWF-B5, UWF-B7 |
| A3 | The upgrade workflow's steps run on `claude` by default because its judge needs `restricts_judge_tools`; a workflow may choose another executor in its policy. | UWF-B6, UWF-B5, UWF-B7 |

## Consequences

- Positive: most upgrades can be done by transforms alone; the rest are drafted and judged, and the owner only answers what is theirs.
- Negative: the engine ships and must evaluate a second built-in workflow.
- Risk: a judged edit passes but changes behaviour subtly. Mitigation: verification against the baseline ([ADR-0059](0059-an-upgrade-is-done-when-model-free-checks-pass-against-the-old-baseline.adr.md)) and the opt-in paired trial.

## Revisit when

The first breaking releases show the share of items done by transform, model and person (WUP report), or the upgrade workflow's judge fails calibration.
