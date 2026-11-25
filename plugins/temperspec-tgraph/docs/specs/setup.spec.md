# setup

## 1. Overview

A repository with no overview spec gets one, and one spec per component, that describe the code as it is

Part of the [overview](overview.spec.md). A repository with two or more component folders first gets one read-only reading session for each, and the step's one writing session then writes the overview, the component specs and the setup note from their findings; the criteria below judge that session's output, and the reading sessions write no document ([parallel reading](parallel-reading.spec.md)).

## 6. Acceptance criteria

- [ ] ts-set-form The overview spec and every spec the setup note lists pass the spec rule's structure check
- [ ] ts-set-listed Every spec the setup note lists exists and is named by its path in the overview spec
- [ ] ts-set-links Every id that a spec of the setup step mentions resolves to exactly one definition
- [ ] ts-set-named No line of a spec the setup step wrote outside a workflow package names that package or its workflow
- [ ] ts-set-literal Every line of a spec the setup step wrote is reported to the judge as a lead when its words tie it to a task or a change
- [ ] ts-set-wording A behaviour sentence over 500 characters, a word two readers could measure differently or a placeholder in a spec written at setup reaches the judge as a lead
- [ ] ts-set-evidence Every behaviour in a spec written at setup has a row under Evidence giving the basis `tested` or `read`, code with line numbers found inside a real source file, and a real test when the basis is `tested`
- [ ] ts-set-ruleread Each rule file the setup prompt names (spec.rule.md, extraction.rule.md, task-notes.rule.md, documents.rule.md) that the repository holds under .claude/rules/temperspec/ is opened with the read tool in the session
- [ ] ts-set-commit Every file the setup step changed is committed
- [ ] ts-set-true Every behaviour the setup step wrote describes what the code does now
- [ ] ts-set-cover Every top-level part of the code base belongs to a component with a spec or is listed as not covered
