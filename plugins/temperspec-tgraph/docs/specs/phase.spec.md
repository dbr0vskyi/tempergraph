# phase

## 1. Overview

Every row of one phase of the plan is built test first and committed, with each criterion its test rows prove carried by a test

Part of the [overview](overview.spec.md). On the arm `phases` of `code_mode` the expand step is followed by one phase item for each phase of the plan, one after another on the engine's sequential map, each in a session of its own, and the [code](code.spec.md) step then runs once as the join on the whole change ([phase coding](phase-coding.spec.md)). A phase's gate checks only its own rows and has no line back; the checks of the whole change and the lines back to the plan, discovery and triage steps stay with the gate of the code step.

## 6. Acceptance criteria

- [ ] ts-phs-rows Every row of the phase is marked completed with its date
- [ ] ts-phs-changed The file of every row of the phase marked completed changed in the run, whichever attempt or visit changed it (KMK-B8)
- [ ] ts-phs-proof Each criterion a test row of the phase proves is carried by a test in the row's file, and that test is not skipped
- [ ] ts-phs-order A source file of the phase is not changed before the phase's test files are first written (SRC-B6)
- [ ] ts-phs-commit Every file the phase changed is committed
- [ ] ts-phs-change Each row of the phase has its change in the file the row names
- [ ] ts-phs-scope No file changed since the phase step was entered is a file that no row of the phase or of an earlier phase names, apart from the plan's marks and status (PHC-B9)
