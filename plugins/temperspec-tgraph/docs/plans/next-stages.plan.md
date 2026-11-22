---
goal: Take temperspec from its first build to a workflow measured on real runs that uses every engine capability its backlog waits for, stage by stage as the engine's releases arrive
date_created: 2026-11-22
owner: dbr0vskyi
status: planned
research: docs/research/stages-against-engine-releases.rsrch.md
---

# Next stages of temperspec

## 0. Hand-off

- Asked by the owner on 2026-11-21: once the engine's release 2 is finished, plan and prepare temperspec's further stages.
- Research: [stages against engine releases](../research/stages-against-engine-releases.rsrch.md). It rests on the [backlog](backlog.plan.md), [next features](../research/next-features.rsrch.md) and the engine's release 3 proposal (ADR-0132, in review).
- What this plan is not: it builds nothing. Each stage is built by its own pull request, which deletes the backlog rows it builds and updates the specs it changes, as the backlog's rule says.
- The backlog stays the one list of features. This plan orders its rows into stages and names what each stage waits for.
- The owner's rulings of 2026-11-22 are in §3.

## 1. Stages

| Stage | Goal | Engine release | Waits for | Rows |
|---|---|---|---|---|
| S0 Evidence | Real runs that reach a draft pull request, with graded judges, on this repository's own work | 2 (built) | nothing | TS-L2; T3 |
| S1 Release 2, no new shape | Drop the workarounds release 1 forced on temperspec | 2 (built) | S0's first run | B1, B2, B3, B10, B16, B17 |
| S2 Release 2, new shapes | Per-phase coding and the conversation | 2 (built), plus one engine request | S1; B9 also needs the phase judge graded live | B7, B6, B9 |
| S3 Release 3 | Sub-workflows, parallel work, hard choices, schedules, the pull-request report | 3 (proposed) | The owner accepting ADR-0132, then each engine track | B11, B8, B12, B13, B14, B15, B18 |
| S4 Release 4 | Other executors and batches of tasks | 4 (proposed) | ADR-0132 | none yet |
| M Engine spec migration | The engine's specs move to temperspec's format | none | nothing: the owner asked for it on 2026-11-22 | the owner's rulings of 2026-11-21 and 2026-11-22 |

B4 (property-based tests) and B5 (the trial against OpenSpec and GSD 2) do not depend on the engine. B4 can go into any stage after S1. B5 is worth most after S2, when per-phase coding and the conversation are in place.

## 2. Stage details

### S0 Evidence

The owner's ruling of 2026-11-22: temperspec is used to develop tempergraph and temperspec themselves, so the evidence comes from real tasks of this repository and not from a scratch one. The judge seeds and the trial passed live on 2026-11-21 and 2026-11-22 ([live checks](live-checks.plan.md)).

| Step | What | Passes when |
|---|---|---|
| S0.1 | This repository is made ready for runs: `tempergraph.commands.json` or today's fixed list covers the engine's commands (pytest, ruff, mypy from `plugins/tempergraph/engine/`), and `prepare` finds the engine's overview spec | A dry start reaches triage without the setup step |
| S0.2 | The first tasks of S1 are run through temperspec, a small one first (B16), each from a task file with its acceptance criteria | The last stage reports `opened`, and the draft pull request carries the model-free description. This also finishes TS-L2's real run |
| S0.3 | The owner grades each run's pull request and answers T3 (decision records 0001 and 0002, tests failing before the code step) | Recorded; the backlog's T3 row is then deleted |

The cost of each step and judge goes into decision record 0002 as the first measured sizing. A run that fails is kept as a finding and the task is finished by hand, so a defect of temperspec never blocks the work it was meant to do. The engine's specs are in the engine's own format until stage M has moved them; until then a run that edits one fails `ts-spec-form`, so S0 starts with tasks in the package and the first migrated specs.

### S1 Release 2, no new shape

| Step | What | Changes |
|---|---|---|
| S1.1 | B10: `@repository` commands. `prepare` writes `tempergraph.commands.json` with today's list when a Python repository has none | `workflow/temperspec/__init__.py`, `routing.py`; overview open question 6 removed |
| S1.2 | B16: per-path deliverables and the `pushed` fact | `outcome.json` (revision 5), overview open questions 2 and 7 |
| S1.3 | B17: the plan route as a complexity switch with arms `single` and `phases`, the second the safe arm; rules file `routing/code_mode.json`; the owner's override at start comes from the engine's arm override | `__init__.py`, `routing.py`, the blueprint |
| S1.4 | B1: conversation, mode `never`, for pipelines and night runs. Triage sorts gaps into findable and owner decisions; the last stage lists the defaults taken | `prompts/triage.md`, `checks.py`, `summary.py`, the triage judge's seeds |
| S1.5 | B2: the outcome check fails when a spec the run edited changed on the base branch since the run started | `checks.py` |
| S1.6 | B3: a model-free drift script for pre-commit and CI, reusing `specfmt.py` | a new script, the `setup` skill |

Each step goes through `author verify` and the package's offline tests. S1.3 changes the run's shape, so it needs a new trial.

### S2 Release 2, new shapes

| Step | What | Notes |
|---|---|---|
| S2.1 | B7: per-phase coding. The `phases` arm of S1.3 is `expand` → a sequential map `phase` over the plan's phases → `code` as the join | The map's gate has no line back; the quick-lane guard and the plan's upstream line move to the join, which checks the whole change. Each item commits through the `after` script |
| S2.2 | B6: conversation, modes `blocking` (the default) and `always`. A route after triage skips the ask when there is no question for the mode; an ask unit takes its questions from triage's list. The agent that started the run answers what it can from the pause's payload and takes the rest to a person | `on_deadline: escalate` until B18 exists. Until S2.2 is built the only mode is `never` |
| S2.3 | B9: a cheaper alias for phases the plan marks mechanical, through the map's `item_model`; the ladder climbs only on a trusted judged blocker | Only after the phase judge's seeds pass live; no large tier (owner, 2026-11-21) |

### S3 Release 3

Each row starts when its engine track is built: B11 on sub-workflows; B8 on the concurrent map and the cap's reservation; B12 on writer branches; B13 on contest and council, and only where a measured switch shows the gain is worth the cost; B14 on schedules; B15 on the pull-request gate. The docs-only version the owner asked for becomes a second workflow built from the same sub-workflows as B11.

### S4 Release 4

Other executors need temperspec's prompts and checks to name no Claude Code tool by name; S1 to S3 keep them so. Batches of tasks build on B2's guard.

### M Engine spec migration

Asked for by the owner on 2026-11-22 and done as work of its own, outside this plan's stages: its plan is written first (what each of the engine's sections becomes, how ids and the links from code, tests and plans are kept, and what to do with a spec over 400 lines), then a few specs as a pilot, then the rest.

## 3. The owner's rulings of 2026-11-22

| # | Question | Ruling |
|---|---|---|
| D1 | Where the evidence comes from | temperspec is used for the development of tempergraph and temperspec |
| D2 | The three proposals of the research note | Added to the backlog as B16, B17 and B18 |
| D3 | The conversation's default mode | `blocking`: the agent that orchestrates temperspec runs can answer the questions or escalate them to a person |
| D4 | When the engine's specs migrate | Now |
