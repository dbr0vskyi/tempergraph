# Regeneration of generated files

## Purpose

What refreshes the files a repository generates, once a run's code step has passed and before anything reads the change: the *regeneration unit*, a unit of the workflow with no session, runs the commands that the repository declares for its generated files (for a workflow package, its stamp, its diagram and its authoring record) when a file they read has changed in the run, and commits what they wrote. A *regeneration* is one entry of the repository's declaration: a command, the inputs it reads and the outputs it writes. A *generated file* is an output of a regeneration. A regeneration is *due* when one of its inputs has changed in the run (RGN-B6). The declaration is the repository's own, in `tempergraph.regenerations.json` at its root, beside the commands file that [repository commands](repository-commands.spec.md) owns ([the decision](../adr/the-regenerations-of-a-repository-are-declared-beside-its-commands.adr.md)). No step's session runs these commands, so no plan row builds a generated file. How a regeneration that fails reaches the code step is owned by [regeneration failures](regeneration-failures.spec.md), and this spec does not own it. The independent review ([independent review](independent-review.spec.md)) and the outcome gate ([outcome gate](outcome-gate.spec.md)) read the files the unit wrote. The owner who reads a run's pull request, the maintainers of a repository's generated files and the maintainers of the workflow depend on it. Part of the [overview](overview.spec.md).

## Behaviours

### RGN-B1 The regeneration unit follows the code step

WHEN a run has passed the code step THE workflow SHALL run the regeneration unit before the independent review and before the outcome gate, whether the plan was built at once or one phase at a time and whatever the lane of the run.

- GIVEN a run that built its plan at once and passed the code step WHEN it goes on THEN the regeneration unit runs, then the review, then the outcome gate
- GIVEN a run that built its plan one phase at a time and passed the code step WHEN it goes on THEN the regeneration unit runs, then the review, then the outcome gate
- GIVEN a run in the quick lane that passed the code step WHEN it goes on THEN the regeneration unit runs and the outcome gate runs after it, with no review

### RGN-B2 The regeneration unit starts no session

WHEN the regeneration unit runs THE workflow SHALL start no model session for it.

- GIVEN a repository that declares a due regeneration and a count of the run's model sessions WHEN the unit runs THEN the count is the same before and after the unit
- GIVEN a repository that declares nothing and the same count WHEN the unit runs THEN the count is the same before and after the unit

### RGN-B3 A regeneration is a command with its inputs and outputs

WHEN the regeneration unit starts THE workflow SHALL read the regenerations of the repository from the list `regenerations` of `tempergraph.regenerations.json` at its root, each with a `name`, a `command`, `inputs` and `outputs`, the inputs and the outputs each a list of files and folders of the repository.

- GIVEN a file with `schema_version` 1 and one regeneration named `diagram` whose command is `make diagram`, whose input is `src` and whose output is `docs/diagram.md` WHEN the unit starts THEN it holds that one regeneration with that command, that input and that output
- GIVEN a file that lists two regenerations WHEN the unit starts THEN it holds both, in the order the file lists them

### RGN-B4 A declaration that cannot be used pauses the run

WHEN `tempergraph.regenerations.json` exists and is not valid JSON, has a `schema_version` other than 1, or holds a regeneration that lacks a `name`, a `command`, `inputs` or `outputs` THE regeneration unit SHALL pause the run at once, naming the file and what is wrong with it.

- GIVEN a file that is not valid JSON WHEN the unit starts THEN the run pauses, the pause names the file, and no trip back to the code step is made
- GIVEN a file with `schema_version` 2, or a regeneration that lacks a `command` WHEN the unit starts THEN the run pauses and names what is wrong
- GIVEN a repository with no `tempergraph.regenerations.json` WHEN the unit starts THEN the run does not pause for the file

### RGN-B5 Prepare declares no regeneration

WHEN prepare runs THE prepare step SHALL write no file that declares regenerations, whatever files the repository holds.

- GIVEN a Python repository with no `tempergraph.regenerations.json` WHEN prepare runs THEN the repository has no such file
- GIVEN a repository that holds a `stamp.json` and a `diagram/` folder and no `tempergraph.regenerations.json` WHEN prepare runs THEN the repository has no such file
- GIVEN a repository whose `tempergraph.regenerations.json` declares one regeneration WHEN prepare runs THEN the file is unchanged

### RGN-B6 A regeneration runs when an input changed

WHEN an input of a regeneration is a path the run has changed since the run's base commit, or a folder that holds one, THE regeneration unit SHALL run that regeneration.

