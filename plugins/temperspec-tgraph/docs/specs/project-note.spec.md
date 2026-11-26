# Project note and rule files

## Purpose

What prepare, the step with no session that starts every run, puts into a repository before any other step reads it: the rule files that say how each document is written, and the temperspec block of the project-context file (`CLAUDE.md`, or `AGENTS.md` when that is the file the repository has). Every later session reads the block to learn where documents are written and where the rules are, so a block that names a folder the repository does not have sends a step's first write to the wrong place, rule files copied into a repository that already has them leave a change for its pull request to carry, and rule files only the machine holds never reach a step session, which loads the repository's own settings and none of the machine's ([ECC-B16](../../../tempergraph/docs/specs/executor-claude-code.spec.md)). The sessions of a run and the people who review its pull request depend on it. A file inside a folder of copies or fixtures (version control, dependencies, tool state, evaluation cases, test fixtures) is not counted as the repository's own. Part of the [overview](overview.spec.md); the unit is [prepare](prepare.spec.md).

## Behaviours

### PNR-B1 The block names the specs folders

WHEN prepare writes the block THE prepare step SHALL name as where the repository keeps its specs the folder of each overview spec (a file named `overview.spec.md`, with or without a number prefix), or, when the repository has no overview spec, the folders of its other specs, or, when it has none, `docs/specs/`.

- GIVEN overview specs `plugins/a/docs/specs/overview.spec.md` and `plugins/b/docs/specs/overview.spec.md` WHEN prepare writes the block THEN the block names `plugins/a/docs/specs/` and `plugins/b/docs/specs/` and no `docs/specs/` of the repository root
- GIVEN an overview spec only inside an `evals/` folder WHEN prepare writes the block THEN the block does not name that folder
- GIVEN no overview spec and a spec in `design/specs/` WHEN prepare writes the block THEN the block names `design/specs/`
- GIVEN no spec at all WHEN prepare writes the block THEN the block names `docs/specs/`

### PNR-B2 The block names where the other documents go

WHEN prepare writes the block THE prepare step SHALL name, beside each specs folder it names, the folders `adr/`, `research/`, `plans/` and `tasks/` as where decision records, research notes, plans and task notes go.

- GIVEN the specs folder `plugins/a/docs/specs/` WHEN prepare writes the block THEN the block names `plugins/a/docs/adr/`, `plugins/a/docs/research/`, `plugins/a/docs/plans/` and `plugins/a/docs/tasks/`, whether or not they exist yet
- GIVEN the specs folders `plugins/a/docs/specs/` and `plugins/b/docs/specs/` WHEN prepare writes the block THEN the block names the four folders beside each of them
- GIVEN no spec at all WHEN prepare writes the block THEN the block names `docs/adr/`, `docs/research/`, `docs/plans/` and `docs/tasks/`

### PNR-B3 Rule files the repository holds are not copied

WHEN the repository has its own rule folder (`.claude/rules/temperspec/`), or a folder that holds every rule file temperspec ships (`spec.rule.md`, `extraction.rule.md`, `plan.rule.md`, `decision.rule.md`, `research.rule.md`, `task-notes.rule.md` and `documents.rule.md`), THE prepare step SHALL install nothing, whether or not the machine has its rule folder (`~/.claude/rules/temperspec/`): no rule file is copied into the repository and no fill-in template is written.

- GIVEN the seven rule files in `plugins/a/rules/` and no other rule folder WHEN prepare runs THEN the repository gains no `.claude/rules/temperspec/` and no `docs/templates/`
- GIVEN the seven rule files in `plugins/a/rules/` and the rule files in the machine's `~/.claude/rules/temperspec/` WHEN prepare runs THEN the repository gains no `.claude/rules/temperspec/` and no `docs/templates/`
- GIVEN a `.claude/rules/temperspec/` of the repository that holds only `spec.rule.md`, and the rule files in the machine's `~/.claude/rules/temperspec/` WHEN prepare runs THEN `.claude/rules/temperspec/` still holds `spec.rule.md` alone and no `docs/templates/` is written

### PNR-B7 Rule files the repository lacks are copied, whether or not the machine has them

WHEN the repository has neither its own rule folder (`.claude/rules/temperspec/`) nor a folder that holds every rule file temperspec ships THE prepare step SHALL install the rule files, whether or not the machine has its rule folder (`~/.claude/rules/temperspec/`): every rule file temperspec ships is copied into `.claude/rules/temperspec/` and the fill-in templates are written into `docs/templates/`.

- GIVEN the seven rule files in the machine's `~/.claude/rules/temperspec/` and none in the repository WHEN prepare runs THEN every rule file is copied into `.claude/rules/temperspec/` and the templates into `docs/templates/`
- GIVEN only `spec.rule.md` in `plugins/a/rules/` and no other rule folder WHEN prepare runs THEN every rule file is copied into `.claude/rules/temperspec/` and the templates into `docs/templates/`
- GIVEN no rule file anywhere WHEN prepare runs THEN every rule file is copied into `.claude/rules/temperspec/` and the templates into `docs/templates/`

### PNR-B4 The block names where the rule files are

WHEN prepare writes the block THE prepare step SHALL name where the rule files are: the repository's own `.claude/rules/temperspec/` if it has one, else the folder of the repository that holds every rule file.

