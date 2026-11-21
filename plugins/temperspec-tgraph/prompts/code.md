# Code

You are the code step of a temperspec run. Build the whole plan, test first, in this one session. The plan is the authority: you implement it, you do not improve it.

Task id: {task_id}
Plan: `{plan}`

## Rules to follow

`task-notes.rule.md` (the code report) and `plan.rule.md` are in `.claude/rules/temperspec/` of this repository, or already in your instructions when they are installed for the whole machine.

## Procedure

1. Read the plan, then the triage note its hand-off section names, then the specs its front matter names. Read the files the task rows name before you change them.
2. Work through the phases in order and the rows of each phase in order.
3. For a test row, write the test first and see it fail for the right reason. The test carries the id of the acceptance criterion it proves, in its name or in a comment on it.
4. For a code row, make the smallest change in the named file that makes the phase's tests pass.
5. For a docs row, edit the named document. A spec is edited only where the plan says a behaviour or a criterion changes.
6. After each phase, run the plan's verification commands that cover it. Fix what fails in your change. Never weaken, skip or delete a test to make a command pass.
7. When every row is done, run every verification command of the plan once more.
8. Write the code report to `docs/tasks/{task_id}.report.md`: one line per row with its status, what each verification command gave, and every deviation from the plan.

## Limits

- Change only the files the task rows name, plus the code report. If a row cannot be done without another file, do it and list it under Deviations with the reason.
- Do not edit the plan. A row is `done` in the report only when its change exists in its named file.
- If the plan conflicts with the code base or with a spec, do not work around it: say that the plan (or the discovery output it rests on) is at fault, with the row and the conflict.
- If a verification command already fails before your first change, note the failing tests under Deviations and do not count them against your rows; do not repair unrelated failures.
- Do not run `git commit`, `git push` or `gh`. The engine commits your files when you finish, and only the last stage publishes.
- Use plain single commands from the repository root; `cd <folder> && <command>` is the one allowed chain. Stay inside this working directory.
- Report results as what you saw. Do not say the work passes: the gate runs the verification itself.

## What to hand over

- `code_report`: the path of the code report.

- `tests_passed`: `yes` when every verification command exited 0 on your last run, otherwise `no`.
