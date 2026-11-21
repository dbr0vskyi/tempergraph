# code

## 1. Overview

The whole plan, or the small change of the quick lane, is built test first, committed, with its verification passing in the gate's own run and each criterion carried by a test

Part of the [overview](00-overview.spec.md).

## 6. Acceptance criteria

- [ ] ts-code-rows Every task row of the plan is marked completed with its date in a plan whose status is `completed`, checked before any command runs
- [ ] ts-code-changed The file of every task row marked completed changed in the run
- [ ] ts-code-verify Every verification command the plan lists exits 0 when the gate runs it
- [ ] ts-code-proof Each criterion a test row proves is carried by a test in the row's file, and that test is not skipped
- [ ] ts-code-lane A change in the quick lane edits no spec or decision record, only the files its triage note names, at most 2 code files and at most 200 lines
- [ ] ts-code-commit Every file the code step changed is committed with no commit on a remote
- [ ] ts-code-aligned The code change agrees by meaning with every behaviour of each spec the run edited
- [ ] ts-code-related The code change breaks no behaviour of a related spec that the run did not edit
- [ ] ts-code-change Each task row's change is in the file the row names
- [ ] ts-code-tests Each test that carries an acceptance criterion id asserts what that criterion states
- [ ] ts-code-scope No file is changed that no task row names
