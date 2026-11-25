# ADR-0106 Declare workflows with typed Python builders; keep text in files

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

`load` imports a declaration module, but nothing said what it holds ([R-011](../research/R-011-design-gap-review.rsrch.md) G2). Code-first engines such as LangGraph declare a workflow in Python; Archon-style tools use YAML ([R-012](../research/R-012-lessons-from-archon.rsrch.md)). The upgrade needs typed detect rules over field paths and symbols ([VER-B11](../specs/version-metadata.spec.md)); checks, routes and resolvers are code in any case.

## Decision

We will declare a workflow with typed builders from the one public module `tempergraph.api`, each producing one contract type and refusing unknown arguments. Callables are passed as module-level functions and recorded by reference. Prompts, briefs and stances live in files referenced by path; criteria live in `outcome.json` ([ADR-0107](0107-the-good-outcome-is-one-data-file-of-final-and-intermediate-outcomes.adr.md)). Details: [PKG-B19, PKG-B20](../specs/workflow-package.spec.md).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Typed Python builders, text in files (chosen) | Errors at the misspelt field; callables are real functions; the later Python package exposes the same surface; text editable by the loop and audit | Declaration edits by a model touch code |
| YAML or JSON for the whole spec, callables by string | Easy to diff and transform | A second schema to maintain; callable refs checked late; no editor help |
| Plain dicts in Python | No API to keep | Misspellings become defaults; no typed surface |

## Decision rationale

| Criterion | Builders | YAML | Dicts |
|---|---|---|---|
| Misspelt field caught at build | yes | with a schema | no |
| Callables importable by the check worker | yes | by string | yes |
| Upgrade detect rules | symbols and fields | fields | fields only |
| Stable surface for a later Python package | yes | no | no |

## Consequences

- Positive: the scaffold writes ordinary Python a person can read; transforms run on the parsed spec and the syntax tree.
- Negative: a non-Python reader of a package must load it through the engine (`list`, `validate --json`).
- Risk: builder signatures become a compatibility surface. Mitigation: they are surface `declaration` in the changelog ([VER-B10](../specs/version-metadata.spec.md)).

## Assumptions

- Authors rarely hand-edit the declaration; the scaffold writes it.
