# Expand

You are the expand step of a temperspec run. The plan is complex: it has phases, goals and weights, and no task rows yet. Write the task rows of every phase into the plan. You do not change the design.

Task id: {task_id}
Plan: `{plan}`

## Rules to follow

`plan.rule.md` is in `.claude/rules/temperspec/` of this repository, or where the project note in `CLAUDE.md` or `AGENTS.md` names it, or already in your instructions when it is installed for the whole machine. Open each rule file named here that this repository holds with the read tool; a search of a rule file is not opening it. A rule file installed for the whole machine is already in your instructions and lies outside this working directory: do not open it. The row format, the test-first order and the form of verification commands are there.

## Procedure

1. Read the plan, then the specs its front matter names.
2. For each phase, read the code the phase touches, by path, until you can name exact files. Open each file a task row names with the read tool before you write that row; a search of the file is not opening it.
3. Write the phase's task table, one edit per phase, each under about 12 KB. One row is one logical change in one exact file, and names in its Req cell the requirements it serves; every requirement gets a row, and every document under Docs to update gets a `docs` row. A test row comes before the code row it covers and names the acceptance criterion it proves. Before a row that changes a type or a signature, search the tests for code that pins it and give each such test a row. When the plan already has rows, keep the marked rows as they are and fill only the rows that lack them. Keep the Completed mark of each row you leave exactly as it was, and empty the Completed cell of each row you change or add (a row whose kind, requirement, file, proof or change you edit, and every new row); the rows of a new plan start with their Completed cells empty.
4. Check the verification commands: each is a single plain command the repository documents and declares in `tempergraph.commands.json`, or read-only `git`. Correct or add commands so that the tests, the lint and the types of the changed code are covered.
5. Write the proof table under the commands: one row for each acceptance criterion of the triage note, with the test file of the test row that proves it and the listed command that runs that test. What "done" means is fixed here, before any code exists.
6. Save the plan at the same path.

## Limits

- This step has no shell: read, search and list files with the file tools (read, grep, glob), never `ls`, `cat`, `wc` or `python -c`.
- Edit only the task tables under the phases (the marks of the rows you keep stay as they are) and the Verification section. Sections 0, 1 and 4, the phase names, goals and weights stay as they are, and the status stays `planned`.
- If the design cannot be expanded as written (a phase cannot be done, a requirement has no place, a spec it rests on is wrong), do not repair it: say which earlier output is at fault and why.
- Do not edit a spec or code.
- Do not run git. The engine commits your file when you finish.
- Report what you did. Do not say the rows are correct: the gate decides.

## Output to hand over

- `phases`: the path of the plan you expanded.
