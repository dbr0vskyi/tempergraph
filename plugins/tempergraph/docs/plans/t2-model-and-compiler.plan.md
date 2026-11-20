---
goal: Turn workflow data into a validated, rendered and compiled LangGraph graph with its diagram model
version: 1
date_created: 2026-11-20
last_updated: 2026-11-20
owner: dbr0vskyi
status: Completed
tags: [track-plan, tempergraph, T2]
tracker: none
spec: plugins/tempergraph/docs/specs/02-workflow-model.spec.md
spec_commit: bd6fc13
task_id: first-release-t2
---

# T2 Model and compiler

## 0. Hand-off

| Field | Value |
|---|---|
| Origin | [Release 1 plan](first-release.plan.md) track T2 |
| Specs | [WFM](../specs/02-workflow-model.spec.md), [PRM](../specs/04-prompt-rendering.spec.md), [VAL](../specs/76-step-values-and-template-keys.spec.md), [CMP](../specs/03-compiler-and-flow.spec.md), [LIF](../specs/18-lifecycle-and-evals.spec.md) (diagram model), with [PKG §2.4](../specs/88-workflow-package.spec.md) for the builders |
| Decisions | [ADR-0003](../adr/0003-workflows-as-data.adr.md), [ADR-0004](../adr/0004-four-nodes-per-unit.adr.md), [ADR-0106](../adr/0106-declare-workflows-with-typed-python-builders-and-text-in-files.adr.md) |

**Status: Completed.** Status pass: WFM, PRM, VAL, CMP and LIF are `ready-for-implementation`; none has an open question. Doc changes this track made: CON §2.1 gains `allow_commands`, `builtin`, `package_root`, the route and switch fields of `UnitSpec`, and the `default` prompt; PRM §2.1 and VAL §2.3 define `default` as `{request}` with the one input `request`; CMP §2 names the nodes and the human node's edges.

## 1. Requirements

| Req | Spec | Criteria | Phase |
|---|---|---|---|
| REQ-4 | WFM | AC-1 (one fixture and code per release-1 row), AC-4 (T1 scan), AC-5, AC-6; AC-2 and AC-3 land with the verbs in T6.1 | T2.1 |
| REQ-5 | PRM, VAL | PRM-AC-1 to AC-4 on the release-1 sections (item, event and self-check sections are release 2); VAL-B1, B2, the value table | T2.2 |
| REQ-6 | CMP | AC-1, AC-4 (diagram equals graph both ways), AC-6 for step, script, route and switch; AC-2, AC-3, AC-5 with the gate funnel in T5 | T2.3 |
| REQ-7 | LIF | Diagram model and digest (LIF-B3); `graph` verb in T6.1 | T2.4 |

## 2. Phases

### T2.1 Validation

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 2.1.1 | `engine/tests/test_api.py` | Test unknown keywords, `name`/`version` refused, lambdas and nested callables refused, callables kept by reference | PKG §2.4, PKG-B2 | yes | P1 | ✓ | 2026-11-20 |
| 2.1.2 | `engine/src/tempergraph/api.py` | Create the builders; kinds of later releases build with their fields in `extra` | PKG §2.4, ADR-0090 | | P1 | ✓ | 2026-11-20 |
| 2.1.3 | `engine/src/tempergraph/executors/capabilities.py` | Declare the four capability sets and tool maps as data | ECC §2.1–2.2, EAS, EMA, EAG §2.1–2.2, ADR-0091 | | P1 | ✓ | 2026-11-20 |
| 2.1.4 | `engine/tests/test_validate.py` | One fixture per release-1 row with its own code; later kinds and fields refuse `not_in_release`; the portable workflow valid on all four; WFM-B3 table; warnings stay warnings | WFM §2.1, §2.2, WFM-B3 | yes | P1 | ✓ | 2026-11-20 |
| 2.1.5 | `engine/src/tempergraph/model/validate.py`, `model/text.py`, `model/flow.py` | Create `validate`, `Finding`, text loading and the successor model | WFM §2, CMP §2 | | P1 | ✓ | 2026-11-20 |

### T2.2 Prompt rendering and values

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 2.2.1 | `engine/tests/test_template.py`, `tests/test_prompt.py` | Test the grammar and marker; the same prompt on four executors but the tools block; no self-assessment; absent sections; literal braces; retry told; value table; blocked and upstream lines | CON §2.2, PRM §2, VAL §2.1 | yes | P1 | ✓ | 2026-11-20 |
| 2.2.2 | `engine/src/tempergraph/render/template.py`, `render/prompt.py`, `render/output.py` | Create the parser and renderer, `render_step`, `parse_output` | PRM §2, VAL §2 | | P1 | ✓ | 2026-11-20 |

### T2.3 Compiler

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 2.3.1 | `engine/tests/test_compiler.py` | Test four nodes per unit, diagram equals graph both ways, the CMP-B6 edge table, retry as an edge, pause and resume of only the human node, `interrupt` first, the deleting reducer | CMP §2, CMP-B1, B2, B6, HUM-AC-1 | yes | P1 | ✓ | 2026-11-20 |
| 2.3.2 | `engine/src/tempergraph/compiler/graph.py`, `compiler/state.py` | Create `compile_workflow`, `UnitNodes`, `RunState` and `merge_units` | CMP §2, §2.3 | | P1 | ✓ | 2026-11-20 |

### T2.4 Diagram model

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 2.4.1 | `engine/src/tempergraph/model/diagram.py` | Create `diagram_model` with a shape digest and the Mermaid renderer | LIF §2, LIF-B3 | | P2 | ✓ | 2026-11-20 |
| 2.4.2 | `engine/tests/test_spec_budget.py` | Test the 400-line and 30 KB budget of every spec | docs README, OVR-AC-2 | yes | P2 | ✓ | 2026-11-20 |

## 6. Code verification

| Kind | Item |
|---|---|
| build, type, lint, test | As T1: `mypy`, `ruff check src tests`, `python -m pytest` |
| end-to-end | Skipped: the first run path is T6.1 |

## 7. Assumptions

| # | Assumption |
|---|---|
| A1 | A route is either a `route` unit (no session) or a route on a step or script unit, run by its gate after a pass; both forms appear in CMP-B6. |
| A2 | Validation reads text files relative to `package_root`; a spec built in test code uses inline text. |
| A3 | Validation never imports a concrete executor: it takes the declared capability sets, so the registry of T3 hands it the registered ones. |