- GIVEN the seven rule files in `plugins/a/rules/` and no other rule folder WHEN prepare writes the block THEN the block names `plugins/a/rules/`
- GIVEN the rule files only in the machine's `~/.claude/rules/temperspec/` WHEN prepare runs THEN it copies them into the repository and the block names `.claude/rules/temperspec/` and not `~/.claude/rules/temperspec/`
- GIVEN a `.claude/rules/temperspec/` of the repository and rule files in `plugins/a/rules/` WHEN prepare writes the block THEN the block names `.claude/rules/temperspec/` and not `plugins/a/rules/`
- GIVEN no rule file anywhere WHEN prepare runs THEN it copies them and the block names `.claude/rules/temperspec/`

### PNR-B5 The block names fill-in templates only where they exist

WHEN prepare writes the block THE prepare step SHALL name `docs/templates/` as the place of the fill-in templates only when that folder holds them (`*.template.md`).

- GIVEN rule files held elsewhere and no `docs/templates/` WHEN prepare writes the block THEN the block names no folder of fill-in templates
- GIVEN no rule file anywhere WHEN prepare copies them and writes the templates THEN the block names `docs/templates/`

### PNR-B6 A file that already says where specs live is left alone

WHEN the project-context file, leaving out any temperspec block, names by its whole path from the repository root a folder that PNR-B1 gives for specs, or the folder that contains it (unless that is the repository root), THE prepare step SHALL leave the file unchanged: no block is added and none is replaced.

- GIVEN an overview spec in `plugins/a/docs/specs/` and a `CLAUDE.md` that names `plugins/a/docs/{specs,adr,research}/` WHEN prepare runs THEN `CLAUDE.md` is byte for byte as it was and no change to it is committed
- GIVEN an overview spec in `docs/specs/` and a `CLAUDE.md` that names `docs/` only inside the path `plugins/b/docs/guides/` WHEN prepare runs THEN the block is added after the file's text
- GIVEN a `CLAUDE.md` that says only how to run the tests WHEN prepare runs THEN the block is added after its text
- GIVEN a `CLAUDE.md` whose only mention of a specs folder is inside an earlier temperspec block WHEN prepare runs THEN that block is replaced in place

### PNR-B8 The block prepare wrote is not a change of the run

WHEN prepare wrote the temperspec block into the project-context file and the file differs from the run's base commit only in that block THE code gate SHALL list the file as written by prepare and not among the changed paths.

- GIVEN a `CLAUDE.md` to which prepare added the block and that holds no other change WHEN the code gate runs THEN its evidence lists `CLAUDE.md` as written by prepare, with no step's change, and not among the changed paths
- GIVEN the same file and a step that then added a line of its own to it WHEN the code gate runs THEN `CLAUDE.md` is among the changed paths

## Acceptance criteria

- PNR-AC1 (PNR-B1): For a repository whose overview specs are in `plugins/a/docs/specs/` and `plugins/b/docs/specs/`, with a third overview spec inside an `evals/` folder, the block names the first two folders and neither the third nor a root `docs/specs/`
- PNR-AC2 (PNR-B1): For a repository with no overview spec and a spec in `design/specs/` the block names `design/specs/`, and for a repository with no spec it names `docs/specs/`
- PNR-AC3 (PNR-B2): For the specs folders `plugins/a/docs/specs/` and `plugins/b/docs/specs/` the block names `adr/`, `research/`, `plans/` and `tasks/` beside each, and for a repository with no spec it names `docs/adr/`, `docs/research/`, `docs/plans/` and `docs/tasks/`
- PNR-AC4 (PNR-B3): With the seven rule files in `plugins/a/rules/`, or with the repository's own rule folder, prepare copies no rule file and writes no template, also when the machine's rule folder holds the rule files
- PNR-AC5 (PNR-B7): With only some of the rule files in `plugins/a/rules/`, or with none anywhere, prepare copies every rule file into `.claude/rules/temperspec/` and writes the templates into `docs/templates/`
- PNR-AC10 (PNR-B7): With the seven rule files in the machine's rule folder and none in the repository, prepare copies every rule file into `.claude/rules/temperspec/` and writes the templates into `docs/templates/`
- PNR-AC6 (PNR-B4): The block names `plugins/a/rules/` for rule files held there alone, and `.claude/rules/temperspec/` when the repository has its own folder, even beside `plugins/a/rules/`, or when prepare has just copied the rule files, whether or not the machine holds them; the block names no folder of the machine
- PNR-AC7 (PNR-B5): The block names `docs/templates/` after prepare has written the templates there, and names no folder of fill-in templates when prepare wrote none and the repository has none
- PNR-AC8 (PNR-B6): For an overview spec in `plugins/a/docs/specs/` and a `CLAUDE.md` that names `plugins/a/docs/{specs,adr,research}/`, prepare leaves `CLAUDE.md` byte for byte as it was and the run's branch holds no commit of a change to it
- PNR-AC9 (PNR-B6): For a `CLAUDE.md` that names no specs folder, and for one that names `docs/` only inside `plugins/b/docs/guides/`, prepare adds the block after its text; for one that names a specs folder only inside an earlier temperspec block, prepare replaces that block in place
- PNR-AC11 (PNR-B8): For a `CLAUDE.md` to which prepare added the block and nothing else, the code gate's evidence lists it as written by prepare and not among the changed paths, and lists it among them after a step added a line of its own
