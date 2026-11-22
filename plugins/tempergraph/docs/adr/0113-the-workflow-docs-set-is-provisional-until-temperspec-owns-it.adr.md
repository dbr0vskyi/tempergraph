# ADR-0113 Every workflow package carries its own docs set, written by the scaffold, with provisional rules until temperspec owns them

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner wrote on 2026-11-20: "The workflow plugin should also have specs in the same way as the engine. Going further we will improve the format and rules based on temperspec, which is not created yet." The engine's docs follow research, decision, spec with type suffixes ([docs README](../README.md), [ADR-0017](0017-artifact-type-suffixes.adr.md)); the monitor plugin already keeps its own set.

## Decision

We will give every package a `docs/` folder in the engine's shape: an overview spec with one acceptance criterion per final criterion, one spec per unit with one acceptance criterion per unit criterion, decision records from the authoring decisions, and a sources research note. The scaffold writes them from the outcome, the blueprint and the authoring record. Criterion text lives only in `outcome.json`; a model-free `docs-drift` check compares ids and text digests. `tempergraph.json` `docs: provisional` names the rules in force; when temperspec ships rule files, the field names that rule set and the files stay where they are. Details: [PKG-B21, PKG-B22](../specs/88-workflow-package.spec.md).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Docs set from the scaffold, provisional rules, drift check (chosen) | Every workflow explains itself the way the engine does; temperspec can take over without moving files | Docs can go stale in prose; only ids and texts are checked |
| No docs; the outcome file and README are enough | Less to keep | Ignores the owner's ask; decisions are lost |
| Wait for temperspec's format | No rework | Workflows authored before then have nothing |

## Decision rationale

| Criterion | Provisional set | No docs | Wait |
|---|---|---|---|
| Meets the owner's ask now | yes | no | no |
| Rework when temperspec lands | rules only | — | none |
| Drift detectable | ids and text | — | — |

## Consequences

- Positive: acceptance criteria of a workflow are its outcome criteria, the same truth ranking as the engine's set.
- Negative: two places a person reads about a criterion. Mitigation: the docs quote the text and the check holds it equal.
- Risk: temperspec's rules differ a lot. Mitigation: `docs` names the rule set, so old and new packages are told apart.

## Assumptions

- "Specs in the same way" includes decision records and research notes, not specs alone.
