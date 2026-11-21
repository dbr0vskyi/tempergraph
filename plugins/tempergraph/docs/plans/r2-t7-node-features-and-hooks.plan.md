---
task: r2-t7
complexity: complex
specs: [plugins/tempergraph/docs/specs/73-ask-unit.spec.md, plugins/tempergraph/docs/specs/07-gate-and-human.spec.md, plugins/tempergraph/docs/specs/74-flow-extensions.spec.md, plugins/tempergraph/docs/specs/03-compiler-and-flow.spec.md, plugins/tempergraph/docs/specs/75-check-contract-and-command-runs.spec.md, plugins/tempergraph/docs/specs/90-run-outcome.spec.md, plugins/tempergraph/docs/specs/17-engine-cli.spec.md, plugins/tempergraph/docs/specs/30-run-events.spec.md]
---

# Plan: node features and lifecycle hooks (R2-T7)

## 0. Hand-off

- Triage note: `plugins/tempergraph/docs/tasks/r2-t7.triage.md`
- Specs read: ASK (73), HUM (07), FLX (74), CMP (03), WFM (02), CON (01), CHK (75), OUT (90), CLI (17) §2.2, EVT (30) §2.6, WSP (13), SEC (14)
- Why this design: every new kind keeps the four nodes of a unit, so the gate still only routes and the human node is still the one place a run pauses. An ask and a wait run nothing in their step node and go straight to the human node. A person's partial answers are kept in the answers file under the thread's folder, not in graph state, so a resume that does not complete the set never moves the graph and a crash loses nothing. A deadline, a fallback and a breakpoint add static edges only. Parallel branches are ordinary units started in one superstep; the block's own unit is the join, which runs only when every branch's gate has passed. Hooks are detached children started from the run log's writer, behind the same "never changes a run" rule as observers.

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | An ask declares questions or takes them from a list artifact; answers are validated by kind; the set completes over one or more resumes | ASK §2, ASK-B1 to B4 |
| R2 | AC 2 | A wait passes only on `event:<name>=<value>` its pure check accepts; `proceed` is refused | HUM-B4, WFM-B4 |
| R3 | AC 3 | `deadline_s` and `on_deadline` on a wait or ask; overdue in `status` and `attention`; `resume --apply-deadline` | FLX §2.3, FLX-B3 |
| R4 | AC 4 | `fallback` with `on_fail` and `on_budget_spent`; artifacts kept; `degraded` on the exit | FLX §2.4, FLX-B4 |
| R5 | AC 5 | `--pause-before <unit>` on `run` and `resume` | FLX §2.5, FLX-B5 |
| R6 | AC 6 | A `parallel` unit names two or more read-only branch units and joins on every pass; a branch that changes the tree fails; several pending gates are answered by unit | CMP §2.2, CMP-B4, HUM-B3, WSP §2.1 |
| R7 | AC 7 | `self-check <ticket>` runs the unit's check as a preview, at most `self_check_limit` times an attempt | CHK §2.5, CHK-B7 |
| R8 | AC 8 | Deliverables per path; a repository's declared commands; `GitFacts.pushed` | OUT §2.4, CHK §2.1, §2.2 |
| R9 | AC 9 | `hooks add|list|remove|test`; hooks run detached with a facts file | CLI §2.2, EVT §2.6 |

## 2. Phases

### Phase 1: Ask, wait, deadlines, fallback, breakpoints

Goal: R1 to R5.
Weight: heavy (many-tests)

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 1.1 | test | `plugins/tempergraph/engine/tests/test_ask_wait.py` | ASK-AC-1 to AC-3, HUM-B4, FLX-B3 | The ASK-B1 table, questions from a step, partial answers, placement refusals, the wait table, the deadline table |
| 1.2 | test | `plugins/tempergraph/engine/tests/test_fallback_breakpoint.py` | FLX-B4, B5, FLX-AC-1, AC-3, AC-4 | Fallback on a spent budget and a hard failure, the refusals of §2.6, a breakpoint with no session |
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
| 2.1 | test | `plugins/tempergraph/engine/tests/test_parallel.py` | CMP-B4, HUM-B3, WSP §2.1 | Join on every pass, a retrying branch, a stopped branch, a writing branch, two pending gates |
| 2.2 | code | `plugins/tempergraph/engine/src/tempergraph/compiler/graph.py` | | Fan-out edges and the join |
| 2.3 | code | `plugins/tempergraph/engine/src/tempergraph/model/flow.py` | | Branch and join targets |
| 2.4 | test | `plugins/tempergraph/engine/tests/test_self_check.py` | CHK-B7, CHK-AC-6 | Two previews, the limit, a foreign ticket, no state change |
| 2.5 | code | `plugins/tempergraph/engine/src/tempergraph/run/selfcheck.py` | | Tickets and the preview |

### Phase 3: Deliverables per path, repository commands, pushed

Goal: R8.
Weight: light

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 3.1 | test | `plugins/tempergraph/engine/tests/test_i2_26.py` | OUT §2.4, CHK §2.1, §2.2 | A deliverable off the path, a repository's command file, a pushed branch |
| 3.2 | code | `plugins/tempergraph/engine/src/tempergraph/run/outcome.py` | | Deliverables by path |
| 3.3 | code | `plugins/tempergraph/engine/src/tempergraph/run/commands.py` | | The repository's declared commands |
| 3.4 | code | `plugins/tempergraph/engine/src/tempergraph/run/checks.py` | | `pushed` |

### Phase 4: Lifecycle hooks

Goal: R9.
Weight: light

| Row | Kind | File | Proves | Change |
|---|---|---|---|---|
| 4.1 | test | `plugins/tempergraph/engine/tests/test_hooks.py` | CLI §2.2 | add, list, remove, test; the facts file; a failing hook |
| 4.2 | code | `plugins/tempergraph/engine/src/tempergraph/observe/hooks.py` | | The registry and the detached start |
| 4.3 | code | `plugins/tempergraph/engine/src/tempergraph/cli/main.py` | | The `hooks` verb |

## 3. Verification

- `cd plugins/tempergraph/engine && python -m pytest`
- `cd plugins/tempergraph/engine && ruff check src tests`
