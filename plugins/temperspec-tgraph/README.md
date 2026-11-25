# temperspec

A tempergraph workflow that takes a task from its acceptance criteria to tested code and a draft pull request, writing the specs the task needs on the way.

Its good outcome: every acceptance criterion in the task's triage_note is met on the run's own branch, by tested code that follows specs which agree with each other, or by those specs alone in a docs-only run.

Start: `tempergraph run temperspec <request>`. The request is the task with its acceptance criteria, or the path of a file that holds it. Add "docs only" to stop after the specs. The plugin is `temperspec-tgraph` (workflow plugins carry the `-tgraph` suffix).

## What a run does

| Step | Writes | Then |
|---|---|---|
| prepare | Nothing by a model: installs the rule files into `.claude/rules/temperspec/` whenever the repository holds none (neither its own `.claude/rules/temperspec/` nor a folder that holds all six rule files), whether or not the machine has them, adds the temperspec note to `CLAUDE.md` (or `AGENTS.md`) unless that file already names where the specs are, writes `tempergraph.commands.json` (the six Python commands) for a Python repository that has none and leaves an existing one unchanged, and looks for an overview spec | No overview spec goes to setup; otherwise triage |
| setup | Only in a repository without an overview spec: first each component folder is read by its own read-only session, three at a time (none for fewer than two folders), then one session writes the overview spec, one spec per component, and the setup note listing what it covered and left out | |
| triage | The triage note: the task's acceptance criteria, the documents that exist, the gaps, the sort of each gap (findable or owner decision) and the owner decisions with their question, options, default and cost of a wrong default, under every value of the conversation setting | A small fix that changes no spec goes straight to code (the quick lane); no gap goes to plan; a task whose every gap a spec already answers takes the short discovery visit; any other gap goes to `owner_questions` |
| discovery_short | Only the hand-off: for each gap, the cited behaviour and how it answers the gap, or `Not covered`; a reading list of at most 10 files | Every gap answered goes to plan; a gap not covered goes on to the full discovery |
| owner_questions | Nothing by a model: the list of the questions of the one pause, one for each owner decision of the triage note (and, on `always`, one for the reading of each findable gap), at most 20 | A run whose list holds a question goes to `ask_owner` through `ask_route`; any other goes to the reading sessions |
| ask_route | Nothing by a model: sends a run with a question to `ask_owner` and any other to the reading sessions of discovery | |
| ask_owner | Nothing by a model: the one pause. The run stops with the questions, each with its options and default, and goes on when they are answered, or at the deadline with the default of each open question | The reading sessions of discovery |
| discovery | Specs, decision records, research notes and the hand-off, one per gap, written by one session after each gap has been read by its own read-only session, three at a time (none for fewer than two gaps, for the short visit, or for a return from a later gate); it closes each owner decision on the owner's answer, or on its default when there is none, instead of ending blocked | A docs-only run ends here; every other run goes to plan |
| plan | The plan: requirements, phases, verification, and its complexity | The switch `code_mode` chooses from the facts the plan check records: `single` goes to code, `phases` goes through expand first |
| expand | The task rows of a plan that took the `phases` arm of `code_mode` | |
| code | Tests first, then code, and the code report, in one session; both arms end in this one session | |
| last stage | Pushes the branch and opens a draft pull request, or reuses the open one, with a description of what to read | |

Each step is followed by a gate: a model-free check first, then a read-only judge. The engine commits after every step. A gate that finds the defect in an earlier step's output sends the run back there by itself. No step or judge uses the large model tier; discovery thinks at the highest effort, its short visit at `high`. A judge grades only what it can read in the step's output and references: criteria about how a step works (narrow reading, the reading list, commands run once, a reused gate result) are checked by the gate's model-free check, from the package's prompts and the gate's own command runs.

### Three lanes

| Lane | Path | For |
|---|---|---|
| quick | triage → code | A fix or small change that leaves every spec as it is: no gap, at most 3 acceptance criteria, at most 2 code files beside their tests |
| standard | triage → (discovery or its short visit) → plan → code | A change of ordinary size |
| full | triage → discovery → plan → expand → code | A plan over a limit of the plan rule's Complexity table |

Triage proposes the quick lane and writes a short Change section that stands in for the plan. The code gate stays whole, and it measures the change afterwards: a spec or decision record edited, a file the note does not name, more than 2 code files or more than 200 changed lines sends the run back to triage, which then plans the task. A run never moves to a lighter lane.

