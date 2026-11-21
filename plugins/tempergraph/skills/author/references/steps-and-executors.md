# Phases 5 and 6: the steps' work, the start and routing

## Phase 5: units in `blueprint.json`

Write one unit per intermediate outcome, in order:

```json
{"schema_version": 1, "name": "<workflow>", "outcome_ref": {"revision": 1, "digest": "<from author check>"},
 "units": [{"name": "draft", "kind": "step", "summary": "Write the release notes", "produces": ["notes"],
            "reads": [], "gate": {"check": true, "judge": true}, "executor": "claude"}],
 "flow": {}}
```

- `summary` is at most 60 characters. A blueprint has at most 20 units.
- Kinds in this release: `step` (a model session), `script` (model-free work), `route` and `switch` (a choice on a value). Offer later kinds (council, contest, ask, map, sub-workflow) only by name, marked "later".
- Each step gets a check where any criterion is `check`, and a judge where any is `judge`. Every step declares at least one criterion.
- `outcome_ref.digest` must match the outcome draft. After an outcome edit, `blueprint check` reports `blueprint_outcome_mismatch`; update the digest.
- Ask each policy as a choice with its consequence: what a failure does, what a spent retry budget does (stop, or ask a person), whether a person approves after a pass, when a person is asked, the self-improvement mode, the repository for the workflow's own issues (required: set `issue_repository` in `authoring.json`), and whether steps run in a worktree. Every option you do not ask takes its documented default; show the defaults.

## Executors and their consequences

Run `tempergraph executors`. For each step, read the chosen executor's `capabilities` and `compat` from that output, and state the consequences from those fields, not from memory:

- `reports_cost`: whether cost is reported or only estimated
- `restricts_judge_tools`: whether the judge can run on the same executor
- `session_options`: which caps (cost, turns, fallback) are available
- `hosts_authoring_surface`: whether skills and agents work there
- `compat`: whether this executor version was tested

Only executors that `executors` lists can be chosen. Record each choice and its stated consequence as a decision.

## Models and effort

Assess every step and every judge, one by one, and write the result in the blueprint as `sizing` and `judge_sizing`: `{"model": "<tier>", "effort": "<effort>", "why": "<one sentence>"}`. `blueprint check` refuses a step or judge without one, and `author verify` fails rung 6 on a declaration that leaves model, effort or the reason to a default. Ask the person only when the cost matters to them; otherwise decide, and record the sizing as an assumption.

Use aliases (`small`, `medium`, `large`), never model ids. Efforts are `low`, `medium`, `high`, `xhigh`, `max`.

| The session mostly | Start at | Raise when |
|---|---|---|
| Sorts, extracts, copies or reformats one input | `small` or `medium`, effort `low` or `medium` | Its gate fails on substance, not on shape |
| Writes one document from a few inputs | `medium`, `medium` | It must reconcile several sources |
| Designs, plans, researches or reads across many files | `medium`, `high`; `large` only with a measured reason | A weak result costs a later long session |
| Runs long with tools and tests that catch slips | `medium`, `high` | Tests cannot catch the defect class |
| Judges one file against a few criteria | The step's tier, `low` or `medium` | It reads across files (never `small`), or a miss ships a defect: `high` |

A judge is at least as strong as its producer. The `why` names the work, not the wish: "reads the diff and the proof of every criterion" and not "needs to be good". Limits and caps come from recorded runs, not guesses; a sizing made before any run says so in its decision.

Approve with `tempergraph author approve <id> 5`.

## Phase 6: how a run starts, and routing

- `input` in the blueprint: the target in one line, each named input with its meaning and an example value, and two or three whole start requests that must resolve. Take the examples from intake where possible.
- No text claims a field is required, gives a default or lists choices. Only the resolver knows.
- `routing` in `authoring.json`: a `description` (one line that starts with a verb and names the output), `when_to_use` (two to four sentences, then "Not for:" naming the closest workflows), and the `task_kind` (`ticket`, `prompt`, `symptom`, `repository` or `findings`).

Approve with `tempergraph author approve <id> 6`.