- GIVEN a regeneration whose input is the folder `plugins/a` and a run that changed `plugins/a/blueprint.json` WHEN the unit runs THEN the regeneration runs
- GIVEN the same regeneration and a run that changed only `plugins/b/blueprint.json` WHEN the unit runs THEN it does not run
- GIVEN a regeneration whose input is the file `plugins/a/outcome.json` and a run that changed only `plugins/a/outcome.json.bak` WHEN the unit runs THEN it does not run

### RGN-B7 An output is never an input of its own regeneration

WHEN a path is an output of a regeneration THE regeneration unit SHALL not count a change to that path as a change to an input of that regeneration, even where an input folder holds it.

- GIVEN a regeneration whose input is the folder `plugins/a` and whose output is `plugins/a/stamp.json`, and a run that changed only `plugins/a/stamp.json` WHEN the unit runs THEN the regeneration does not run
- GIVEN the same regeneration and a run that changed `plugins/a/stamp.json` and `plugins/a/blueprint.json` WHEN the unit runs THEN it runs

### RGN-B8 A run with nothing due passes with nothing run

WHEN the repository has no `tempergraph.regenerations.json`, or declares no regeneration, or declares none that is due (RGN-B6), THE regeneration unit SHALL pass with no regeneration command run, no file written and no commit made.

- GIVEN a repository with no `tempergraph.regenerations.json` WHEN the unit runs THEN no regeneration command starts, the workspace is unchanged, no commit is added and the run goes on
- GIVEN a file whose `regenerations` list is empty WHEN the unit runs THEN the same holds
- GIVEN a declared regeneration whose inputs the run did not change WHEN the unit runs THEN the same holds

### RGN-B9 A command is started as the engine starts any command

WHEN the regeneration unit runs a due regeneration THE workflow SHALL start its `command` in the run's workspace as the engine starts any command ([SEC-B5](../../../tempergraph/docs/specs/security.spec.md)): its words as a list, with no shell.

- GIVEN a due regeneration whose command is `make docs --quiet` WHEN the unit runs it THEN the program `make` starts with the arguments `docs` and `--quiet` and no shell starts
- GIVEN a run in a linked worktree and a due regeneration WHEN the unit runs it THEN the command starts in the worktree and every file of the main checkout holds what it held before

### RGN-B10 A command that needs a shell, an absolute path or a parent path is refused

WHEN a regeneration's `command` has a shell metacharacter, a parent path or an absolute path THE regeneration unit SHALL refuse it, starting nothing for it ([RGF-B8](regeneration-failures.spec.md) says what the run does).

- GIVEN a regeneration whose `command` is `make docs && make site` WHEN the unit is to run it THEN it is refused for the shell metacharacter and nothing starts
- GIVEN a regeneration whose `command` is `/usr/bin/make docs` WHEN the unit is to run it THEN it is refused for the absolute path and nothing starts
- GIVEN a regeneration whose `command` is `make -C ../other docs` WHEN the unit is to run it THEN it is refused for the parent path and nothing starts

### RGN-B16 The declaration alone names the commands the unit starts

WHEN the regeneration unit runs THE workflow SHALL take every command it starts for a regeneration from `tempergraph.regenerations.json` alone, whatever `tempergraph.commands.json` lists.

- GIVEN a `tempergraph.commands.json` that lists `make site` and a declaration whose only regeneration is due and has the command `make docs` WHEN the unit runs THEN `make docs` starts and `make site` does not
- GIVEN a `tempergraph.commands.json` that lists `make docs` and no `tempergraph.regenerations.json` WHEN the unit runs THEN no regeneration command starts

### RGN-B11 What the regenerations wrote is committed

WHEN every due regeneration has passed THE regeneration unit SHALL commit the files they wrote on the run's branch, as every step of the workflow commits its files, so that no file they wrote is left uncommitted.

- GIVEN a due regeneration whose command writes its output WHEN it passes THEN the run's branch holds a commit of the unit with the output and the workspace has no uncommitted change
- GIVEN a due regeneration whose command writes the same bytes the output holds WHEN it passes THEN the unit adds no commit

### RGN-B12 A failed pass leaves the workspace unchanged

WHEN a due regeneration fails THE regeneration unit SHALL leave the workspace and the run's branch unchanged, putting back every file that any regeneration wrote in that pass.

- GIVEN two due regenerations of which the first passes and writes a file and the second fails WHEN the unit ends THEN it made no commit and the file the first wrote holds what it held before the unit ran
- GIVEN a due regeneration that fails after it created a file that did not exist before WHEN the unit ends THEN that file does not exist

### RGN-B13 A file the regeneration wrote is not a change of the steps

WHEN a file that a regeneration declares as an output has been changed since the run's base commit only by commits of the regeneration unit THE phase gate and the code gate SHALL list it as written by the regeneration and not among the changed paths.

