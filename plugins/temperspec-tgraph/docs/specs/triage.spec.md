# triage

## 1. Overview

The triage note states the task's acceptance criteria, its intent, the questions it leaves open, the gaps in the specs, and a route that follows the gaps, the open questions and the size of the task

Part of the [overview](overview.spec.md). With any value of the conversation setting the note also sorts each gap and takes a default for each owner decision ([conversation](conversation.spec.md)); a run on `blocking` or `always` that has a question for the owner pauses once, after the reading sessions of discovery and before its writing session ([owner questions](owner-questions.spec.md)). The note's `Intent` and `Uncertainties` sections are defined in the rule file `task-notes.rule.md`; an uncertainty row that says `Blocks` or `Shapes` is read by a reading session when it is routed to the code, the documents or a source ([parallel reading](parallel-reading.spec.md)).

## 6. Acceptance criteria

- [ ] ts-tri-form The triage note has each section the triage rule requires, states the task's intent (goal, in scope, out of scope, assumptions each with what it costs if wrong) and lists each open question as a row with one of the fixed categories, an impact (Blocks, Shapes or Detail) and a route (code, docs, source, owner or plan), a Detail row and no other going to plan
- [ ] ts-tri-route The route follows the gap list and the open questions: discovery with a gap or with a question that blocks or shapes the change, plan or quick with neither, and quick only within the quick lane's limits and never on a return to triage
- [ ] ts-tri-ruleread Each rule file the triage prompt names (task-notes.rule.md, documents.rule.md) that the repository holds under .claude/rules/temperspec/ is opened with the read tool in the session
- [ ] ts-tri-commit Every file the triage step changed is committed
- [ ] ts-tri-criteria Every acceptance criterion in the triage note is stated by the task
- [ ] ts-tri-gaps Every concept the task needs that no ready spec covers is listed as a gap
- [ ] ts-tri-uncertain Every question the task leaves open about its own intent that would change which behaviours are written is an uncertainty row, and no row's impact is lower than what rests on its answer
- [ ] ts-tri-covered Every gap row that says `Covered by` names a behaviour id and the id of a criterion that names that behaviour, both of one spec and each defined exactly once
- [ ] ts-tri-owner With the conversation setting `never`, `blocking` or `always`, the triage note says for every gap row whether the gap is findable or an owner decision, and its `Owner decisions` section gives each owner decision a question, two to four options, a default that is one of them and what a wrong default costs, or says `None`
