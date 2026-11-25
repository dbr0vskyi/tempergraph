## What changes

<!-- One or two sentences. -->

Closes #

## Why

<!-- The issue says why; add only what the issue does not. -->

## Specs and docs

- [ ] The specs this change makes true are updated in this PR (truth ranking: acceptance criteria, specs and decision records, plans, code)
- [ ] The engine names no workflow (ADR-0129)
- [ ] New artifact files use their type suffix (`*.spec.md`, `*.adr.md`, `*.rsrch.md`, `*.plan.md`)

## Verification

<!-- Commands run from plugins/tempergraph/engine/ and their result. CI runs these three on every pull request; tick them when its checks pass. -->

- [ ] `python -m pytest`
- [ ] `ruff check src tests`
- [ ] `mypy`
- [ ] Live checks run (row ids), or "none needed"

## Left out

<!-- Anything the issue asked for that this PR does not do, each with the follow-up issue number. -->