- GIVEN an output `stamp.json` that only the unit's commit changed and a code step that changed `src/a.py` WHEN the code gate hands its judge the evidence THEN it lists `stamp.json` as written by the regeneration and its changed paths hold `src/a.py` alone
- GIVEN the same output and a step that then edited it by hand WHEN the code gate hands its judge the evidence THEN `stamp.json` is among the changed paths
- GIVEN a run in the quick lane whose triage note names `src/a.py` and `tests/test_a.py`, a change of those two files and an output that only the unit's commit changed WHEN the code gate runs THEN it finds no changed file that the triage note does not name and does not send the run back to triage

### RGN-B14 The plan and expand briefs say a generated file gets no task row

WHEN the plan step and the expand step are briefed THE workflow SHALL tell each that a file the repository declares as an output in `tempergraph.regenerations.json` gets no task row.

- GIVEN the plan prompt WHEN it is read THEN it names `tempergraph.regenerations.json` and says that a file listed there as an output gets no task row
- GIVEN the expand prompt WHEN it is read THEN it says the same

### RGN-B15 The briefs say a stamp's revision and digests and a diagram are never edited by hand

WHEN the plan step and the expand step are briefed THE workflow SHALL tell each that the outcome revision and the digests that a stamp holds, and a diagram, are never edited by hand.

- GIVEN the plan prompt WHEN it is read THEN it says that the outcome revision and the digests of a stamp and a diagram are written by the regeneration and never edited by hand
- GIVEN the expand prompt WHEN it is read THEN it says the same

## Acceptance criteria

- RGN-AC1 (RGN-B1): A fixture run on each arm and one in the quick lane enter the regeneration unit after the code step and before the independent review and the outcome gate, and the quick-lane run enters no review
- RGN-AC2 (RGN-B2): A fixture run with a scripted executor that counts sessions holds the same count before and after the regeneration unit, for a due regeneration and for none
- RGN-AC3 (RGN-B3): A fixture declaration of two regenerations is read with the command, the inputs and the outputs of each, in the order the file lists them
- RGN-AC4 (RGN-B4): A fixture run pauses at the unit, naming the file, for a declaration that is not valid JSON, for one with `schema_version` 2 and for one with a regeneration that lacks a `command`, and does not pause for a repository with no such file
- RGN-AC5 (RGN-B5): Prepare writes no `tempergraph.regenerations.json` for a Python repository or for a repository that holds a stamp and a diagram, and leaves an existing one unchanged
- RGN-AC6 (RGN-B6): A regeneration runs for a changed file inside its input folder and for its changed input file, and does not run for a changed file of another folder or for a name that only begins like its input file
- RGN-AC7 (RGN-B7): A regeneration whose only changed path is one of its own outputs does not run, and runs when an input that is not an output changed too
- RGN-AC8 (RGN-B8): A fixture run with no declaration file, one with an empty list and one whose inputs did not change each pass the unit with no regeneration command started, the workspace unchanged and no commit added
- RGN-AC9 (RGN-B9): A fixture command starts with its words as a list and no shell, in the workspace, and in a linked worktree a tree digest of the main checkout is the same before and after
- RGN-AC10 (RGN-B10): A command with a shell metacharacter, one with an absolute path and one with a parent path are each refused and start nothing
- RGN-AC16 (RGN-B16): In a fixture repository whose `tempergraph.commands.json` lists a command that no regeneration holds, the unit starts that command in no run: with one due regeneration only that regeneration's command starts, and with no declaration file no regeneration command starts
- RGN-AC11 (RGN-B11): After a passing due regeneration the run's branch holds one commit of the unit with the files written and the workspace has no uncommitted change, and a regeneration that writes the same bytes its output holds adds no commit
- RGN-AC12 (RGN-B12): After a failing regeneration the unit has made no commit, and every file any regeneration wrote holds what it held before the unit ran or does not exist
- RGN-AC13 (RGN-B13): The evidence of the code gate and of a phase gate lists an output that only the unit's commits changed as written by the regeneration and not among the changed paths, and lists it among them after a step edited it, and a quick-lane run whose change is only the files the triage note names, beside such an output, is not sent back to triage
- RGN-AC14 (RGN-B14): The plan prompt and the expand prompt each name `tempergraph.regenerations.json` and say that a file listed there as an output gets no task row
- RGN-AC15 (RGN-B15): The plan prompt and the expand prompt each say that the outcome revision and the digests of a stamp and a diagram are never edited by hand
- [ ] ts-rgn-declaration The repository's declaration of regenerations is absent or usable
- [ ] ts-rgn-ran Every regeneration whose input the run changed ran to an end
- [ ] ts-rgn-passed No regeneration failed
