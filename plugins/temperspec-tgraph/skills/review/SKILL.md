---
name: review
description: Review a temperspec plan before coding, or a finished implementation against its plan and specs, and report what does not hold. Use when the user asks to review, audit or double-check a plan, a run's code or a temperspec pull request, or doubts that a run's result does what its gates passed.
---

# Review a plan or an implementation

A second look by a person's own session, outside a run. The run's gates already checked form and judged meaning; this review reads the result as someone who did not write it and trusts no mark, no report and no verdict. It changes nothing: the report goes to the chat.

Open the rule files that describe what you review with the read tool first (`plan.rule.md`, `spec.rule.md`, `task-notes.rule.md`, in `.claude/rules/temperspec/` of the repository or the plugin's `rules/` folder).

## Find what to review

Ask for the task id, the pull request or the plan's path unless the user gave one. The task notes are in `docs/tasks/` (or the `tasks/` folder beside the repository's specs): `<task>.triage.md` holds the acceptance criteria, `<task>.handoff.md` what discovery changed, `<task>.report.md` what coding claims. The plan is in the plans folder. Review the plan when no code exists yet, the implementation when it does; say which.

## Reviewing a plan

1. Build the trace table: one row per acceptance criterion of the task, with the plan requirement that covers it, the task rows that build it and the test named to prove it. A criterion with an empty cell is a finding. So is a requirement or a task row that serves no criterion: scope the task did not ask for.
2. Read each spec behaviour the plan names and compare by meaning: does the planned work do what the behaviour says, in its boundary cases too? A plan that names a type, a command or a path the specs or the code contradict is a finding.
3. Read the code the plan will change, enough to judge each phase: is the order buildable, is something that already exists planned again, is a phase far heavier than its rows suggest?
4. Check the hand-off and the reading lists: could a session that knows nothing else start from them?
5. Verdict: `ready`, or `not ready` with the findings that must be fixed first.

## Reviewing an implementation

The code is the truth; the plan, the report and the specs are claims about it.

1. For each task row of the plan, find the code and state one of `built`, `partial`, `missing`, `differs`, with the file and lines. A completion mark is not evidence.
2. For each behaviour of the specs the change edited, and of the specs that cover the changed files, read the code path and say whether it does what the behaviour says, case by case for its scenarios. Search for specs that cover the changed files yourself; do not rely on the plan's list.
3. For each acceptance criterion of the task, open the test that carries its id: does it fail if the criterion is broken, or does it assert something weaker (a mock's own answer, a type, that no error was raised)? Run the repository's test command when the user agrees, and report the real result beside the code report's claim.
4. Look for what no gate asks: the result a user of the feature gets from start to end. Follow one real path through the changed code and say what comes out. A change that passes every criterion and still produces a poor or wrong result is the most valuable finding; describe it with the input and the output.
5. Read the diff for work outside the task: files changed that no task row names, behaviour changed that no spec edit records.
6. Verdict: `holds`, or `does not hold` with the findings, each marked `must fix` or `worth fixing`.

## The report

Lead with the verdict. Then the findings, most serious first, each with what you expected, what you found, where (file and lines) and what would settle it. Then the trace or audit table. End with what you did not read. A finding you could not confirm is listed as a question, not as a defect.

## Limits

- Read only. No edit to code, tests, specs, the plan or the notes, and no git command that changes anything. The user decides what to do with a finding: a new task (the `task` skill), a fix by hand, or nothing.
- Do not repeat the gates' form checks; say only what a reader finds.
- Never soften a finding because a gate passed, and never invent one to look thorough: "holds" with an empty list is a full answer.
