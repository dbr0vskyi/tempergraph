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
- [ ] ts-code-once The code prompt tells the session to run only the test files a phase's rows name after that phase, and each verification command of the plan once, after the last phase, with the plan marked completed and the code report written, and to change no file after that run (in the quick lane, the note's `Verify` commands once, after the last criterion and the report, with no file changed after that run)
- [ ] ts-code-reuse The code gate runs a verification command only when no result of that command is recorded for the same tree, so a retry or a later visit of the code step on an unchanged tree runs nothing again (CHK-B13)
- [ ] ts-code-preview The code step declares the engine's check preview, and its prompt tells the session to make its one run of each verification command of the plan through that preview
- [ ] ts-code-previewed A preview of the code gate's check, run after the last phase with the plan marked completed, runs each verification command of the plan (in the quick lane, the note's `Verify` commands) and lists each one that fails with its exit code, and reports no failure for the code report the session has not handed over yet or for the commit that follows the session
- [ ] ts-code-session The code gate does not run a verification command again when the session ran it through the check preview on the same tree content, though the session's files were committed after that run (CHK-B13)
- [ ] ts-code-rerun The code gate runs a verification command again when any file of the tree changed after the session's run of it (CHK-B13)
- [ ] ts-code-ran The code gate's evidence names each verification command of the plan that the gate ran or reused, with the word `reused` or `run`
