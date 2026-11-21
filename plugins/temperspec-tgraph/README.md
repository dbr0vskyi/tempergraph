# temperspec

A tempergraph workflow that takes a task from its acceptance criteria to tested code and a draft pull request, writing the specs the task needs on the way.

Its good outcome: every acceptance criterion in the task's triage_note is met on the run's own branch, by tested code that follows specs which agree with each other, or by those specs alone in a docs-only run.

Start: `tempergraph run temperspec <request>`. The request is the task with its acceptance criteria, or the path of a file that holds it. Add "docs only" to stop after the specs. The plugin is `temperspec-tgraph` (workflow plugins carry the `-tgraph` suffix).

## What a run does

| Step | Writes | Then |
|---|---|---|
| prepare | Nothing by a model: installs the rule files when missing, adds the temperspec note to `CLAUDE.md` (or `AGENTS.md`), and looks for an overview spec | No overview spec goes to setup; otherwise triage |
| setup | Only in a repository without an overview spec: the overview spec, one spec per component, and the setup note listing what it covered and left out | |
| triage | The triage note: the task's acceptance criteria, the documents that exist, the gaps | No gap goes to plan; any gap goes to discovery |
| discovery | Specs, decision records, research notes and the hand-off, one per gap | A docs-only run ends here; every other run goes to plan |
| plan | The plan: requirements, phases, verification, and its complexity | A complex plan goes to expand; a simple one already has its task rows |
| expand | The task rows of a complex plan | |
| code | Tests first, then code, and the code report, in one session | |
| last stage | Pushes the branch and opens a draft pull request, or reuses the open one | |

Each step is followed by a gate: a model-free check first, then a read-only judge. The engine commits after every step. A gate that finds the defect in an earlier step's output sends the run back there by itself. No step or judge uses the large model tier; discovery thinks at the highest effort.

Per-phase coding is not built yet: a complex plan is still coded in one session, and will be split by phase once the engine has its sequential map.

## Rule files

`rules/*.rule.md` say how each document is written: `spec`, `plan`, `decision`, `research`, `task-notes` (the setup note, the triage note, the hand-off, the code report) and `documents` (folders, names, the truth ranking, the rules against cascade edits). The checks read the same formats from `workflow/temperspec/specfmt.py`, and `tests/test_temperspec.py` fails when a rule file and that module disagree.

A run starts by checking that the repository is set up, with no model. It installs the rules into `.claude/rules/temperspec/` when neither the repository nor `~/.claude/rules/temperspec/` has them, and it adds a short block to `CLAUDE.md` (to `AGENTS.md` when the repository has that instead) saying that the repository uses temperspec and where its documents are. When the repository has no overview spec, the `setup` step then writes one from the code and the existing docs, with one spec per component, extending documents that exist and never replacing them. A repository that is already set up skips the step. The step is built so that it can become a sub-workflow once the engine has them.

The `setup` skill installs or updates the rule files by hand, for the repository (the default) or for the whole machine.

## Limits of this version

- Verification commands come from one fixed list: `pytest`, `python3 -m pytest`, `ruff check`, `ruff format --check`, `mypy` and read-only `git`. Another toolchain is added to `VERIFY` in `workflow/temperspec/__init__.py`.
- No release step and no start from a work tracker.
- The last stage needs a remote named `origin` and the `gh` command; without them the run still ends, with the branch and the steps to take by hand.

## State of verification

`tempergraph author verify plugins/temperspec-tgraph` passes its model-free rungs (1 to 7 and 10). Two rungs need a signed-in `claude` and have not run:

- Rung 8, `--judge-seeds`: grades the 32 seed cases under `evals/calibration/` with the real judges. Until it passes, every judged criterion is at uncalibrated trust.
- Rung 9, `--trial`: one capped trial run of a case from `evals/cases.json`.

No real run has been made yet. The commands and pass criteria are in [docs/plans/live-checks.plan.md](docs/plans/live-checks.plan.md).

## What it asks of the engine

temperspec uses the engine like any other workflow package: through `tempergraph.api`, its manifests and its settings. The engine names no workflow. When temperspec needs something the engine lacks, the need is written here under Limits first, and the engine change is made as a capability any workflow can use, stated in the engine's specs without temperspec (engine ADR-0129).
