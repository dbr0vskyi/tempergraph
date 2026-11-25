# Session record checks

## Purpose

What the gates of the temperspec steps confirm from the record of the step's session, so that what a prompt asks for is held by what the session did and not by what it reported: a session opens the rule files its prompt names, the expand step opens the files its task rows name, and the code step writes each phase's tests before its source. The record is the tool calls of the attempt's session that the engine gives a check ([CHK-B24](../../../tempergraph/docs/specs/check-contract-and-command-runs.spec.md)); where the engine gives none ([CHK-B25](../../../tempergraph/docs/specs/check-contract-and-command-runs.spec.md)), the criterion does not apply. "Opening" a file means a call of the read tool that ended without an error; lines printed by a search of a file never count. The seven steps are setup, triage, the short discovery, the full discovery, plan, expand and code, and a rule file is one of the `*.rule.md` files in the repository's `.claude/rules/temperspec/` folder. The reasons are in [the decision on rule files](../adr/a-step-check-confirms-that-each-rule-file-its-prompt-names-was-opened.adr.md) and [the decision on phases](../adr/a-phases-tests-and-source-are-the-files-of-its-test-and-code-rows.adr.md). The owner who reads a retry's findings and the maintainers of the step prompts depend on it. Part of the [overview](overview.spec.md).

## Behaviours

### SRC-B1 A rule file the prompt names must be opened

WHEN the check of a step runs and the session record shows no opening of a rule file that the step's prompt names and the repository holds THE step's check SHALL fail, naming the rule file.

- GIVEN a triage prompt that names `task-notes.rule.md` and `documents.rule.md`, a repository that holds both, and a session that opened `task-notes.rule.md` and only searched `documents.rule.md` WHEN the triage check runs THEN it fails naming `documents.rule.md` and does not name `task-notes.rule.md`
- GIVEN a session that opened every rule file its prompt names WHEN the step's check runs THEN it does not fail for a rule file
- GIVEN a session whose only call on `plan.rule.md` ended with an error WHEN the plan check runs THEN it fails naming `plan.rule.md`
- GIVEN a session that opened `plugins/x/rules/spec.rule.md` and a repository that holds `.claude/rules/temperspec/spec.rule.md` WHEN the discovery check runs THEN it does not fail for `spec.rule.md`
- GIVEN a prompt that names `task-notes.rule.md` and `documents.rule.md` and a repository that holds only `task-notes.rule.md`, and a session that opened neither WHEN the check runs THEN it fails naming `task-notes.rule.md` and does not name `documents.rule.md`
- GIVEN attempt 1 that opened every rule file its prompt names and a retry attempt whose session opened none WHEN the check runs after the retry THEN it fails naming each of them

### SRC-B2 The prompt tells the session to open the files it names

WHEN a step's prompt names a rule file THE workflow SHALL have the prompt tell the session to open that file with the read tool, not by a search of it, when the repository holds it.

- GIVEN the prompt of each of the seven steps WHEN it is read THEN it tells the session to open each rule file it names that the repository holds with the read tool and says that a search of a rule file is not opening it
- GIVEN the short discovery prompt, which limits the visit to 10 files WHEN it is read THEN it says that the rule files it names do not count in that limit

### SRC-B10 The prompt places the rule files in the repository

WHEN a step's prompt names a rule file THE workflow SHALL have the prompt place that file in the repository, in its `.claude/rules/temperspec/` folder or where the project note names it, and nowhere else.

- GIVEN the prompt of each of the seven steps WHEN it is read THEN it says the rule files it names are in `.claude/rules/temperspec/` of the repository or where the project note names them
- GIVEN the prompt of each of the seven steps WHEN it is read THEN it says nothing of a rule file installed for the whole machine

### SRC-B3 A repository with none of the rule files asks for none

WHEN the check of a step runs in a repository whose `.claude/rules/temperspec/` folder holds none of the rule files the step's prompt names, THE step's check SHALL record the rule-file criterion not applicable, with a message that says the rule files are not in the repository.

- GIVEN a repository with no `.claude/rules/temperspec/` folder WHEN the check of any of the seven steps runs THEN the rule-file criterion is not applicable and its message says the rule files are not in the repository

### SRC-B4 The expand prompt tells the session to open each file a row names

WHEN the expand step is prompted THE workflow SHALL have the prompt tell the session to open each file a task row names, with the read tool, before it writes that row.

- GIVEN the expand prompt WHEN it is read THEN it tells the session to open each file a task row names with the read tool before it writes that row

### SRC-B5 A row's existing file the session never opened fails the expand check

WHEN the expand check runs on a plan with a task row that names a file that exists in the repository and the session record shows no opening of that file THE expand check SHALL fail, naming the row and the path.

- GIVEN a row `2.1` that names `src/auth/session.py`, which exists, and a session that only searched it WHEN the expand check runs THEN it fails naming row `2.1` and `src/auth/session.py`
- GIVEN a row that names `tests/test_new.py`, which does not exist WHEN the expand check runs THEN it does not fail for that row
- GIVEN a session that opened every existing file the rows name WHEN the expand check runs THEN it does not fail for a row's file
- GIVEN rows `1.2` and `2.3` that name the same unread file WHEN the expand check runs THEN it names both rows
- GIVEN a row of kind `docs` that names an existing spec the session never opened WHEN the expand check runs THEN it fails naming that row and the spec

### SRC-B6 A phase's source changed before its tests fails the code check

