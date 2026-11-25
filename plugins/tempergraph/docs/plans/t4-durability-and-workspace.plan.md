---
goal: Build durability and the workspace — the SQLite checkpoint, thread states, the run lock, aliases, status and wait, the release-1 worktree mode, and stop requests
version: 1
date_created: 2026-11-20
last_updated: 2026-11-20
owner: dbr0vskyi
status: Completed
tags: [track-plan, tempergraph, T4]
tracker: none
spec: plugins/tempergraph/docs/specs/durability-and-resume.spec.md
spec_commit: d60fbd5
task_id: first-release-t4
---

# T4 Durability and workspace

## 0. Hand-off

| Field | Value |
|---|---|
| Origin | [Release 1 plan](first-release.plan.md) track T4 |
| Specs | [DUR](../specs/durability-and-resume.spec.md), [WSP](../specs/workspace-and-concurrency.spec.md), [RCT](../specs/run-control.spec.md), the release-1 part of [WTR](../specs/worktree-mode.spec.md) |
| Decisions | [ADR-0014](../adr/0014-sqlite-checkpointer.adr.md), [ADR-0028](../adr/0028-stop-verb-as-the-only-observer-control.adr.md), [ADR-0100](../adr/0100-the-engine-owns-the-run-worktree-executor-worktrees-are-not-used.adr.md), [ADR-0101](../adr/0101-one-workspace-setting-with-an-auto-default.adr.md) |

**Status: Completed** for the parts that need no gate funnel. Status pass: DUR, WSP, RCT and WTR are `ready-for-implementation`; RCT and WTR's open questions have release 1 defaults. Doc changes this track made:
- DUR-B4 says how an observer opens the store.
- DUR-B5 gives wait's exit codes.
- DUR-B8 names the alias file and its form.
- WTR-B18 now reads `side_effects: workspace`. It said `local`, which is no SCR value.
- CON's `WorktreeDecl` in code now carries every WTR-B19 field.

The run-path behaviours land where their code is: `start` and `resume`, DUR-B1, B2 and B7, RCT-B1 and AC-3 with the runner in T5 and T6.1. DUR-AC4 needs a fixture from an earlier release, and none exists yet, so it starts with release 1's own fixture at T6.1. RCT-B4 (batch) is release 3.

## 1. Requirements

| Req | Spec | Criteria | Phase |
|---|---|---|---|
| REQ-10 | DUR | AC-1 (state rows), AC-2, AC-3; B3, B4, B5, B8 | T4.1, T4.2 |
| REQ-11 | WSP, WTR | WSP-AC1, B1, B2, B3; WTR-B18, WTR-B20, WTR-B21 `head`, §2.6 start, resume and release, `worktree list` and `path` data | T4.3 |
| REQ-12 | RCT | B2, B3, §4, AC-2 | T4.4 |

## 2. Phases

### T4.1 Checkpoints and resume

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 4.1.1 | `engine/tests/test_durability.py` | Test every thread state, running over a held lock, 16 writer processes, the lock probe, aliases | DUR-B9, B3, B8 | yes | P1 | ✓ | 2026-11-20 |
| 4.1.2 | `engine/src/tempergraph/durability/checkpoint.py` | Create `open_saver`, `open_readonly`, `thread_ids`, `observer_graph`, `snapshot`, `classify_snapshot` | DUR-B9, DUR-B11, B3, B4 | | P1 | ✓ | 2026-11-20 |
| 4.1.3 | `engine/src/tempergraph/durability/lock.py`, `alias.py` | Create `RunLock`, `is_held`, alias `claim` and `resolve` | WSP-B8, WSP-B9, WSP-B11, DUR-B8 | | P1 | ✓ | 2026-11-20 |

### T4.2 Status and wait

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 4.2.1 | `engine/tests/test_durability.py` | Test the status rows, selection by alias, wait outcomes with a replaced clock, nothing written | DUR-B11, B4, B5, AC-3 | yes | P1 | ✓ | 2026-11-20 |
| 4.2.2 | `engine/src/tempergraph/durability/status.py` | Create `classify`, `status`, `select`, `wait` | DUR-B11 | | P1 | ✓ | 2026-11-20 |

### T4.3 Workspace

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 4.3.1 | `engine/tests/test_workspace.py` | Test flat names, `auto` rows, the lifecycle with real git worktrees, a failed bootstrap, the interpreter order | WTR-B18, WTR-B19, WTR-B20, WTR-B21, WTR-B22, WSP-B1–B3 | yes | P1 | ✓ | 2026-11-20 |
| 4.3.2 | `engine/src/tempergraph/workspace.py` | Create `resolve_workspace`, `check_plan`, `prepare_workspace`, `bootstrap`, `attach_workspace`, `release_workspace`, `list_worktrees`, `worktree_path`, `python_for` | WTR-B17 to WTR-B27, WSP | | P1 | ✓ | 2026-11-20 |

### T4.4 Stop

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 4.4.1 | `engine/tests/test_control.py` | Test not-live refusal, the stronger mode, an unparsable request, `--now` ending a real tree within 15 s | RCT-B2, B3, §4, AC-2 | yes | P1 | ✓ | 2026-11-20 |
| 4.4.2 | `engine/src/tempergraph/durability/control.py` | Create `request_stop`, `take_stop`, `StopWatcher` | RCT-B6, RCT-B7 | | P1 | ✓ | 2026-11-20 |

## 6. Code verification

| Kind | Item |
|---|---|
| type, lint, test | `mypy`, `ruff check src tests`, `python -m pytest` |
| end-to-end | Skipped: no run path until T6.1 |

## 7. Assumptions

| # | Assumption |
|---|---|
| A1 | Thread states are read through a graph compiled with node bodies that never run, so classification uses LangGraph's own view of pending nodes and interrupts rather than the checkpoint's internal channel names. |
| A2 | `stopped` and `finished` both have no pending node; `finished` is told by the finalizer's `finalized` state channel. |
| A3 | Setup commands of a worktree bootstrap run through a command runner passed in; T5's runner (CHK-B12, CHK-B13) is that runner. |
| A4 | Release 1 never removes a worktree: `release_workspace` unlocks it and keeps it (`cleanup: on_finish` is release 2). |
