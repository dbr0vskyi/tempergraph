# Parallel reading

## Purpose

The discovery and setup steps read before they write. When a step has two or more subjects to read (the gaps of the triage note, the component folders of a repository), it first starts one read-only reading session for each, a few at a time on the engine's concurrent map ([MAP-B7](../../../tempergraph/docs/specs/map-unit.spec.md), [MAP-B9](../../../tempergraph/docs/specs/map-unit.spec.md)), and its one writing session then closes the gaps or writes the specs from their findings, which reach it as [VAL-B9](../../../tempergraph/docs/specs/step-values-and-template-keys.spec.md) renders them. The reading sessions write no document, so every spec, the hand-off and every commit stay the writing session's, and the criteria of [discovery](discovery.spec.md) and [setup](setup.spec.md) judge its output. A reading session that fails runs again alone ([MAP-B10](../../../tempergraph/docs/specs/map-unit.spec.md)), and the sessions in flight share the run's cost cap ([BUD-B12](../../../tempergraph/docs/specs/budgets-and-failures.spec.md)). The owner who waits for a run and the maintainers of the two steps depend on it. Part of the [overview](overview.spec.md).

## Behaviours

### PRL-B1 One reading session for each gap and each open question to read

WHEN the full discovery step is entered from triage or from the short visit and the triage note lists two or more rows to read THE discovery step SHALL start one reading session for each gap row and one for each uncertainty row that says `Blocks` or `Shapes` and is routed to `code`, `docs` or `source`.

- GIVEN a triage note that lists three gaps WHEN the full discovery step runs THEN three reading sessions run, one for each gap
- GIVEN a triage note that lists two gaps WHEN the full discovery step runs THEN two reading sessions run
- GIVEN a triage note that lists one gap and the uncertainty rows U1 (`Shapes`, `Route: code`), U2 (`Blocks`, `Route: owner`) and U3 (`Detail`, `Route: plan`) WHEN the full discovery step runs THEN two reading sessions run, one for the gap and one for U1
- GIVEN a triage note whose four gaps each say `Covered by` WHEN the run takes the short visit THEN no reading session starts

### PRL-B2 No reading session for fewer than two rows to read

WHEN the discovery step is entered and the triage note lists fewer than two rows to read (gap rows, and uncertainty rows that say `Blocks` or `Shapes` and are routed to `code`, `docs` or `source`) THE discovery step SHALL start no reading session.

- GIVEN a triage note that lists one gap WHEN the full discovery step runs THEN one writing session runs and no reading session starts
- GIVEN a triage note that lists no gap and a plan gate that sends the run back to discovery WHEN the discovery step runs THEN one writing session runs and no reading session starts

### PRL-B3 A return to discovery starts no reading session

WHEN a later gate sends the run back to the discovery step THE discovery step SHALL start no reading session.

- GIVEN a visit that ran three reading sessions and a plan gate that sends the run back to discovery WHEN the discovery step runs again THEN one more writing session runs and no reading session starts
- GIVEN a visit that ran three reading sessions and a code gate that sends the run back to discovery WHEN the discovery step runs again THEN one more writing session runs and no reading session starts

### PRL-B4 One reading session for each component folder

WHEN the setup step begins on a repository with two or more component folders (top-level folders other than hidden ones, dependency folders, build-output folders and the documentation folder) THE setup step SHALL start one reading session for each component folder.

- GIVEN a repository with the folders `src`, `tests`, `docs`, `node_modules` and `.github` WHEN the setup step begins THEN reading sessions start for `src` and `tests` only
- GIVEN a repository with three component folders WHEN the setup step begins THEN three reading sessions run, one for each folder

### PRL-B5 No reading session for fewer than two component folders

WHEN the setup step begins on a repository with no component folder or one (PRL-B4) THE setup step SHALL start no reading session.

- GIVEN a repository whose only top-level folders are `src` and `docs` WHEN the setup step begins THEN one writing session runs and no reading session starts
- GIVEN a repository with no top-level folder WHEN the setup step begins THEN one writing session runs and no reading session starts

### PRL-B6 Reading sessions only read

WHEN a reading session starts THE workflow SHALL give it only tools that read: files, searches and folder listings and, for the discovery step, web search and public pages.

- GIVEN a reading session of the discovery step WHEN it starts THEN its tools read files, search them, list folders and search the web, and none writes a file or runs a command
- GIVEN a reading session of the setup step WHEN it starts THEN its tools read files, search them and list folders, and none writes a file, runs a command or reaches the web

### PRL-B7 Three reading sessions at a time

