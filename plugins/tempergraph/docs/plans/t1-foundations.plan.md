---
goal: Build the foundations every later track uses — the engine package, the source rules, the shared types, launch rules and scrubbing, and the store layouts
version: 1
date_created: 2026-11-20
last_updated: 2026-11-20
owner: dbr0vskyi
status: Completed
tags: [track-plan, tempergraph, T1]
tracker: none
spec: plugins/tempergraph/docs/specs/01-contracts.spec.md
spec_commit: 14799ea
task_id: first-release-t1
---

# T1 Foundations

## 0. Hand-off

| Field | Value |
|---|---|
| Origin | [Release 1 plan](first-release.plan.md) track T1; owner's instruction of 2026-11-20 to start release 1 |
| Specs | [CON](../specs/01-contracts.spec.md), [SEC](../specs/14-security.spec.md), [LOS](../specs/33-local-observability-store.spec.md), read at `14799ea` |
| Decisions | [ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md), [ADR-0091](../adr/0091-first-release-ships-the-claude-executor-only.adr.md), [ADR-0115](../adr/0115-the-engine-is-a-src-layout-python-package-inside-its-plugin.adr.md) |

**Problem statement.** No code exists. Every track needs the same package, test runner, source rules, shared types, launch rules and store layout first.

**Status: Completed.** Status pass done: CON, SEC and LOS are `ready-for-implementation`, each open question has a release 1 default in its row.

## 1. Requirements

| Req | Spec | Criteria | Phase |
|---|---|---|---|
| REQ-1 | CON | CON-AC1 (one module, `contracts.py`), AC-4 (tolerant readers), AC-6 (exit-code drift test); AC-2, AC-3, AC-5 land with T2 and T3 where their code is | T1.2 |
| REQ-2 | SEC | SEC-AC1 (launch-site scan, grown as each site is built), scrubber; SEC-AC2 canary lands with T3 and T5 | T1.3 |
| REQ-3 | LOS | §2.1 and §2.2 layouts with manifests, §2.3 code log; LOS-AC1 tree comparison lands with T5.1 | T1.4 |
| REQ-0 | Plan | LangGraph confined to `tempergraph.compiler` and `tempergraph.durability`; EXI-AC1 and WFM-AC4 source scans | T1.1 |

## 2. Phases

### T1.1 Repository skeleton and rules

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 1.1.1 | `plugins/tempergraph/engine/pyproject.toml` | Create the `tempergraph` package (src layout, Python ≥ 3.11, `langgraph`, `langgraph-checkpoint-sqlite`, dev extras pytest, ruff, mypy) | ADR-0115 | | P1 | ✓ | 2026-11-20 |
| 1.1.2 | `engine/tests/test_source_rules.py` | Test LangGraph confinement, sanctioned launch sites, no `shell=True`, concrete executors only in `tempergraph.executors`, no shipped workflow named | SEC-B7, EXI-AC1, WFM-AC4 | yes | P1 | ✓ | 2026-11-20 |
| 1.1.3 | `CLAUDE.md` | Record the build, lint, type and test commands | — | | P1 | ✓ | 2026-11-20 |

