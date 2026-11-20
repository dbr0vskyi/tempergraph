"""Compiler and flow (CMP §2; CMP-AC-1, AC-4, AC-6 for release-1 kinds; CMP-B1, B6; HUM-AC-1)."""

from __future__ import annotations

import ast
import inspect
from collections import defaultdict
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from tempergraph.compiler import compile_workflow
from tempergraph.compiler import graph as graph_module
from tempergraph.compiler.state import merge_units
from tempergraph.model import flow
from tempergraph.model.diagram import diagram_model, edge_set, to_mermaid

from .fixtures.workflows import routed, single_route, switched, two_step


class Scripted:
    """Node bodies that route by a scripted list of tokens per unit."""

    def __init__(self, spec: Any, script: dict[str, list[str]]) -> None:
        self.spec = spec
        self.script = {k: list(v) for k, v in script.items()}
        self.calls: dict[str, int] = defaultdict(int)

    def step(self, unit: str, state: Any) -> dict[str, Any]:
        self.calls[unit] += 1
        return {"attempts": {unit: {"attempt": self.calls[unit]}}}

    def judge(self, unit: str, state: Any) -> dict[str, Any]:
        return {}

    def gate(self, unit: str, state: Any) -> dict[str, Any]:
        token = self.script.get(unit, ["PROCEED"]).pop(0) if self.script.get(unit) else "PROCEED"
        s = flow.successors(self.spec, unit)
        node = s.by_token()[token][0]
        return {"route": {unit: {"token": token, "node": node}}, "pause": {unit: {"kind": "escalation"}}}

    def human(self, unit: str, state: Any, decision: Any) -> dict[str, Any]:
        s = flow.successors(self.spec, unit)
        node = s.proceed[0] if decision == "proceed" else s.retry[0]
        return {"route": {unit: {"token": decision, "node": node}}, "pause": {unit: None}}

    def finalizer(self, state: Any) -> dict[str, Any]:
        return {"finalized": {"done": True}}


def test_four_nodes_per_unit() -> None:
    spec = two_step()
    cw = compile_workflow(spec, Scripted(spec, {}), None)
    for unit in spec.order:
        for n in flow.node_names(unit):
            assert n in cw.nodes
    assert len(cw.nodes) == 4 * len(spec.order) + 1


def _graph_edges(cw: Any) -> set[tuple[str, str]]:
    g = cw.graph.get_graph()
    return {(e.source, e.target) for e in g.edges}


def test_diagram_equals_graph_both_directions() -> None:
    for spec in (two_step(), routed(), switched(), single_route()):
        cw = compile_workflow(spec, Scripted(spec, {}), None)
        model = diagram_model(spec)
        assert edge_set(model) == _graph_edges(cw), spec.order
        assert set(model["nodes"]) | {"__start__", "__end__"} == {n for n in cw.graph.get_graph().nodes}


def test_edge_table_of_cmp_b6() -> None:
    spec = two_step()
    m = diagram_model(spec)
    edges = {(a, b, t) for a, b, t in m["edges"]}
    assert ("review.gate", "draft.step", "BACK") in edges
    assert ("draft.gate", "review.step", "PROCEED") in edges
    assert ("review.gate", "finalizer", "PROCEED") in edges
    r = diagram_model(routed())
    redges = {(a, b, t) for a, b, t in r["edges"]}
    assert ("draft.gate", "review.step", "PROCEED") in redges and ("draft.gate", "finalizer", "PROCEED") in redges


def test_diagram_digest_ignores_line_endings_and_changes_with_shape() -> None:
    a = diagram_model(two_step())["digest"]
    assert a == diagram_model(two_step())["digest"]
    assert a != diagram_model(routed())["digest"]
    assert to_mermaid(diagram_model(two_step())).startswith("flowchart TD")


def test_retry_is_an_edge() -> None:
    spec = two_step()
    nodes = Scripted(spec, {"draft": ["RETRY", "PROCEED"]})
    cw = compile_workflow(spec, nodes, InMemorySaver())
    out = cw.graph.invoke({"request": {"task_id": "t"}}, cw.config("demo/t"))
    assert nodes.calls == {"draft": 2, "review": 1}
    assert out["finalized"] == {"done": True}


def test_escalation_pauses_and_resume_replays_only_the_human_node() -> None:
    spec = two_step()
    nodes = Scripted(spec, {"review": ["ESCALATE"]})
    cw = compile_workflow(spec, nodes, InMemorySaver())
    cfg = cw.config("demo/t")
    cw.graph.invoke({"request": {"task_id": "t"}}, cfg)
    snap = cw.graph.get_state(cfg)
    assert snap.next == ("review.human",) and snap.tasks[0].interrupts
    before = dict(nodes.calls)
    out = cw.graph.invoke(Command(resume="proceed"), cfg)
    assert nodes.calls == before  # no step, judge or gate ran again (CMP-B2)
    assert out["finalized"] == {"done": True}


def test_interrupt_is_the_first_statement_of_the_human_node() -> None:
    src = inspect.getsource(graph_module._human_node)
    fn = ast.parse(src).body[0]
    inner = next(n for n in fn.body if isinstance(n, ast.FunctionDef))  # type: ignore[attr-defined]
    first = inner.body[0]
    assert isinstance(first, ast.Assign)
    call = first.value
    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "interrupt"


def test_reducer_deletes() -> None:
    old = {"a": {"x": 1, "y": 2}, "b": {"z": 3}}
    assert merge_units(old, {"a": {"x": None}, "b": None}) == {"a": {"y": 2}}
