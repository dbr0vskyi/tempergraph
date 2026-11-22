# discovery_short

## 1. Overview

A task whose every gap a spec already answers gets a hand-off and a reading list from a short, read-only visit, and a gap the citation does not answer goes on to the full discovery

Part of the [overview](00-overview.spec.md). The route after triage chooses it when the triage check has verified every `Covered by` mark; every return to discovery from a later gate goes to the full [discovery](05-discovery.spec.md) ([decision 0003](../adr/0003-short-discovery-visit.adr.md)).

## 6. Acceptance criteria

- [ ] ts-dsh-form The short visit's hand-off has each section the task-notes rule requires
- [ ] ts-dsh-cited The hand-off's `Gaps closed` names every behaviour id a gap row of the triage note cites
- [ ] ts-dsh-only The short visit's hand-off lists no changed document
- [ ] ts-dsh-settled The `settled` value is `no` exactly when a line of `Gaps closed` says `Not covered`
- [ ] ts-dsh-reading The hand-off of a settled short visit has a reading list of at most 10 items, each naming an existing file, the line ranges or ids that matter and one line on why
- [ ] ts-dsh-limit The short visit's prompt tells the session to read at most 10 files
- [ ] ts-dsh-commit Every file the short discovery step changed is committed
- [ ] ts-dsh-answers Every behaviour a gap row cites answers that gap's question as the task's acceptance criteria need it, or the hand-off says `Not covered` for the gap
