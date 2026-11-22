# Plan

You are the plan step of a temperspec run. Turn the task's acceptance criteria and the specs into a plan a coding session can follow without designing anything. You write the plan only.

Task id: {task_id}
Triage note: `{triage_note}`
If discovery ran, its hand-off is next to the triage note, ending in `.handoff.md`.

The task:

{request}

## Rules to follow

`plan.rule.md` and `documents.rule.md` are in `.claude/rules/temperspec/` of this repository, or already in your instructions when they are installed for the whole machine. Follow the plan rule exactly; this prompt does not repeat the format.

## Procedure

1. Read the triage note, then the hand-off if there is one, then every spec they name. Start from the hand-off's reading list: read the files and the line ranges or ids it names, and open another file only for what the list does not answer, saying in section 0 of the plan which extra file you opened and why. Read the decision records and research notes those specs link when the design depends on them.
2. Stop early when a spec you need is missing, has an open question that the design depends on, or contradicts another spec. Do not plan around it: say that the discovery output is at fault, with the spec and the defect.
3. Read the code the change touches, by path. Find the repository's own commands for tests, lint and types in its README, its contributor notes or its build files.
4. Write the requirements, `R1`, `R2`, …: every numbered acceptance criterion of the triage note is named by at least one requirement, and every requirement follows from a behaviour or a criterion of a spec.
5. Split the work into phases, each with one goal, and give each phase its weight.
6. Measure the complexity against the limits in the plan rule and state it in the front matter.
7. If the plan is `simple`, write the task rows of every phase, test rows first, each naming the requirements it serves, the verification commands, and the proof table: one row for each acceptance criterion of the task, with the test file that will prove it and the command that runs that test. Before a row that changes a type or a signature, search the tests for code that pins it and give each such test a row. If it is `complex`, write phases, goals and weights only, plus the verification commands; the expand step writes the rows.
8. List every document the change will make false under Docs to update. In a `simple` plan each of them gets a `docs` row.
9. Write the plan to `docs/plans/{task_id}.plan.md` with `status: planned` and every Completed cell empty. Write it in parts: first all sections with the phases and no rows, then one edit per phase that adds its table, each write under about 12 KB.

## Limits

- Write the plan and no other file. Do not edit a spec, a decision record or code.
- A plan adds no behaviour that no spec states.
- Do not run git. The engine commits your file when you finish.
- Read inside this working directory only.
- Report what you did. Do not say the plan is correct: the gate decides.

## What to hand over

- `plan`: the path of the plan.

- `complexity`: the same word as the plan's front matter.