WHEN the code check runs on a plan whose phase has `test` rows and `code` rows and the session record shows the file of a `code` row of the phase changed before the file of any `test` row of the phase was first written (a change or a write being a call of the edit or the write tool that ended without an error, and a file named by rows of several phases counting for the first phase that names it) THE code check SHALL fail, naming the phase.

- GIVEN phase 2 with the test row file `tests/test_b.py` and the code row file `src/b.py`, and a record that writes `tests/test_b.py` and then edits `src/b.py` WHEN the code check runs THEN it does not fail for phase 2
- GIVEN the same plan and a record that edits `src/b.py` and then writes `tests/test_b.py` WHEN the code check runs THEN it fails naming phase 2
- GIVEN phases 1 and 3 whose code rows name `src/a.py`, and a record that writes the test of phase 1, edits `src/a.py`, writes the test of phase 3 and edits `src/a.py` again WHEN the code check runs THEN it does not fail for phase 3
- GIVEN a record that edits `src/b.py` and never writes `tests/test_b.py`, as a retry that only repairs the source does WHEN the code check runs THEN it does not fail for the order of phase 2
- GIVEN a `docs` row or a `chore` row whose file the record changes before the phase's test file is written WHEN the code check runs THEN it does not fail for that file
- GIVEN a call that edited `src/b.py` and ended with an error, followed by the write of `tests/test_b.py` and a good edit of `src/b.py` WHEN the code check runs THEN it does not fail for phase 2

### SRC-B7 The quick lane has no phases

WHEN the code check runs on a run in the quick lane THE code check SHALL record the test-first criterion not applicable, with a message that says the quick lane has no phases.

- GIVEN a quick-lane run whose record edits the source file before it writes the test file WHEN the code check runs THEN the test-first criterion is not applicable and its message says the quick lane has no phases

### SRC-B8 Without a session record the criterion does not apply

WHEN a check of this spec runs and the engine gives it no session record, or a record in which a call of the read, edit or write tool has no path, THE check SHALL record each criterion of this spec that needs the record not applicable, with a message that says there is no session record to read.

- GIVEN a run with a stand-in executor that reports tool names only WHEN the rule-file check, the expand check and the code check run THEN each of their session-record criteria is not applicable and its message says there is no session record
- GIVEN the check preview of the code gate WHEN it runs THEN the rule-file and test-first criteria are not applicable
- GIVEN `observe.tool_inputs = off` WHEN the checks run THEN each of their session-record criteria is not applicable

### SRC-B9 A finding quotes no call

WHEN a check of this spec fails a criterion THE check SHALL name in its finding only the rule file, the row, the path and the phase it took from the step's prompt and the plan, and quote no call of the session.

- GIVEN a record with a shell call whose command holds a distinctive word WHEN a check of this spec fails a criterion THEN no finding and no evidence of the check holds the word

## Acceptance criteria

- SRC-AC1 (SRC-B1): The check of each of the seven steps fails, naming a rule file that its prompt names and the repository holds, for a record that holds no opening of it, and does not fail for a record that holds one
- SRC-AC2 (SRC-B1): A search of a rule file and a call on it that ended with an error do not count as opening it, an opening by another folder's path with the same file name does, and a rule file the repository does not hold is not asked for
- SRC-AC3 (SRC-B1): The check after a retry attempt reads only the retry session's calls
- SRC-AC4 (SRC-B2): The prompt of each of the seven steps tells the session to open each rule file it names that the repository holds with the read tool and says that a search of a rule file is not opening it, and the short discovery prompt says that the rule files do not count in its limit of 10 files
- SRC-AC13 (SRC-B10): The prompt of each of the seven steps places the rule files it names in `.claude/rules/temperspec/` of the repository or where the project note names them, and says nothing of a rule file installed for the whole machine
- SRC-AC5 (SRC-B3): With none of the rule files of its prompt in the repository's `.claude/rules/temperspec/` folder, the check of each of the seven steps marks the rule-file criterion not applicable and its message says the rule files are not in the repository
- SRC-AC6 (SRC-B4): The expand prompt tells the session to open each file a task row names, with the read tool, before it writes the row
- SRC-AC7 (SRC-B5): The expand check fails naming row `2.1` and `src/auth/session.py` for an existing file the record shows only searched, names both of two rows that name one unread file, and does not fail for a file that does not exist or a file the record shows opened
- SRC-AC8 (SRC-B6): The code check fails naming phase 2 for a record that edits the phase's source file and then writes its test file, and does not fail for the reverse order
- SRC-AC9 (SRC-B6): The code check does not fail a phase for a source file that an earlier phase names, for a phase whose test file the record never writes, for a `docs` or `chore` row's file, or for a call that ended with an error
- SRC-AC10 (SRC-B7): The code check of a quick-lane run marks the test-first criterion not applicable and says the quick lane has no phases
- SRC-AC11 (SRC-B8): The rule-file, expand and test-first criteria are not applicable, with a message that says there is no session record, for a stand-in executor that reports tool names only, in the check preview and under `observe.tool_inputs = off`
- SRC-AC12 (SRC-B9): The findings and the evidence of a failing check of this spec hold no word of a shell call's command in the record

## Open questions

- Should a failed test-first criterion send the code step back? It costs a retry session that cannot undo the order: the retry can only write the phase's tests before it touches the source again, or leave the source alone. Until answered: it fails the check, as the task asks. Owner: owner.
- Should the quick lane be checked as one phase made of its note's `Tests` and `Files`? Until answered: not applicable (SRC-B7). Owner: owner.
