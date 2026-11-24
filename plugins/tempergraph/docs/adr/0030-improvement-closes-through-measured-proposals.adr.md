# ADR-0030 Improvement closes through measured proposals that a person merges

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The loop of [SIL](../specs/16-self-improvement.spec.md) ends at an issue. Such a loop detects well, but its bottleneck is what comes after: a person chooses every issue, writes every brief and merges every fix, and loop-filed issues wait for an owner ([R-031 F1](../research/R-031-self-improvement-gap-analysis.rsrch.md), G1 and G5). Public systems that improve themselves either draft and score changes against a dataset (DSPy, GEPA, AFlow) or modify their own code, and the latter were seen gaming their own evaluator ([R-030 F1, F5](../research/R-030-self-improving-agent-systems.rsrch.md)). The owner asked for a self-improvement design that works end to end.

## Decision

We will extend the loop from diagnosis to a **proposal**: one small, typed change to one workflow package, drafted by a gated proposer workflow or by a person, classified by the engine, measured in a **trial** against the current version on a fixed case set, and delivered as a **draft pull request** with the trial report. Autonomy is a per-workflow ladder (`record`, `file`, `propose`, `trial`), default `file`. No level merges, and the loop drafts no engine code ([PRP](../specs/40-improvement-proposals.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Measured proposals, person merges (chosen) | Closes the loop; every change carries evidence; a person stays the decider | Trials cost money; needs a case set per workflow |
| Keep issues only | Cheapest; no new trust | The bottleneck after the issue stays; drafted remedies are prose nobody tested |
| Proposals without trials | Cheap | A reviewer cannot tell a fix from noise; figures per version move with the issue mix |
| Automatic merge after a passing trial | Fastest | Small trials confirm only large effects (R-031 F3); a self-scored loop games its gates (R-030 F5); against "the loop closes through a person" |
| Search over many candidates per cluster | Higher ceiling (GEPA, AFlow) | N times the trial cost; deferred until one-candidate trials show value |

## Decision rationale

| Criterion | Chosen | Issues only | No trials | Auto-merge | Search |
|---|---|---|---|---|---|
| Closes the loop | yes | no | partly | yes | yes |
| Evidence with every change | yes | no | no | yes | yes |
| A person decides | yes | yes | yes | no | yes |
| Bounded cost | yes (caps) | yes | yes | yes | no |

## Consequences

- Positive: a reviewer gets a patch, a rule sentence and paired results instead of an issue; the post-release watch (SIL-B5) extends to every merged proposal.
- Negative: each workflow needs a reviewed case set before trials; trials of large workflows cost hundreds of dollars. Mitigation: `propose` works without trials, and caps apply per trial and per month.
- Risk: reviewers rubber-stamp `shown_better`. Mitigation: the report shows in-sample pairs apart, the noise floor and guard margins, and a weakening is labelled on the pull request.

## Assumptions

- The owner wants the loop to stay human-merged in the first release, on the principle "the loop closes through a person, never around one".
- Workflow packages live in a repository where a draft pull request can be opened.

## Revisit when

Ten proposals have been merged and held after release, or the issue backlog stops shrinking with proposals on.
