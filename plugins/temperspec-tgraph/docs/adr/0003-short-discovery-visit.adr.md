# 0003 Discovery gets a short visit when triage marks every gap covered

Status: proposed, not built. The run `speedup-runs` (2026-11-22) built the covered marks that this decision reads, but not the second step: the engine's generated stand-in run needs every unit of `order` visited, and the docs self-test, the eval fixtures, the diagram and the stamp all change with a new unit ([code report](../tasks/speedup-runs.report.md), deviation 6). Backlog row B21 holds what is left.

## Context

Triage lists a gap in doubt ([task-notes rule](../../rules/task-notes.rule.md)), so a task whose behaviour a spec already states still reaches discovery, and discovery runs at `max` ([0002](0002-model-and-effort-per-unit.adr.md)). Run r3-t1-1b spent 16 minutes and about 4 USD there on a behaviour that was already specified ([backlog B21](../plans/backlog.plan.md), [R-160](../../../tempergraph/docs/research/R-160-does-the-improvement-loop-find-what-a-reviewer-finds.rsrch.md)). `max` stays right for a gap no spec answers, since nothing downstream rechecks what discovery finds. This record adds a visit to the table of 0002 and replaces none of its rows.

The task `speedup-runs` asks that triage mark a gap a spec already answers, that discovery for a task with only such gaps be short (a lower effort and a reading limit), and that the choice use the engine's existing means of choosing a unit's sizing or arm by a run fact. What the engine offers, read in its specs and in the package:

- A complexity switch picks one arm from measured facts and is sticky for the whole run ([CXR-B7](../../../tempergraph/docs/specs/94-complexity-routing.spec.md)).
- Arm overrides give the units of an arm another model, other limits or another effort. They change no prompt, and the engine asks no sizing reason for them ([SWM-B4](../../../tempergraph/docs/specs/79-measured-switches.spec.md), [SWM-B6](../../../tempergraph/docs/specs/79-measured-switches.spec.md)).
- An effort ladder starts every visit at its first rung and climbs only on trusted failure evidence ([LAD-B9](../../../tempergraph/docs/specs/92-effort-ladder-and-model-escalation.spec.md), [LAD-B10](../../../tempergraph/docs/specs/92-effort-ladder-and-model-escalation.spec.md)).
- The route after triage already picks the next unit from the values the triage step produced (`route_triage` in `workflow/temperspec/routing.py`), and every step unit states its model, effort and a reason of its own ([SCF-B10](../../../tempergraph/docs/specs/91-blueprint-and-scaffold.spec.md)).
- The plan, expand and code gates name `discovery` as a unit a run may be sent back to (`back_targets` in `workflow/temperspec/__init__.py`).

## Decision

We will declare a second discovery step, the short visit, beside the existing one, and let the route after triage choose it. A run takes the short visit only when the triage check has verified that every gap row says `Covered by` and names a behaviour and a criterion that exist. A task with any other gap takes the full discovery as today, and every return to discovery from a later gate takes the full one. Both visits produce the same hand-off, with its reading list, and are held by the same discovery check and the same judge file. The short visit's prompt states a reading limit of 10 files.

Each step and judge states its effort and why, as 0002 requires. A first assessment, made without a run:

| Visit | Step | Why | Judge | Why |
|---|---|---|---|---|
| Short | medium, high | It confirms that each cited behaviour answers its gap and lists the files the plan will need; it designs nothing, and the check and the judge verify the cited ids | medium, high | A gap wrongly marked covered would cost a whole code session, so the verdict keeps the effort of the full visit |
| Full | medium, max | Unchanged from 0002 | medium, high | Unchanged from 0002 |

## Options considered

### One discovery step under a complexity switch, with an arm override for the effort

For: the engine's own choice by a measured fact, reported by arm and zone; one step, one prompt. Against: the arm is sticky for the run, so a run that comes back to discovery after a short first visit would stay short, which is the wrong direction; an override changes the effort but not the prompt, so the reading limit would sit in the prompt every visit reads; the override has no reason of its own, so the reasons would live in a table the engine's sizing check does not read; and the switch's rules file and zones are built for choosing a decomposition by measured size, not for a yes or no that the triage check has already counted.

### An effort ladder on the one discovery step

For: the engine's own means, and it climbs only on trusted evidence. Against: it starts every visit at its first rung whatever the note says, so a task with an open gap would start below `max` where nothing downstream rechecks it, and it never reads the covered marks.

### One lower effort for every discovery visit

For: no new step. Against: it takes depth from the gaps that need it, which 0002 keeps at `max`.

### Skip discovery when every gap is covered

For: the cheapest run. Against: the plan then has no hand-off and no reading list, a wrong covered mark meets only the plan gate, and the task asks for a short visit, not for none.

### A second discovery step chosen by the route after triage

For: it uses a means the workflow already has; each visit states its own sizing and reason, which the existing sizing test and audit rule already hold; a return to discovery goes to the full visit by name; the run log shows which visit ran. Against: two declarations to keep in step. One check, one judge file, one hand-off form and a package test that compares the two declarations limit the drift.

## Consequences

A task whose gaps a spec already answers costs less: an effort of `high` instead of `max`, and 10 files instead of an open reading. The plan starts from a reading list on both paths. The cost is a second step to maintain.

A gap marked covered by mistake meets three nets: the triage check confirms that the cited behaviour and criterion exist and that the criterion names the behaviour, the short visit's judge reads whether the behaviour answers the gap, and a later gate sends the run back to the full visit. The effort `high` and the limit of 10 files are first assessments, as in 0002: the session log of a short visit shows how many files it read.

## Revisit when

Measured runs show short visits sent back to the full visit often, or the engine's complexity switch can be evaluated again at each visit.
