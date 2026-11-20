---
goal: Build the executor layer — registry, binding table, preflight, the session launcher, normalized events, the conformance suite with stand-ins, and the Claude Code executor
version: 1
date_created: 2026-11-20
last_updated: 2026-11-20
owner: dbr0vskyi
status: Completed
tags: [track-plan, tempergraph, T3]
tracker: none
spec: plugins/tempergraph/docs/specs/10-executor-interface.spec.md
spec_commit: be8992f
task_id: first-release-t3
---

# T3 Executors

## 0. Hand-off

| Field | Value |
|---|---|
| Origin | [Release 1 plan](first-release.plan.md) track T3 |
| Specs | [EXI](../specs/10-executor-interface.spec.md), [ECC](../specs/11-executor-claude-code.spec.md), with [SEC §2.2, §2.4](../specs/14-security.spec.md) and [CON §2.6, §2.7](../specs/01-contracts.spec.md) |
| Decisions | [ADR-0006](../adr/0006-executors-as-capability-adapters.adr.md), [ADR-0009](../adr/0009-normalized-session-event-stream.adr.md), [ADR-0010](../adr/0010-judge-isolation-per-executor.adr.md), [ADR-0091](../adr/0091-first-release-ships-the-claude-executor-only.adr.md) |

**Status: Completed** for the offline build; ECC-AC-5 (probe table filled) waits on the owner's machine. Status pass: EXI and ECC are `ready-for-implementation`; each open question has a release 1 default in its row. Doc changes this track made: EXI §2.1 names `ProbeReport`; EXI §2.2 fixes the binding file at `<home>/config/bindings.json` with built-in `claude` tiers; EXI §2.3 adds the 30 s prompt window and puts probes and host speed at the launcher; EXI-B14 states the walk bound and the 3 s floor; EXI-AC-6 leaves `slow_host` to the gate; ECC §2.6 gains the `connection` and `out_of_memory` rows and the provisional budget subtype; ECC §2.7 records the model-free checks on 2.1.329; SEC §2.2 and §2.4 name the probe site and the credentials path.

## 1. Requirements

| Req | Spec | Criteria | Phase |
|---|---|---|---|
| REQ-8 | EXI | AC-1 (T1 scan), AC-2, AC-3, AC-4 (POSIX), AC-5, AC-6, AC-7 with the guard in T5.4, AC-8, AC-9 (four capability sets against the recorded stand-in), AC-10 | T3.1–T3.3 |
| REQ-9 | ECC | AC-1 to AC-4; AC-5 waits on the owner's probes; judge MCP views later (`judge_mcp = false`) | T3.4 |

## 2. Phases

### T3.1 Registry and preflight

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 3.1.1 | `engine/tests/test_preflight.py` | Test registry order, unknown and non-constant names, judge selection order, each EXI-B1 refusal, nothing created | EXI §2.1, §2.4, B1, B10, B12 | yes | P1 | ✓ | 2026-11-20 |
| 3.1.2 | `engine/src/tempergraph/contracts.py` | Add `Executor`, `ProbeReport`, `ViewSet`, `Deferred` | CON §2.6, GRD §2 | | P1 | ✓ | 2026-11-20 |
| 3.1.3 | `engine/src/tempergraph/executors/registry.py` | Create `Registry`, `UnknownExecutor`, `judge_executor`, `default_registry` (`claude` only) | EXI §2.1, §2.4 | | P1 | ✓ | 2026-11-20 |
| 3.1.4 | `engine/src/tempergraph/executors/binding.py` | Create the binding table reader and alias lookup | EXI §2.2, SEC-B1 | | P1 | ✓ | 2026-11-20 |
| 3.1.5 | `engine/src/tempergraph/executors/preflight.py` | Create `preflight`: validation, probes, qualified aliases, judge selection, enforcement, deferred MCP views | EXI-B1 | | P1 | ✓ | 2026-11-20 |

### T3.2 Session launcher

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 3.2.1 | `engine/tests/test_launcher.py` | Test stdin delivery and canary, caller variables, raw files, timeout and signal tree kill with a grandchild, both stop rows, idle table and floor, spawn failure, prompt window, prompt gap and host speed with a replaced clock | EXI-B2–B5, B13–B15 | yes | P1 | ✓ | 2026-11-20 |
| 3.2.2 | `engine/src/tempergraph/executors/launcher.py` | Create `LaunchSpec`, `RawOutcome`, `StopRequest`, `idle_action`, `launch`, `run_probe`, `host_speed`; add the site to `SANCTIONED_SITES` | EXI §2.3, SEC §2.2 | | P1 | ✓ | 2026-11-20 |

### T3.3 Normalized events and conformance

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 3.3.1 | `engine/tests/test_conformance.py`, `engine/tests/fixtures/standin_cli.py` | Conformance suite over the four declared sets: stdin, list argv, tree kill, no raise on each cause, unknown usage, tools in order, cost only where declared; the recorded CLI stand-in | EXI-B11, AC-6, AC-9 | yes | P1 | ✓ | 2026-11-20 |
| 3.3.2 | `engine/src/tempergraph/executors/session.py` | Create `summarize`, `process_cause`, `build_result` | EXI-B6, B7, CON §2.6 | | P1 | ✓ | 2026-11-20 |
| 3.3.3 | `engine/src/tempergraph/executors/standins.py` | Create `ScriptedExecutor`, `standin`, `answer` for the engine's offline tests | ADR-0091 item 2 | | P1 | ✓ | 2026-11-20 |

### T3.4 Claude Code executor

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 3.4.1 | `engine/tests/test_claude_executor.py`, `engine/tests/fixtures/streams.py` | Test argv shapes (ECC-B1, B2, AC-4), binding lookups, every §2.5 row, every §2.6 row and the ECC-B5 table, probe words, step and judge runs through a fake `claude` on PATH | ECC §2–§3 | yes | P1 | ✓ | 2026-11-20 |
| 3.4.2 | `engine/src/tempergraph/executors/claude.py` | Create `step_argv`, `judge_argv`, `parse_line`, `classify`, `ClaudeExecutor` | ECC | | P1 | ✓ | 2026-11-20 |
| 3.4.3 | ECC §2.7 | Run P-CC-2, 5, 6, 9 on the owner's machine and fill the table | ECC-AC-5 | | P1 | | |

## 4. Dependencies

No new package. The tests start the engine's own interpreter as the CLI stand-in.

## 6. Code verification

| Kind | Item |
|---|---|
| type | `mypy` |
| lint | `ruff check src tests` |
| test | `python -m pytest` (about 20 s of the suite is the conformance runs) |
| end-to-end | Skipped: no run path until T6.1 |
| live | Not run here; see A3 |

## 7. Assumptions

| # | Assumption |
|---|---|
| A1 | Windows tree kill uses `taskkill /F /T` until a job object is added; EXI-AC-4 is tested on POSIX only in this track. |
| A2 | `error_max_budget_usd`, `connection_error` and `network_error` are the CLI's words for a budget stop and a network retry; P-CC-3 and real stalls confirm or replace them. A wrong word costs a misclassified failure, not a safety property. |
| A3 | The live probes are not run in the build container: it is a hosted Claude Code session, and a nested session would inherit its environment. They wait on the owner's machine (EC-3 of the release plan). |
| A4 | Judges keep `isolates_user_config = false` and launch with `--setting-sources ""` until P-CC-1 passes; the guard in T5 is the backstop. |
