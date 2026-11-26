# Decision revisit

## Purpose

The part of the [workflow audit](workflow-audit.spec.md) that reads a workflow package's decision records and reports a record whose `Revisit when` trigger has fired: a live check got a result, an issue closed, a measure of a model-facing file crossed a value, or an engine or CLI version moved. A position can rest on a claim that a later check disproves, and nothing else links the check's result to the position ([research `why-the-loop-missed-flaws-in-prompts-formats-and-decisions`](../research/why-the-loop-missed-flaws-in-prompts-formats-and-decisions.rsrch.md) F5). The finding is advisory and files nothing.

## Depends on

- `workflow-audit.spec.md`: the definition layer, the report and the `audit` verb's views
- `prompt-audit.spec.md`: the measures of a model-facing file
- `workflow-package.spec.md`: the package's `docs/` folders and its stamp
- Outside: the code host's issue state, read through `gh`

## Does not own

- How a decision record is written, its `Revisit when` section included: the decision rule of the repository's document rules
- The live check runbooks and their results tables: the package's own plans

## Behaviours

### DRV-B1 Machine-readable triggers

WHEN the audit reads the `Revisit when` section of a decision record under the package's `docs/adr/` THE audit SHALL read, from each line, every trigger in one of these forms: a live check id (`live check <id>`), an issue number (`#<n>` of the workflow's issue repository), a measure of a package file with a value (`` `<file>` <measure> above|below|at or above|at or below <number> ``, a measure of [PRA-B12](prompt-audit.spec.md)), and a version (`engine version moves`, `claude version moves`, `claude version reaches <x.y.z>`); a line with none of them is prose.

- GIVEN the line "`prompts/a.md` chars above 12000" WHEN read THEN it is one measure trigger on that file
- GIVEN the line "The team grows." WHEN read THEN it is prose

### DRV-B2 A fired trigger is reported

WHEN a trigger's state now differs from the state the last stamp recorded for it in the direction its form names (a live check's last results row in the package's `docs/plans/` changed, the issue is closed, the measure crossed its value, the version moved or reached its value) THE audit SHALL report `decision-revisit-due` (info/high, `decision_revisit`) naming the record and the trigger; a state that cannot be read fires nothing, and a package with no stamp gets no such finding.

- GIVEN a trigger on an issue that is now closed WHEN audited THEN `decision-revisit-due` names the record and the issue
- GIVEN a stamp and no trigger whose state changed WHEN audited THEN no `decision-revisit-due` is reported

### DRV-B3 The stamp records trigger states

WHEN a package is stamped THE engine SHALL record in `stamp.json` under `revisit`, per decision record, the state of each trigger that reads without the network (live check rows, measures, the engine version), so an issue trigger fires while the issue is closed until the record is revised.

- GIVEN a record with a measure trigger WHEN the package is stamped THEN `stamp.json` holds that trigger's state under the record's path

### DRV-B4 The decisions view

WHEN `audit decisions <workflow>` runs THE audit SHALL print JSON rows, one per trigger with its record, kind, the stamped state, the state now and whether it is due, and one per prose line with the kind `not machine-readable`, which is never a finding.

- GIVEN a record with one prose line WHEN `audit decisions` runs THEN that line is listed as `not machine-readable`

## Acceptance criteria

- DRV-AC1 (DRV-B1): A fixture record gives one trigger of each form, in order, and lists its one prose line as prose
- DRV-AC2 (DRV-B2): Against a stamp of the same states no trigger fires and without a stamp none does; with each state changed, a live check row, a closed issue, a crossed measure, a moved engine version and a reached CLI version each fire; an issue whose state cannot be read never fires
- DRV-AC3 (DRV-B2, DRV-B3): The audit reports `decision-revisit-due` at info severity for the triggers that fired against a stamp, and a stamp's `revisit` holds the offline states and no issue state
- DRV-AC4 (DRV-B4): `audit decisions` on a fixture package lists its triggers and its one prose line as `not machine-readable`