### What "done" means is fixed before coding

The plan ends with a proof table: for each acceptance criterion of the task, the test file that will prove it and the command that runs it. The code gate runs the commands itself, whatever the step reported, and compares a command that fails with the run's base commit: a failure that was already there, or that no changed file touches, ends the run in an escalation instead of spending retries, and a command that passes at the base and fails on the branch is a retry as before. It also checks that a test in the named file carries the criterion (the spec's id, or `AC <n>`) and is not skipped. The outcome gate applies the same rule to each acceptance criterion a run added or reworded in a spec, and to each old criterion that proves a behaviour the run changed; a spec edited only to add a link asks nothing of its old criteria.

### The pull request says what to read

The last stage writes the description with no model: the task's acceptance criteria, the behaviours and criteria that changed in each spec, the decisions and open questions of discovery, and the deviations of the code report. When the owner answered the pause, the description lists under `Decided`, before the assumptions, each owner decision that has an answer, with its question and the words of the option chosen. When the triage note has an `Owner decisions` section, it lists every other owner decision under `Assumptions to confirm` with its question, the default the run took and what a wrong default costs, or says that the run took no default. A run that made no pause has no `Decided` heading. The notes that steps hand to each other are listed by path as not needed for review.

### An unattended run

The conversation setting says how much a run may ask the owner, with three values: `never`, `blocking` (the default) and `always`. Under every value triage sorts each gap into a findable gap (the code, the documents or a public source can answer it) or an owner decision (only the owner can), and writes for each owner decision its question, two to four options, a default and the cost of a wrong default; the triage check refuses a note that leaves one out.

- `never`: no step or gate stops to ask. Start a run for a pipeline or overnight with `tempergraph run temperspec <request> --set settings.conversation=never`, or set `conversation` to `never` for the repository in the engine's settings files. Discovery closes each owner decision on its default and records any other question it meets as `Until answered: <option>`; the owner reads the defaults in the pull request, under `Assumptions to confirm`.
- `blocking`: one pause after triage, before any reading session, with one question for each owner decision. A run whose note lists no owner decision pauses nowhere. Discovery ends blocked on a question that blocks planning and the note does not list.
- `always`: the same one pause, with one more question after the owner decisions for the reading of each findable gap the note does not mark `Covered by`, answered `right` (the default) or `wrong`. A reading answered `wrong` keeps the pause open until it is answered `right` or the run is stopped to correct the task.

