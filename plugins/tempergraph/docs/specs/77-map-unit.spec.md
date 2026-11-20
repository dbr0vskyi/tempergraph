---
title: Map unit
type: component
status: review
prefix: MAP
adrs: [0004, 0062]
---

# Map unit

## 1. Overview

A **map** runs one step once per item of a list that an earlier unit produced, gates each item on its own, and passes when every item has passed. Its sequential form is how a workflow codes one plan phase per fresh session in the run's own worktree, the shape temperspec's per-phase code depends on (expand is the fork that writes the list, the phase step runs per item, code is the join that follows) ([R-075](../research/R-075-temperspec-needs-against-the-engine.rsrch.md) T43). [CMP §2.2](03-compiler-and-flow.spec.md) names the primitive; this spec owns its declaration and its per-item rules. A map over a sub-workflow is [FLX §2.2](74-flow-extensions.spec.md); a contest's slots reuse the item machinery ([CTS](72-contest-unit.spec.md)).

## 2. Contract

### 2.1 Declaration

| Type | Field | Kind | Meaning |
|---|---|---|---|
| `MapSpec` (on a `map` unit) | `items_from` | `{unit, key}` | The artifact that holds the list; the unit must precede the map on every path |
| | `extract` | callable ref, optional | `(ctx: ExtractContext) -> list[MapItem]`, model-free and pure. Without it the artifact must be a JSON file holding an array of strings or of `{id, text}` objects |
| | `max_items` | int, default 20, at most 50 | |
| | `on_empty` | `one_item` \| `stop` \| `skip`, default `stop` | `one_item` runs the whole artifact as one item with id `all`; `skip` passes the map with no item |
| | `mode` | `sequential` \| `concurrent`, default `sequential` | |
| | `concurrency` | int 1 to 10, default 3 | `concurrent` only |
| | `item_model` | callable ref, optional | `(item: MapItem) -> alias`, choosing among one to eight aliases the map declares |
| `UnitSpec.step` | | `StepSpec` | The step every item runs |
| `UnitSpec.gate` | | `GateSpec` | Applied to every item on its own |
| `MapItem` | `id` | slug, unique in the list | Names the item's artifacts, records and pauses |
| | `text` | ≤ 4,000 chars | Rendered as `{item}` ([VAL §2.3](76-step-values-and-template-keys.spec.md)) |
| `ExtractContext` | `artifact`, `workdir`, `values` | path, path, map | Read-only |

### 2.2 One visit of a map

| Order | What happens |
|---|---|
| 1 Fan-out | The list is read once per visit and recorded as a `map_items` event (ids and count). A list that cannot be read, has a duplicate id, or is longer than `max_items` stops the run with exit 4 naming the map, before any item starts |
| 2 Items | Each item runs the unit's four nodes as a subgraph addressed `<unit>.<item id>`: a fresh step session, the check (with `ctx.item`), the judge, the gate. Sequential items run one after another in the run's worktree, each seeing what earlier items committed; concurrent items run up to `concurrency` at once and must be read-only unless declared writers ([WSP](13-workspace-and-concurrency.spec.md)) |
| 3 Per-item budgets | Each item has its own retry budget and spends only its own; a failed item retries alone |
| 4 Passed items | An item that passed is never run again in this visit, including after a person's retry of another item and after a resume |
| 5 Spent items | With `on_budget_spent: ask` a spent item pauses with kind `budget`, addressed by unit and item; the other items keep their results. With `stop`, the map stops |
| 6 The join | When every item has passed, the map's gate proceeds to its successor (the join unit), which reads the items' artifacts by key and item id |

Artifacts, values and facts of an item are keyed `<key>[<item id>]`. A later unit reads them as a map from item id ([VAL §2.2](76-step-values-and-template-keys.spec.md)).

### 2.3 What is refused

| Refused before a run | Why |
|---|---|
| `back_targets` on a map's gate; an upstream line offered to an item | A trip back from one item would reset its siblings; a defect across items is found at the join |
| `items_from` naming a unit that does not precede the map on every path, or a key it does not produce | The list would not exist |
| `concurrent` with a writing step and no worktrees | Writers share no worktree ([WSP](13-workspace-and-concurrency.spec.md)) |
| A map inside a map, or a `wait` or `ask` as the item | As [FLX §2.6](74-flow-extensions.spec.md) |

## 3. Behaviours

**MAP-B1 One phase per session.** Given a sequential map `phase` over the plan's phase list with three items, when the run reaches it, then three step sessions run in order in the run's worktree, each gated on its own, and the join unit starts only after the third passes.

| Item | Attempt 1 | Attempt 2 | Result |
|---|---|---|---|
| p1 | pass | — | passed, never rerun |
| p2 | check FAIL | pass | passed after one retry; p1 not rerun |
| p3 | judge RETRY, budget spent, `ask` | — | pause `phase.p3`; resume with retry runs only p3 |

**MAP-B2 No phase heading.** Given `on_empty: one_item` and a plan whose extractor finds no phase, when the map fans out, then one item `all` runs with the whole plan as its text.

**MAP-B3 Trip back reruns every item.** Given a map that passed p1 to p3 and a join gate that sends the run back to the plan unit, when the plan and the fork rerun, then the map reads the list again and runs every item of the new list as a new visit; whether an item that needs no change commits nothing and passes is the item's check's decision.

**MAP-B4 A drained run resumes at the pending item.** Given an attempt cap reached during item p4 of six, when the run is resumed, then it continues at p4; p1 to p3 are not rerun ([BUD](08-budgets-and-failures.spec.md) attempt cap).

**MAP-B5 Too many items.** Given `max_items: 20` and a list of 25, when the map fans out, then the run stops with exit 4 naming the map and the count, and no item starts.

**MAP-B6 Resume one item.** Given pauses at `phase.p2` and `phase.p5`, when a person resumes without naming an item, then the resume is refused with both exact commands ([HUM-B3](07-gate-and-human.spec.md)); the printed command for `phase.p5` with decision `stop` stops the map, and with `retry` reruns only p5.

## 4. Error conditions

| Condition | Result |
|---|---|
| The extractor raises | Run stops with exit 4 before the fan-out, the exception type recorded |
| An item stops | The map stops; items still running finish their attempt and record it |
| `item_model` returns an alias the map does not declare | That item's attempt fails before launch; recorded as a workflow fault |
| An item pause and a parallel branch pause at once | Each addressed by unit and item ([HUM](07-gate-and-human.spec.md)) |

## 5. Design notes

- The list is read once per visit so a step cannot change the plan under the map mid-visit; changing it takes a trip back.
- Whether per-item work pays is the workflow's measurement: temperspec measured it dearer on small plans and routes between a map arm and a single-session arm ([SWM](79-measured-switches.spec.md)).

## 6. Acceptance criteria

- [ ] MAP-AC-1 Every row of the MAP-B1 table and MAP-B2 to MAP-B6 holds offline with scripted executors and a scratch git repository.
- [ ] MAP-AC-2 Every row of §2.3 has a fixture workflow that fails validation with its own finding code.
- [ ] MAP-AC-3 A passed item starts no session after a resume, a person's retry of a sibling, or a re-open (scripted executor call count).
- [ ] MAP-AC-4 Sequential item k sees the commits of items 1 to k−1 and nothing of k+1.

## Open questions

None.

## References

