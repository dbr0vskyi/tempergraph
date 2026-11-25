# ADR-0040 Take script and hybrid steps, an attention verb and composable workflow packs; keep step outputs free-form

| | |
|---|---|
| Status | accepted |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner); decisions by the owner |
| Supersedes | — |

## Context

[R-012](../research/R-012-lessons-from-archon.rsrch.md) sorted Archon's features into adopt, adapt and avoid. On 2026-11-19 the owner chose among them, in the thread that asked for R-012:

- Take steps with scripts, and probably hybrid steps that combine a script and a model.
- Do not require JSON-schema step outputs. A step's output can be a Markdown file, a Confluence page and so on.
- Take one command that lists everything waiting on a person.
- Take composability.
- Have a detailed run log, adding it if it is missing.

This record fixes those choices so the specs can be changed in one pass. It is `accepted` because the owner made the decisions; the field-level design is still for the owning specs.

## Decision

We will:

1. Add a unit kind **`script`**. It runs a declared command or a workflow callable with no model session. Its gate holds a check and, optionally, a judge: a judge is allowed when the script produces content a person would read, such as a generated report. It is logged as a step attempt with no model call.
2. Let a model step declare **`before` and `after` scripts** (a *hybrid step*). These run in the same attempt, around the model session: `before` prepares inputs (fetch, export, render), and `after` transforms or publishes the session's output. A failed script fails the attempt and spends the retry budget, unless its result is marked environmental, which escalates as a check does. Scripts run through the same command rules as checks ([SEC](../specs/security.spec.md)). Their duration and exit code are recorded; they spend no model call.
3. Keep **step outputs free-form**. An artifact is declared by key and kind (file, URL, wiki page, tracker issue, pull request, and later more) and points to where the content lives. The judge reads it through its view set. No step output must be JSON. [R-011 G6](../research/R-011-design-gap-review.rsrch.md) narrows to the judge's own answer, whose shape the engine defines, and stays optional per executor.
4. Add a read-only, model-free verb **`tempergraph attention`**. It lists every item waiting on a person across all threads under the state root, oldest first. Each item gives the thread, workflow, unit and item, pause kind, age, a one-line reason and the exact command that answers it. Orchestration attention items (spec `orchestration` ORC, in PR 5) are included when present.
5. Make **composition** a first-class authoring rule. Reference workflows ship as small workflows in **workflow packs**. A pack is a Claude Code plugin with its skills, prompts and agents, plus the Python part tempergraph loads once the pack is registered. Each workflow runs on its own and is usable as a sub-workflow unit through its declared artifacts. Composition across runs is the orchestration of PR 5.
6. Treat the **detailed run log** as covered by the observability work in PR 7. The run log on `main` is a JSON-lines event log ([OBS-B7, OBS-B1, OBS-B8, OBS-B9](../specs/observability-and-cost.spec.md)). Its per-attempt detail view is the run detail document of spec `run-detail-document` RDD, built by `status --detail`. This record adds nothing there and checks only that `script` units and hybrid-step scripts appear in it as attempts with their check, duration and exit code.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Script and hybrid steps (chosen) | Non-model pipeline work (build, export, publish) needs no agent session; cheaper, deterministic, honest cost | Two more shapes to validate and draw |
| Checks only, script work wrapped in a model step | No new unit kind | Spends a model call on a shell command; non-experts learn to wrap scripts in prompts |
| Required JSON-schema outputs | Typed artifacts, easy parsing | Wrong fit for Markdown documents, wiki pages and tickets, which most delivery-pipeline outputs are |
| Free-form outputs addressed by kind and pointer (chosen) | Fits any artifact; the judge reads the real thing | Parsing stays per kind |
| Attention per thread via `status` only | Nothing new | A person with many runs must check each one |
| One attention verb (chosen) | One place to look; also the monitor's home view | One more read-only verb |

## Decision rationale

| Criterion | Chosen set | Alternatives |
|---|---|---|
| Fits any delivery-pipeline workflow, not only code | yes | JSON outputs do not |
| Keeps model spend where it adds value | yes (script units) | no (wrapped scripts) |
| Keeps a person's work in one place | yes (attention) | no |
| Owner's stated choice | yes | — |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| B1 | "Hybrid step" means scripts before and after one model session in the same attempt, not a script that calls a model itself. | CON-B4, CON-B5, CON-B6, CON-B7, CMP |
| B2 | A `script` unit may carry an optional judge; a model step must carry one, as today. | WFM-B8, WFM-B9, WFM-B10, WFM-B11 |
| B3 | Specs `run-detail-document` RDD and `orchestration` ORC land as designed in PRs 7 and 5; if they change, items 4 and 6 follow them. | CLI, OBS |

## Consequences

- Positive: delivery-pipeline steps that are not model work become cheap, deterministic units. A person has one inbox. Reference workflows stay small and reusable.
- Negative: `UnitSpec` gains a kind and `StepSpec` gains two optional fields. The renderer, compiler, diagram and run detail must show them.
- Risk: a script with broad side effects (publish to Confluence) runs before any judge sees the content. Mitigation: publishing belongs in `after` of a gated step or in the finalizer. Validation warns when a `before` script names a publish-like command, and SEC's rule that a command prefix is a capability grant applies ([R-011 G10](../research/R-011-design-gap-review.rsrch.md)).

## Revisit when

The first workflow pack outside coding is authored, or an executor offers typed outputs for document artifacts.
