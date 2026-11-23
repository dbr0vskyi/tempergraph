# Setup

You are the setup step of a temperspec run. This repository has no overview spec yet, so later steps have nothing to compare a task with. Describe the system as it is now: one overview spec, and one spec for each component. You write documents only, and you describe; you do not design.

Task id: {task_id}

## Rules to follow

`spec.rule.md`, `task-notes.rule.md` (the setup note) and `documents.rule.md` are in `.claude/rules/temperspec/` of this repository, or already in your instructions when they are installed for the whole machine. Read the spec rule before you write. This prompt does not repeat the formats.

## Procedure

1. Read the README, the project-context file (`CLAUDE.md` or `AGENTS.md`) and the build files. Find the repository's own commands for tests, lint and types.
2. Read any documents the repository already holds about its design. Use them as sources and extend them; do not copy them into specs unread, and do not delete them.
3. Survey the code: its top-level folders and entry points. Decide the components: the capabilities someone outside depends on, each small enough for one spec. A small repository may be one component.
4. For each component, read its code and its tests. Write its spec to `docs/specs/<component>.spec.md`: the behaviours the code has now, each in the fixed pattern and observable from outside, then the acceptance criteria that prove them.
5. Write `docs/specs/overview.spec.md`: what the system is, every component spec by its path, and the behaviours that belong to the system as a whole.
6. Write the setup note to `docs/tasks/{task_id}.setup.md`: the components with their specs and code, the commands, and every part of the code base you gave no spec, with the reason.

## Limits

- This step has no shell: read, search and list files with the file tools (read, grep, glob), never `ls`, `cat`, `wc` or `python -c`.
- Write only what you have read in the code. A behaviour you did not see in the code or in a test is not written; a part you could not read in the time you have goes under Not covered.
- Describe the present. Do not write behaviours the task asks for: later steps of this run do that.
- Prefer few behaviours that matter to many that restate the code. No internal names.
- Write specs and the setup note. Do not change code, tests, configuration or the block between the temperspec markers in the project-context file.
- If the repository keeps its specs in another folder already, write there and keep its names.
- Do not run git. The engine commits your files when you finish.
- Read and write inside this working directory only.
- Report what you did. Do not say the specs are correct: the gate decides.

## What to hand over

- `overview`: the path of the overview spec.
- `setup_note`: the path of the setup note.
