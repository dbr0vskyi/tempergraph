# A quick-lane run takes no review

## Context

A review costs about 120,000 to 170,000 tokens, and sending a defect it finds back after the run has ended cost a second run each time, 11.58 and 7.80 USD (the task text, `batch-queue/tasks/i173.md`). The task asks for a lane or a size of change under which the review does not run, with its reason, and leaves the choice to the run. No owner decision of the triage note covers it.

What the package holds today, read in it:

- The quick lane is the lane of a small fix: no gap, no spec to change, at most 3 acceptance criteria, at most 2 code files beside their tests, and at most 200 changed lines (`workflow/temperspec/specfmt.py` line 39, the quick lane of [the task-notes rule](../../rules/task-notes.rule.md)). Its path is triage, then the code step; it has no plan step and no discovery.
- The code gate measures the change afterwards. A spec or decision record changed, a file the note does not name, more than 2 code files or more than 200 changed lines sends the run back to triage, which plans it, and a run that came back to triage never takes the quick lane again (`workflow/temperspec/checks.py` lines 1423-1448; `tests/test_temperspec.py` lines 648-670). So a run that leaves the lane's size also leaves the lane.
- The lane is a plain value of the triage step, and a route unit reads the values of earlier units (`workflow/temperspec/routing.py` lines 42-50, `RouteView` in `plugins/tempergraph/engine/src/tempergraph/contracts.py` lines 981-987). A route reads no git fact, and a script is given none (see [the decision on independence](review-independence-is-held-by-inputs-and-the-session-record.adr.md)), so a bound on changed lines would need a measure the package has to build.
- A run that reaches the code step by the quick lane has no plan step on its path, so the review could send it back to the code step only ([OGT-B8](../specs/outcome-gate.spec.md) names the same path for the outcome gate).

## Decision

We will skip the review for a run in the quick lane and take it for every other run that passes the code step, as [the spec](../specs/independent-review.spec.md) says (IRV-B2). The lane's own size limits are the bound.

## Options considered

### A. The quick lane (chosen)

For: the bound is a number the code gate already measures and enforces, so no new threshold has to be tuned with no run measured; the review's cost is highest against the smallest change; the value is a plain value a route reads; a run that grows past the lane is planned and then takes the review. Against: a planned run with a very small change still pays for a review; a defect of the kind the task cites in a quick-lane change is not read by an independent reader.

### B. A size of the change itself, in lines or files, whatever the lane

For: the cost follows what is read, in every lane. Against: a number to choose with no run measured; a route cannot read lines or files, so a measure has to be built and kept; the lane already carries the same limits for the smallest changes.

### C. No bound

For: every change is read once. Against: the cost is paid on the smallest changes, where the gates of the lane read the whole change already.

## Consequences

A quick-lane run goes from the code step to the outcome gate as it does today. A planned run takes the review whatever its size. The first live runs of the unit give the cost of a review against the cost of a run, and so the data to choose a size bound in the place of the lane.

Chosen by the discovery step on the task's own words, "a lane or a size of change", and open to change by the owner.

## Revisit when

A live run shows a review that cost more than the change it read, or a quick-lane change that shipped a defect that a review would have found.
