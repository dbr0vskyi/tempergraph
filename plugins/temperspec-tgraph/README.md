# temperspec

A tempergraph workflow that takes a task from its acceptance criteria to tested code and a draft pull request, writing the specs the task needs on the way.

Its good outcome: every acceptance criterion in the task's triage_note is met on the run's own branch, by tested code that follows specs which agree with each other, or by those specs alone in a docs-only run.

Start: `tempergraph run temperspec <request>`. The request is the task with its acceptance criteria, or the path of a file that holds it. Add "docs only" to stop after the specs. The plugin is `temperspec-tgraph` (workflow plugins carry the `-tgraph` suffix).

## What a run does

| Step | Writes | Then |
|---|---|---|
| triage | The triage note: the task's acceptance criteria, the documents that exist, the gaps | No gap goes to plan; any gap goes to discovery |
| discovery | Specs, decision records, research notes and the hand-off, one per gap | A docs-only run ends here; every other run goes to plan |
| plan | The plan: requirements, phases, verification, and its complexity | A complex plan goes to expand; a simple one already has its task rows |
| expand | The task rows of a complex plan | |
| code | Tests first, then code, and the code report, in one session | |
| last stage | Pushes the branch and opens a draft pull request, or reuses the open one | |

Each step is followed by a gate: a model-free check first, then a read-only judge. The engine commits after every step. A gate that finds the defect in an earlier step's output sends the run back there by itself. No step or judge uses the large model tier; discovery thinks at the highest effort.

Per-phase coding is not built yet: a complex plan is still coded in one session, and will be split by phase once the engine has its sequential map.

## Rule files

`rules/*.rule.md` say how each document is written: `spec`, `plan`, `decision`, `research`, `task-notes` (the triage note, the hand-off, the code report) and `documents` (folders, names, the truth ranking, the rules against cascade edits). The checks read the same formats from `workflow/temperspec/specfmt.py`, and `tests/test_temperspec.py` fails when a rule file and that module disagree.

A run installs the rules into `.claude/rules/temperspec/` of the repository when neither the repository nor `~/.claude/rules/temperspec/` has them. The `setup` skill installs or updates them by hand, for the repository (the default) or for the whole machine.

## Limits of this version

- Verification commands come from one fixed list: `pytest`, `python3 -m pytest`, `ruff check`, `ruff format --check`, `mypy` and read-only `git`. Another toolchain is added to `VERIFY` in `workflow/temperspec/__init__.py`.
- No release step and no start from a work tracker.
- The last stage needs a remote named `origin` and the `gh` command; without them the run still ends, with the branch and the steps to take by hand.

## State of verification

`tempergraph author verify plugins/temperspec-tgraph` passes its model-free rungs (1 to 7 and 10). Two rungs need a signed-in `claude` and have not run:

- Rung 8, `--judge-seeds`: grades the 28 seed cases under `evals/calibration/` with the real judges. Until it passes, every judged criterion is at uncalibrated trust.
- Rung 9, `--trial`: one capped trial run of a case from `evals/cases.json`.

No real run has been made yet.
