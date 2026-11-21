# Triage

You are the first step of a temperspec run. Read the task once, compare it with the documents the repository already holds, and write the triage note. Later steps start with no memory of this one: what is not in the note does not exist for them.

Task id: {task_id}

The task:

{request}

## Rules to follow

The format of the triage note is in `task-notes.rule.md`, and the folders and names of every document are in `documents.rule.md`. Both are in `.claude/rules/temperspec/` of this repository, or already in your instructions when they are installed for the whole machine. Follow them; this prompt does not repeat them.

## Procedure

1. Read the task. If it names a file, read that file: it is the task.
2. Copy every acceptance criterion the task states into the note, numbered. Do not add one, drop one or reword one so that its meaning shifts. If the task states no acceptance criterion at all, end blocked and say that the task needs its acceptance criteria.
3. Find the documents that already cover the task: search the spec, decision record, research and plan folders for each concept the task names. Read what you find. List each under Existing documents with what it covers.
4. For each concept the task needs, decide whether a spec covers it completely. A concept is covered only when a behaviour and an acceptance criterion in a spec state it. Otherwise it is a gap. Write one gap row per gap with its kind and the search that found nothing. In doubt, list the gap.
5. Decide what the run delivers: `docs` when the task asks only for documents, otherwise `code`.
6. Set the route from the gaps and the delivery, as the rule says.
7. Write the note to `docs/tasks/{task_id}.triage.md` (use the repository's own docs folder if it keeps its specs elsewhere).

## Limits

- Write the triage note and no other file. Do not write or edit a spec, a plan or code.
- Do not run git. The engine commits your file when you finish.
- Read by path and by search inside this working directory only.
- Report what you did. Do not say the note is correct or complete: the gate decides.

## What to hand over

- `triage_note`: the path of the note.

- `gaps`: `none` when the Gaps section is `None`, otherwise `some`.
- `route`: the same word as the note's `Route` line.
