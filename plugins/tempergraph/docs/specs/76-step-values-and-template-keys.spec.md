---
title: Step values and template keys
type: component
status: review
prefix: VAL
adrs: [0003, 0004]
---

# Step values and template keys

## 1. Overview

Steps hand work on as files ([PRM §5](04-prompt-rendering.spec.md)), but a workflow also needs short **values**: a route, a gap list, a release-track mark, a story line, a tests-passed claim. temperspec hands four such values to the run from its first step and routes on two of them ([R-075](../research/R-075-temperspec-needs-against-the-engine.rsrch.md) T13, T14). This spec adds the `value` artifact kind and lists the **template keys** a prompt may name: the engine keys, the declared inputs, and the pointers of earlier artifacts. A template never receives an earlier artifact's content; it receives where it is or, for a value, the value itself.

## 2. Contract

### 2.1 The `value` artifact kind

| Field of a `produces` entry | Kind | Meaning |
|---|---|---|
| `kind` | `value` | One line of text, set by the step's `ARTIFACT <key>: <text>` line ([PRM §2.3](04-prompt-rendering.spec.md)) or by a script's result ([SCR](70-script-units-and-hybrid-steps.spec.md)) |
| `choices` | list of strings, optional | Allowed values, compared after trimming and lower-casing |
| `pattern` | regular expression, optional | Full-match rule for the trimmed value |
| `max_chars` | int, default 500 | Longer text is clipped and recorded |
| `optional` | bool, default false | A missing optional value is not a failure of the built-in output contract |

A `produces` map entry is either an `ArtifactKind` name, as today, or this table's entry. Values are scrubbed before they are stored.

| Step output | Stored as | Recorded on the step record |
|---|---|---|
| `ARTIFACT route: plan` with `choices: [plan, discovery]` | `values.route = "plan"` | — |
| `ARTIFACT route: Plan ` | `"plan"` | — |
| `ARTIFACT route: maybe` | absent | `value_invalid: route` |
| no line for a required value | absent | `value_missing: route` |

An absent value is read as absent by every reader; it is never defaulted by the engine. A switch whose predicate finds it absent may take its default arm ([CMP §2.2](03-compiler-and-flow.spec.md)), and a check decides whether absence fails the step.

### 2.2 Where values are read

| Reader | How |
|---|---|
| Route and switch predicates | `state.values[unit][key]` |
| Checks | `ctx.values` ([CHK §2.1](75-check-contract-and-command-runs.spec.md)) |
| Templates | `{key}` renders the value (§2.3) |
| Judges | A `references` or `subject` entry naming a value key shows it as one quoted line |
| Finalizer | `FinalizerContext.values` ([FIN](78-finalizer-contract.spec.md)) |
| People and tools | The `facts` verb, the status and detail documents |

Values live in a per-unit state channel (contract C7); a trip back to or past a unit clears its values with its other artifacts ([BUD-B4](08-budgets-and-failures.spec.md)). A map item's values are keyed by item ([MAP](77-map-unit.spec.md)).

### 2.3 Template keys

A template field `{name}` ([CON §2.2](01-contracts.spec.md)) names one of these, in this order of lookup:

| Kind | Keys | Renders |
|---|---|---|
| Engine key | `task_id`, `thread_id`, `workflow`, `unit`, `attempt`, `visit`, `branch`, `base`, `workdir`, `run_label` | The run's value; `workdir` is the absolute workspace path |
| Item key (map items only) | `item_id`, `item_index`, `item_count`, `item` | The item's id, 1-based index, the count, and the item's text (≤ 4,000 chars) |
| Input | A declared input name | The resolved value, as today |
| Setting | `settings.<name>`, as the run settings design defines it | The resolved setting |
| Earlier artifact | A key a unit before this one produces | A `file` key: its path relative to `workdir`; `url`, `wiki_page`, `tracker_issue`, `pull_request`: its URL or id; `value`: the value |

Engine and item keys are reserved: an input or artifact may not use one of those names. Nothing else renders: no file content, no judge text, no fact.

## 3. Behaviours

**VAL-B1 Route on a value.** Given a triage step that produces `gaps` and `route` (`choices: [plan, discovery]`) and a switch whose predicate reads `route`, when triage ends with `ARTIFACT route: plan`, then the switch takes `plan` and its `route` record names the value; when triage writes `ARTIFACT route: unclear`, then `route` is absent, the predicate faults, and the switch takes its default arm, `discovery`.

**VAL-B2 The code step finds the plan.** Given a plan step that produces `plan` (kind `file`) and a code step whose template says `Implement {plan} for {task_id}`, when the code step is rendered, then the fields render as `docs/plans/billing.plan.md` and `PROJ-12`, and the plan's content is not in the prompt.

**VAL-B3 A value from a skipped unit.** Given a release step whose template names `{discovery_note}`, produced only by a unit a route can skip, when the workflow is validated, then it warns `template-key-not-on-every-path`; when the run skipped discovery, the field renders as the missing marker and is recorded ([CON §2.2](01-contracts.spec.md)).

**VAL-B4 Item keys.** Given a sequential map over three phases whose step template names `{item_id}` and `{item}`, when item 2 is rendered, then they render the second phase's id and text, and `{item_count}` renders 3.

## 4. Error conditions

| Condition | Result |
|---|---|
| A field naming nothing in §2.3 | Validation error (as today) |
| An input or artifact named like an engine or item key | Validation error `reserved-key` |
| An item key in a template outside a map | Validation error |
| An earlier-artifact field not produced on every path into the step | Validation warning; the marker at run time if absent |
| `choices` and `pattern` both set, or an invalid pattern | Validation error |
| A value line longer than `max_chars` | Clipped; `value_clipped` on the step record |

## 5. Design notes

- A value is an artifact, not a new channel of trust: the step's word for a value is a claim like any other, which is why a check ties temperspec's route to its gap list. The engine only parses and bounds it.
- Pointers, not content, keep the rule that the engine pastes no earlier artifact into a prompt ([PRM §5](04-prompt-rendering.spec.md)); the step reads what the pointer names with its own tools.
- The grammar stays the plain `{name}` field (plus the run settings design's `settings.<name>`); no other dotted path or expression is added, so templates stay checkable by the same validation and prompt audit ([PRA](58-prompt-audit.spec.md)).

## 6. Acceptance criteria

- [ ] VAL-AC-1 Every row of the §2.1 output table and of §4 has a fixture test.
- [ ] VAL-AC-2 A rendered prompt never contains the content of an earlier `file` artifact (canary test).
- [ ] VAL-AC-3 VAL-B1 holds offline with scripted steps, for both the valid and the invalid value.
- [ ] VAL-AC-4 The list of engine and item keys in §2.3 equals the engine's constants (generated-table drift test).

## Open questions

None.

## References

[CON §2.1, §2.2](01-contracts.spec.md) · [PRM](04-prompt-rendering.spec.md) · [CMP](03-compiler-and-flow.spec.md) · [R-075](../research/R-075-temperspec-needs-against-the-engine.rsrch.md)
