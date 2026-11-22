# Map unit

## Purpose

A map runs one step once per item of a list that an earlier unit produced, gates each item on its own, and passes when every item has passed. Its sequential form is how a workflow does one plan phase per fresh session in the run's own worktree: a fork writes the list, the phase step runs per item, and a join follows ([R-075](../research/R-075-temperspec-needs-against-the-engine.rsrch.md) T43). [CMP](03-compiler-and-flow.spec.md) names the primitive; this spec owns its declaration and its per-item rules. A map over a sub-workflow is [FLX-B7](74-flow-extensions.spec.md); a contest's slots reuse the item machinery ([CTS](72-contest-unit.spec.md)). Whether per-item work pays is a workflow's own measurement, which it can route on ([SWM](79-measured-switches.spec.md), [CXR](94-complexity-routing.spec.md)). Workflow authors and the compiler depend on it; design and build notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### MAP-B7 Declaration

WHEN a `map` unit is declared, built as `Map(items_from=(unit, key), step=Step(...))` THE engine SHALL read `MapSpec` with `items_from` (`{unit, key}`, the unit preceding the map on every path), an optional pure model-free `extract` (`(ctx: ExtractContext) -> list[MapItem]`, the context read-only `artifact`, `workdir` and `values`; without it the artifact is a JSON file of an array of strings or of `{id, text}` objects), `max_items` (default 20, at most 50), `on_empty` (`one_item` runs the whole artifact as one item `all`, `skip` passes with no item, `stop` the default), `mode` (`sequential`, the default, or `concurrent`), `concurrency` (1 to 10, default 3, `concurrent` only) and an optional `item_model` (`(item: MapItem) -> alias`, choosing among the one to eight aliases listed in `models`); take the unit's `step` as the step every item runs and its `gate` as applied to every item on its own; and take each `MapItem` with a slug `id` unique in the list, naming its artifacts, records and pauses, and `text` of at most 4,000 characters rendered as `{item}` ([VAL-B8](76-step-values-and-template-keys.spec.md)).

- GIVEN a map whose `items_from` unit can be skipped by a route WHEN validated THEN it is refused

### MAP-B8 Fan-out

WHEN a visit reaches a map THE engine SHALL read the list once per visit, so a step cannot change it mid-visit, record a `map_items` event with the ids and count, and stop the run with exit 4 and reason `map` naming the map, before any item starts, when the list cannot be read, has a duplicate id, is longer than `max_items` or the extractor raises (recording the exception type).

- GIVEN a list with a duplicate id WHEN the map fans out THEN the run stops with exit 4 naming the map

### MAP-B5 Too many items

WHEN a list is longer than `max_items` THE engine SHALL stop the run naming the map and the count, starting no item.

- GIVEN `max_items: 20` and a list of 25 WHEN the map fans out THEN the run stops with exit 4 naming the map and the count

### MAP-B2 No phase heading

WHEN the extractor finds no item under `on_empty: one_item` THE engine SHALL run one item `all` with the whole artifact as its text.

- GIVEN a plan with no phase heading WHEN the map fans out THEN one item `all` runs with the whole plan as its text

### MAP-B9 Items

WHEN a map's items run THE engine SHALL run each through the unit's four nodes as a subgraph addressed `<unit>.<item id>`, a fresh step session, the check with `ctx.item`, the judge and the gate; run sequential items one after another in the run's worktree, each seeing what earlier items committed; run concurrent items up to `concurrency` at once, read-only unless declared writers ([WSP](13-workspace-and-concurrency.spec.md)); keep the list, the passed ids and each item's attempt count in a `maps` state channel, an item's attempt number continuing across visits so session keys never repeat; key an item's artifacts, values and facts `<key>[<item id>]`, read by a later unit as a map from item id ([VAL-B7](76-step-values-and-template-keys.spec.md)), the plain key holding the item in hand; and fail an item's attempt before launch, recorded as a workflow fault, when `item_model` returns an alias the map does not declare.

