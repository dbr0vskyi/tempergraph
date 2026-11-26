# Built-in upgrade workflow

## Purpose

The model-assisted part of a workflow upgrade ([WUP-B18](workflow-upgrade.spec.md)) is itself a tempergraph workflow, shipped with the engine like the self-improvement workflow ([SIL](self-improvement.spec.md)). It takes the items of one upgrade plan that no transform can do, edits the workflow package on the upgrade branch, and is held to the engine's own rails: every edit is a step session followed by a deterministic check and an independent judge, the engine derives the verdict, budgets bound retries, and every question only the owner can answer is a pause for the owner ([ADR `upgrade-by-transforms-first-and-a-gated-model-workflow-for-the-rest`](../adr/upgrade-by-transforms-first-and-a-gated-model-workflow-for-the-rest.adr.md), [ADR `independent-judge-engine-verdict`](../adr/independent-judge-engine-verdict.adr.md)). It never verifies the whole upgrade, never stamps and never opens a pull request; those stay with the model-free verb ([WUP-B19](workflow-upgrade.spec.md)). Steps and their gates change apart ([ADR `steps-and-their-graders-change-apart`](../adr/steps-and-their-graders-change-apart.adr.md)): the model may touch a gate's text only through an owner item. Workflow owners upgrading a package and the `upgrade` verb depend on it; design and build notes are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Depends on

- `budgets-and-failures.spec.md`: budgets, failures and timeouts
- `compiler-and-flow.spec.md`: compiler and flow
- `durability-and-resume.spec.md`: status document (DUR-B11)
- `eval-suites.spec.md`: eval suites for checks, steps and workflows
- `executor-interface.spec.md`: executor interface
- `improvement-proposals.spec.md`: change classes (PRP-B14)
- `independence-guard.spec.md`: independence guard and judge views
- `judge-and-verdict.spec.md`: judge and verdict
- `judge-calibration.spec.md`: judge calibration and acceptance
- `version-metadata.spec.md`: compatibility changelog entries (VER-B9); migrate actions (VER-B12); workflow version fields (VER-B14)
- `workflow-model.spec.md`: workflow model and validation
- `workflow-upgrade.spec.md`: where it works (WUP-B14); the plan (WUP-B16)
- `worktree-mode.spec.md`: worktree mode

## Behaviours

### UWF-B6 Registration

WHEN the catalog is built THE engine SHALL find the upgrade workflow by its spec's `builtin` field set to `upgrade` (self-improvement's is `true`), never by its name, add it after every package so none can shadow it ([WFM](workflow-model.spec.md)), exempt it from the issue-repository rule and hide it from `workflows list`.

- GIVEN a package that declares a workflow named `upgrade` WHEN the catalog is built THEN the built-in is still the one the verb starts

### UWF-B5 Direct start refused

WHEN `tempergraph run upgrade …` is typed by a person THE engine SHALL exit 2 naming `tempergraph upgrade <workflow>`, since only the `upgrade` verb starts it, with `origin: upgrade` ([DUR-B11](durability-and-resume.spec.md)).

- GIVEN `tempergraph run upgrade …` WHEN it is checked THEN it exits 2 and names `tempergraph upgrade <workflow>`

### UWF-B7 Input, workspace and limits

WHEN the verb starts the workflow THE workflow SHALL take `upgrade_id`, read `plan.json` and `baseline.json` ([WUP-B14](workflow-upgrade.spec.md)) in a model-free script unit that produces the list artifacts `owner_items` and `assisted_items` and refuses with exit 2 a `plan.json` that is missing or of another engine version; run in place in the upgrade branch's worktree, which an in-place run started inside a linked worktree keeps ([WTR](worktree-mode.spec.md)), with edits limited to the package folder and its inputs and results in `.tempergraph-upgrade/` under the worktree, which the upgrade removes before it commits; use the executor of `UpgradePolicy.executor` ([VER-B14](version-metadata.spec.md)), default `claude`, or the verb's `--executor`, with step model `large` and judge model `medium`; and take the run cost cap from the verb's `--cap`, default $10 ([BUD](budgets-and-failures.spec.md)), exiting 5 when it is spent with finished items left on the branch.

- GIVEN a `plan.json` of another engine version WHEN the input is read THEN it exits 2

### UWF-B8 Units and order

WHEN the workflow runs THE workflow SHALL run, after the script unit, a sequential map `draft_answer` over the owner items and then a sequential map `adjust` over the assisted items, ending for the verb to verify, owner items first because an owner's answer can change what an assisted edit must do, and both maps sequential so edits on one branch never race ([CMP](compiler-and-flow.spec.md)).

- GIVEN one owner item and one assisted item WHEN the run is read THEN `draft_answer` finished before `adjust` started

### UWF-B9 Draft an answer for the owner

WHEN `draft_answer` runs for an owner item THE step SHALL read the entry and the package, draft the smallest change that would answer the owner's question with the question, the choices and what each would change, and write the draft on the branch, its gate the checks and judge of UWF-B12 followed by `approval: true`.

- GIVEN an owner item WHEN its draft passes the gate THEN the run pauses at the approval

### UWF-B3 The owner's answer is the owner's

WHEN the owner decides at a `draft_answer` approval THE workflow SHALL mark the item `answered` by person on proceed (the draft is the answer), keep it `pending` with a new draft on retry with feedback, and mark it `skipped` by person on stop with the feedback as reason.

