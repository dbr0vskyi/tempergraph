# Judge reading

## Purpose

What each judge of the temperspec workflow is told to read and to cite before it grades. The code gate hands its judge the list of changed source files and a reading budget sized to the change, so that the judge reads the code before it grades alignment ([code](code.spec.md)); every judge is asked for the line behind a MET, so that a grade rests on a file it read and not on search fragments. The owner who reads an escalation and the maintainers of the judge briefs depend on it. Part of the [overview](overview.spec.md).

## Depends on

- `regeneration.spec.md`: which changed files were written by the regeneration unit alone (RGN-B13)

## Behaviours

### JRD-B1 Every changed source file is listed

WHEN the code gate hands its judge the check evidence of a change THE code gate SHALL list every source file the change touched (any file other than a Markdown document and any file that [RGN-B13](regeneration.spec.md) leaves out of the changed paths) with the lines it changed (lines added plus lines removed since the run's base), the file with the most changed lines first.

- GIVEN a change that touches source files of 120, 80 and 30 changed lines, one Markdown document and one file that only the regeneration unit's commit changed WHEN the code gate hands its judge the check evidence THEN the evidence lists the three source files in the order of 120, 80 and 30 lines, each with its count, and does not list the document or the file the regeneration wrote
- GIVEN a change that touches 40 source files WHEN the judge's prompt is built THEN the prompt names all 40 files
- GIVEN a change that touches only Markdown documents WHEN the code gate hands its judge the check evidence THEN the evidence says the change has no source file

### JRD-B2 The reading budget grows with the change

WHEN the code gate hands its judge the check evidence of a change THE code gate SHALL state a reading budget of one source file to read for every 50 changed source lines, rounded up, within a floor of 10 files and a ceiling of 50.

- GIVEN a change of 2,100 changed source lines WHEN the code gate hands its judge the check evidence THEN the evidence states 2,100 changed source lines and a reading budget of 42 files
- GIVEN a change of 2,101 changed source lines WHEN the code gate hands its judge the check evidence THEN the reading budget is 43 files
- GIVEN a change of 120 changed source lines WHEN the code gate hands its judge the check evidence THEN the reading budget is 10 files
- GIVEN a change of 5,000 changed source lines WHEN the code gate hands its judge the check evidence THEN the reading budget is 50 files

### JRD-B3 The judge reads the listed files before it grades alignment

WHEN the code gate briefs its judge THE code gate SHALL tell the judge to read each source file the evidence lists (the file itself, not only search results from it), in the listed order, up to the reading budget, before it grades an alignment criterion.

- GIVEN a change that touches 12 source files and a reading budget of 12 files WHEN the judge reads its brief and the evidence THEN they tell it to read all 12 files, the file with the most changed lines first, before it grades `ts-code-aligned` or `ts-code-related`
- GIVEN a change that touches 80 source files and a reading budget of 10 files WHEN the judge reads its brief and the evidence THEN they tell it to read the first 10 files of the list before it grades `ts-code-aligned` or `ts-code-related`

### JRD-B4 A file left unread is named, and nothing rests on it

WHEN the evidence lists more source files than the reading budget covers THE code gate SHALL tell its judge to grade UNVERIFIABLE, naming the files it did not read, any alignment criterion that rests on one of them.

- GIVEN a change that touches 80 source files and a reading budget of 10 files WHEN the judge has read the first 10 files of the list THEN its brief has told it to grade UNVERIFIABLE, naming the 70 files it did not read, an alignment criterion whose result depends on one of them
- GIVEN the same change WHEN the judge grades an alignment criterion that rests only on files it read THEN the unread files do not limit that grade

### JRD-B5 A MET carries its quoted line

WHEN a judge of the workflow is briefed THE workflow SHALL ask the judge to quote, behind every criterion it grades MET, the line it relied on, with its path and line number.

- GIVEN the brief of each step judge, the judges of reading sessions included, and the stance of the outcome judge WHEN each text is read THEN each asks the judge to quote the line, with its path and line number, behind every MET

### JRD-B6 Search lines alone are PARTIAL

WHEN a judge of the workflow is briefed THE workflow SHALL tell the judge to grade a criterion PARTIAL, not MET, when the only evidence it saw for the criterion is lines printed by a search.

- GIVEN the brief of each step judge, the judges of reading sessions included, and the stance of the outcome judge WHEN each text is read THEN each tells the judge to grade PARTIAL, not MET, a criterion whose only evidence is lines a search printed
- GIVEN a judge that found a line with a search and then read the file around that line WHEN it grades the criterion MET THEN it quotes that line from the file it read

### JRD-B7 A criterion the check verified is graded from its finding

WHEN a judge of the workflow is briefed THE workflow SHALL tell the judge to grade a criterion the gate's check verified from the check's finding, quoting that finding as the line behind its MET, and never to grade it UNVERIFIABLE because the judge cannot run the check.

- GIVEN the brief of each step judge, the judges of reading sessions included, and the stance of the outcome judge WHEN each text is read THEN each says that a check-verified criterion is graded from the check's finding and is not UNVERIFIABLE for want of running it

## Acceptance criteria

- JRD-AC1 (JRD-B1): The check evidence of the code gate for a change that touches source files of 120, 80 and 30 changed lines, one Markdown document and one file that only the regeneration unit's commit changed lists exactly the three source files, in the order of 120, 80 and 30 lines, each with its count, and states 230 changed source lines
- JRD-AC2 (JRD-B1): The judge's prompt for a change that touches 40 source files names all 40
- JRD-AC3 (JRD-B2): The check evidence for changes of 120, 2,100, 2,101 and 5,000 changed source lines states reading budgets of 10, 42, 43 and 50 files
- JRD-AC4 (JRD-B3): The code judge's brief tells the judge to read each source file the evidence lists (the file itself, not only search results from it), up to the reading budget, before it grades `ts-code-aligned` or `ts-code-related`
- JRD-AC5 (JRD-B4): The code judge's brief tells the judge to grade UNVERIFIABLE, naming the files it did not read, an alignment criterion that rests on a listed file beyond the reading budget
- JRD-AC6 (JRD-B5): The brief of each step judge, the judges of reading sessions included, and the stance of the outcome judge asks for the quoted line, with its path and line number, behind every MET
- JRD-AC7 (JRD-B6): The brief of each step judge, the judges of reading sessions included, and the stance of the outcome judge tells the judge to grade PARTIAL, not MET, a criterion whose only evidence is lines a search printed
- JRD-AC8 (JRD-B7): The brief of each step judge, the judges of reading sessions included, and the stance of the outcome judge says that a criterion the gate's check verified is graded from the check's finding, quoted as the line behind its MET, and never UNVERIFIABLE because the judge cannot run the check