### T1.2 Shared types

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 1.2.1 | `engine/tests/test_contract_tables.py` | Test the exit-code table of CON-B12, CON-B13 against `ExitCode`; test the docs type-suffix rule | CON-B12, CON-B13, ADR-0017 | yes | P1 | ✓ | 2026-11-20 |
| 1.2.2 | `engine/src/tempergraph/constants.py` | Create `ExitCode`, schema versions, reserved verbs, executor names, release number | CON-B12, CON-B13, CON-B14, CON-B1, CON-B15, CLI-B2 | | P1 | ✓ | 2026-11-20 |
| 1.2.3 | `engine/src/tempergraph/contracts.py` | Create every CON-B4, CON-B5, CON-B6, CON-B7, CON-B8, CON-B9, CON-B3, CON-B11, SSN-B1 to SSN-B6, SSN-B7, SSN-B8, SSN-B9, SSN-B10, CON-B12, CON-B13, CON-B14, CON-B1, CON-B15, AUD (moved), RST (moved), PRV (moved), PKG, OUT (moved) type used by release 1 as dataclasses | CON-B3 to CON-B15, SSN-B1 to SSN-B10 | | P1 | ✓ | 2026-11-20 |
| 1.2.4 | `engine/tests/test_docs.py` | Test unknown key, newer schema, unknown event kind counted, owner-only writes | CON-B14, CON-B1, CON-B15, CON-B1 | yes | P1 | ✓ | 2026-11-20 |
| 1.2.5 | `engine/src/tempergraph/docs.py` | Create `read_json`, `write_json` (atomic, 0600), `append_jsonl`, `iter_jsonl`, `NewerSchema` | CON-B14, CON-B1, CON-B15 | | P1 | ✓ | 2026-11-20 |

### T1.3 Launch rules and scrubbing

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 1.3.1 | `engine/tests/test_scrub.py` | Test the scrubber's secret shapes, `clip`, `head_tail` and its marker | SEC-B8 to SEC-B11, JDG-B3, JDG-B13, JDG-B11 | yes | P1 | ✓ | 2026-11-20 |
| 1.3.2 | `engine/src/tempergraph/security/scrub.py` | Create `scrub` (fixed word on a raise), `clip`, `head_tail` | SEC-B8 to SEC-B11, SEC-B7, SEC-B8 | | P1 | ✓ | 2026-11-20 |
| 1.3.3 | `engine/src/tempergraph/security/launch.py` | Create `SANCTIONED_SITES` and `has_shell_metacharacter` | SEC-B5, SEC-B6, SEC-B7 | | P1 | ✓ | 2026-11-20 |
| 1.3.4 | `engine/src/tempergraph/git.py` | Create the git reader site: list argv, safe refs, main checkout, fingerprint, changed paths | SEC-B4, WSP-B8, WSP-B9, WSP-B11, GRD-B3 | | P1 | ✓ | 2026-11-20 |

### T1.4 Store layouts and code log

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 1.4.1 | `engine/tests/test_layout.py` | Test the state root from a nested worktree, its own `.gitignore`, owner-only mode, newer layout refused, home `machine.json`, session keys | LOS-B7, LOS-B8, LOS-B9, LOS-B10, LOS-B11, LOS-B4, WSP-AC1, EVT-B8, EVT-B9 | yes | P1 | ✓ | 2026-11-20 |
| 1.4.2 | `engine/src/tempergraph/store/layout.py` | Create path helpers (read-only), `ensure_state_root`, `ensure_home`, `session_key` | LOS-B7, LOS-B8, LOS-B9, LOS-B10, LOS-B11 | | P1 | ✓ | 2026-11-20 |
| 1.4.3 | `engine/src/tempergraph/store/codelog.py` | Create the JSON-lines code log handler, scrubbed, per process per day | LOS-B13 | | P2 | ✓ | 2026-11-20 |

## 4. Dependencies

`langgraph` 1.2 and `langgraph-checkpoint-sqlite` 3.1 (current releases on PyPI on 2026-11-20); dev: `pytest`, `ruff`, `mypy`.

## 6. Code verification

| Kind | Item |
|---|---|
| build | `pip install -e 'plugins/tempergraph/engine[dev]'` |
| type | `mypy` (from `plugins/tempergraph/engine`) |
| lint | `ruff check src tests` |
| test | `python -m pytest` |
| end-to-end | Skipped: T1 has no run path; M1 after T6.1 is the first |
| release | Not in this track |

## 7. Assumptions

| # | Assumption |
|---|---|
| A1 | The engine's Python source is the plugin's staged engine, at `plugins/tempergraph/engine/` (ADR-0115). |
| A2 | Launch sites are added to `SANCTIONED_SITES` in the phase that builds them, so the scan is exact at every commit. |