- GIVEN an owner item asking for the repository that receives the workflow's issues and a draft of `issue_repository` from the git remote WHEN it pauses THEN the question, draft and effect are shown, and the value stays only if the owner proceeds
- GIVEN retry with feedback WHEN decided THEN the item is `pending` with a new draft
- GIVEN stop WHEN decided THEN the item is `skipped` with the feedback as reason

### UWF-B10 Adjust an assisted item

WHEN `adjust` runs for an assisted item THE step SHALL make the edit the entry's instruction asks for at each hit, gated by UWF-B12 with no approval.

- GIVEN an assisted item WHEN its edit passes the gate THEN the item is `done` by model

### UWF-B11 What a step is told and may use

WHEN a step of the workflow is prompted THE workflow SHALL give it the entry's `note`, its `assisted` instruction or `owner` question ([VER-B12](version-metadata.spec.md)), the item's hits with file and field path, the `protected` paths and the workflow's own criteria text for the units the hits sit in; let it read the subject files through tools, not pasted; grant `read`, `search`, `list`, `edit`, `write` and `shell` limited to `validate`, `upgrade --check`, `audit --layer definition` and the package's own check-fixture command ([EVS](eval-suites.spec.md)); grant no network tool, no path outside the package and, in `adjust`, no `protected` path (such an item became an owner item in the plan, [WUP-B16](workflow-upgrade.spec.md)); and take as output the edit and a short change note per hit, what was changed and why, which the report quotes.

- GIVEN an `adjust` step WHEN its tools are read THEN no network tool is granted

### UWF-B12 Gate of each item

WHEN an item's attempt is graded THE gate SHALL run the checks first and the judge only when they pass ([JDG](judge-and-verdict.spec.md)): scope (the attempt's diff touches no file outside the package and, in `adjust`, no `protected` path), load and validate (the package loads and validation has no `error` the baseline lacks), proof (the item's detect rules no longer hit and no `proof` code of its entry is raised, [VER-B9](version-metadata.spec.md)) and fixtures (a changed check or resolver passes its must-pass and must-fail fixtures); then judge the blockers that the edit does what the entry's instruction asks at every hit and nothing only the owner should decide, that behaviour the entry does not concern is unchanged (no rewording, reformatting or extra edits), and that no criterion, check or judge view is weakened and no rubric or bar is invented ([PRP-B14](improvement-proposals.spec.md) `weakening`), and the warning that the diff is the smallest that meets the instruction; the judge reading the diff, the entry's note and instruction and the files before the edit in a read-only view on an executor that declares `restricts_judge_tools` ([GRD](independence-guard.spec.md), [ADR `cross-executor-judging`](../adr/cross-executor-judging.adr.md)), preflight exiting 2 when none does ([EXI](executor-interface.spec.md)).

- GIVEN an attempt whose diff touches a file outside the package WHEN graded THEN the scope check fails and no judge runs

### UWF-B1 An assisted edit is gated

WHEN an `adjust` step edits a check THE gate SHALL re-run the entry's detect rule and the check's fixtures, the judge grading only when both pass and the engine deriving the verdict.

- GIVEN an instruction that a check must read `state.attempts[-1]` instead of `state.last_output` WHEN the step edits `checks/coverage.py` THEN the `symbol` rule and the fixtures run first and the judge grades only when both pass

### UWF-B2 Out-of-scope edit is retried

WHEN the judge finds behaviour the entry does not concern changed THE gate SHALL grade that blocker `UNMET` and retry, telling the next attempt the criterion and the place.

- GIVEN an attempt that also reformats an unrelated template WHEN judged THEN the second blocker is `UNMET`, the verdict is `RETRY` and the next attempt is told the criterion and the place

### UWF-B13 Retries and failures

WHEN an item's retry budget of 2 is spent THE gate SHALL pause for the person under `on_budget_spent: ask`, who may retry with feedback, proceed (the item is left for a hand edit, which the verb's verification names) or stop, and a step session failing for infrastructure SHALL end as any run, exit 5 after its policy with the items not finished left `pending`.

- GIVEN two failed retries of one item WHEN the budget is spent THEN the run pauses for the person

### UWF-B4 A protected path stays the owner's

WHEN the plan finds an assisted entry whose hit is a protected path, such as a criterion text THE engine SHALL make it an owner item, so the model's change reaches the branch only through the owner's approval.

- GIVEN an assisted entry hitting a criterion text WHEN planned THEN it is an owner item

## Acceptance criteria

- UWF-AC1 (UWF-B6, UWF-B5, UWF-B7): The workflow validates under the engine that ships it and is found by its flag, not its name (source-scan test), and a direct run is refused
- UWF-AC2 (UWF-B12, UWF-B1, UWF-B2): Each check of UWF-B12 has a fixture attempt that fails it alone
- UWF-AC3 (UWF-B3, UWF-B9, UWF-B8): Every scenario of UWF-B3 is a test with a scripted executor
- UWF-AC4 (UWF-B11, UWF-B4, UWF-B10): No attempt of the workflow can write outside the package folder (file-system guard with scripted executors)
- UWF-AC5 (UWF-B13): The workflow's step suite upgrades each planted item of its fixture packages, and its judge's gold set reaches the acceptance bar of [JCL](judge-calibration.spec.md) before it is marked `stable`

## Open questions

- Should items of one entry that hit many files be grouped into one `adjust` item per file, as public practice does per file ([research `automated-and-model-assisted-migrations`](../research/automated-and-model-assisted-migrations.rsrch.md) M4), or kept per entry? Until answered: one item per entry and hit set; measure on the first breaking release. Owner: implementer.
- Not met yet: UWF-AC5 needs the step suite's planted fixture packages and a labelled gold set. Owner: engine owner.
