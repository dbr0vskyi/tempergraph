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
- The backlog stays the one list of features. This plan orders its rows into stages and names what each stage waits for. A proposal below that has no row yet becomes one only when the owner wants it.

## 1. Stages

| Stage | Goal | Engine release | Waits for | Rows |
|---|---|---|---|---|
| S0 Evidence | One real run that reaches a draft pull request, with graded judges | 2 (built) | Pull request 36 merged | TS-L1, TS-L2; T3 |
| S1 Release 2, no new shape | Drop the workarounds release 1 forced on temperspec | 2 (built) | S0 | B1, B2, B3, B10; P1, P2 |
| S2 Release 2, new shapes | Per-phase coding and the conversation | 2 (built), plus one engine request | S1; B9 also needs the phase judge graded live | B7, B6, B9; P3 |
| S3 Release 3 | Sub-workflows, parallel work, hard choices, schedules, the pull-request report | 3 (proposed) | The owner accepting ADR-0132, then each engine track | B11, B8, B12, B13, B14, B15 |
| S4 Release 4 | Other executors and batches of tasks | 4 (proposed) | ADR-0132 | none yet |
| M Engine spec migration | The engine's 70 specs move to temperspec's format | none | S1 and two real runs | the owner's ruling of 2026-11-21 |

B4 (property-based tests) and B5 (the trial against OpenSpec and GSD 2) do not depend on the engine. B4 can go into any stage after S1. B5 is worth most after S2, when per-phase coding and the conversation are in place.

**Proposals with no backlog row yet** (research §4):

| # | Proposal | Stage |
|---|---|---|
| P1 | List `handoff`, `plan` and `code_report` as deliverables, now that a deliverable is required only on its own path; the outcome check reports `pushed` | S1 |
| P2 | Route the plan through the engine's complexity switch instead of `routing.py`'s hand-written route, measured on the plan check's facts | S1 |
| P3 | Ask the engine for an `on_deadline` choice that fills unanswered questions with their defaults and proceeds | S2, engine release 3 |

## 2. Stage details

### S0 Evidence

| Step | What | Passes when |
|---|---|---|
| S0.1 | TS-L1 and the trial run again after pull request 36 merges, on the engine at `main` | Rung 8 `passed` and the trial reaches the outcome gate (as in the [live checks](live-checks.plan.md)) |
| S0.2 | TS-L2's real run in a scratch repository with a GitHub remote | The last stage reports `opened` and the draft pull request carries the model-free description |
| S0.3 | The owner grades the run and answers T3 (decision records 0001 and 0002, tests failing before the code step) | Recorded in the backlog's T3 row, which is then deleted |

The cost of each step and judge in S0.2 goes into decision record 0002 as the first measured sizing.

### S1 Release 2, no new shape

| Step | What | Changes |
|---|---|---|
| S1.1 | B10: `@repository` commands. `prepare` writes `tempergraph.commands.json` with today's list when a Python repository has none | `workflow/temperspec/__init__.py`, `routing.py`; overview open question 6 removed |
| S1.2 | P1: per-path deliverables and the `pushed` fact | `outcome.json` (revision 5), overview open questions 2 and 7 |
| S1.3 | P2: the plan route as a complexity switch with arms `single` and `phases`, the second the safe arm; rules file `routing/code_mode.json`; the owner's override at start comes from the engine's arm override | `__init__.py`, `routing.py`, the blueprint |
| S1.4 | B1: conversation, mode `never`. Triage sorts gaps into findable and owner decisions; the last stage lists the defaults taken | `prompts/triage.md`, `checks.py`, `summary.py`, the triage judge's seeds |
| S1.5 | B2: the outcome check fails when a spec the run edited changed on the base branch since the run started | `checks.py` |
| S1.6 | B3: a model-free drift script for pre-commit and CI, reusing `specfmt.py` | a new script, the `setup` skill |

Each step goes through `author verify` and the package's offline tests. S1.3 changes the run's shape, so it needs a new trial.

### S2 Release 2, new shapes

| Step | What | Notes |
|---|---|---|
| S2.1 | B7: per-phase coding. The `phases` arm of S1.3 is `expand` → a sequential map `phase` over the plan's phases → `code` as the join | The map's gate has no line back; the quick-lane guard and the plan's upstream line move to the join, which checks the whole change. Each item commits through the `after` script |
| S2.2 | B6: conversation, modes `blocking` and `always`. A route after triage skips the ask when there is no question for the mode; an ask unit takes its questions from triage's list | `on_deadline: escalate` until P3 exists |
| S2.3 | B9: a cheaper alias for phases the plan marks mechanical, through the map's `item_model`; the ladder climbs only on a trusted judged blocker | Only after the phase judge's seeds pass live; no large tier (owner, 2026-11-21) |

### S3 Release 3

Each row starts when its engine track is built: B11 on sub-workflows; B8 on the concurrent map and the cap's reservation; B12 on writer branches; B13 on contest and council, and only where a measured switch shows the gain is worth the cost; B14 on schedules; B15 on the pull-request gate. The docs-only version the owner asked for becomes a second workflow built from the same sub-workflows as B11.

### S4 Release 4

Other executors need temperspec's prompts and checks to name no Claude Code tool by name; S1 to S3 keep them so. Batches of tasks build on B2's guard.

## 3. Decisions for the owner

| # | Decision | Default taken here |
|---|---|---|
| D1 | The stage order, evidence first | As above |
| D2 | P1, P2 and P3 enter the backlog | Yes |
| D3 | The conversation's default mode | `never`; `blocking` per repository |
| D4 | When the engine's specs migrate (stage M) | After S1 and two real runs |