WHEN a step has more than three reading sessions to run THE workflow SHALL run at most three of them at the same time.

- GIVEN a triage note that lists five gaps WHEN the reading sessions run THEN never more than three are open at once and all five run
- GIVEN a triage note that lists two gaps WHEN the reading sessions run THEN both are open at the same time

### PRL-B8 A reading session is briefed on one subject

WHEN a reading session starts THE workflow SHALL brief it on one subject: the row of its gap with the path of the triage note, or the name of its component folder, and no other subject's row or name.

- GIVEN a triage note with gaps G1 and G2 WHEN the reading session of G2 is briefed THEN the brief carries the row of G2 and the path of the triage note, and not the row of G1
- GIVEN a repository with the component folders `src` and `tests` WHEN the reading session of `tests` is briefed THEN the brief names `tests` and not `src`

### PRL-B9 A reading session ends with one line of findings

WHEN a reading session is briefed THE workflow SHALL tell it to end with its findings as one line of at most 1,500 characters that names each file, with the line ranges or ids, its answer rests on, or what it searched when it found nothing.

- GIVEN a reading session of the discovery step WHEN its brief is read THEN it asks for one line of at most 1,500 characters that names the files with their line ranges or ids, or what was searched
- GIVEN a reading session of the setup step WHEN its brief is read THEN it asks for the same line

### PRL-B10 The writing session waits for every reading session

WHEN the reading sessions of a step have started THE workflow SHALL start the step's writing session only after every one of them has ended with its findings.

- GIVEN three reading sessions of which the first to start ends last WHEN they have all ended THEN the writing session starts after the last of them
- GIVEN a reading session that ends with no findings line WHEN the other reading sessions have ended THEN that session runs again, alone, and the writing session has not started

### PRL-B11 The writing session is given the findings

WHEN the writing session of a step starts THE workflow SHALL brief it with the findings of the step's reading sessions, one line for each subject led by its gap number or folder name, in the order of the gap rows of the triage note (for setup, in the alphabetical order of the folder names), or with the statement that no reading session ran and that it reads its subjects itself.

- GIVEN reading sessions of gaps G1, G2 and G3 that ended in the order G3, G1, G2 WHEN the writing session starts THEN its brief lists the findings of G1, G2 and G3 in that order, each line led by its gap
- GIVEN reading sessions of the folders `tests` and `src` WHEN the writing session of the setup step starts THEN its brief lists the findings of `src` before those of `tests`
- GIVEN a visit that ran three reading sessions and a plan gate that sends the run back to discovery WHEN the writing session starts again THEN its brief lists the same three findings
- GIVEN no reading session ran WHEN the writing session starts THEN its brief lists no findings and tells it to read its subjects itself

### PRL-B12 Findings are claims to confirm

WHEN the writing session is briefed with findings THE workflow SHALL tell it that a finding is a claim to confirm in the file it names before a document rests on it.

- GIVEN a writing session briefed with findings WHEN its brief is read THEN it says that a finding is a claim to confirm in the file it names before a document rests on it

### PRL-B13 A reading session is judged on its own

WHEN a reading session ends with findings THE workflow SHALL grade them with one judge session of their own, on whether they answer their subject or say what was searched, unless the check of the gate fails them first ([JDG-B1](../../../tempergraph/docs/specs/judge-and-verdict.spec.md)).

- GIVEN a visit with three reading sessions WHEN the three have ended with findings that pass the check THEN the run holds one judge session for each of them, three in all, apart from the judge session of the writing session
- GIVEN a reading session whose findings the judge does not accept WHEN the other reading sessions have ended THEN only that reading session runs again

### PRL-B14 One judge session for each attempt of a gate

WHEN a gate of the workflow judges an attempt THE workflow SHALL start one judge session for it, however many reading sessions the step had, apart from the re-ask that [JDG-B2](../../../tempergraph/docs/specs/judge-and-verdict.spec.md) states.

- GIVEN a discovery visit with three reading sessions WHEN the attempt of its writing session is judged THEN one judge session runs for the attempt
- GIVEN a setup with three reading sessions WHEN the attempt of its writing session is judged THEN one judge session runs for the attempt
- GIVEN a reading session WHEN its attempt is judged THEN one judge session runs for the attempt

## Acceptance criteria

