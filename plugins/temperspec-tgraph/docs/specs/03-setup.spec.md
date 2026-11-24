# setup

## 1. Overview

A repository with no overview spec gets one, and one spec per component, that describe the code as it is

Part of the [overview](00-overview.spec.md).

## 6. Acceptance criteria

- [ ] ts-set-form The overview spec and every spec the setup note lists pass the spec rule's structure check
- [ ] ts-set-listed Every spec the setup note lists exists and is named by its path in the overview spec
- [ ] ts-set-links Every id that a spec of the setup step mentions resolves to exactly one definition
- [ ] ts-set-ruleread Each rule file the setup prompt names (spec.rule.md, task-notes.rule.md, documents.rule.md) that the repository holds under .claude/rules/temperspec/ is opened with the read tool in the session
- [ ] ts-set-commit Every file the setup step changed is committed
- [ ] ts-set-true Every behaviour the setup step wrote describes what the code does now
- [ ] ts-set-cover Every top-level part of the code base belongs to a component with a spec or is listed as not covered
