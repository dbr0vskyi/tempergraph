---
goal: Turn workflow data into a validated, rendered and compiled LangGraph graph with its diagram model
version: 1
date_created: 2026-11-20
last_updated: 2026-11-20
owner: dbr0vskyi
status: Completed
tags: [track-plan, tempergraph, T2]
tracker: none
spec: plugins/tempergraph/docs/specs/workflow-model.spec.md
spec_commit: bd6fc13
task_id: first-release-t2
---

# T2 Model and compiler

## 0. Hand-off

| Field | Value |
|---|---|
| Origin | [Release 1 plan](first-release.plan.md) track T2 |
| Specs | [WFM](../specs/workflow-model.spec.md), [PRM](../specs/prompt-rendering.spec.md), [VAL](../specs/step-values-and-template-keys.spec.md), [CMP](../specs/compiler-and-flow.spec.md), [LIF](../specs/lifecycle-and-evals.spec.md) (diagram model), with [PKG-B19, PKG-B20](../specs/workflow-package.spec.md) for the builders |
| Decisions | [ADR `workflows-as-data`](../adr/workflows-as-data.adr.md), [ADR `four-nodes-per-unit`](../adr/four-nodes-per-unit.adr.md), [ADR `declare-workflows-with-typed-python-builders-and-text-in-files`](../adr/declare-workflows-with-typed-python-builders-and-text-in-files.adr.md) |

**Status: Completed.** Status pass: WFM, PRM, VAL, CMP and LIF are `ready-for-implementation`; none has an open question. Doc changes this track made: CON-B4, CON-B5, CON-B6, CON-B7 gains `allow_commands`, `builtin`, `package_root`, the route and switch fields of `UnitSpec`, and the `default` prompt; PRM-B6 and VAL-B8 define `default` as `{request}` with the one input `request`; CMP-B8 names the nodes and the human node's edges.

## 1. Requirements

| Req | Spec | Criteria | Phase |
|---|---|---|---|
| REQ-4 | WFM | AC-1 (one fixture and code per release-1 row), AC-4 (T1 scan), AC-5, AC-6; AC-2 and AC-3 land with the verbs in T6.1 | T2.1 |
| REQ-5 | PRM, VAL | PRM-AC1 to AC-4 on the release-1 sections (item, event and self-check sections are release 2); VAL-B1, B2, the value table | T2.2 |
| REQ-6 | CMP | AC-1, AC-4 (diagram equals graph both ways), AC-6 for step, script, route and switch; AC-2, AC-3, AC-5 with the gate funnel in T5 | T2.3 |
| REQ-7 | LIF | Diagram model and digest (LIF-B3); `graph` verb in T6.1 | T2.4 |

## 2. Phases

### T2.1 Validation

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 2.1.1 | `engine/tests/test_api.py` | Test unknown keywords, `name`/`version` refused, lambdas and nested callables refused, callables kept by reference | PKG-B19, PKG-B20, PKG-B2 | yes | P1 | ✓ | 2026-11-20 |
| 2.1.2 | `engine/src/tempergraph/api.py` | Create the builders; kinds of later releases build with their fields in `extra` | PKG-B19, PKG-B20, ADR `first-release-is-simple-trusted-workflows-on-one-machine` | | P1 | ✓ | 2026-11-20 |
| 2.1.3 | `engine/src/tempergraph/executors/capabilities.py` | Declare the four capability sets and tool maps as data | ECC-B6, ECC-B7, EAS, EMA, EAG-B8, EAG-B9, ADR `first-release-ships-the-claude-executor-only` | | P1 | ✓ | 2026-11-20 |
| 2.1.4 | `engine/tests/test_validate.py` | One fixture per release-1 row with its own code; later kinds and fields refuse `not_in_release`; the portable workflow valid on all four; WFM-B3 table; warnings stay warnings | WFM-B8, WFM-B9, WFM-B10, WFM-B11, WFM-B12, WFM-B3 | yes | P1 | ✓ | 2026-11-20 |
| 2.1.5 | `engine/src/tempergraph/model/validate.py`, `model/text.py`, `model/flow.py` | Create `validate`, `Finding`, text loading and the successor model | WFM-B7, CMP-B8 | | P1 | ✓ | 2026-11-20 |

### T2.2 Prompt rendering and values

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 2.2.1 | `engine/tests/test_template.py`, `tests/test_prompt.py` | Test the grammar and marker; the same prompt on four executors but the tools block; no self-assessment; absent sections; literal braces; retry told; value table; blocked and upstream lines | CON-B8, PRM-B1, PRM-B6, VAL-B5, VAL-B6 | yes | P1 | ✓ | 2026-11-20 |
| 2.2.2 | `engine/src/tempergraph/render/template.py`, `render/prompt.py`, `render/output.py` | Create the parser and renderer, `render_step`, `parse_output` | PRM-B1, PRM-B6, VAL-B5 to VAL-B8 | | P1 | ✓ | 2026-11-20 |

### T2.3 Compiler

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 2.3.1 | `engine/tests/test_compiler.py` | Test four nodes per unit, diagram equals graph both ways, the CMP-B6 edge table, retry as an edge, pause and resume of only the human node, `interrupt` first, the deleting reducer | CMP-B8, CMP-B1, B2, B6, HUM-AC1 | yes | P1 | ✓ | 2026-11-20 |
| 2.3.2 | `engine/src/tempergraph/compiler/graph.py`, `compiler/state.py` | Create `compile_workflow`, `UnitNodes`, `RunState` and `merge_units` | CMP-B8, CMP-B17 | | P1 | ✓ | 2026-11-20 |
| 2.3.3 | `engine/src/tempergraph/run/gate.py`, `run/nodes.py`, `engine/tests/test_routing.py` | The gate evaluates a step's route, a route unit and a switch: the pick is made before an approval pause and kept for the person's `proceed`; a route that raises or returns a non-target stops with exit 4 (`route`); a switch fault takes the default arm; a switch is sticky per visit or run; every pick writes a `route` record with `chosen_by`. Route and switch units run no session. Found missing while building T11.1: the gate had always taken the first target. `--arm` stays refused with the `arm` setting (SWM, release 2) | CMP-B10 to CMP-B16, CMP-B3, OBS `route` | yes | P1 | ✓ | 2026-11-20 |

### T2.4 Diagram model

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 2.4.1 | `engine/src/tempergraph/model/diagram.py` | Create `diagram_model` with a shape digest and the Mermaid renderer | LIF-B7 to LIF-B16, LIF-B3 | | P2 | ✓ | 2026-11-20 |
| 2.4.2 | `engine/tests/test_spec_budget.py` | Test the 400-line and 30 KB budget of every spec | docs README, OVR-AC2 | yes | P2 | ✓ | 2026-11-20 |

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
