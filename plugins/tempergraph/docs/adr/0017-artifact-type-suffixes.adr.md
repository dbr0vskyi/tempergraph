# ADR-0017 Every SDD artifact names its type in a double file suffix

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner asked that SDD artifacts use type suffixes (`*.spec.md`, `*.adr.md`, `*.plan.md`, `*.rsrch.md` and so on), to be enforced later by temperspec's rule files. temperspec scopes each rule file by path, so Claude Code loads a rule only when a matching file is in play. A folder alone is a weak scope: a plan placed in `specs/` by mistake would load the spec rule, and a checker would have to read front matter to know a file's type.

## Decision

We will name every artifact written for tempergraph `<name>.<type>.md`, with the types and folders in the [docs README](../README.md#file-naming): `.spec.md`, `.adr.md`, `.rsrch.md` in use, and `.plan.md`, `.task.md`, `.triage.md`, `.rule.md` reserved. Folder indexes stay `README.md`. temperspec's rule files will take this table as their path scopes.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Double suffix per type (chosen) | Type readable from the path; rule scopes like `**/*.spec.md` work anywhere; misplaced files are caught | Longer names; every link carries the suffix |
| Folder decides the type | Short names | A misplaced file gets the wrong rule; nested folders blur the scope |
| Front matter `type` only | One source of truth inside the file | A tool must open every file; path-scoped rules cannot use it |

## Decision rationale

| Criterion | Suffix | Folder | Front matter |
|---|---|---|---|
| Type known from the path | yes | partly | no |
| Path-scoped rule loading | yes | partly | no |
| Misplaced file detected | yes | no | yes |
| Name length | longer | short | short |

## Consequences

- Positive: temperspec's rules and checkers can select artifacts with one glob per type.
- Negative: the suffix and the spec header's `type` field could disagree. Mitigation: a checker compares them; the suffix names the artifact type and `type` names the spec kind within it (overview, contracts, component).
- Risk: a new artifact type is added without a suffix. Mitigation: the naming table is the only list; adding a type means adding a row.

## Revisit when

temperspec's rule files are written and choose a different scope mechanism.
