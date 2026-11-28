# Plan task rows

## Purpose

What a task row of a plan may be, and what the plan check and the expand check refuse about it. A task row is one logical change in one exact file, and its kind says what the change is: `test`, `code`, `docs`, `chore` or `remove`. A *removal row* is a row of kind `remove`; its file is the one file that goes away. A plan promises only rows that a session of the code step or of a phase can build by creating and changing files outside the repository's `.claude/` folder, or that the workflow itself carries out: a file that goes away is a removal row, which the workflow removes after the session ([file removal](file-removal.spec.md)), and a change to a file under `.claude/` is left to a person. The plan step, the expand step and the owner who reads a plan depend on it. Part of the [overview](overview.spec.md).

## Depends on

- Outside: git, for the files that the run's base commit holds

## Does not own

- How the workflow removes the file of a removal row, and the tools a session has: `file-removal.spec.md`
- Which completed marks of a plan's rows survive a trip back to the plan: `kept-marks.spec.md`
- That a file the repository declares as the output of a regeneration gets no task row: `regeneration.spec.md`
- The sections of a plan, its complexity and its trace to the task's criteria: `plan.spec.md`

## Behaviours

### PRW-B1 A task row has an id, a known kind and a file

WHEN the plan check or the expand check reads a task row that has no id, a kind other than `test`, `code`, `docs`, `chore` or `remove`, or no file THE check SHALL fail the plan, naming the row.

- GIVEN a simple plan with a row of kind `refactor` WHEN the plan check runs THEN it fails, naming the row
- GIVEN an expanded plan with a row whose File cell is empty WHEN the expand check runs THEN it fails, naming the row
- GIVEN rows of the kinds `test`, `code`, `docs`, `chore` and `remove`, each with an id and a file WHEN the plan check runs THEN it names none of them for its kind

### PRW-B2 A removal row needs no proof and no test before it

WHEN a plan holds a task row of kind `remove` THE plan check and the expand check SHALL ask neither for a criterion in its Proves cell nor for a test row before it in its phase.

- GIVEN a phase whose rows are, in order, a `remove` row with an empty Proves cell, a `test` row and a `code` row WHEN the plan check runs THEN it makes no finding about the `remove` row
- GIVEN a phase that holds a `remove` row and no other row WHEN the expand check runs THEN it makes no finding about a missing test row

### PRW-B3 A row for a file under `.claude/` is refused

WHEN a task row, whatever its kind, names a file whose path from the repository root starts with `.claude/` THE plan check and the expand check SHALL refuse the row, naming it.

- GIVEN a `docs` row whose file is `.claude/rules/temperspec/plan.rule.md` WHEN the plan check runs THEN it fails, naming the row
- GIVEN a `remove` row whose file is `.claude/settings.json` WHEN the expand check runs THEN it fails, naming the row
- GIVEN a `docs` row whose file is `.claude-plugin/plugin.json` WHEN the plan check runs THEN it makes no finding about the file's place

### PRW-B4 A removal row names a file the run's base commit holds

WHEN the file of a removal row is not a file that the run's base commit holds (the files of the workspace when the run has no base commit), or its path is absolute or has a parent element, THE plan check and the expand check SHALL refuse the row, naming it.

- GIVEN a removal row for a path that no file of the base commit has, and one for a folder of the repository WHEN the plan check runs THEN it fails for each, naming the row
- GIVEN a removal row whose file is `../outside.txt` WHEN the plan check runs THEN it fails, naming the row
- GIVEN a removal row for a file that the base commit holds and that an earlier commit of the run has already removed WHEN the expand check runs THEN it makes no finding about the file

### PRW-B5 The file of a removal row is named by no other row

WHEN a plan has a removal row and another row, of any kind, names the same file THE plan check and the expand check SHALL fail the plan, naming both rows.

- GIVEN a `remove` row and a `code` row for `src/old.py` WHEN the plan check runs THEN it fails, naming both rows
- GIVEN two `remove` rows for `src/old.py` WHEN the expand check runs THEN it fails, naming both rows
- GIVEN a `remove` row for `src/old.py` and a `code` row for `src/new.py` whose Change cell says its content comes from `src/old.py` WHEN the plan check runs THEN it makes no finding about the pair

### PRW-B6 The planning steps are told how a file goes away

WHEN the plan step and the expand step are briefed THE workflow SHALL tell each that a file that goes away is a row of kind `remove`, and that a file that moves is a `remove` row for its old path and a row of another kind for its new path.

- GIVEN the prompt of the plan step, the prompt of the expand step and the plan rule WHEN each is read THEN each lists the kind `remove` and says that it names a file that goes away
- GIVEN the same three texts WHEN each is read THEN each says that a moved file has a `remove` row for its old path and a row of another kind for its new path

### PRW-B7 The planning steps are told a file under `.claude/` gets no row

WHEN the plan step and the expand step are briefed THE workflow SHALL tell each that a file whose path starts with `.claude/` gets no task row and that the plan's hand-off section names the change a person makes there.

- GIVEN the prompt of the plan step and the prompt of the expand step WHEN each is read THEN each says that no row names a file whose path starts with `.claude/`
- GIVEN the same two prompts WHEN each is read THEN each says that the plan's hand-off section names the change that a person makes in such a file

## Acceptance criteria

- PRW-AC1 (PRW-B1): The plan check on a fixture simple plan with a row of kind `refactor` and the expand check on a fixture expanded plan with a row that has no file each fail and name the row, and the plan check on a fixture plan with one row of each of the five kinds makes no finding about a kind
- PRW-AC2 (PRW-B2): The plan check makes no finding about a fixture `remove` row that has an empty Proves cell and stands before the test row of its phase, and the expand check makes no finding about a fixture phase whose only row is a `remove` row
- PRW-AC3 (PRW-B3): The plan check and the expand check each fail and name a fixture `docs` row for `.claude/rules/temperspec/plan.rule.md` and a fixture `remove` row for `.claude/settings.json`, and make no finding about the place of a `docs` row for `.claude-plugin/plugin.json`
- PRW-AC4 (PRW-B4): The plan check fails and names a fixture removal row for a path no file of the base commit has, one for a folder and one for `../outside.txt`, and the expand check makes no finding about a removal row whose file the base commit holds and an earlier commit of the run removed
- PRW-AC5 (PRW-B5): The plan check and the expand check each fail and name both rows of a fixture plan in which a removal row and a `code` row, or two removal rows, name one file, and make no finding about a removal row whose file another row names only in its Change cell
- PRW-AC6 (PRW-B6): The prompt of the plan step, the prompt of the expand step and the plan rule each list the kind `remove` for a file that goes away and say that a moved file has a `remove` row for its old path and a row of another kind for its new path
- PRW-AC7 (PRW-B7): The prompt of the plan step and the prompt of the expand step each say that a file whose path starts with `.claude/` gets no task row and that the plan's hand-off section names the change a person makes there
