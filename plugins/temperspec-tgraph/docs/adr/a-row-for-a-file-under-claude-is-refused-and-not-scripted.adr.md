# A row for a file under `.claude/` is refused and not scripted

## Context

A plan row that names a file under `.claude/` pauses a run, because a session of the code step cannot change a file there. The plan check may refuse such a row, or mark it for a script that writes the file. The two differ in who changes the file and in what a plan may do to the folder that holds the repository's permissions, hooks and rule copies.

## Current state

- The session of the code step and of a phase changes files with `edit` and `write` (`plugins/temperspec-tgraph/workflow/temperspec/__init__.py` lines 267-278).
- A row that named a file under `.claude/` paused a run on `tool_access` (`plugins/temperspec-tgraph/docs/tasks/i166e.triage.md`, section Task).
- The folder `.claude/rules/temperspec/` holds the repository's copies of the rule files, which prepare installs with no session (`plugins/temperspec-tgraph/workflow/temperspec/routing.py` lines 22 and 531-543).
- The checks leave a path under `.claude/rules/` out of their evidence lists and a path under `.claude/` out of the quick-lane guard (`plugins/temperspec-tgraph/workflow/temperspec/checks.py` lines 625 and 1628).
- A file that a repository generates is declared with the command that writes it, and no task row names it ([RGN-B14](../specs/regeneration.spec.md)).
- This repository refreshes its `.claude/rules/temperspec/` copies by hand with `install_rules.py --update` (`CLAUDE.md`).

## Forces

- C1 (constraint): A session is not made able to write under `.claude/`. Source: the out-of-scope list of `plugins/temperspec-tgraph/docs/tasks/i166e.triage.md`
- C2 (constraint): A plan promises only rows that the code step can build or the workflow can carry out. Source: criterion 1 of `plugins/temperspec-tgraph/docs/tasks/i166e.triage.md`
- F1: The smallest change: no staging area and no hand-over of content from a session to a script.
- F2: No run, by a session or by a script, changes the files that decide what later sessions may do.
- F3: The owner learns what is left to a person.

## Options considered

### A. Refuse the row at the plan check and the expand check

How it works: a row whose file path starts with `.claude/` fails the check, whatever its kind, and the plan's hand-off section names the change a person makes.
For: F1 (a path test and a sentence in two prompts), F2 (no run touches the folder), C1 and C2 hold. Against: F3, because the owner sees the change only if the plan's hand-off section reaches them.

### B. Mark the row for a script that copies a staged file into `.claude/`

How it works: the session writes the content to a staging path, and a script after its session copies the file into `.claude/`.
For: C2 holds, and the change is made with no person. Against: F1, because the plan needs a staging path and a row pair for each file; F2, because a plan could then rewrite a settings file that holds permission rules.

### C. Refuse writes under `.claude/` and let a removal row delete there

How it works: the check refuses a row of every kind but `remove` for such a path, and the removal script deletes the file.
For: F1, since the removal script exists. Against: F2, because deleting a settings file that holds deny rules widens what later sessions may do.

## Decision

We will take option A: the plan check and the expand check refuse a task row, of any kind, for a file whose path starts with `.claude/`, and the plan names the change in its hand-off section for a person to make.

## Decision rationale

- C1: met; no session or script gets write access to `.claude/`.
- C2: met; no row asks for what neither a session nor the workflow does.
- F1: met; one path test and two prompt sentences.
- F2: met; no run changes the folder.
- F3: met in part; the plan names the change, and the owner reads it only through the plan.

## Consequences

A task whose criteria need a change under `.claude/` is finished by a person, and a repository that generates files there declares them as outputs of a regeneration so that no row names them.

## Risks

- A criterion that needs a `.claude/` change ends unmet. Limited by: the plan names the change, and the code judge reads the task's criteria. Noticed by: a criterion in the pull request's list that no commit meets.
- A path test that reads only the repository root misses a `.claude/` folder in a subfolder. Limited by: the pause of such a run names the refused call, so the path test can be widened to that folder. Noticed by: a `tool_access` pause on a row for a file in a subfolder's `.claude/`.

## Assumptions

- A1: A write under `.claude/` is refused to a session in an unattended run. Check: the pause record of a run whose plan names such a file. If wrong: the refusal turns down rows that a session could build.
- A2: The plan's hand-off section reaches the owner who must make the change. Check: read the pull request description's lists in `plugins/temperspec-tgraph/docs/specs/pull-request-description.spec.md`. If wrong: a change left to a person is missed.

## Revisit when

A run's session writes a file under `.claude/` with no `tool_access` pause.