- PRL-AC1 (PRL-B1): In a stand-in run of the full discovery step on a triage note that lists three gaps, three reading sessions run, one for each gap; with two gaps two run; a run that takes the short visit starts none; the items read from a note with one gap and uncertainty rows routed to the code, to the owner and to the plan are the gap and the row routed to the code
- PRL-AC2 (PRL-B2): In a stand-in run of the full discovery step on a triage note that lists one gap, and in one on a note that lists no gap, one writing session runs and no reading session starts
- PRL-AC3 (PRL-B3, PRL-B11): In a stand-in run in which a plan gate, and in another a code gate, sends the run back to discovery after a visit with three reading sessions, one more writing session runs, no reading session starts, and the brief of that writing session lists the same three findings
- PRL-AC4 (PRL-B4): In a stand-in run of the setup step on a repository with the folders `src`, `tests`, `docs`, `node_modules` and `.github`, reading sessions run for `src` and `tests` only, and for no other folder
- PRL-AC5 (PRL-B5): In a stand-in run of the setup step on a repository whose only top-level folders are `src` and `docs`, and in one on a repository with no top-level folder, one writing session runs and no reading session starts
- PRL-AC6 (PRL-B6): The tools of a reading session of the discovery step read files, search them, list folders and search the web, those of a reading session of the setup step are the same without the web, and neither has a tool that writes a file or runs a command
- PRL-AC7 (PRL-B7): In a stand-in run of the full discovery step on a triage note that lists five gaps, with each reading session held open for a moment, never more than three are open at once and all five run
- PRL-AC8 (PRL-B8): The brief of the reading session of the second of two gaps carries that gap's row and the path of the triage note and not the row of the first gap, and the brief of the reading session of `tests` names `tests` and not `src`
- PRL-AC9 (PRL-B9): The brief of a reading session of each step asks for its findings as one line of at most 1,500 characters that names the files with their line ranges or ids, or what it searched
- PRL-AC10 (PRL-B10): In a stand-in run in which the reading session of the first gap ends last, the writing session starts after it, and a reading session that ends with no findings line runs again, alone, before the writing session starts
- PRL-AC11 (PRL-B11): In a stand-in run in which the reading sessions of gaps G1, G2 and G3 end in the order G3, G1, G2, the brief of the writing session lists their findings in the order G1, G2, G3, each line led by its gap; in one of the setup step on the folders `src` and `tests` it lists the findings of `src` first; and in a run with no reading session it lists none and tells the session to read its subjects itself
- PRL-AC12 (PRL-B12): The brief of a writing session that is given findings says that a finding is a claim to confirm in the file it names before a document rests on it
- PRL-AC13 (PRL-B13): A stand-in run of a visit with three reading sessions holds three judge sessions for them, one for each, besides the judge session of the writing session, and a reading session whose findings the judge does not accept is the only one that runs again
- PRL-AC14 (PRL-B14): A stand-in run of the full discovery step with three reading sessions and one of the setup step with three each start one judge session for each attempt of the writing session and one for each attempt of a reading session

## Open questions

- Judges of one gate. The engine gives a gate one judge and defers a panel of judges ([JDG-B10](../../../tempergraph/docs/specs/judge-and-verdict.spec.md), [decision 0005](../../../tempergraph/docs/adr/independent-judge-engine-verdict.adr.md), [decision 0063](../../../tempergraph/docs/adr/council-is-a-gated-step-with-engine-tallied-outcomes.adr.md)), and no gate of this workflow has more than one, so no judges run at the same time. The engine also asks every model step, a reading session included, for a judge, which is why PRL-B13 exists. Default: each gate keeps its one judge, the judges of the existing steps are unchanged, and each reading gate has one of its own (PRL-B13, PRL-B14). Reopen when the engine can run several judges of one gate concurrently and a gate gains from splitting its criteria between them, the code gate's judge, which reads up to 50 files, being the first candidate; or when the engine lets a read-only step go without a judge and the reading sessions are shown not to need one.
- How many subjects, and how many at a time. Two subjects before reading sessions start and three at a time rest on no measured run: with one subject nothing runs at the same time, so two is the least (PRL-B2, PRL-B5), and three is the engine's own default ([MAP-B7](../../../tempergraph/docs/specs/map-unit.spec.md)). Default: two, and three. A map takes at most 50 items, so a triage note of more than 50 gaps, or a repository of more than 50 component folders, stops the run at the map ([MAP-B5](../../../tempergraph/docs/specs/map-unit.spec.md)); default: no list is cut to fit, and a task or a repository that large is split first. Reopen when measured runs of the two steps give their cost and time with and without reading sessions, or when such a case occurs.
- Component folders of a large repository. A repository whose code sits under one top-level folder, or under a folder of packages, gets a reading session that reads nearly all of it, so reading in parallel gains little there. Default: top-level folders only, with the exclusions of PRL-B4. Reopen when the setup of such a repository has been measured.
