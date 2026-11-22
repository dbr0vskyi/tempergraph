# ADR-0129 The engine names no workflow, and takes a workflow's request as a general capability

| | |
|---|---|
| Status | accepted |
| Date | 2026-11-21 |
| Authors | Claude (build session for the owner) |
| Supersedes | — |

Numbers 0121 to 0128 are held by the release 2 design, which is in review.

## Context

OVR-B10 says the engine core never names a workflow, and [WFM-AC4](../specs/02-workflow-model.spec.md) checks the engine's source for it. Building the first real workflow packages showed where that rule was thinner than it read:

- The source scan and the skill scans compared against a typed list of names. The list was already wrong: it missed one example and named a workflow that does not exist.
- The engine's test suite named the packages it loaded, and held one example's own scenarios.
- The engine's live-check list held one workflow's rows.
- Building a workflow package produces requests to the engine: a missing capability, a fix, an extension. Nothing said in what form such a request may land. The risk is an engine that grows a branch per workflow and stops being usable for the next one.

The owner's ruling (2026-11-21): workflows may ask for engine changes, extensions and fixes, and the engine still knows nothing about any specific workflow.

## Decision

We will keep every workflow outside the engine, and let a workflow's request into the engine only as a capability any workflow can use.

1. **No names.** No engine source file, engine skill, engine test or engine plan row names a workflow package or its workflow. The scans take the names from the packages found in the repository (`plugins/*/tempergraph.json`), in their hyphen and underscore spellings, and never from a typed list.
2. **The engine's suite finds packages; it does not know them.** It loads every package it finds, runs its generated tests, checks its outcome coverage and its marketplace entry, and runs the package's own tests. What one workflow does on its own paths is tested in that package's `tests/`. A package's live checks are in its own `docs/plans/`.
3. **A request is written in the package first.** The package states what it needs or works around in its own docs (its README's limits, its specs or a decision record), in its own words.
4. **The engine change is stated without the workflow.** It lands as a behaviour and acceptance criteria in the engine's specs that hold for any workflow, with a fixture workflow in the engine's tests. The engine reads declarations, never a workflow's name, folder or artifact names. Then the package uses the capability through `tempergraph.api`, its manifests or its settings, like any other package.
5. **The test for a request.** If the change cannot be said without naming the workflow, or only one workflow could ever use it, it belongs in the package (a check, a script, a prompt, a rule file), not in the engine.
6. **Docs.** An engine spec may use a workflow as an illustration in a scenario. No behaviour or acceptance criterion may hold only for a named workflow.

## Options considered

| Option | For | Against |
|---|---|---|
| **A request lands only as a general capability (chosen)** | The engine stays usable by the next workflow; one rule to check | A request costs a little more thought: it must be generalised first |
| Workflow-specific hooks inside the engine, behind a name check | Fastest for the first workflow | Every workflow adds a branch; the engine can no longer be tested without the workflows |
| Freeze the engine; workflows work around every limit | Engine stays small | The limits found by real workflows are the best evidence of what the engine lacks |

## Consequences

- `tests/test_workflow_packages.py` replaces the test that named the examples; the document workflow's scenarios moved into its package; the scans read the names from the repository.
- The engine's live-check list has one row for "every package's own list"; the delivery workflow's two rows moved into its package.
- Requests already taken this way: a step's claim about an earlier step is judged instead of pausing ([JDG-B9](../specs/05-judge-and-verdict.spec.md)); a newer outcome revision records the stamp's audit list anew ([WUP-B19](../specs/63-workflow-upgrade.spec.md)). Neither names a workflow.
- Known debt: two engine behaviours describe one workflow, PKG-B8 and AUT-B8. They are examples of the general rules beside them and move to that workflow's package when the engine's specs are migrated to the new spec format. Other specs name that workflow only inside scenarios.
- Limits a package has found and the engine has not yet answered stay listed in the package's README until an engine change, stated generally, removes them.
