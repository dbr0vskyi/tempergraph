# Review repeats

## Purpose

Split from [session review](44-session-review.spec.md) by capability, keeping its ids: how a review category kept again and again, in several sessions of one run or in several runs of a workflow, is counted, recorded as a finding and handed to the proposer, and why such a finding files no issue by itself ([the decision record](../adr/a-review-category-kept-in-several-sessions-is-a-finding-that-never-files-alone.adr.md), [ADR-0119](../adr/0119-review-observations-are-candidates-corroborated-before-they-file.adr.md)). Counting is not reading: a repeat is arithmetic over observations whose citations the engine has already checked ([SRV-B20](44-session-review.spec.md)). Workflow authors who read `improve backlog`, the loop and the proposer depend on it.

## Behaviours

### SRV-B26 A category kept in several sessions is a finding

WHEN the reviews of a run have kept the same category on the same unit in at least `review.repeat_sessions` (3, provenance `default_no_data`) distinct sessions THE engine SHALL record one finding `review_repeat:<category>` on that unit in the thread's findings ([SIL-B8](16-self-improvement.spec.md)), once per unit and category in the run, carrying the unit, the category and the session keys and no note text, as a fault of the workflow except that `environment_fault` gives `infra` and `request_ambiguous` gives `designed` (SRV-B19; the reasons are in [the decision record](../adr/a-review-category-kept-in-several-sessions-is-a-finding-that-never-files-alone.adr.md)).

- GIVEN `tool_thrash` kept on `a` in sessions `a.1.step`, `a.2.retry` and `a.3.retry` WHEN the reviews end THEN the thread's findings hold one `review_repeat:tool_thrash` finding on `a` with those three session keys and no note text, and `improve backlog` lists a cluster for it
- GIVEN `tool_thrash` kept on `a` in two sessions and rejected by the citation check in a third WHEN the reviews end THEN no `review_repeat` finding is recorded
- GIVEN `tool_thrash` kept on `a` three times in one session and once in a second WHEN the reviews end THEN no `review_repeat` finding is recorded
- GIVEN `tool_thrash` kept in three sessions of `a` and in two of `b` WHEN the reviews end THEN the finding is on `a` only
- GIVEN `environment_fault` kept in three sessions of `a` WHEN the reviews end THEN the finding is class `infra` and no cluster of `improve backlog` holds it

### SRV-B32 A category kept in several runs is a finding

WHEN the reviews of a run end with a category kept on a unit, and the reviews of at least `review.repeat_runs` runs of the workflow (3, provenance `default_no_data`, [IMD-B23](43-improvement-data.spec.md)), this run included, have kept that category on that unit, each run counting once however many of its sessions kept it, THE engine SHALL record one finding `review_repeat:<category>` on that unit in the thread's findings ([SIL-B8](16-self-improvement.spec.md)), once per unit and category in the run whichever of SRV-B26 and this behaviour records it, carrying the unit, the category and the ids of those runs and no note text, with the class and side that SRV-B26 gives.

- GIVEN `instruction_ignored` kept on `a` in one session of each of three runs of a workflow WHEN the reviews of the third run end THEN that run's findings hold one `review_repeat:instruction_ignored` finding on `a` naming the three runs and no note text, and `improve backlog` lists a cluster for it
- GIVEN `instruction_ignored` kept on `a` in two runs only WHEN the reviews of the second run end THEN no `review_repeat` finding is recorded and `improve backlog` lists no cluster for it
- GIVEN `instruction_ignored` kept on `a` in two runs and rejected by the citation check in a third WHEN the reviews of the third run end THEN no `review_repeat` finding is recorded
- GIVEN `instruction_ignored` kept on `a` in two runs and on `b` in a third WHEN the reviews of the third run end THEN no `review_repeat` finding is recorded
- GIVEN `instruction_ignored` kept on `a` in two sessions of one run and in two sessions of another WHEN the reviews of the second run end THEN no `review_repeat` finding is recorded
- GIVEN `tool_thrash` kept on `a` in two runs and in three sessions of a third WHEN the reviews of the third run end THEN that run holds one `review_repeat:tool_thrash` finding
- GIVEN `instruction_ignored` kept on `a` in four runs WHEN the reviews of the fourth run end THEN that run holds one finding too and the cluster of `improve backlog` lists two runs
- GIVEN `environment_fault` kept on `a` in three runs WHEN the reviews of the third run end THEN the finding is class `infra` and no cluster of `improve backlog` holds it

### SRV-B27 The finding corroborates its own category

WHEN SRV-B26 or SRV-B32 records a finding THE engine SHALL count the kept observations of its category on its unit in its run as corroborated by it, as SRV-B7 does for a model-free finding: the finding carries `review:<category>` and a `review_weight` that is their number, and `improve review show` and `improve review summary` report them `corroborated`.

- GIVEN three kept `tool_thrash` observations on `a` and the finding `review_repeat:tool_thrash` WHEN `improve review show` runs THEN each of the three is `corroborated`, and the cluster of `improve backlog` has a `review_weight` of 3
- GIVEN a kept `tool_thrash` observation on `b` and the finding on `a` WHEN `improve review show` runs THEN the observation on `b` is not `corroborated`
- GIVEN a kept `tool_thrash` observation on `a` in each of three runs and the finding of SRV-B32 in the third WHEN `improve review show` runs on the first run and on the third THEN the observation of the third is `corroborated` and the observation of the first is not

### SRV-B28 A review repeat is the proposer's input, never an issue

WHEN the same review category has been kept on the same unit in 3 or more runs of a workflow (SRV-B32), or in 3 or more sessions of one run (SRV-B26), THE loop SHALL give the finding that records it to the proposer alone: its cluster is open to the loop's own proposal when the autonomy allows proposals ([PRP-B23](40-improvement-proposals.spec.md)), and no issue or comment is made for it, in the run that records it or in any later run.

- GIVEN `review_repeat:tool_thrash` on `a` recorded by two runs and no other finding on `a` WHEN filing runs THEN no issue or comment is made
- GIVEN `tool_thrash` kept on `a` in three runs of a stable workflow at autonomy `propose` and no other finding WHEN the loop child of the third run ends THEN the loop proposes on the cluster of `review_repeat:tool_thrash` and makes no issue or comment
- GIVEN the same three runs at autonomy `file` WHEN the loop child of the third run ends THEN nothing is proposed, no issue or comment is made and `improve backlog` lists the cluster

## Acceptance criteria

- SRV-AC10 (SRV-B26, SRV-B27): Fixture review records that keep one category on one unit in three sessions give one finding with the unit, the category and the three session keys and no note text, listed by `improve backlog`, and show those observations `corroborated`, while two sessions give none
- SRV-AC11 (SRV-B28): The findings of the fixtures of SRV-AC10 and SRV-AC17, recorded by one run, by two runs and by three runs, file no issue and no comment
- SRV-AC17 (SRV-B32, SRV-B27): Fixture review records that keep one category on one unit in one session of each of three runs give one finding in the third run, with the unit, the category and the three run ids and no note text, listed by `improve backlog`, and show the third run's observation `corroborated`, while two runs give no finding and no cluster, under the parameter `review.repeat_runs` (3, provenance `default_no_data`)
- SRV-AC18 (SRV-B28): A stable-mode fixture at autonomy `propose` whose third run's review records the finding of SRV-B32 is proposed on by the loop child and has no issue and no comment, and the same fixture at autonomy `file` proposes nothing and has its cluster listed by `improve backlog`
