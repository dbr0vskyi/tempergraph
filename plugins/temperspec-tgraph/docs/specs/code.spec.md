# code

## 1. Overview

The whole plan, or the small change of the quick lane, is built test first, committed, with its verification passing in the gate's own run and each criterion carried by a test

Part of the [overview](overview.spec.md). On the arm `single` and in the quick lane this step builds the whole change in one session. On the arm `phases` the [phase](phase.spec.md) items have built and committed each phase before it, and this step is the join: it builds only a row whose Completed cell is empty, ends the plan and writes the code report, and its gate checks the whole change and holds the lines back to the plan, discovery and triage steps ([phase coding](phase-coding.spec.md)).

## 6. Acceptance criteria

- [ ] ts-code-rows Every task row of the plan is marked completed with its date in a plan whose status is `completed`, checked before any command runs
- [ ] ts-code-changed The file of every task row marked completed changed in the run, whichever visit of the code step changed it (KMK-B8)
- [ ] ts-code-verify Every verification command the plan lists exits 0 when the gate runs it, whatever the step reported about its own run
- [ ] ts-code-proof Each criterion a test row proves is carried by a test in the row's file, and that test is not skipped
- [ ] ts-code-lane A change in the quick lane edits no spec or decision record, only the files its triage note names, at most 2 code files and at most 200 lines
- [ ] ts-code-ruleread Each rule file the code prompt names (task-notes.rule.md, plan.rule.md) that the repository holds under .claude/rules/temperspec/ is opened with the read tool in the session
- [ ] ts-code-order A phase's source files are not changed before the phase's test files are first written
- [ ] ts-code-commit Every file the code step changed is committed
- [ ] ts-code-aligned The code change agrees by meaning with every behaviour of each spec the run edited
- [ ] ts-code-related The code change breaks no behaviour of a related spec that the run did not edit
- [ ] ts-code-change Each task row's change is in the file the row names
- [ ] ts-code-tests Each test that carries an acceptance criterion id asserts what that criterion states
- [ ] ts-code-scope No file is changed that no task row names
- [ ] ts-code-once The code prompt tells the session to run only the test files a phase's rows name after that phase, and each verification command of the plan once, after the last phase, with the plan marked completed and the code report written, and to change no file after that run (in the quick lane, the note's `Verify` commands once, after the last criterion and the report, with no file changed after that run)
- [ ] ts-code-reuse The code gate runs a verification command only when no result of that command is recorded for the same tree, so a retry or a later visit of the code step on an unchanged tree runs nothing again (CHK-B13)
- [ ] ts-code-base A verification command that fails at the gate and fails with the same non-zero exit code at the run's base commit makes the code check return an environmental result, so the gate escalates with no retry and no judge (CHK-B18, CHK-B14)
- [ ] ts-code-touch A verification command that fails at the gate and fails with a different non-zero exit code at the run's base commit makes the check environmental when no path the run changed (written from the repository root or from the folder the command ran in) appears in the last lines the command printed at the gate, and fails the check, so the code step retries, when one does
- [ ] ts-code-passes A verification command that exits 0 at the run's base commit and fails at the gate fails the check, so the code step retries
- [ ] ts-code-nobase A verification command that fails at the gate and was not compared with the run's base commit (the run has no base commit, the command could not start there, or the command did not finish at the gate or at the base) fails the check, so the code step retries with evidence saying the command was not compared
- [ ] ts-code-mixed When a verification command is judged environmental and another finding of the code check also fails, the check fails so that the code step retries with only the findings it can fix listed, while its evidence still names the environmental command
- [ ] ts-code-evidence The code check's evidence names each verification command that failed at the gate with its exit code at the gate and at the run's base commit, with the reason it was judged environmental, caused by the change or not compared
- [ ] ts-code-spend A verification command that exits 0 at the gate is never run at the run's base commit, and one that fails is run there at most once per visit of the code step, however many attempts the visit takes (CHK-B20)
- [ ] ts-code-preview The engine's check preview is declared on the code step, and the code prompt tells the session to make its one run of each verification command of the plan through that preview
- [ ] ts-code-previewed A preview of the code gate's check, run after the last phase with the plan marked completed, runs each verification command of the plan (in the quick lane, the note's `Verify` commands) and lists each one that fails with its exit code, and reports no failure for the code report the session has not handed over yet, for the commit that follows the session or for a marked removal row whose file the workflow removes after the session (FRM-B7)
- [ ] ts-code-session The code gate does not run a verification command again when the session ran it through the check preview on the same tree content, though the session's files were committed after that run (CHK-B13)
- [ ] ts-code-rerun The code gate runs a verification command again when any file of the tree changed after the session's run of it (CHK-B13)
- [ ] ts-code-ran The code gate's evidence names each verification command of the plan that the gate ran or reused, with the word `reused` or `run`
