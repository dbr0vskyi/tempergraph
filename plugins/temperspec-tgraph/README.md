# temperspec

A tempergraph workflow that takes a task from its acceptance criteria to tested code and a draft pull request, writing the specs the task needs on the way.

Its good outcome: every acceptance criterion in the task's triage_note is met on the run's own branch, by tested code that follows specs which agree with each other, or by those specs alone in a docs-only run.

Start: `tempergraph run temperspec <request>`. The request is the task with its acceptance criteria, or the path of a file that holds it. Add "docs only" to stop after the specs. The plugin is `temperspec-tgraph` (workflow plugins carry the `-tgraph` suffix).

## What a run does

| Step | Writes | Then |
|---|---|---|
| prepare | Nothing by a model: installs the rule files only when neither the repository (its own `.claude/rules/temperspec/`, or a folder that holds all six rule files) nor the machine has them, adds the temperspec note to `CLAUDE.md` (or `AGENTS.md`) unless that file already names where the specs are, and looks for an overview spec | No overview spec goes to setup; otherwise triage |
| setup | Only in a repository without an overview spec: the overview spec, one spec per component, and the setup note listing what it covered and left out | |
| triage | The triage note: the task's acceptance criteria, the documents that exist, the gaps | A small fix that changes no spec goes straight to code (the quick lane); no gap goes to plan; a task whose every gap a spec already answers takes the short discovery visit; any other gap goes to discovery |
| discovery_short | Only the hand-off: for each gap, the cited behaviour and how it answers the gap, or `Not covered`; a reading list of at most 10 files | Every gap answered goes to plan; a gap not covered goes on to the full discovery |
| discovery | Specs, decision records, research notes and the hand-off, one per gap | A docs-only run ends here; every other run goes to plan |
| plan | The plan: requirements, phases, verification, and its complexity | A complex plan goes to expand; a simple one already has its task rows |
| expand | The task rows of a complex plan | |
| code | Tests first, then code, and the code report, in one session | |
| last stage | Pushes the branch and opens a draft pull request, or reuses the open one, with a description of what to read | |

Each step is followed by a gate: a model-free check first, then a read-only judge. The engine commits after every step. A gate that finds the defect in an earlier step's output sends the run back there by itself. No step or judge uses the large model tier; discovery thinks at the highest effort, its short visit at `high`. A judge grades only what it can read in the step's output and references: criteria about how a step works (narrow reading, the reading list, commands run once, a reused gate result) are checked by the gate's model-free check, from the package's prompts and the gate's own command runs.

### Three lanes

| Lane | Path | For |
|---|---|---|
| quick | triage → code | A fix or small change that leaves every spec as it is: no gap, at most 3 acceptance criteria, at most 2 code files beside their tests |
| standard | triage → (discovery or its short visit) → plan → code | A change of ordinary size |
| full | triage → discovery → plan → expand → code | A complex plan |

Triage proposes the quick lane and writes a short Change section that stands in for the plan. The code gate stays whole, and it measures the change afterwards: a spec or decision record edited, a file the note does not name, more than 2 code files or more than 200 changed lines sends the run back to triage, which then plans the task. A run never moves to a lighter lane.

### What "done" means is fixed before coding

The plan ends with a proof table: for each acceptance criterion of the task, the test file that will prove it and the command that runs it. The code gate runs the commands itself, whatever the step reported, and compares a command that fails with the run's base commit: a failure that was already there, or that no changed file touches, ends the run in an escalation instead of spending retries, and a command that passes at the base and fails on the branch is a retry as before. It also checks that a test in the named file carries the criterion (the spec's id, or `AC <n>`) and is not skipped. The outcome gate applies the same rule to each acceptance criterion a run added or reworded in a spec, and to each old criterion that proves a behaviour the run changed; a spec edited only to add a link asks nothing of its old criteria.

### The pull request says what to read

