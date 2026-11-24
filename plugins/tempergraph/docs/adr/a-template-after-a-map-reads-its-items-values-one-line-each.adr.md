# A template after a map reads its items' values, one line for each item

## Context

A map runs one step once per item of a list ([MAP-B9](../specs/77-map-unit.spec.md)). When the step declares neither `write` nor `edit`, its items run side by side in the run's worktree and fail if they change a file ([WSP-B11](../specs/13-workspace-and-concurrency.spec.md)). Such an item can hand on only what its step declares as values, each one line of text ([VAL-B5](../specs/76-step-values-and-template-keys.spec.md)), and the engine stores them per item as `<key>[<item id>]` (`engine/src/tempergraph/run/nodes.py`, lines 654-658). The map spec says the unit after the map reads them ([MAP-B10](../specs/77-map-unit.spec.md)).

What the code gives a step after a map today:

- A prompt may name a field `name` or one dotted pair only (`engine/src/tempergraph/render/template.py`, line 16), and the dotted pair is accepted for a sub-workflow unit only ([CON-B8](../specs/01-contracts.spec.md), [SWF-B12](../specs/99-subworkflow-unit.spec.md), `engine/src/tempergraph/model/validate.py`, lines 917-922). A field such as `{note[a]}` is not valid, and the ids of the items are not known when the workflow is written.
- The plain field `{note}` after a map renders the map unit's value for that key (`engine/src/tempergraph/run/nodes.py`, lines 1074-1077). When the map ends, the engine puts the last item of the list under the plain key, for a sequential and a concurrent map alike (`engine/src/tempergraph/run/nodes.py`, lines 1026-1030; the assumption recorded in `plugins/tempergraph/docs/tasks/r3-t3-2.handoff.md`), so the field renders the last item's value and the values of the other items are out of reach of a template. A search of `plugins/` for `Map(` and for the fields of the units after each map found no workflow and no test that names a map's key in a later template, so nothing pins what it renders.
- A script's callable receives the unit, the working folder and the request only (`engine/src/tempergraph/run/nodes.py`, lines 1116-1118). A check runs after the step it checks, and the gate check of a concurrent map runs once for the whole map only when its step writes ([MAP-B12](../specs/77-map-unit.spec.md)), so no check can compose a file for the step that follows a read-only map.

So a workflow that fans out read-only sessions, and then runs one step that needs what they found, has no way to give that step the results. A workflow with this shape needs the capability, and any workflow can use it.

## Decision

We will let a template of a unit after a map name the plain field `{<key>}` for a key the map's step produces, and render one line `<item id>: <value>` for each item of the map's list, in the order of the list, and `none` when no item has one ([VAL-B9](../specs/76-step-values-and-template-keys.spec.md)). The grammar, the validator, the dotted form and the plain key in the run's state stay as they are.

## Options considered

### The plain field renders every item's value (chosen)

For: no new syntax, so [CON-B8](../specs/01-contracts.spec.md) and [SWF-B12](../specs/99-subworkflow-unit.spec.md) stay true as written; the field already validates, because a map's key is an earlier artifact; it matches what the map spec says about reading the items "as a map from item id"; the order is the list's, never the order in which items ended. Against: it changes what the plain field renders after a map, from the last item's value to one line for each item, which only an author who relied on the old value would notice, and none is known; a check or a route predicate still reads the plain key as before.

### A dotted field `{<map unit>.<key>}`

For: the plain field keeps its old meaning. Against: three specs say the dotted form belongs to a sub-workflow unit ([CON-B8](../specs/01-contracts.spec.md), [VAL-B8](../specs/76-step-values-and-template-keys.spec.md), [SWF-B12](../specs/99-subworkflow-unit.spec.md)), so all three change, and so do the grammar's tests and the validator, to keep a meaning that nothing uses.

### A script or a check composes a file for the next step

For: any shape of result. Against: the context of a script carries no values, so the interface of scripts changes anyway; a check cannot run for a read-only map as a whole; a generated file lands in the repository and in the commit of the step after it; every workflow writes its own glue.

### Items that write

For: files, and no engine change. Against: the items are no longer read-only, each one works in its own worktree and is merged at the join in list order ([WSP-B11](../specs/13-workspace-and-concurrency.spec.md)), the notes become documents of the repository, and a merge conflict can block the map.

### The next step reads the items' sessions from the state root

Against: a step works inside its workspace only, and the state root holds raw session records, not results.

## Consequences

A workflow can read in parallel and give one step all the results, in a fixed order, with no file and no new field syntax. The renderer builds the lines from the map's list and its per-item values, and the prompt grows with the list: at most `max_items` lines (50) of at most the value's `max_chars` each, so a workflow that sets a large `max_chars` on a key it reads this way pays for it in the next prompt. A retried item shows only its last value. A value is one line, so a result that needs structure goes in a file, which only a writing map can produce. A template after a map that wants the last item's value alone has no field for it; the state keeps it for checks and predicates.

## Revisit when

A workflow needs a result of several lines from a read-only item, or a later unit needs a subset of the items.
