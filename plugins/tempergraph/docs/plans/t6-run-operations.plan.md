---
goal: Build run operations — the CLI's core verbs and exit codes, then settings, tool grants, feedback and reruns, and caller provenance
version: 1
date_created: 2026-11-20
last_updated: 2026-11-20
owner: dbr0vskyi
status: In progress
tags: [track-plan, tempergraph, T6]
tracker: none
spec: plugins/tempergraph/docs/specs/17-engine-cli.spec.md
spec_commit: 41ca415
task_id: first-release-t6
---

# T6 Run operations

## 0. Hand-off

| Field | Value |
|---|---|
| Origin | [Release 1 plan](first-release.plan.md) track T6 |
| Specs | [CLI](../specs/17-engine-cli.spec.md), [RST](../specs/80-run-settings-and-overrides.spec.md), [RRN](../specs/81-reruns-and-feedback.spec.md), [PRV](../specs/85-caller-provenance.spec.md) |

**Status: In progress.** T6.1 is built, so milestone M1 holds on stand-ins: a two-step workflow defined in Python test code runs end to end through `tempergraph run`, pauses with exit 3, and finishes through `tempergraph resume`. M1 on a signed-in `claude` waits for the owner's machine (T0.1). T6.2 to T6.5 are not started.

Status pass: CLI, RST, RRN and PRV are `ready-for-implementation`. RST, RRN and PRV have release 1 defaults for their open questions.

Doc changes this track made:
- CLI §2.1 adds `--task-id` and `--input` on `run`.
- CLI §2.1 gives the resolution rule for a workflow with no resolver, so the same request finds the same thread.
- CLI §2.1 gives the exit codes of `run --check` and says where machine output goes.

The catalog reads the home registry and loads each package by the first steps of PKG §2.3 (both manifests, the entry import from `workflow/`, the build). The rest of PKG §2.3 is T8.1: the private import name, the source scan, the interface level, `outcome.json` and the package rules.

## 1. Requirements

| Req | Spec | Criteria | Phase |
|---|---|---|---|
| REQ-20 | CLI | all, for the release 1 verbs of ADR-0090 (T6.1 here; the observability verbs in T7.4) | T6.1 |
| REQ-21 | RST | all but rows for orchestration, council, contest and switch-arm keys | T6.2, T6.3 |
| REQ-22 | RRN | all but §2.6 | T6.4 |
| REQ-23 | PRV | all; AC-6 for P-SUP-1 and P-SUP-2 | T6.5 |

## 2. Phases

### T6.1 Core verbs

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 6.1.1 | `engine/tests/test_cli.py` | M1 through the CLI; pause exit 3 and resume; `run --check` creates nothing and agrees with `run` on refusals; usage refusals exit 2; read-only verbs leave the state root unchanged (hash test); `executors` shows live facts as `not run`; exit codes and reserved words against the spec text | CLI §3, §6 | yes | P1 | ✓ | 2026-11-20 |
| 6.1.2 | `engine/src/tempergraph/catalog.py` | `Catalog`, `load_package` (PKG §2.3 steps 1, 3, 4), `from_registry`, `resolve_request` | CLI §2.1, CON §2.3, UPD §2.8 | | P1 | ✓ | 2026-11-20 |
| 6.1.3 | `engine/src/tempergraph/cli/main.py` | `run`, `run --check`, `resume`, `status`, `list`, `validate`, `executors [--probe]`, `facts`, `graph`, `wait`, `stop`, `worktree list` and `path`; reserved words; exit codes; `entry` for the `tempergraph` script | CLI §2, §4 | | P1 | ✓ | 2026-11-20 |
| 6.1.4 | `engine/src/tempergraph/cli/main.py` | Generated verb, option and exit code tables in the docs with a drift test (CLI §5) | CLI §5 | yes | P2 | ○ | |
| 6.1.5 | `engine/src/tempergraph/cli/main.py` | `attention` (CLI-B6, AC-5) | CLI-B6 | yes | P1 | ○ | |
| 6.1.6 | `engine/src/tempergraph/cli/main.py` | The other run options of CLI §2.1: executor and model overrides, timeouts, `--approve`, `--auto-reopen`, `--arm`, `--pause-before`, `--dry-run` | CLI §2.1, RST | yes | P1 | ○ | |

### T6.2 Settings

Not started: the settings catalog, layers and files, workflow settings and profiles, the snapshot on resume, `settings_resolved`, `config`.

### T6.3 Tool grants

Not started: `--grant`, `--allow-command`, and the tool-access pause that names them.

### T6.4 Feedback, rulings, rewind, rerun

`--feedback` and `--feedback-file` on `resume`, and `rewind:<unit>` decisions, work through the T5 human node. Not started: lasting rulings, `rerun` as a linked fork.

### T6.5 Caller provenance

The CLI records `{kind: person, via: cli}` on every mutating call. Not started: the classification of PRV §2.3, deciders and relay evidence.

## 3. Verification

From `plugins/tempergraph/engine/`: `python -m pytest`, `ruff check src tests` and `mypy` are clean. No test calls a model.
