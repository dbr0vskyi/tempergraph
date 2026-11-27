# The regenerations of a repository are declared in a file beside its commands file

## Context

A run has to refresh the files that a repository generates (a package's stamp, its diagram, its authoring record) when the files they are made from change, and no step session may run the commands that write them, so no plan row can ask for them. Which command writes which file from which inputs is a fact of the repository and not of the workflow. The unit that runs them needs a declaration to read.

## Current state

- A repository declares the commands a run may use to verify its work in `tempergraph.commands.json` (`schema_version` 1 and a `commands` list). The engine reads that list for every step or check that lists `@repository` and ignores every other key of the file (`plugins/tempergraph/engine/src/tempergraph/run/commands.py`, `repository_commands`). Each prefix the list holds is a command the code step's session may run and a command a plan may list ([repository commands](../specs/repository-commands.spec.md)).
- The engine's workflow audit reads the same list as the commands the audited repository declares ([AUD-B17](../../../tempergraph/docs/specs/workflow-audit.spec.md) to [AUD-B19](../../../tempergraph/docs/specs/workflow-audit.spec.md)).
- Prepare writes that file for a Python repository that has none and leaves an existing file as it is ([RCM-B6](../specs/repository-commands.spec.md) to [RCM-B8](../specs/repository-commands.spec.md)).
- The format of that file is the engine's ([CHK-B11](../../../tempergraph/docs/specs/check-contract-and-command-runs.spec.md)); the package reads it only through the engine's command resolution (`plugins/temperspec-tgraph/workflow/temperspec/__init__.py`, the `VERIFY` list).

## Forces

- C1 (constraint): which command regenerates what from which inputs is declared by the repository; the workflow invents no regeneration for it. Source: [RGN-B3](../specs/regeneration.spec.md) and [RGN-B5](../specs/regeneration.spec.md)
- F1: a regeneration's command does not become a command a session may run or a plan may list
- F2: the engine's reader of the commands file, its audit and the file prepare writes stay as they are
- F3: the package owns the format of the declaration and changes it without an engine release
- F4: a repository says in one place which commands it has

## Options considered

### A. A file of its own (chosen)

How it works: the repository lists its regenerations in `tempergraph.regenerations.json` at its root, each with a name, a command, inputs and outputs. Only the package's regeneration unit reads the file.
For: a regeneration's command never becomes a command a session may run or a plan may list, whatever a repository writes in its commands file (F1); the engine's reader, its audit and the file prepare writes stay as they are (F2); the package owns the format and changes it without an engine release (F3). Against: a second file at the repository's root, so a repository says in two places which commands it has (F4).

### B. A new key of `tempergraph.commands.json`

How it works: the commands file gains a key `regenerations` beside `commands`, which the engine ignores and the package reads.
For: one file for everything a repository says about commands, and the engine already ignores a key it does not know (F4). Against: the format of that file is the engine's, so a package key would extend an engine document that the engine's audit and prepare also read (F2, F3); and a repository that lists a regeneration's command in `commands` as well, to run it by hand, makes it a command a session may run and a plan may list, which is what the declaration is there to prevent (F1).

### C. A list in the workflow package

How it works: the package holds the list of regenerations, and a repository edits the package to change it.
Against: breaks C1: a repository that is not the package's own would have to edit the package to say what it generates.

## Decision

We will declare regenerations in `tempergraph.regenerations.json` at the repository root, option A: a file of its own beside `tempergraph.commands.json`, which only the package reads, as [the regeneration spec](../specs/regeneration.spec.md) says.

## Decision rationale

C1 is met: the file is the repository's and prepare writes none. F1 is met: the unit takes its commands from this file alone and the session's commands come from the other ([RGN-B16](../specs/regeneration.spec.md)). F2 is met, no engine reader changes. F3 is met, the format has a `schema_version` of the package's own. F4 is given up: a repository has two files about commands, which costs less than a package key in an engine document (option B gives up F2 and F3 and weakens F1).

## Consequences

Prepare writes no such file, so a repository declares nothing until its owner writes the file, and a repository with no file runs no regeneration. The engine's audit does not see the file; the package's own tests do. The file carries a `schema_version`, so a later format is told apart from this one. A regeneration command that a repository also lists in its commands file stays a command a session may run: the repository's choice, not the package's.

## Risks

- A repository's generated files go stale in a run because its owner did not know of the second file and declared nothing. Limited by: the package's `README.md` and [the regeneration spec](../specs/regeneration.spec.md) name the file. Noticed by: whatever in the repository reads the generated files, a test or a person, since the unit reports nothing for a repository that declares nothing.

## Assumptions

- A1: this package is the only reader of the declaration. Check: search the workflow packages and the engine for the file's name. If wrong: a second reader copies the format, and the format should move into the engine as a general capability.

## Revisit when

A second workflow package needs the same declaration, or the engine reads other declarations of a repository in one place: the format may then move into the engine as a general capability.
