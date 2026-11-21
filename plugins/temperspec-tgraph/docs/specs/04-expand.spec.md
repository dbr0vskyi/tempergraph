# expand

## 1. Overview

Every phase of a complex plan has task rows with tests first and verification commands that run

Part of the [overview](00-overview.spec.md).

## 6. Acceptance criteria

- [ ] ts-exp-rows Every phase of the plan has at least one task row
- [ ] ts-exp-tests Every code row is preceded by a test row that names an acceptance criterion id
- [ ] ts-exp-commands Every verification command in the plan resolves against the repository's allowed commands
- [ ] ts-exp-commit Every file the expand step changed is committed
- [ ] ts-exp-design Every task row implements a requirement of the plan with no change to the plan's design
