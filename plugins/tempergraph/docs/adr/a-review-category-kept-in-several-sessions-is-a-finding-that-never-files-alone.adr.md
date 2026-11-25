# A review category kept in several sessions of one unit is a finding that never files alone

## Context

[ADR-0119](0119-review-observations-are-candidates-corroborated-before-they-file.adr.md) keeps a session review's observation local: it files nothing on its own and weights only the cluster of a model-free finding on the same unit and run. This record refines ADR-0119 and does not change it. Its decision stands: no issue rests on a model's reading alone.

The first live dev-mode review of a delivery run showed what that rule leaves unseen ([R-160](../research/R-160-does-the-improvement-loop-find-what-a-reviewer-finds.rsrch.md) F2, F4). The loop read 13 sessions for 0.66 USD, and the reviewer met the same problem in several sessions of one unit: every code session broke the command limits, in five sessions at confidence 0.45 to 0.7. No model-free cause named it, so no finding corroborated it. The observations stayed in a local report that a person who does not run `improve review show` never reads, and `improve backlog` showed nothing for them. The two categories that need corroboration (`prompt_misread` and `judge_shallow`, [SRV-B19](../specs/44-session-review.spec.md)) can wait for one indefinitely.

Counting is not reading. How often a category was kept on a unit is arithmetic over observations whose citations the engine has already checked ([SRV-B20](../specs/44-session-review.spec.md)).

## Decision

We will record a review category kept on one unit in at least three sessions of a run as a finding of its own, count that finding as the corroboration of those observations in the way a model-free finding is counted, and let it file nothing, in the run that records it or in any later one. The behaviours are [SRV-B26, SRV-B27 and SRV-B28](../specs/review-repeats.spec.md).

## Options considered

### A. Record a finding at three sessions in one run (chosen)

For: the pattern reaches `improve backlog` and the loop summary in the run that shows it, at no model cost; the cause name shows its trust tier; nothing is filed on one model's reading. Against: three sessions read by one reviewer in one run are persistence, not independent confirmation, and the reviewer's bias repeats in each.

### B. Keep every observation local, as ADR-0119 had it

For: nothing new to maintain, and no reviewer reading can inflate a cluster. Against: R-160 F4 shows the loop finding a problem that nobody learns of unless they run a report verb, and the model-only categories never surface.

### C. File an issue at three sessions

For: it reaches people at once. Against: an issue then rests on a model's reading in one run, the noise ADR-0119 was written to avoid; the best public method found the decisive step of a multi-agent failure 14.2 % of the time ([R-110](../research/R-110-reading-session-logs-for-self-improvement.rsrch.md) P3).

### D. Record the finding only when a second run repeats it

For: two runs are better independent evidence than one. Against: a workflow run a few times a month waits weeks to show a problem it showed on its first day. Recording costs nothing and files nothing, so waiting buys no safety.

## Consequences

- `improve backlog` shows a repeated review category after one run, beside the model-free causes, and the loop summary can name the top observations ([SIL-B22](../specs/16-self-improvement.spec.md)).
- A reader must tell a counted fact from a reading. The cause name carries the category and the trust tier (`review_repeat:`), the finding carries no note, and `review_weight` is shown beside the score and not added to it ([PRP-B12](../specs/40-improvement-proposals.spec.md)).
- Risk: the reviewer's bias, repeated across sessions, inflates a cluster. Limits: the threshold is a parameter with provenance `default_no_data` ([IMD-B23](../specs/43-improvement-data.spec.md)); an observation that fails the citation check counts for nothing; the finding never files; and `environment_fault` and `request_ambiguous`, which no workflow change can fix, are recorded as `infra` and `designed` and stay out of the backlog.
- It answers the open question of R-160 whether one run is enough: one run is enough to record, and no number of runs is enough to file on a review alone.

## Revisit when

A gold set of reviewed sessions exists and the reviewer can be scored like a judge ([JCL](../specs/50-judge-calibration.spec.md)), as ADR-0119 already says, or the first live runs show how often a person agrees with a repeat finding.
