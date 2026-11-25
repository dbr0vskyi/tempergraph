---
task: r2-t7
complexity: complex
specs: [plugins/tempergraph/docs/specs/ask-unit.spec.md, plugins/tempergraph/docs/specs/gate-and-human.spec.md, plugins/tempergraph/docs/specs/flow-extensions.spec.md, plugins/tempergraph/docs/specs/compiler-and-flow.spec.md, plugins/tempergraph/docs/specs/check-contract-and-command-runs.spec.md, plugins/tempergraph/docs/specs/run-outcome.spec.md, plugins/tempergraph/docs/specs/engine-cli.spec.md, plugins/tempergraph/docs/specs/run-events.spec.md]
---

# Plan: node features and lifecycle hooks (R2-T7)

## 0. Hand-off

- Triage note: `plugins/tempergraph/docs/tasks/r2-t7.triage.md`
- Specs read: ASK (`ask-unit`), HUM (`gate-and-human`), FLX (`flow-extensions`), CMP (`compiler-and-flow`), WFM (`workflow-model`), CON (`contracts`), CHK (`check-contract-and-command-runs`), OUT (`run-outcome`), CLI (`engine-cli`) §2.2, EVT (`run-events`) §2.6, WSP (`workspace-and-concurrency`), SEC (`security`)
- Why this design: every new kind keeps the four nodes of a unit, so the gate still only routes and the human node is still the one place a run pauses. An ask and a wait run nothing in their step node and go straight to the human node. A person's partial answers are kept in the answers file under the thread's folder, not in graph state, so a resume that does not complete the set never moves the graph and a crash loses nothing. A deadline, a fallback and a breakpoint add static edges only. Parallel branches are ordinary units started in one superstep; the block's own unit is the join, which runs only when every branch's gate has passed. Hooks are detached children started from the run log's writer, behind the same "never changes a run" rule as observers.

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | An ask declares questions or takes them from a list artifact; answers are validated by kind; the set completes over one or more resumes | ASK-B5 to ASK-B9, ASK-B1 to B4 |
| R2 | AC 2 | A wait passes only on `event:<name>=<value>` its pure check accepts; `proceed` is refused | HUM-B4, WFM-B4 |
| R3 | AC 3 | `deadline_s` and `on_deadline` on a wait or ask; overdue in `status` and `attention`; `resume --apply-deadline` | FLX-B8, FLX-B3 |
| R4 | AC 4 | `fallback` with `on_fail` and `on_budget_spent`; artifacts kept; `degraded` on the exit | FLX-B9, FLX-B4 |
| R5 | AC 5 | `--pause-before <unit>` on `run` and `resume` | FLX-B10, FLX-B5 |
| R6 | AC 6 | A `parallel` unit names two or more read-only branch units and joins on every pass; a branch that changes the tree fails; several pending gates are answered by unit | CMP-B10 to CMP-B16, CMP-B4, HUM-B3, WSP-B11, WSP-B12 |
| R7 | AC 7 | `self-check <ticket>` runs the unit's check as a preview, at most `self_check_limit` times an attempt | CHK-B17, CHK-B7 |
| R8 | AC 8 | Deliverables per path; a repository's declared commands; `GitFacts.pushed` | OUT-B15, OUT-B16, OUT-B17, CHK-B10, CHK-B11 |
| R9 | AC 9 | `hooks add|list|remove|test`; hooks run detached with a facts file | HOK-B1 to HOK-B6, EVT-B22, EVT-B23, EVT-B24 |

## 2. Phases

### Phase 1: Ask, wait, deadlines, fallback, breakpoints

Goal: R1 to R5.
Weight: heavy (many-tests)

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 1.1 | test | `plugins/tempergraph/engine/tests/test_ask_wait.py` | ASK-AC1 to AC-3, HUM-B4, FLX-B3 | The ASK-B1 table, questions from a step, partial answers, placement refusals, the wait table, the deadline table |
| 1.2 | test | `plugins/tempergraph/engine/tests/test_fallback_breakpoint.py` | FLX-B4, B5, FLX-AC1, AC-3, AC-4 | Fallback on a spent budget and a hard failure, the refusals of §2.6, a breakpoint with no session |
| 1.3 | code | `plugins/tempergraph/engine/src/tempergraph/contracts.py` | | `AskSpec`, `AskQuestion`, `WaitSpec` |
| 1.4 | code | `plugins/tempergraph/engine/src/tempergraph/run/asking.py` | | Questions, answer validation, the answers file |
| 1.5 | code | `plugins/tempergraph/engine/src/tempergraph/run/gate.py` | | The input and event pauses, the deadline, the fallback route |
| 1.6 | code | `plugins/tempergraph/engine/src/tempergraph/run/runner.py` | | Answers and events at a resume, `--apply-deadline`, breakpoints |
| 1.7 | code | `plugins/tempergraph/engine/src/tempergraph/model/validate.py` | | The kinds leave the later-release list; the refusals |
| 1.8 | code | `plugins/tempergraph/engine/src/tempergraph/cli/main.py` | | `--answers`, `--apply-deadline`, `--pause-before`, a repeatable `--decision` |

### Phase 2: Parallel branches and the check preview

Goal: R6 and R7.
Weight: heavy (many-tests)

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 2.1 | test | `plugins/tempergraph/engine/tests/test_parallel.py` | CMP-B4, HUM-B3, WSP-B11, WSP-B12 | Join on every pass, a retrying branch, a stopped branch, a writing branch, two pending gates |
| 2.2 | code | `plugins/tempergraph/engine/src/tempergraph/compiler/graph.py` | | Fan-out edges and the join |
| 2.3 | code | `plugins/tempergraph/engine/src/tempergraph/model/flow.py` | | Branch and join targets |
| 2.4 | test | `plugins/tempergraph/engine/tests/test_self_check.py` | CHK-B7, CHK-AC6 | Two previews, the limit, a foreign ticket, no state change |
| 2.5 | code | `plugins/tempergraph/engine/src/tempergraph/run/selfcheck.py` | | Tickets and the preview |

### Phase 3: Deliverables per path, repository commands, pushed

Goal: R8.
Weight: light

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 3.1 | test | `plugins/tempergraph/engine/tests/test_i2_26.py` | OUT-B15, OUT-B16, OUT-B17, CHK-B10, CHK-B11 | A deliverable off the path, a repository's command file, a pushed branch |
| 3.2 | code | `plugins/tempergraph/engine/src/tempergraph/run/outcome.py` | | Deliverables by path |
| 3.3 | code | `plugins/tempergraph/engine/src/tempergraph/run/commands.py` | | The repository's declared commands |
| 3.4 | code | `plugins/tempergraph/engine/src/tempergraph/run/checks.py` | | `pushed` |

### Phase 4: Lifecycle hooks

Goal: R9.
Weight: light

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 4.1 | test | `plugins/tempergraph/engine/tests/test_hooks.py` | HOK-B1 to HOK-B6 | add, list, remove, test; the facts file; a failing hook |
| 4.2 | code | `plugins/tempergraph/engine/src/tempergraph/observe/hooks.py` | | The registry and the detached start |
| 4.3 | code | `plugins/tempergraph/engine/src/tempergraph/cli/main.py` | | The `hooks` verb |

## 3. Verification

- `cd plugins/tempergraph/engine && python -m pytest`
- `cd plugins/tempergraph/engine && ruff check src tests`
