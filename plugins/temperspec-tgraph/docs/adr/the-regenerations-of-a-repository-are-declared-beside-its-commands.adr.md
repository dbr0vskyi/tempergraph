# The regenerations of a repository are declared in a file beside its commands file

## Context

A run has to refresh the files that a repository generates (a package's stamp, its diagram, its authoring record) when the files they are made from change, and no step session may run the commands that write them, so no plan row can ask for them. Which command writes which file from which inputs is a fact of the repository and not of the workflow. The unit that runs them needs a declaration to read.

What the repository and the engine hold today, read in the code:

- A repository declares the commands a run may use to verify its work in `tempergraph.commands.json` (`schema_version` 1 and a `commands` list). The engine reads that list for every step or check that lists `@repository` and ignores every other key of the file (`plugins/tempergraph/engine/src/tempergraph/run/commands.py`, `repository_commands`). Each prefix the list holds is a command the code step's session may run and a command a plan may list ([repository commands](../specs/repository-commands.spec.md)).
- The engine's workflow audit reads the same list as the commands the audited repository declares ([AUD-B17](../../../tempergraph/docs/specs/workflow-audit.spec.md) to [AUD-B19](../../../tempergraph/docs/specs/workflow-audit.spec.md)).
- Prepare writes that file for a Python repository that has none and leaves an existing file as it is ([RCM-B6](../specs/repository-commands.spec.md) to [RCM-B8](../specs/repository-commands.spec.md)).
- The format of that file is the engine's ([CHK-B11](../../../tempergraph/docs/specs/check-contract-and-command-runs.spec.md)); the package reads it only through the engine's command resolution.

## Decision

We will declare regenerations in `tempergraph.regenerations.json` at the repository root, a file of its own beside `tempergraph.commands.json`, which only the package reads, as [the regeneration spec](../specs/regeneration.spec.md) says.

## Options considered

### A. A file of its own (chosen)

For: a regeneration's command never becomes a command a session may run or a plan may list, whatever a repository writes in its commands file; the engine's reader, its audit and the file prepare writes stay as they are; the package owns the format and changes it without an engine release. Against: a second file at the repository's root, so a repository says in two places which commands it has.

### B. A new key of `tempergraph.commands.json`

For: one file for everything a repository says about commands, and the engine already ignores a key it does not know. Against: the format of that file is the engine's, so a package key would extend an engine document that the engine's audit and prepare also read; and a repository that lists a regeneration's command in `commands` as well, to run it by hand, makes it a command a session may run and a plan may list, which is what the declaration is there to prevent.

### C. A list in the workflow package

For: no file in the repository. Against: which command regenerates what from which inputs is a fact of the repository; a repository that is not the package's own would have to edit the package to say it.

## Consequences

Prepare writes no such file, so a repository declares nothing until its owner writes the file, and a repository with no file runs no regeneration. The engine's audit does not see the file; the package's own tests do. The file carries a `schema_version`, so a later format is told apart from this one. A regeneration command that a repository also lists in its commands file stays a command a session may run: the repository's choice, not the package's.

## Revisit when

A second workflow package needs the same declaration, or the engine reads other declarations of a repository in one place: the format may then move into the engine as a general capability.
