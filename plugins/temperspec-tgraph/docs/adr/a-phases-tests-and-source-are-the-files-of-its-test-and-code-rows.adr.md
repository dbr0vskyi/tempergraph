# A phase's tests and source are the files of its test and code rows

## Context

The test-first rule is not held: run `r3-t5-2` wrote code before its tests in phases 4, 6, 7, 8 and 9, and the reports of `r3-t3-1`, `r3-t4-2` and `r3-t8-3` say the same (issue 74, from [R-160](../../../tempergraph/docs/research/R-160-does-the-improvement-loop-find-what-a-reviewer-finds.rsrch.md) F7). The task asks the code check to fail, naming the phase, when the session record shows a phase's source file changed before the phase's test file was first written. The task does not say which files belong to a phase, which calls count as a change, or what a retry that repairs code owes.

What the package and the rules hold, read in them:

- The plan rule says "in every phase, a `code` row comes after a `test` row of that phase", and a row is one logical change in one exact file with a `Kind` of `test`, `code`, `docs` or `chore` (`rules/plan.rule.md` lines 43-46, 79, 84). The plan parser keeps each row's kind, file and phase, and the phases in plan order (`workflow/temperspec/specfmt.py` lines 362-372, 400-448). Nothing forbids two phases from naming the same file.
- The code step's shell runs only the plan's verification commands and read-only git (`prompts/code.md` line 33; `workflow/temperspec/__init__.py` line 153), so every file it changes is changed by a call of the edit or the write tool, which the engine's record shows with the path ([CHK-B24](../../../tempergraph/docs/specs/75-check-contract-and-command-runs.spec.md)).
- A retry runs a fresh session on the tree the first attempt left ([PRM-B5](../../../tempergraph/docs/specs/04-prompt-rendering.spec.md)), and a check FAIL that is neither environmental nor a repeat sends the step back for a retry (`engine/src/tempergraph/run/nodes.py` lines 1389-1402). Its record holds its own calls only.
- The quick lane has a note with `Files`, `Tests` and `Verify` and no phases (`rules/task-notes.rule.md` lines 47-77); the code check stands the note's criteria in as one phase with test rows only (`workflow/temperspec/checks.py` lines 795-807).

## Decision

We will take option A: read a phase's files from its rows and compare them with the record, as [the spec](../specs/session-record-checks.spec.md) says:

- A phase's test files are the files of its `test` rows and its source files the files of its `code` rows. A `docs` or a `chore` row is neither.
- A file counts for the first phase, in plan order, that names it, whichever kind of row names it. A phase left with no test file or no source file of its own is not measured.
- A file is changed, and a test file written, by a call of the edit or the write tool that ended without an error. The first write of a test file is the first such call on it.
- A phase fails when the first change of one of its source files comes before the first write of any of its test files. The order is the record's call order.
- A phase whose test files the session never wrote is not measured for order: that session shows no write to put the source before, and a retry that only repairs code writes none. A test file that was never written is found by the gate's other criteria.
- The quick lane has no phases, so the criterion does not apply there.
- The finding names the phase, and the source file from the plan, never a call of the session.

## Options considered

### A. Each phase's own files, a shared file counted for the first phase that names it (chosen)

For: it states the plan rule's own sentence as a check; a source file that two phases name is not charged to the later phase, which would have been flagged for a change that was right when it was made; a violation in one phase is found whatever the others did. Against: a test file shared with an earlier phase leaves the later phase with no test file of its own, so its order is not measured, which hides a violation of that phase.

### B. Pool every test file and every source file of the plan

For: one comparison for the whole session. Against: it passes the order test, source, test, source (the first source change comes after the first test write) although the second phase's source came first, which is the failure the issue names.

### C. Measure each phase on every file it names, with no ownership

For: simpler to say. Against: a source file that phases 1 and 3 name is changed in phase 1, before phase 3's test, and phase 3 fails for it.

### D. Cut the session into windows, one per phase

For: it would measure a shared file in each phase. Against: the record does not mark where a phase begins, and the order in which a session takes the phases is not the plan's to command.

### E. Pair each test file with a source file by name

For: no need of the plan's kinds. Against: a name pairing (`test_session.py` and `session.py`) fits only some languages and layouts, and a plan row already says which file is which.

## Consequences

A session that writes a phase's source before its tests fails the code check with a finding that names the phase, which the run of `r3-t5-2` would have met in five phases. A check FAIL sends the code step back, and a retry cannot undo an order: it can write the phase's tests before it touches the source again, or leave the source alone, and the check on a retry reads the retry session's calls only. A failed order therefore costs a retry session for a process rule; the spec records this as an open question, with the check failing until the owner answers.

Risks, each with what limits it:

- A retry that repairs a phase by editing its source and then its test fails the order for that phase, though it repairs: the next attempt starts again from the finding, and a retry that edits only the source passes.
- Two calls in one model message are ordered as the message lists them, so a message that lists the source before the test is a violation although both were issued together.
- A test file shared with an earlier phase hides a later violation (Option A, Against); the plan rule does not forbid a shared file, and the gate's other criteria still ask each test row's file to change.

Taken without the owner, who is away, and open to change: a phase whose test files the session never wrote is not a failure of order; the quick lane is not measured; the first phase owns a shared file.

## Revisit when

A measured run shows false failures on retry attempts, or the plan records which rows a phase works first.
