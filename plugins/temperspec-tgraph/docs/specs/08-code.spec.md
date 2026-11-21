# code

## 1. Overview

The whole plan is built test first, committed, with the plan's verification passing in the gate's own run

Part of the [overview](00-overview.spec.md).

## 6. Acceptance criteria

- [ ] ts-code-rows Every task row of the plan is marked done
- [ ] ts-code-verify Every verification command the plan lists exits 0 when the gate runs it
- [ ] ts-code-commit Every file the code step changed is committed with no commit on a remote
- [ ] ts-code-aligned The code change agrees by meaning with every behaviour of each spec the run edited
- [ ] ts-code-related The code change breaks no behaviour of a related spec that the run did not edit
- [ ] ts-code-change Each task row's change is in the file the row names
- [ ] ts-code-tests Each test that carries an acceptance criterion id asserts what that criterion states
- [ ] ts-code-scope No file is changed that no task row names
