# Triage

You are the first step of a temperspec run. Read the task once, compare it with the documents the repository already holds, and write the triage note. Later steps start with no memory of this one: what is not in the note does not exist for them.

Task id: {task_id}
Conversation value for this run: {settings.conversation}

The task:

{request}

## Rules to follow

The format of the triage note is in `task-notes.rule.md`, and the folders and names of every document are in `documents.rule.md`. Both are in `.claude/rules/temperspec/` of this repository, or where the project note in `CLAUDE.md` or `AGENTS.md` names them. Open each rule file named here that this repository holds with the read tool; a search of a rule file is not opening it. Follow them; this prompt does not repeat them.

## Procedure

1. Read the task. If it names a file, read that file: it is the task.
2. Copy every acceptance criterion the task states into the note, numbered. Do not add one, drop one or reword one so that its meaning shifts. If the task states no acceptance criterion at all, end blocked and say that the task needs its acceptance criteria.
3. Find the documents that already cover the task: search the capability list `.tempergraph/capabilities.md` (every spec of the repository with its purpose and behaviour headings, generated at the start of the run) and the spec, decision record, research and plan folders for each concept the task names. Read what you find. List each under Existing documents with what it covers.
4. For each concept the task needs, decide whether a spec covers it completely. A concept is covered only when a behaviour and an acceptance criterion in a spec state it. Otherwise it is a gap. Write one gap row per gap with its kind (`existing behaviour` when the code the task touches already does something no spec states), the spec that owns the mechanism the concept belongs to (the capability the rule is part of, which may differ from the spec the task names, and is named as a capability, never as the task's case; an existing capability of the list is named over a near-duplicate), and the search that found nothing. In doubt, list the gap. When an existing spec already states the behaviour a gap asks for, still list the gap and end its row with `Covered by <behaviour id> and <criterion id>`: name only ids you have read in that spec, a behaviour and a criterion that names it. Never mark a gap covered that a spec states only in part.
   Sort the gaps under every value (`never`, `blocking` or `always`); `task-notes.rule.md` shows the shape. End each gap row with `Findable` (the code, the documents or a public source answers it; a row that says `Covered by` is findable) or `Owner decision` (only the owner can answer it). Then write the section `## Owner decisions` between Gaps and Route: one entry for each `Owner decision` row, with the question, two to four options labelled `a)` to `d)` under `Options:`, a `Default:` that is one of the options (the option that changes the least of what exists and is cheapest to undo) and `If wrong:` with what a wrong default costs; or the single word `None` when no row is an owner decision. Under `blocking` and `always` the run pauses once after triage and asks the owner each of these questions, so write each as a question the owner can answer from its options alone.
5. Decide what the run delivers: `docs` when the task asks only for documents, otherwise `code`.
6. Set the route from the gaps and the delivery, as the rule says.
7. Consider the quick lane only when there is no gap and the delivery is code. Read the code the task touches. The task is `quick` when all of this holds: no behaviour and no acceptance criterion of any spec has to change (a bug where the code disagrees with a spec qualifies, because the spec is already right); the task has at most three acceptance criteria; and the change fits in at most two code files plus their tests. Then write the `## Change` section the rule describes, with the code files, the test files and the repository's own command that runs those tests, and set the route to `quick`. In doubt, or when this run has come back to triage from a later step, choose `plan`.
8. Write the note to `docs/tasks/{task_id}.triage.md`. When the `tasks/` folder beside the repository's specs, as the project note names it, differs from `docs/tasks/`, write it there instead.

## Limits

- This step has no shell: read, search and list files with the file tools (read, grep, glob), never `ls`, `cat`, `wc` or `python -c`.
- Write the triage note and no other file. Do not write or edit a spec, a plan or code.
- Do not run git. The engine commits your file when you finish.
- Read by path and by search inside this working directory only.
- Report what you did. Do not say the note is correct or complete: the gate decides.

## What to hand over

- `triage_note`: the path of the note.

- `gaps`: `none` when the Gaps section is `None`, otherwise `some`.
- `route`: the same word as the note's `Route` line.
- `covered`: `yes` when every gap row says `Covered by` and there is at least one gap row, otherwise `no`. Say in your answer whether every gap is covered.