- GIVEN `item_model` returning an undeclared alias WHEN the item starts THEN its attempt fails before launch as a workflow fault

### MAP-B10 Item budgets, pauses and the join

WHEN an item is graded THE engine SHALL give it its own retry budget, spent only by it, retrying a failed item alone; never run a passed item again in the visit, after a person's retry of another item or after a resume; on a spent item pause with kind `budget` addressed by unit and item under `on_budget_spent: ask`, the other items keeping their results, or stop the map under `stop`; when an item stops, stop the map, items still running finishing and recording their attempt; address each pending pause by unit and item ([HUM](07-gate-and-human.spec.md)); and when every item has passed proceed to the join unit, which reads the items' artifacts by key and item id.

- GIVEN a passed item and a person's retry of a sibling WHEN the sibling runs THEN the passed item starts no session

### MAP-B1 One phase per session

WHEN a sequential map runs its items THE engine SHALL gate each on its own and start the join only after the last passes.

- GIVEN items p1, p2, p3 where p1 passes, p2 fails its check and then passes, and p3's judge RETRY spends the budget under `ask` WHEN the map runs THEN p1 is never rerun, p2 passes after one retry, and the run pauses at `phase.p3`
- GIVEN the pause at `phase.p3` WHEN resumed with retry THEN only p3 runs

### MAP-B3 Trip back reruns every item

WHEN a join gate sends the run back before the map THE engine SHALL read the list again and run every item of the new list as a new visit, an item's check deciding whether an item that needs no change passes.

- GIVEN a map that passed p1 to p3 and a join gate back to the plan unit WHEN the plan and fork rerun THEN every item of the new list runs

### MAP-B4 A drained run resumes at the pending item

WHEN a run stopped by the attempt cap during an item resumes THE engine SHALL continue at that item, the passed items not rerun ([BUD](08-budgets-and-failures.spec.md)).

- GIVEN an attempt cap reached during item p4 of six WHEN resumed THEN it continues at p4 and p1 to p3 are not rerun

### MAP-B6 Resume one item

WHEN a person resumes a map with several pending item pauses without naming one THE engine SHALL refuse with every exact command ([HUM-B3](07-gate-and-human.spec.md)), the named item's `stop` stopping the map and its `retry` rerunning only that item.

- GIVEN pauses at `phase.p2` and `phase.p5` WHEN resumed without an item THEN it is refused with both commands, and `phase.p5` with `retry` reruns only p5

### MAP-B11 What is refused

WHEN a workflow with a map is validated THE engine SHALL refuse `back_targets` on a map's gate and an upstream line offered to an item (a trip back from one item would reset its siblings; a defect across items is found at the join); `items_from` naming a unit that does not precede the map on every path or a key it does not produce; `concurrent` with a writing step and no worktrees ([WSP](13-workspace-and-concurrency.spec.md)); and a map inside a map or a `wait` or `ask` as the item ([FLX-B11](74-flow-extensions.spec.md)).

- GIVEN `back_targets` on a map's gate WHEN validated THEN it is refused with its own finding code

## Acceptance criteria

- MAP-AC1 (MAP-B1, MAP-B2, MAP-B3, MAP-B4, MAP-B5, MAP-B6, MAP-B8, MAP-B9): Every scenario of MAP-B1 to MAP-B6 holds offline with scripted executors and a scratch git repository
- MAP-AC2 (MAP-B11, MAP-B7): Every refusal of MAP-B11 has a fixture workflow that fails validation with its own finding code
- MAP-AC3 (MAP-B10): A passed item starts no session after a resume, a person's retry of a sibling, or a re-open (scripted executor call count)
- MAP-AC4 (MAP-B9): Sequential item k sees the commits of items 1 to k−1 and nothing of k+1

## Open questions

- Not built yet: the concurrent mode, refused `not_in_release` with the parallel map (release 3); a sequential map holds one pause at a time, so MAP-B6's two pending items arise only in that mode. Owner: engine owner.
