---
title: Workflow lessons
type: component
status: review
prefix: LSN
adrs: [0032, 0031, 0016]
---

# Workflow lessons

## 1. Overview

A small, itemised place in a workflow package for what runs have taught one step: general rules such as "read the test command from the plan, not from the repository's README". Lessons are rendered into that step's prompt as their own block. They are workflow content, versioned and reviewed: they change only through a proposal of class `lessons` ([PRP](40-improvement-proposals.spec.md)) and are never rewritten by a run ([ADR-0032](../adr/0032-lessons-are-versioned-workflow-content.adr.md)). The shape follows the itemised, delta-updated playbook of [R-030 F4](../research/R-030-self-improving-agent-systems.rsrch.md), which avoids the collapse that wholesale rewriting causes.

## 2. Contract

### 2.1 Lessons file

One file per step, `lessons/<unit>.json` in the workflow package, with `schema_version` and a list of entries.

| Field | Kind | Rule |
|---|---|---|
| `id` | `L-<n>`, unique in the file | Never reused |
| `text` | one sentence, ≤ 300 characters | A general rule; no id, URL, number from a run, product name or quote (prompt-lint literals check) |
| `status` | `active` \| `retired` | Retired entries are kept, not rendered |
| `source` | `proposal:<id>` \| `person` | |
| `evidence` | `{cluster_id, runs, distinct_requests}` | Counts at the time it was added |
| `added_in`, `retired_in` | workflow versions | |

### 2.2 Rendering

| Rule | Detail |
|---|---|
| Who sees lessons | The step session only. Judges never see lessons; their lens is the criteria ([ADR-0031](../adr/0031-steps-and-their-graders-change-apart.adr.md)) |
| Where | A `Lessons` block after the tools block of [PRM](04-prompt-rendering.spec.md), active entries in id order, each with its id |
| Budget | At most 12 active entries and 2,500 characters per step; validation fails beyond it |
| Digest | The rendered block's digest is recorded beside the template digest on every `agent_run` ([OBS](15-observability-and-cost.spec.md)), so reports split by lessons version |
| Executors | Plain text in the prompt on every executor; nothing is written to an executor's instruction files ([ADR-0016](../adr/0016-portable-authoring-surface.adr.md)) |

### 2.3 Allowed changes

| Change | In one proposal |
|---|---|
| Add one entry | yes, with its cluster as evidence |
| Edit one entry's text | yes; the old text is kept in git history only |
| Retire one entry | yes |
| More than two entries at once, or a reorder | refused `lessons_rewrite` |
| Add an entry that restates a criterion | refused `lesson_is_criterion` when its text matches a criterion of the same step (normalized word overlap ≥ 0.8) |

## 3. Behaviours

**LSN-B1 Rendered to the step only.** Given a step with two active and one retired lesson, when the step and its judge are rendered, then the step prompt holds the two active entries with their ids, and the judge prompt holds none.

**LSN-B2 Budget enforced.** Given a lessons file with 13 active entries, when the workflow is validated, then validation fails naming the file and the count.

**LSN-B3 Delta only.** Given a proposer patch that rewrites five entries, when classified, then it is refused `lessons_rewrite` and nothing is trialled.

**LSN-B4 Retire by trial.** Given a step at the entry budget, when a person proposes retiring an entry, then the proposal is of class `lessons`, its trial's target is the step's first-pass yield, and a `not_shown` or `shown_better` decision with guards holding is enough to retire it (no loss shown).

**LSN-B5 Lessons version is visible.** Given two runs of one workflow version whose lessons digests differ (a local edit), when the report runs, then their rows are split by lessons digest and the local edit is flagged `unreleased_lessons`.

## 4. Error conditions

| Condition | Result |
|---|---|
| A lessons file for a unit the workflow does not declare | Validation fails |
| A literal in an entry | Validation fails (prompt lint) |
| A malformed file | Validation fails; a run never starts with half-read lessons |

## 5. Design notes

- Retiring needs only "no loss shown", while adding needs "better shown" through the trial rule of [PRP](40-improvement-proposals.spec.md): the budget then trends toward entries that earn their place.
- A lesson is the cheapest producer-side change: no template edit, one sentence, easy to review and to revert. A lesson that grows into a procedure should become a template change or a split step instead.

## 6. Acceptance criteria

- [ ] LSN-AC-1 No judge prompt of a fixture workflow with lessons contains any lesson text.
- [ ] LSN-AC-2 Validation fails each planted defect of the fixture set (budget, literal, unknown unit, rewrite).
- [ ] LSN-AC-3 Every `agent_run` of a step with lessons carries the lessons digest.

## Open questions

| Question | Owner |
|---|---|
| Should a lesson be scoped to one executor (a fact about `agy`'s shell, say)? Assumed no in the first release; an executor fact belongs in the executor mapping, not in a workflow. | Owner |

## References

[PRM](04-prompt-rendering.spec.md) · [PRP](40-improvement-proposals.spec.md) · [WFM](02-workflow-model.spec.md) · [R-030](../research/R-030-self-improving-agent-systems.rsrch.md)
