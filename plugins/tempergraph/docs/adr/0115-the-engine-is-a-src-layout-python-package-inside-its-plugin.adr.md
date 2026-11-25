# ADR-0115 The engine is a src-layout Python package inside its plugin, with pytest, ruff and mypy

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (implementation session for the owner) |
| Supersedes | — (answers plan T1.1 "chooses the tooling") |

## Context

Release 1 starts code ([first-release plan](../plans/first-release.plan.md) T1.1). The plugin "carries a staged copy of the engine of the same version" that `install` and `update` put into a side-by-side environment ([UPD-B18, UPD-B19](../specs/engine-update.spec.md)), and the product may later be published as a Python package ([R-150 PKG](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md)). No document said where the source lives or which tools build and check it. The owner was away and asked for work to go on without questions.

## Decision

We will keep the engine's Python source at `plugins/tempergraph/engine/` as one setuptools project in the src layout (`src/tempergraph/`, tests in `tests/`), requiring Python 3.11 or newer, with LangGraph and its SQLite checkpointer as the only run-time dependencies. Tests use pytest; lint is ruff; types are mypy. The commands are recorded in the repository's `CLAUDE.md` and in each track plan's verification section. The distribution name is `tempergraph`, its console script `tempergraph` (`tempergraph.cli.main:entry`), which the shim of [UPD-B11, UPD-B12, UPD-B13](../specs/engine-update.spec.md) calls once T8.2 builds it.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **`plugins/tempergraph/engine/`, src layout (chosen)** | The staged engine ships inside the plugin folder Claude Code copies, as UPD needs; src layout stops tests importing the tree by accident; one later `pip install` path for a PyPI package | One more folder level |
| Repository root `src/` | Shorter paths | The engine would not travel with its plugin; the marketplace copies plugin folders only |
| Flat `plugins/tempergraph/tempergraph/` | Simple | Imports the source tree from the working directory in tests; mixes engine code with the plugin's own folders (`skills/`, `bin/`) |
| uv-only project | Fast installs | The owner's machine and CI may not have uv; UPD installs with `pip` ([SEC-B7](../specs/security.spec.md) Updater) |

## Decision rationale

| Criterion | Chosen | Root `src/` | Flat |
|---|---|---|---|
| Travels with the plugin (UPD-B18, UPD-B19) | yes | no | yes |
| Tests import the installed package only | yes | yes | no |
| Same install path for a later PyPI release | yes | yes | partly |

## Consequences

- Positive: the plugin folder is self-contained; the source-scan tests read one tree.
- Negative: commands are run from `plugins/tempergraph/engine/`.
- Risk: a workflow package imports engine internals. Mitigation: the private-import scan of [PKG-B15, PKG-B16, PKG-B17](../specs/workflow-package.spec.md) step 3.

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| S1 | Python 3.11 is the floor, as UPD-B18, UPD-B19 step 1 looks for "3.11+". | `requires-python` |
| S2 | LangGraph 1.2 and `langgraph-checkpoint-sqlite` 3.1, current on PyPI on 2026-11-20, keep the `interrupt` and `Command(resume=…)` interface [ADR-0002](0002-langgraph-graph-runtime.adr.md) relies on. | Compiler, durability |

## Revisit when

The engine is published to PyPI, or the plugin layout of Claude Code changes.
