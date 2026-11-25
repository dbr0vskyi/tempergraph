# discovery

## 1. Overview

Every gap is closed by a spec, a decision record or a research note in the agreed format, committed

Part of the [overview](overview.spec.md). A triage note that lists two or more gaps first gets one read-only reading session for each gap, and the step's one writing session then closes the gaps from their findings and writes the hand-off; the criteria below judge that session's output, and the reading sessions write no document ([parallel reading](parallel-reading.spec.md)). When the run paused for the owner's answers, the step closes each owner decision of the triage note on its answer, or on its default when it has none, and says in its hand-off how each was closed ([owner questions](owner-questions.spec.md)).

## 6. Acceptance criteria

- [ ] ts-dis-form Every spec the discovery step wrote passes the spec rule's structure check
- [ ] ts-dis-budget Every spec the discovery step wrote is within the repository's spec budget: at most 400 lines and at most 30 KB (30,720 bytes)
- [ ] ts-dis-over A spec over the budget in lines or in bytes fails the discovery check with a finding, carried to the next discovery attempt, that names the spec with its figure over the budget and says to split the spec by capability
- [ ] ts-dis-names Every document the discovery step created carries its type suffix in its file name
- [ ] ts-dis-links Every id that a document of the discovery step links to resolves to exactly one definition
- [ ] ts-dis-ruleread Each rule file the discovery prompt names (spec.rule.md, extraction.rule.md, decision.rule.md, research.rule.md, task-notes.rule.md, documents.rule.md) that the repository holds under .claude/rules/temperspec/ is opened with the read tool in the session
- [ ] ts-dis-commit Every file the discovery step changed is committed
- [ ] ts-dis-gaps Every gap in the triage note is closed by a document the hand-off names
- [ ] ts-dis-behaviour Every behaviour the discovery step wrote states an observable result with no internal name
- [ ] ts-dis-named No line the discovery step added to a spec outside a workflow package names that package or its workflow
- [ ] ts-dis-literal Every line the discovery step added to a spec in words that tie it to the task is reported to the judge as a lead
- [ ] ts-dis-wording A behaviour sentence over 500 characters, a word two readers could measure differently or a placeholder that discovery put into a spec reaches the judge as a lead
- [ ] ts-dis-specname A spec created in discovery is named for its capability: no task id, issue number or leading work verb in its file name, no task id or issue number in its title
- [ ] ts-dis-general Every behaviour written or edited in discovery states a general rule of its capability that reads true to someone who never saw the task and can be read only one way
- [ ] ts-dis-scope No document the discovery step wrote covers a concept outside the task's gaps
- [ ] ts-dis-narrow Every discovery prompt tells the session to search for ids and names, to read the line ranges it needs instead of whole files, and to stop reading once each gap has its answer
- [ ] ts-dis-reading The hand-off of a task that goes on to a plan has a reading list with one item for each file the plan will need, naming an existing file, the line ranges or ids that matter and one line on why
