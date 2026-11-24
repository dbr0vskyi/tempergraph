# code

## 1. Overview

The whole plan, or the small change of the quick lane, is built test first, committed, with its verification passing in the gate's own run and each criterion carried by a test

Part of the [overview](00-overview.spec.md).

## 6. Acceptance criteria

- [ ] ts-code-rows Every task row of the plan is marked completed with its date in a plan whose status is `completed`, checked before any command runs
- [ ] ts-code-changed The file of every task row marked completed changed in the run
- [ ] ts-code-verify Every verification command the plan lists exits 0 when the gate runs it, whatever the step reported about its own run
- [ ] ts-code-proof Each criterion a test row proves is carried by a test in the row's file, and that test is not skipped
- [ ] ts-code-lane A change in the quick lane edits no spec or decision record, only the files its triage note names, at most 2 code files and at most 200 lines
- [ ] ts-code-commit Every file the code step changed is committed
- [ ] ts-code-aligned The code change agrees by meaning with every behaviour of each spec the run edited
- [ ] ts-code-related The code change breaks no behaviour of a related spec that the run did not edit
- [ ] ts-code-change Each task row's change is in the file the row names
- [ ] ts-code-tests Each test that carries an acceptance criterion id asserts what that criterion states
- [ ] ts-code-scope No file is changed that no task row names
- [ ] ts-code-once The code prompt tells the session to run only the test files a phase's rows name after that phase, and each verification command of the plan once, after the last phase and before it writes the report (in the quick lane, the note's `Verify` commands once, after the last criterion)
- [ ] ts-code-reuse The code gate runs a verification command only when no result of that command is recorded for the same tree, so a retry or a later visit of the code step on an unchanged tree runs nothing again (CHK-B13)
- [ ] ts-code-base A verification command that fails at the gate and fails with the same non-zero exit code at the run's base commit makes the code check return an environmental result, so the gate escalates with no retry and no judge (CHK-B18, CHK-B14)
- [ ] ts-code-touch A verification command that fails at the gate and fails with a different non-zero exit code at the run's base commit makes the check environmental when no path the run changed (written from the repository root or from the folder the command ran in) appears in the last lines the command printed at the gate, and fails the check, so the code step retries, when one does
- [ ] ts-code-passes A verification command that exits 0 at the run's base commit and fails at the gate fails the check, so the code step retries
- [ ] ts-code-nobase A verification command that fails at the gate and was not compared with the run's base commit (the run has no base commit, the command could not start there, or the command did not finish at the gate or at the base) fails the check, so the code step retries, and the evidence says it was not compared
- [ ] ts-code-mixed When a verification command is judged environmental and another finding of the code check also fails, the check fails so that the code step retries with only the findings it can fix listed, and its evidence still names the environmental command
- [ ] ts-code-evidence The code check's evidence names each verification command that failed at the gate with its exit code at the gate and at the run's base commit, and the reason it was judged environmental, caused by the change or not compared
- [ ] ts-code-spend A verification command that exits 0 at the gate is never run at the run's base commit, and one that fails is run there at most once per visit of the code step, however many attempts the visit takes (CHK-B20)