The last stage writes the description with no model: the task's acceptance criteria, the behaviours and criteria that changed in each spec, the decisions and open questions of discovery, and the deviations of the code report. The notes that steps hand to each other are listed by path as not needed for review.

Per-phase coding is not built yet: a complex plan is still coded in one session. The engine has had the sequential map it needs since release 2 (`0.2.0`); splitting the code step by phase is [issue #122](https://github.com/dbr0vskyi/tempergraph/issues/122).

## Rule files

`rules/*.rule.md` say how each document is written: `spec`, `plan`, `decision`, `research`, `task-notes` (the setup note, the triage note, the hand-off, the code report) and `documents` (folders, names, the truth ranking, the rules against cascade edits). The checks read the same formats from `workflow/temperspec/specfmt.py`, and `tests/test_temperspec.py` fails when a rule file and that module disagree. Installing the rules in a repository also writes fill-in templates into `docs/templates/`, generated from each rule's example, so a template cannot drift from its rule.

A run starts by checking that the repository is set up, with no model. It installs the rules into `.claude/rules/temperspec/` only when none of these has them: the repository's own `.claude/rules/temperspec/`, a folder of the repository (outside copies and fixtures) that holds all six rule files, and `~/.claude/rules/temperspec/` for the whole machine. A repository that holds the rule files in a folder of its own, as this one does, gets no copy and no templates. It adds a short block to `CLAUDE.md` (to `AGENTS.md` when the repository has that instead) saying that the repository uses temperspec and where its documents are. The block is written from the repository's real layout: the folder of each overview spec as the specs folder, `adr/`, `research/`, `plans/` and `tasks/` beside each, the rule files' real location, and `docs/templates/` only where it holds templates. A project-context file that already names a specs folder (or the folder that contains it) by its whole path from the repository root is left unchanged and gets no block. When the repository has no overview spec, the `setup` step then writes one from the code and the existing docs, with one spec per component, extending documents that exist and never replacing them. A repository that is already set up skips the step. The step is built so that it can become a sub-workflow once the engine has them.

The `setup` skill installs or updates the rule files by hand, for the repository (the default) or for the whole machine.

## Limits of this version

- Verification commands come from one fixed list: `pytest`, `python -m pytest`, `python3 -m pytest`, `ruff check`, `ruff format --check`, `mypy` and read-only `git`. A command may be written `cd <folder> && <command>`, as a repository's `CLAUDE.md` often writes it, and runs in that folder. Another toolchain is added to `VERIFY` in `workflow/temperspec/__init__.py`.
- No release step and no start from a work tracker.
- The quick lane's limits are first values with no run behind them. A test carries its criterion as text; the check does not prove that the named test is the one the command ran.
- The last stage needs a remote named `origin` and the `gh` command; without them the run still ends, with the branch and the steps to take by hand.

## State of verification

`tempergraph author verify plugins/temperspec-tgraph` passes its model-free rungs (1 to 7 and 10). Two rungs need a signed-in `claude` and have not run:

- Rung 8, `--judge-seeds`: grades the 34 seed cases under `evals/calibration/` with the real judges. Until it passes, every judged criterion is at uncalibrated trust.
- Rung 9, `--trial`: one capped trial run of a case from `evals/cases.json`.

No real run has been made yet. The commands and pass criteria are in [docs/plans/live-checks.plan.md](docs/plans/live-checks.plan.md).

## What comes next

Features found useful and not built yet are [GitHub issues labelled `area: temperspec`](https://github.com/dbr0vskyi/tempergraph/issues?q=is%3Aissue+is%3Aopen+label%3A%22area%3A+temperspec%22), each with what it waits for; see [CONTRIBUTING.md](../../CONTRIBUTING.md).

## What it asks of the engine

temperspec uses the engine like any other workflow package: through `tempergraph.api`, its manifests and its settings. The engine names no workflow. When temperspec needs something the engine lacks, the need is written here under Limits first, and the engine change is made as a capability any workflow can use, stated in the engine's specs without temperspec (engine ADR-0129).
