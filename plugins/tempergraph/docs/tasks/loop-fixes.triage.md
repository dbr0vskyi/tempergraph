# Triage: loop-fixes

## Task

Source: a task file (`loop-fixes.task.md`) kept outside the repository, from research note `plugins/tempergraph/docs/research/does-the-improvement-loop-find-what-a-reviewer-finds.rsrch.md` (F1 to F4). Make the improvement loop find by itself what a run reviewer finds: review targets in priority order, a budget decision from reported spend, a finding for a category kept repeatedly on one unit, a loop summary in `attention` and `status`, and an immediate escalation when a check fails with the same evidence twice. Documents live under `plugins/tempergraph/docs/`; the engine names no workflow package (ADR `the-engine-names-no-workflow`).

## Acceptance criteria

1. Review targets are read in priority order, not run order: first the sessions of a unit whose gate failed its check, sent the run back, escalated or paused, the later attempts before the earlier ones; a target dropped for budget is always one of lower priority than every target read.
2. The budget decision before each review uses the review spend reported so far in the run and an estimate for the next review no higher than the mean reported cost of the reviews already done in the run (when there is one); with the research `does-the-improvement-loop-find-what-a-reviewer-finds` figures (12 reviews at 0.66 USD against a 3.46 USD cap) no target is skipped.
3. When the same review category is kept on the same unit in at least three reviewed sessions of one run, the loop records one finding for it (unit, category, the session keys, no note text) that appears in `tempergraph improve backlog` and corroborates like a model-free finding; filing rules for issues are otherwise unchanged (a review still never files alone across runs). The decision is written down: update ADR `review-observations-are-candidates-corroborated-before-they-file` or write a decision record that refines it.
4. After the loop child of a thread finishes, `tempergraph attention` and the thread's `tempergraph status` detail show a short loop summary: findings recorded and filed, and the top three kept observations by confidence (category, unit, confidence), with no note text.
5. When a unit's check fails with the same evidence on two attempts in a row although the step changed files in between, the gate stops retrying: it escalates at once with a cause that names the repeated failure, spends no further retry, and the run's findings carry that cause; a check failure that changes between attempts keeps the normal retries.
6. Each criterion above has an offline test (stand-in executor or fixture loop records) that carries the spec criterion id it proves, the edited specs and the decision record say what the code does, and the engine's offline suite and `ruff check src tests` pass.

## Existing documents

- `plugins/tempergraph/docs/specs/session-review.spec.md`: review plans (SRV-B15, SRV-B16, SRV-B21), budget caps dropping targets by signal priority (SRV-B21, run-order within a plan unstated), corroboration and filing (SRV-B7); says nothing about reading order of failed-gate attempts, a per-review estimate from the mean of reports, or a finding for a repeated category
- `plugins/tempergraph/docs/specs/self-improvement.spec.md`: loop child (SIL-B17), review observations corroborate (SIL-B16), filing by attribution (SIL-B18), uncalibrated stays local (SIL-B7); says nothing about a loop summary or a repeated-category finding
- `plugins/tempergraph/docs/specs/budgets-and-failures.spec.md`: retry counters and causes that escalate at once (BUD-B11); has no cause for the same check evidence repeating
- `plugins/tempergraph/docs/adr/review-observations-are-candidates-corroborated-before-they-file.adr.md`: reviews are candidates filed only when corroborated; to be updated or refined by task criterion 3
- `plugins/tempergraph/docs/specs/improvement-proposals.spec.md`: improve backlog and clusters (PRP); mentions `improve backlog`
- `plugins/tempergraph/docs/specs/orchestration.spec.md`: `attention` command; has no loop summary
- `plugins/tempergraph/docs/research/does-the-improvement-loop-find-what-a-reviewer-finds.rsrch.md`: evidence and conclusions behind the task

## Gaps

- G1 spec update: priority order of review targets (criterion 1). SRV-B16 and SRV-B21 only order by signal priority at the cap; searched `docs/specs/` for "later attempt", "priority", "run order": no behaviour or criterion states attempts of failed or paused units first, later before earlier
- G2 spec update: review budget estimate from reported spend (criterion 2). SRV-B21 names caps but not the estimate rule; searched `docs/specs/` for "mean", "reported cost", "estimate" with review: no behaviour states it
- G3 spec update: finding for a category kept in three sessions of one run (criterion 3). Searched `docs/specs/` and `docs/adr/` for "three reviewed sessions", "same category", "kept on the same unit": nothing; SRV-B7 only corroborates model-free findings
- G4 spec update: loop summary in `attention` and thread `status` (criterion 4). Searched `docs/specs/` for "loop summary", "kept observations" with attention and status: nothing in SIL, SRV or ORC
- G5 spec update: immediate escalation on the same check evidence twice (criterion 5). Searched `docs/specs/budgets-and-failures.spec.md` for "same evidence", "repeated failure", "escalate": BUD-B11 lists causes, none for repetition
- G6 decision needed: refine ADR `review-observations-are-candidates-corroborated-before-they-file` on a repeated review category recording a finding (criterion 3). The ADR says a review never files alone; searched `docs/adr/` for "three sessions", "repeated category": nothing

## Route

- Deliver: code
- Route: discovery
