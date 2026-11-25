# owner_questions

## 1. Overview

A script, with no model session, reads the triage note and the run's conversation value and lists the questions the one pause asks, each with its kind, its choices and its default, so that the [pause](17-ask_owner.spec.md) can take them from the list; it also says whether the list holds any question.

Part of the [overview](00-overview.spec.md). It runs after [triage](04-triage.spec.md) on the routes through the full [discovery](05-discovery.spec.md), before the [route that pauses or skips](16-ask_route.spec.md). Which questions it lists (an owner decision, and under `always` the reading of a findable gap that no spec answers), their names, wordings, choices and defaults, and the limit of 20 questions are the behaviours OWQ-B3, OWQ-B4 and OWQ-B6 of [owner questions](owner-questions.spec.md), which this page does not restate.

## 6. Acceptance criteria

None: the unit has no gate criteria.
