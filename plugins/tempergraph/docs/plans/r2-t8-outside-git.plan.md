---
task: r2-t8
complexity: simple
specs: [plugins/tempergraph/docs/specs/workspace-and-concurrency.spec.md, plugins/tempergraph/docs/specs/check-contract-and-command-runs.spec.md]
---

# Plan: runs outside a git repository (R2-T8)

## 0. Hand-off

- Triage note: `plugins/tempergraph/docs/tasks/r2-t8.triage.md`
- Specs read: WSP (`workspace-and-concurrency`) §2.4, WTR (`worktree-mode`) §2.2, CHK (`check-contract-and-command-runs`) §2.1, GRD (`independence-guard`), CLI (`engine-cli`), ADR `outside-git-the-state-root-is-found-by-walk-up`, research `running-outside-a-git-repository`

## 1. Requirements

| Id | Criterion | Requirement | Spec |
|---|---|---|---|
| R1 | AC 1 | The state root outside git: declared, walk-up, start dir; never the home folder | WSP-B15 to WSP-B18 |
| R2 | AC 2 | `in_place` only | WSP-B15 to WSP-B18, WTR-B18 |
| R3 | AC 3 | The manifest fingerprint | WSP-B15 to WSP-B18, GRD |
| R4 | AC 4 | No `GitFacts`; changed paths from the manifest | CHK-B10 |
| R5 | AC 5 | `needs_git` refusals before spend | WSP-B15 to WSP-B18 |

## 2. Phases

### Phase 1: State root, manifest and refusals

Goal: R1 to R5.
Weight: light

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 1.1 | test | `plugins/tempergraph/engine/tests/test_outside_git.py` | WSP-AC5 | The root rule, a run in a plain folder, the manifest catching a judge's write, a check without git facts, every refusal |
| 1.2 | code | `plugins/tempergraph/engine/src/tempergraph/store/layout.py` | | The state root outside git |
| 1.3 | code | `plugins/tempergraph/engine/src/tempergraph/store/manifest.py` | | The manifest, its fingerprint and changed paths |
| 1.4 | code | `plugins/tempergraph/engine/src/tempergraph/git.py` | | The fingerprint falls back to the manifest |
| 1.5 | code | `plugins/tempergraph/engine/src/tempergraph/run/checks.py` | | `GitFacts` is `None`; `changed_paths` on the context |
| 1.6 | code | `plugins/tempergraph/engine/src/tempergraph/run/runner.py` | | The `needs_git` and size refusals at start |
| 1.7 | code | `plugins/tempergraph/engine/src/tempergraph/cli/main.py` | | `--state-root` |

## 3. Verification

- `cd plugins/tempergraph/engine && python -m pytest`
- `cd plugins/tempergraph/engine && ruff check src tests`
