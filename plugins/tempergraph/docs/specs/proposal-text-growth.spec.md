# Proposal text growth

## Purpose

How the self-improvement loop's proposer and its judge weigh the size of the text a proposal changes: the proposer may replace, merge or delete text and not only add a rule, its judge asks whether a change grows a file where replacing text would do, every proposal records the measures of each model-facing file it changes, and a package that declares character budgets has proposals above them refused. Text grows one added rule at a time, and a trial on few cases cannot show that growth made a step worse ([research `why-the-loop-missed-flaws-in-prompts-formats-and-decisions`](../research/why-the-loop-missed-flaws-in-prompts-formats-and-decisions.rsrch.md)).

## Depends on

- `improvement-proposals.spec.md`: the proposer, its judge, the proposal record and its refusals
- `prompt-audit.spec.md`: the measures of a model-facing file
- `workflow-package.spec.md`: the package's `text_budgets`

## Does not own

- The budget of a lessons file and its one-entry patch: `workflow-lessons.spec.md`
- Classifying a patch into change classes: `improvement-proposals.spec.md`

## Behaviours

### PTG-B1 The proposer may replace text and its judge weighs growth

WHEN the proposer is briefed for a cluster THE loop SHALL allow a patch that replaces, merges or deletes sentences as well as one that adds them, ask for a half-line reason beside a rule that is not mechanical, and grade the change with a criterion that it adds no text where replacing or deleting text would address the cause and repeats no sentence another file of the package holds, beside the proposer judge's criteria of [PRP-B4](improvement-proposals.spec.md).

- GIVEN a patch that adds a rule beside the sentence the cause points at, where rewording that sentence would do WHEN the proposer's judge grades it THEN the growth criterion is not met
- GIVEN a patch that only deletes a sentence WHEN it is recorded THEN it is classed like any other change of that file

### PTG-B2 A proposal records the measures of the text it changes

WHEN a proposal is recorded THE loop SHALL store, for each model-facing file whose text the patch changes, its characters, prohibitions, reasons and prohibitions per reason before and after ([PRA-B12](prompt-audit.spec.md)), and the pull request text SHALL show the characters and prohibitions per reason of each such file before and after.

- GIVEN a patch that deletes one of a template's two prohibitions WHEN it is recorded THEN the record holds 2 prohibitions before and 1 after for that template
- GIVEN a proposal opened as a pull request WHEN its text is written THEN it holds one line of measures per changed file

### PTG-B3 A proposal above a declared budget is refused

WHEN a patch takes a package file above its character budget ([PKG-B26](workflow-package.spec.md)) that the file was within before THE loop SHALL refuse the proposal with `growth`, naming each file, its characters and its budget; a package without budgets has no proposal refused for its size.

- GIVEN a template budget 20 characters above the template WHEN a patch adds a 45-character sentence THEN the proposal is refused `growth`
- GIVEN a package with no `text_budgets` WHEN a patch adds three sentences THEN the proposal is drafted

## Acceptance criteria

- PTG-AC1 (PTG-B1): The proposer's brief allows replacing, merging and deleting sentences and asks for a half-line reason, and its judge's criteria include `replaces-before-adding`
- PTG-AC2 (PTG-B2): A deletion-only patch to a fixture template is drafted with class `prompt`, its record holds the template's measures before and after, and the pull request text shows them
- PTG-AC3 (PTG-B3): A fixture patch that takes a template above its budget is refused `growth` with the file named, the same package's change within the budget is drafted, and a growing patch to a package without budgets is drafted
