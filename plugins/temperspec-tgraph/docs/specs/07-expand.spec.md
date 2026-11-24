# expand

## 1. Overview

Every phase of a complex plan has task rows with tests first and verification commands that run

Part of the [overview](00-overview.spec.md).

## 6. Acceptance criteria

- [ ] ts-exp-rows Every phase of the plan has at least one task row, a completed mark only on a row that kept its mark through a trip back (KMK-B1 to KMK-B4), and the plan's status is still `planned`
- [ ] ts-exp-tests Every code row is preceded by a test row that names an acceptance criterion id, and every acceptance criterion of the task has a proof row with its test file and command
- [ ] ts-exp-links Every task row names a requirement of the plan, every requirement is named by a row, and every document under Docs to update is the file of a docs row
- [ ] ts-exp-commands Every verification command in the plan resolves against the repository's allowed commands
- [ ] ts-exp-scope No task row says it does less than asked (a stub, a placeholder, for now, a later task)
- [ ] ts-exp-ruleread Each rule file the expand prompt names (plan.rule.md) that the repository holds under .claude/rules/temperspec/ is opened with the read tool in the session
- [ ] ts-exp-opened A task row that names a file that exists in the repository has that file opened by the session with the read tool
- [ ] ts-exp-commit Every file the expand step changed is committed
- [ ] ts-exp-design Every task row implements a requirement of the plan with no change to the plan's design