A pause holds at most 20 questions, the owner decisions first. Answer it in the terminal when `tempergraph run` asks, by file with `resume --answers FILE` (`tempergraph resume temperspec <thread> --answers answers.json`), by `--decision answer:<name>=<value>` (the name is the gap's id in lower case, `g2`), or by the agent that started the run, which answers what it can and takes the rest to a person. Answers that leave a question open leave the pause open for it. The pause has a deadline of 86,400 seconds, or the seconds `--set ask_owner.deadline_s=<seconds>` gives; `resume --apply-deadline` before it is refused, and after it the run goes on with the answers already given and the default of each open question. Discovery closes each owner decision on its answer and lists under `Decisions` how each was closed; the pull request lists the answered ones under `Decided` and the rest under `Assumptions to confirm`.

Per-phase coding is not built yet: a complex plan is still coded in one session. The engine has had the sequential map it needs since release 2 (`0.2.0`); splitting the code step by phase is [issue #65](https://github.com/dbr0vskyi/tempergraph/issues/65).

What goes to expand is chosen by the engine's complexity switch `code_mode`, not by the plan's own word: after the plan passes its gate, the arm `single` (straight to code) is taken when every fact the plan check records is inside the limits of `routing/code_mode.json` (the plan rule's limits for a simple plan), and the arm `phases` (through expand first) otherwise or when the switch cannot decide. To name the arm yourself, start the run with `tempergraph run temperspec "<task>" --arm code_mode=<single|phases>`. A repository overrides the limits at `.tempergraph/routing/temperspec/code_mode.json`. `tempergraph report --switch temperspec/code_mode` shows the runs of each arm and zone, the operator's own choices apart from the switch's, and their cost per phase.

## Rule files

`rules/*.rule.md` say how each document is written: `spec`, `plan`, `decision`, `research`, `task-notes` (the setup note, the triage note, the hand-off, the code report) and `documents` (folders, names, the truth ranking, the rules against cascade edits). The checks read the same formats from `workflow/temperspec/specfmt.py`, and `tests/test_temperspec.py` fails when a rule file and that module disagree. Installing the rules in a repository also writes fill-in templates into `docs/templates/`, generated from each rule's example, so a template cannot drift from its rule.

A run starts by checking that the repository is set up, with no model. It installs the rules into `.claude/rules/temperspec/` whenever the repository holds none, that is, when it has neither its own `.claude/rules/temperspec/` nor a folder of the repository (outside copies and fixtures) that holds all six rule files. `~/.claude/rules/temperspec/` does not count, whether or not the machine holds the rule files: a step session starts with the project setting source only and cannot open a file outside its working directory, so it reads only the repository's rule files. A repository that holds the rule files in a folder of its own, as this one does, gets no copy and no templates. It adds a short block to `CLAUDE.md` (to `AGENTS.md` when the repository has that instead) saying that the repository uses temperspec and where its documents are. The block is written from the repository's real layout: the folder of each overview spec as the specs folder, `adr/`, `research/`, `plans/` and `tasks/` beside each, the rule files' real location, and `docs/templates/` only where it holds templates. A project-context file that already names a specs folder (or the folder that contains it) by its whole path from the repository root is left unchanged and gets no block. When the repository has no overview spec, the `setup` step then writes one from the code and the existing docs, with one spec per component, extending documents that exist and never replacing them. A repository that is already set up skips the step. The step is built so that it can become a sub-workflow once the engine has them.

The `setup` skill installs or updates the rule files by hand, for the repository (the default) or for the whole machine.

## Limits of this version

- Verification commands come from the repository's own `tempergraph.commands.json` (the engine's `@repository` commands; [spec](docs/specs/repository-commands.spec.md)). `prepare` writes it for a Python repository that has none, with `pytest`, `python -m pytest`, `python3 -m pytest`, `ruff check`, `ruff format --check` and `mypy`, and leaves an existing file as it is; a repository of another language declares its own commands there. Read-only `git` is always allowed. A command may be written `cd <folder> && <command>`, as a repository's `CLAUDE.md` often writes it, and runs in that folder.
- No release step and no start from a work tracker.
- The quick lane's limits are first values with no run behind them. A test carries its criterion as text; the check does not prove that the named test is the one the command ran.
- The writing sessions of discovery and setup are briefed with what the reading sessions found through the engine's [VAL-B9](../tempergraph/docs/specs/76-step-values-and-template-keys.spec.md): a later template that names a key a map's step produces gets one line for each item, in list order. The need is written here first (engine ADR-0129). Two subjects before reading sessions start, and three at a time, are first values with no measured run behind them. Each reading session has a judge session of its own, because the engine asks every model step for a judge; the judges of one gate stay one, and the open question is in [parallel-reading.spec.md](docs/specs/parallel-reading.spec.md).
- The last stage needs a remote named `origin` and the `gh` command; without them the run still ends, with the branch and the steps to take by hand.

## State of verification

`tempergraph author verify plugins/temperspec-tgraph` passes its model-free rungs (1 to 7 and 10). Two rungs need a signed-in `claude` and have not run:

- Rung 8, `--judge-seeds`: grades the 34 seed cases under `evals/calibration/` with the real judges. Until it passes, every judged criterion is at uncalibrated trust.
- Rung 9, `--trial`: one capped trial run of a case from `evals/cases.json`. The trial run that shows the route after the plan, the switch `code_mode` with its `route` record, is row TS-L3 of the live checks.

No real run has been made yet. The commands and pass criteria are in [docs/plans/live-checks.plan.md](docs/plans/live-checks.plan.md).

## What comes next

Features found useful and not built yet are [GitHub issues labelled `area: temperspec`](https://github.com/dbr0vskyi/tempergraph/issues?q=is%3Aissue+is%3Aopen+label%3A%22area%3A+temperspec%22), each with what it waits for; see [CONTRIBUTING.md](../../CONTRIBUTING.md).

## What it asks of the engine

temperspec uses the engine like any other workflow package: through `tempergraph.api`, its manifests and its settings. The engine names no workflow. When temperspec needs something the engine lacks, the need is written here under Limits first, and the engine change is made as a capability any workflow can use, stated in the engine's specs without temperspec (engine ADR-0129). The reading sessions of discovery and setup run on the engine's concurrent map, and the writing session reads their findings through the map's items in a later template (VAL-B9). The callable of a script unit (`owner_questions`) gets the artifacts, values and settings of the run so far (SCR-B5, RST-B25), so that it reads the triage note and the `conversation` setting.
