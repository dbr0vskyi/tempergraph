# discovery

## 1. Overview

Every gap is closed by a spec, a decision record or a research note in the agreed format, committed

Part of the [overview](00-overview.spec.md).

## 6. Acceptance criteria

- [ ] ts-dis-form Every spec the discovery step wrote passes the spec rule's structure check
- [ ] ts-dis-names Every document the discovery step created carries its type suffix in its file name
- [ ] ts-dis-links Every id that a document of the discovery step links to resolves to exactly one definition
- [ ] ts-dis-commit Every file the discovery step changed is committed
- [ ] ts-dis-gaps Every gap in the triage note is closed by a document the hand-off names
- [ ] ts-dis-behaviour Every behaviour the discovery step wrote states an observable result with no internal name
- [ ] ts-dis-scope No document the discovery step wrote covers a concept outside the task's gaps
- [ ] ts-dis-short A task whose gap rows all say `Covered by` gets a short discovery visit: an effort below `max` and a prompt that states a reading limit of at most 10 files
- [ ] ts-dis-full A task with a gap that no spec covers, and every return to discovery from a later step, gets the full discovery visit at effort `max`
- [ ] ts-dis-narrow Every discovery prompt tells the session to search for ids and names, to read the line ranges it needs instead of whole files, and to stop reading once each gap has its answer
- [ ] ts-dis-reading The hand-off of a task that goes on to a plan has a reading list with one item for each file the plan will need, naming an existing file, the line ranges or ids that matter and one line on why
