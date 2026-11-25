# Map unit

## Purpose

A map runs one step once per item of a list that an earlier unit produced, gates each item on its own, and passes when every item has passed. Its sequential form runs one fresh session per item in the run's own worktree: an earlier unit writes the list, the map's step runs once per item, and a join follows. [CMP](03-compiler-and-flow.spec.md) names the primitive; this spec owns its declaration and its per-item rules. A map over a sub-workflow is [FLX-B7](74-flow-extensions.spec.md); a contest's slots reuse the item machinery ([CTS](72-contest-unit.spec.md)). Whether per-item work pays is a workflow's own measurement, which it can route on ([SWM](79-measured-switches.spec.md), [CXR](94-complexity-routing.spec.md)). Workflow authors and the compiler depend on it; design and build notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### MAP-B7 Declaration

WHEN a `map` unit is declared, built as `Map(items_from=(unit, key), step=Step(...))` THE engine SHALL read `MapSpec` with `items_from` (`{unit, key}`, the unit preceding the map on every path), an optional pure model-free `extract` (`(ctx: ExtractContext) -> list[MapItem]`, the context read-only `artifact`, `workdir` and `values`; without it the artifact is a JSON file of an array of strings or of `{id, text}` objects), `max_items` (default 20, at most 50), `on_empty` (`one_item` runs the whole artifact as one item `all`, `skip` passes with no item, `stop` the default), `mode` (`sequential`, the default, or `concurrent`), `concurrency` (1 to 10, default 3, `concurrent` only) and an optional `item_model` (`(item: MapItem) -> alias`, choosing among the one to eight aliases listed in `models`); take the unit's `step` as the step every item runs and its `gate` as applied to every item on its own; and take each `MapItem` with a slug `id` unique in the list, naming its artifacts, records and pauses, and `text` of at most 4,000 characters rendered as `{item}` ([VAL-B8](76-step-values-and-template-keys.spec.md)).

- GIVEN a map whose `items_from` unit can be skipped by a route WHEN validated THEN it is refused
- GIVEN a map with `mode: concurrent` and `concurrency` 4 WHEN validated THEN it validates
- GIVEN a map with `mode: concurrent` and `concurrency` 11 WHEN validated THEN it is refused

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
- GIVEN a concurrent map of five items with `concurrency` 2 WHEN it runs THEN two items run at once, never a third, and every item runs

### MAP-B10 Item budgets, pauses and the join

WHEN an item is graded THE engine SHALL give it its own retry budget, spent only by it, retrying a failed item alone; never run a passed item again in the visit, after a person's retry of another item or after a resume; on a spent item pause with kind `budget` addressed by unit and item under `on_budget_spent: ask`, the other items keeping their results, or stop the map under `stop`; when an item stops, stop the map, items still running finishing and recording their attempt; address each pending pause by unit and item ([HUM](07-gate-and-human.spec.md)); and when every item has passed (the items of a writing concurrent map first merged and checked, MAP-B12) proceed to the join unit, which reads the items' artifacts by key and item id.

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
- GIVEN a concurrent map whose step declares `write` in a workflow that declares `workspace: in_place` WHEN validated THEN it is refused with its own finding code

### MAP-B12 The joined result is checked once

WHEN the items of a concurrent map whose step declares `write` or `edit` have all passed and been merged into the run branch ([WSP-B11](13-workspace-and-concurrency.spec.md)) and the map's gate declares a check THE engine SHALL run that check once on the run's worktree, over the joined result and with no item, before the next unit starts.

- GIVEN a concurrent map of items p1 and p2 that each write one file and a check that lists the files of its working directory WHEN the items have been merged THEN the check runs once on the run's worktree, lists both files, and runs before the next unit's first session
- GIVEN a concurrent map whose step declares `write` and whose gate declares no check WHEN the items have been merged THEN no check runs on the run's worktree and the next unit starts

### MAP-B13 A failed joined check blocks the map

WHEN the check of MAP-B12 fails THE engine SHALL end the map blocked, not retried as a failed item check is ([JDG-B1](05-judge-and-verdict.spec.md)), with the check's failing findings listed, rerunning no item and starting no model session, for a person to decide.

- GIVEN two items whose merged files fail the check WHEN the check ends THEN the run pauses at the map listing the failing finding, no retry is spent, the run branch still holds both merge commits, and no item or model session starts

## Acceptance criteria

- MAP-AC1 (MAP-B1, MAP-B2, MAP-B3, MAP-B4, MAP-B5, MAP-B6, MAP-B8, MAP-B9): Every scenario of MAP-B1 to MAP-B6 holds offline with scripted executors and a scratch git repository
- MAP-AC2 (MAP-B11, MAP-B7): Every refusal of MAP-B11 has a fixture workflow that fails validation with its own finding code
- MAP-AC3 (MAP-B10): A passed item starts no session after a resume, a person's retry of a sibling, or a re-open (scripted executor call count)
- MAP-AC4 (MAP-B9): Sequential item k sees the commits of items 1 to k−1 and nothing of k+1
- MAP-AC5 (MAP-B7, MAP-B9): A concurrent map of five items with `concurrency` 2 validates, runs two items at once and never a third, and runs every item; the same map with `concurrency` 11 fails validation
- MAP-AC6 (MAP-B10): In a concurrent map of five items where p2 and p5 fail every attempt, with a retry budget of 1 and `on_budget_spent: ask`, each of the two runs one retry and then pauses with kind `budget` at `phase.p2` or `phase.p5`, while p1, p3 and p4 keep their results and start no session after a resume
- MAP-AC7 (MAP-B6): With pauses at `phase.p2` and `phase.p5` pending, a resume naming no item is refused with both exact commands, and a `retry` named for `phase.p5` runs only p5
- MAP-AC8 (MAP-B12): In a concurrent map whose step declares `write`, a gate check that records its calls is called once with the run's worktree as its working directory and no item, after the last merge and before the next unit's first session, besides the one call per item attempt in that item's own worktree
- MAP-AC9 (MAP-B13): When the gate check run on the joined result of a concurrent map whose step declares `write` fails, the run pauses at the map listing the failing finding, spends no retry, the run branch still holds the merge commits, and no item or model session starts
