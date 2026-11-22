# triage

## 1. Overview

The triage note states the task's acceptance criteria, the gaps in the specs, and a route that follows the gaps and the size of the task

Part of the [overview](00-overview.spec.md).

## 6. Acceptance criteria

- [ ] ts-tri-form The triage note has each section the triage rule requires
- [ ] ts-tri-route The route follows the gap list: discovery with a gap, plan or quick with none, and quick only within the quick lane's limits and never on a return to triage
- [ ] ts-tri-commit Every file the triage step changed is committed
- [ ] ts-tri-criteria Every acceptance criterion in the triage note is stated by the task
- [ ] ts-tri-gaps Every concept the task needs that no ready spec covers is listed as a gap
- [ ] ts-tri-covered Every gap row that says `Covered by` names a behaviour id and the id of a criterion that names that behaviour, both of one spec and each defined exactly once
