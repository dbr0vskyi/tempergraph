# Workflow lessons

## Purpose

A small, itemised place in a workflow package for what runs have taught one step: general rules such as "read the test command from the plan, not from the repository's README". Lessons are rendered into that step's prompt as their own block. They are workflow content, versioned and reviewed: they change only through a proposal of class `lessons` ([PRP](improvement-proposals.spec.md)) and are never rewritten by a run ([ADR `lessons-are-versioned-workflow-content`](../adr/lessons-are-versioned-workflow-content.adr.md)). The shape follows the itemised, delta-updated playbook of [research `self-improving-agent-systems`](../research/self-improving-agent-systems.rsrch.md) F4, which avoids the collapse that wholesale rewriting causes. A lesson is the cheapest producer-side change: one sentence, easy to review and to revert; a lesson that grows into a procedure should become a template change or a split step. Retiring needs only "no loss shown" while adding needs "better shown", so the budget trends toward entries that earn their place. Workflow authors, the proposer and the reports depend on it.

## Behaviours

### LSN-B6 Lessons file

WHEN a workflow package holds `lessons/<unit>.json` THE engine SHALL read `schema_version` and a list of entries, each with `id` (`L-<n>`, unique in the file, never reused), `text` (one sentence of at most 300 characters stating a general rule), `status` (`active` or `retired`, retired entries kept and not rendered), `source` (`proposal:<id>` or `person`), `evidence` (`cluster_id`, `runs`, `distinct_requests` at the time it was added), `added_in` and `retired_in` (workflow versions), and fail `validate` with `lessons-unknown-unit` for a unit the workflow does not declare, `lessons-malformed` for a malformed file (a run never starts with half-read lessons), and `lessons-id`, `lessons-text`, `lessons-status` or `lessons-source` for a bad field.

- GIVEN a lessons file for an undeclared unit WHEN validated THEN it fails `lessons-unknown-unit`

### LSN-B7 No literals in a lesson

WHEN a lesson's text holds a ticket id (`ABC-12`), a URL, an e-mail address, an absolute path, a number of three or more digits, or a quote of four or more words THE engine SHALL fail `validate` with `lessons-literal`, a product name being left to review.

- GIVEN a lesson naming `https://example.com` WHEN validated THEN it fails `lessons-literal`

### LSN-B8 Rendering

WHEN a step's prompt is rendered THE engine SHALL add a block headed "Lessons from earlier runs" after the tools block ([PRM](prompt-rendering.spec.md)) with the active entries in id order, each with its id, as plain text on every executor, writing nothing to an executor's instruction files ([ADR `portable-authoring-surface`](../adr/portable-authoring-surface.adr.md)), and record the block's digest (the first 16 hex of its SHA-256) as `lessons_digest` beside the template digest on the step's `agent_run` ([OBS](observability-and-cost.spec.md)); judges never see lessons, their lens being the criteria ([ADR `steps-and-their-graders-change-apart`](../adr/steps-and-their-graders-change-apart.adr.md)).

- GIVEN a step with lessons WHEN its `agent_run` is recorded THEN it carries `lessons_digest`

### LSN-B1 Rendered to the step only

WHEN a step with two active and one retired lesson and its judge are rendered THE engine SHALL put the two active entries with their ids in the step prompt and none in the judge prompt.

- GIVEN two active and one retired lesson WHEN rendered THEN the step prompt holds two and the judge prompt none

### LSN-B2 Budget enforced

WHEN a workflow whose lessons file holds more than 12 active entries or more than 2,500 characters for one step is validated THE engine SHALL fail with `lessons-budget` naming the file and the count.

- GIVEN 13 active entries WHEN validated THEN it fails naming the file and 13

### LSN-B9 Allowed changes

WHEN a `lessons` proposal is classified THE engine SHALL allow in one proposal adding one entry with its cluster as evidence, editing one entry's text (the old text kept in git history only) or retiring one entry, refuse `lessons_rewrite` for more than two entries at once, a reorder, or an entry removed instead of retired, and refuse `lesson_is_criterion` for an entry whose shared lowercase words over the smaller word set with a criterion of the same step reach 0.8.

- GIVEN a patch that deletes an entry WHEN classified THEN it is refused `lessons_rewrite`
- GIVEN a lesson restating a criterion of its step in fewer words WHEN classified THEN it is refused `lesson_is_criterion`

### LSN-B3 Delta only

WHEN a proposer patch that rewrites five entries is classified THE engine SHALL refuse it `lessons_rewrite` and trial nothing.

- GIVEN five entries rewritten WHEN classified THEN it is refused and nothing is trialled

### LSN-B4 Retire by trial

WHEN a person proposes retiring an entry of a step at the entry budget THE engine SHALL classify it `lessons`, target the trial at the step's first-pass yield, and retire it on a `not_shown` or `shown_better` decision with guards holding.

- GIVEN a retirement trial decided `not_shown` with guards holding WHEN it ends THEN the entry may be retired

### LSN-B5 Lessons version is visible

WHEN the report runs over two runs of one workflow version whose lessons digests differ THE engine SHALL split their rows by lessons digest and flag the local edit `unreleased_lessons`.

- GIVEN a local lessons edit WHEN reported THEN its rows are flagged `unreleased_lessons`

## Acceptance criteria

- LSN-AC1 (LSN-B1, LSN-B8): No judge prompt of a fixture workflow with lessons contains any lesson text
- LSN-AC2 (LSN-B2, LSN-B6, LSN-B7, LSN-B9, LSN-B3): Validation and the classifier fail each planted defect of the fixture set (budget, literal, unknown unit, rewrite)
- LSN-AC3 (LSN-B8, LSN-B5): Every `agent_run` of a step with lessons carries the lessons digest, and reports split by it
- LSN-AC4 (LSN-B4): A retirement trial decided `not_shown` with guards holding retires the entry

## Open questions

- Should a lesson be scoped to one executor (a fact about `agy`'s shell, say)? Until answered: no; an executor fact belongs in the executor mapping, not in a workflow. Owner: owner.
