# plan

## 1. Overview

The plan traces every acceptance criterion to requirements and phases, states its complexity, and agrees with the specs

Part of the [overview](00-overview.spec.md).

## 6. Acceptance criteria

- [ ] ts-plan-form The plan has each section the plan rule requires, with the status `planned` and a completed mark only on a row that kept its mark through a trip back (KMK-B1 to KMK-B4)
- [ ] ts-plan-trace Every acceptance criterion in the triage note is named by at least one plan requirement, and in a simple plan by a proof row with its test file and command
- [ ] ts-plan-links In a simple plan every task row names a requirement of the plan, every requirement is named by a row, and every document under Docs to update is the file of a docs row
- [ ] ts-plan-size The complexity value matches the plan's measured signs
- [ ] ts-plan-scope No requirement or task row says it does less than asked (a stub, a placeholder, for now, a later task)
- [ ] ts-plan-commit Every file the plan step changed is committed
- [ ] ts-plan-spec No plan requirement contradicts a behaviour of a spec the plan references
- [ ] ts-plan-reading The plan prompt tells the session to start from the hand-off's reading list and to open another file only for what the list does not answer
