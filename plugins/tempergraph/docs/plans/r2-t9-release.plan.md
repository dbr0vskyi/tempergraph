---
task: r2-t9
complexity: simple
specs: [plugins/tempergraph/docs/specs/61-version-metadata.spec.md, plugins/tempergraph/docs/specs/92-effort-ladder-and-model-escalation.spec.md]
---

# Plan: release 2 examples, guides and release files (R2-T9)

## 0. Hand-off

- Triage note: `plugins/tempergraph/docs/tasks/r2-t9.triage.md`
- Specs read: VER (61) §2.2, §2.3, LAD (92) §2.8, PKG (88), the four guides

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | Each example's draft step declares an effort ladder | LAD-B9 |
| R2 | AC 2 | The guides say what to do for every release 2 feature a person uses | — |
| R3 | AC 3 | Version `0.2.0` in the engine, the release record and the plugin manifest; `data/changelog/0.2.0.json` | VER-B8, VER-B9, LAD-AC6 |
| R4 | AC 4 | The packages' stamps | VER-B16 |

## 2. Phases

### Phase 1: Release files, examples and guides

Goal: R1 to R4.
Weight: light

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 1.1 | test | `plugins/tempergraph/engine/tests/test_stamp.py` | VER-AC6, LAD-AC6 | The release ships its changelog file, every entry is well formed, and the model-list entry carries its transform |
| 1.2 | code | `plugins/tempergraph/engine/src/tempergraph/data/changelog/0.2.0.json` | | The entries of release 2 |
| 1.3 | code | `plugins/tempergraph/engine/src/tempergraph/constants.py` | | `0.2.0`, with `release.json`, `pyproject.toml` and `plugin.json` |
| 1.4 | code | `plugins/release-notes-tgraph/workflow/release_notes/__init__.py` | | An effort ladder on `draft`; the same in `doc-refresh` |
| 1.5 | docs | `plugins/tempergraph/docs/guides/running-workflows.guide.md` | | The new pauses, hooks, outside git, carry; the other guides likewise |

## 3. Verification

- `cd plugins/tempergraph/engine && python -m pytest`
- `cd plugins/tempergraph/engine && ruff check src tests`
