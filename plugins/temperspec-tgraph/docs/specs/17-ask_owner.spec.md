# ask_owner

## 1. Overview

The unit that pauses the run once for the owner's answers. It holds the questions that [owner_questions](15-owner_questions.spec.md) listed, takes answers by terminal, by file or from the agent that started the run, lets the run go on to [discovery](05-discovery.spec.md) when every question has an answer, and, once its deadline has passed and `resume --apply-deadline` is run, lets the run go on with each open question at its default. It is the engine's ask unit ([ASK-B5](../../../tempergraph/docs/specs/73-ask-unit.spec.md)); its gate holds the engine's check of the answers and the workflow's check that refuses a reading called wrong, with no judge and no sign-off.

Part of the [overview](00-overview.spec.md). What it asks, how long it waits and what discovery does with the answers are the behaviours OWQ-B3 to OWQ-B10 of [owner questions](owner-questions.spec.md), which this page does not restate.

## 6. Acceptance criteria

None: the unit has no gate criteria.
