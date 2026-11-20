# ADR-0070 One catalog of run settings, resolved over fixed layers from flags to engine defaults

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner asked whether a person can override a workflow's configuration in every variation: models for steps and judges, retry budgets, per-step time limits, cost caps and the rest. [R-070](../research/R-070-config-overrides-and-reruns-gaps.rsrch.md) finds a layered, recorded order for models, executors and timeouts only (F1 to F3). Budgets other than the run cost cap, session options, subagent models, the members, chair and slots of the PR 10 units, deadlines and workflow-specific switches have no operator layer; there is no machine or project file, no profile, no single record of the effective configuration, and overrides aimed at a missing unit are not refused (F4 to F13).

## Decision

We will define every overridable value as a key in one engine catalog, `<scope>.<name>`, with a type, a range, the scopes it applies to and an engine default, and resolve every key over the same nine layers, highest first: flags (including orchestration and batch options), chosen profiles, the project file's overrides, the user file's overrides, the unit's own workflow field, the workflow default, the project file's defaults, the user file's defaults, the engine default ([RST §2.3](../specs/80-run-settings-and-overrides.spec.md)). Resolution is layer-major, and inside a layer the narrowest scope wins. Workflows may declare typed settings and named profiles. One `settings_resolved` record per run segment and a read-only `config show` verb carry every value with its source.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| One catalog, fixed layers (chosen) | One rule for every key; validation can refuse a misaimed or out-of-range override; a preview equals the run | A catalog to keep in step with new fields |
| A free-form override map (Hydra-style dotted paths into the workflow) | Anything can be changed with no catalog | Nothing is validated; it reaches criteria, prompts and tools ([ADR-0071](0071-overrides-never-change-what-verifies-the-work.adr.md)) |
| A flag per key, as today | No new concept | Dozens of flags; no files, no profiles, no member or slot scope; each key picks its own order |
| Environment variables as a layer | Easy in CI | Invisible in the record; [EXI §2.1](../specs/10-executor-interface.spec.md) forbids environment selection of executors |

## Decision rationale

| Criterion | Catalog | Free-form | Flags only | Environment |
|---|---|---|---|---|
| Every variation the owner listed | yes | yes | partly | partly |
| Refused before spend when misaimed | yes | no | partly | no |
| Verification surface protected | yes | no | yes | yes |
| Machine-wide defaults | yes | yes | no | yes |
| Effective value recorded with its source | yes | partly | partly | no |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | An operator's per-machine file should beat the workflow's own value when it says `overrides`, and sit below it when it says `defaults`; both are needed (a slow host's limits; a team's model choice). | RST §2.3 |
| A2 | A file committed in the repository is not a layer in the first release, so a pull request cannot raise an operator's caps. | RST §5 |
| A3 | Profiles are used whole, never merged across files, so a profile means the same values wherever it is found first. | RST §2.4 |

## Consequences

- Positive: every variation of the owner's list, and temperspec's operator levers, has one spelling and one order; the improvement loop can tell an operator's override from a workflow's own value.
- Negative: the existing flags become spellings of `--set`; docs and tests generated from the catalog must stay in step ([CLI §5](../specs/17-engine-cli.spec.md)).
- Risk: layer-major order surprises an operator whose user file overrides a step's declared value. Mitigation: `config show` prints the winning layer and every shadowed one.

## Revisit when

A team needs a shared repository file or an organisation needs a managed ceiling above flags (RST open questions).
