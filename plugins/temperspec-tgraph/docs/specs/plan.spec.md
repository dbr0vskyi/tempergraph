# plan

## 1. Overview

The plan traces every acceptance criterion to requirements and phases, states its complexity, and agrees with the specs

Part of the [overview](overview.spec.md).

## Does not own

- Test-first order of session writes for `chore` and `docs` row files: `session-record-checks.spec.md`
- Execution of `chore` rows that describe a file deletion: `code.spec.md`

## Behaviours

### PLN-B1 A `chore` row names a housekeeping file change

WHEN a plan contains a row of kind `chore` THE plan check SHALL accept it as a valid row without requiring a preceding test row in the same phase.

- GIVEN a phase containing only a `chore` row WHEN the plan check runs THEN the row is accepted and the phase is not empty
- GIVEN a `chore` row in a phase with no `test` row before it WHEN the plan check runs THEN the check does not fail for the absent test row

### PLN-B2 Forbidden file operation in a non-`chore` row fails the plan check

WHEN the plan check reads a row whose Change cell describes deleting a file, moving a file, or writing under `.claude/` and the row's kind is not `chore` THE plan check SHALL fail with a finding naming the row and the operation.

- GIVEN a row of kind `code` whose Change describes deleting a named file WHEN the plan check runs THEN it fails naming the row
- GIVEN a row of kind `chore` whose Change describes deleting a named file WHEN the plan check runs THEN no finding is raised for the operation
- GIVEN a row of kind `docs` whose Change describes writing a path under `.claude/` WHEN the plan check runs THEN it fails naming the row

## 6. Acceptance criteria

- [ ] ts-plan-form The plan has each section the plan rule requires, with the status `planned` and a completed mark only on a row that kept its mark through a trip back (KMK-B1 to KMK-B4)
- [ ] ts-plan-trace Every acceptance criterion in the triage note is named by at least one plan requirement, and in a simple plan by a proof row with its test file and command
- [ ] ts-plan-links In a simple plan every task row names a requirement of the plan, every requirement is named by a row, and every document under Docs to update is the file of a docs row
- [ ] ts-plan-size The complexity value matches the plan's measured signs
- [ ] ts-plan-scope No requirement or task row says it does less than asked (a stub, a placeholder, for now, a later task)
- [ ] ts-plan-ruleread Each rule file the plan prompt names (plan.rule.md, documents.rule.md) that the repository holds under .claude/rules/temperspec/ is opened with the read tool in the session
- [ ] ts-plan-commit Every file the plan step changed is committed
- [ ] ts-plan-spec No plan requirement contradicts a behaviour of a spec the plan references
- [ ] ts-plan-reading The plan prompt tells the session to start from the hand-off's reading list and to open another file only for what the list does not answer
- PLN-AC1 (PLN-B1): A plan whose sole task row in a phase is a `chore` row passes both the row-validity and the phase-completeness parts of the plan check, and no test-row finding is raised for the `chore` row's phase
- PLN-AC2 (PLN-B2): The plan check fails with a finding naming the row for a row of kind `code` whose Change describes deleting a named file, and does not fail for a `chore` row with the same Change cell
- PLN-AC3 (PLN-B2): The plan check fails with a finding naming the row for a row of kind `docs` whose Change describes writing under `.claude/`, and does not fail for a `chore` row with the same Change cell
