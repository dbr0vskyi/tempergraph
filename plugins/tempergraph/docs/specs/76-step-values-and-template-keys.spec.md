# Step values and template keys

## Purpose

Steps hand work on as files ([PRM-B14](04-prompt-rendering.spec.md)), but a workflow also needs short values: a route, a gap list, a release-track mark, a story line, a tests-passed claim, handed on from a first step and routed on ([R-075](../research/R-075-temperspec-needs-against-the-engine.rsrch.md) T13, T14). This spec adds the `value` artifact kind and lists the template keys a prompt may name: the engine keys, the declared inputs, and the pointers of earlier artifacts. A template never receives an earlier artifact's content; it receives where it is or, for a value, the value itself, and the step reads what the pointer names with its own tools. A value is a claim like any other step output: the engine only parses and bounds it, and a check ties it to the evidence. Workflow authors, the prompt renderer and the prompt audit ([PRA](58-prompt-audit.spec.md)) depend on it; design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### VAL-B5 The value artifact kind

WHEN a `produces` entry declares kind `value` THE engine SHALL take one line of text, set by the step's `ARTIFACT <key>: <text>` line ([PRM-B11](04-prompt-rendering.spec.md)) or by a script's result ([SCR](70-script-units-and-hybrid-steps.spec.md)), scrubbed before it is stored, with optional `choices` (allowed values compared after trimming and lower-casing), optional `pattern` (a full-match rule for the trimmed value), `max_chars` (default 500; longer text clipped with `value_clipped` on the step record) and `optional` (default false; a missing optional value is not a failure of the built-in output contract), a `produces` entry being either an `ArtifactKind` name or this entry, and `choices` with `pattern`, or an invalid pattern, a validation error.

- GIVEN `choices` and `pattern` both set WHEN validated THEN it is refused

### VAL-B6 Storing a value

WHEN a step's output is read for a value THE engine SHALL store the trimmed, lower-cased match of `choices` (`ARTIFACT route: plan` and `ARTIFACT route: Plan ` both give `values.route = "plan"` for `choices: [plan, discovery]`), record `value_invalid: <key>` and store nothing for a value outside the rule, record `value_missing: <key>` for a required value with no line, and never default an absent value, which every reader reads as absent, a switch whose predicate finds it absent free to take its default arm ([CMP-B10](03-compiler-and-flow.spec.md)) and a check deciding whether absence fails the step.

- GIVEN `ARTIFACT route: maybe` with `choices: [plan, discovery]` WHEN read THEN no value is stored and the step records `value_invalid: route`
- GIVEN no line for a required value WHEN read THEN the step records `value_missing: route`

### VAL-B7 Where values are read

WHEN a value is read THE engine SHALL give it to route and switch predicates as `state.values[unit][key]`, to checks as `ctx.values` ([CHK](75-check-contract-and-command-runs.spec.md)), to templates as `{key}`, to judges as one quoted line for a `references` or `subject` entry naming it, to the finalizer as `FinalizerContext.values` ([FIN](78-finalizer-contract.spec.md)), and to people and tools through `facts` and the status and detail documents; keep values in a per-unit state channel (OVR-B9) cleared with the unit's other artifacts by a trip back to or past it ([BUD-B4](08-budgets-and-failures.spec.md)); and key a map item's values by item ([MAP](77-map-unit.spec.md)).

- GIVEN a trip back past a unit WHEN its values are read THEN they are absent

### VAL-B8 Template keys

WHEN a template field `{name}` ([CON-B8](01-contracts.spec.md)) is rendered THE renderer SHALL look it up in this order: an engine key (`task_id`, `thread_id`, `workflow`, `unit`, `attempt`, `visit`, `branch`, `base`, `workdir` as the absolute workspace path, `run_label`); an item key in map items only (`item_id`, `item_index` 1-based, `item_count`, and `item`, the item's text up to 4,000 characters); a declared input (a workflow with no parameters has the one input `request`, the whole start request); a setting `settings.<name>` ([RST](80-run-settings-and-overrides.spec.md)); an earlier artifact a unit before this one produces (a `file` key renders its path relative to `workdir`; `url`, `wiki_page`, `tracker_issue` and `pull_request` their URL or id; `value` the value); and `<unit>.<key>`, a key a sub-workflow unit before this one exposes, rendered the same way ([SWF-B12](99-subworkflow-unit.spec.md)); render nothing else, no file content, judge text or fact; and SHALL refuse at validation a field naming none of these, an input or artifact named like an engine or item key (`reserved-key`), and an item key outside a map.

- GIVEN an input named `workdir` WHEN validated THEN it is refused `reserved-key`
- GIVEN `{item_id}` in a template outside a map WHEN validated THEN it is refused

### VAL-B1 Route on a value

WHEN a switch's predicate reads a value THE engine SHALL take the arm the value names and record it on the `route` record, and take the default arm when the value is absent.

- GIVEN a triage step producing `route` (`choices: [plan, discovery]`) WHEN it writes `ARTIFACT route: plan` THEN the switch takes `plan` and its `route` record names the value
- GIVEN `ARTIFACT route: unclear` WHEN the switch runs THEN `route` is absent, the predicate faults and the switch takes its default arm `discovery`

### VAL-B2 The code step finds the plan

WHEN a template names an earlier `file` artifact THE renderer SHALL render its path, never its content.

- GIVEN a plan step producing `plan` (kind `file`) and a template `Implement {plan} for {task_id}` WHEN rendered THEN it reads `Implement docs/plans/billing.plan.md for PROJ-12` and the plan's content is not in the prompt

### VAL-B3 A value from a skipped unit

WHEN a template names an artifact not produced on every path into the step THE engine SHALL warn `template-key-not-on-every-path` at validation and, when the run skipped its producer, render the missing marker and record it ([CON-B8](01-contracts.spec.md)).

- GIVEN `{discovery_note}` produced only by a unit a route can skip WHEN validated THEN it warns, and WHEN the run skipped it THEN the marker renders and is recorded

### VAL-B4 Item keys

WHEN a map item's template is rendered THE renderer SHALL render the item keys of that item.

- GIVEN a sequential map over three phases naming `{item_id}` and `{item}` WHEN item 2 is rendered THEN they render the second phase's id and text and `{item_count}` renders 3

## Acceptance criteria

- VAL-AC1 (VAL-B5, VAL-B6, VAL-B8): Every scenario of VAL-B5, VAL-B6 and VAL-B8 has a fixture test
- VAL-AC2 (VAL-B2, VAL-B7): A rendered prompt never contains the content of an earlier `file` artifact (canary test)
- VAL-AC3 (VAL-B1): VAL-B1 holds offline with scripted steps, for both the valid and the invalid value
- VAL-AC4 (VAL-B8, VAL-B3, VAL-B4): The list of engine and item keys in VAL-B8 equals the engine's constants (generated-table drift test)
