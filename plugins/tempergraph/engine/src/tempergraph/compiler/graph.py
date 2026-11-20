"""Four nodes per unit, one finalizer node, static edges for every target (CMP §2, ADR-0004).

The node bodies come from the gate funnel through :class:`UnitNodes`; this module owns only the graph
shape and the human node's ``interrupt``, which is its first statement (HUM-AC-1). LangGraph is imported
only here and in the durability package.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from tempergraph.compiler.state import RunState
from tempergraph.contracts import WorkflowSpec
from tempergraph.model import flow

RECURSION_LIMIT = 10_000  # a backstop only; the attempt cap stops runs first (CMP-B5)


class UnknownRoutingToken(Exception):
    pass


class UnitNodes(Protocol):
    def step(self, unit: str, state: RunState) -> dict[str, Any]: ...
    def judge(self, unit: str, state: RunState) -> dict[str, Any]: ...
    def gate(self, unit: str, state: RunState) -> dict[str, Any]: ...
    def human(self, unit: str, state: RunState, decision: Any) -> dict[str, Any]: ...
    def finalizer(self, state: RunState) -> dict[str, Any]: ...


@dataclass
class CompiledWorkflow:
    graph: Any  # CompiledStateGraph
    spec: WorkflowSpec
    nodes: list[str]
    edges: list[tuple[str, str]]  # every possible (source, target), conditional ones included

    def config(self, thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}


def _end(name: str) -> str:
    return END if name == flow.END else name


def compile_workflow(spec: WorkflowSpec, nodes: UnitNodes, checkpointer: BaseCheckpointSaver | None) -> CompiledWorkflow:
    g: Any = StateGraph(RunState)
    order = flow.effective_order(spec)
    names: list[str] = []
    edges: list[tuple[str, str]] = []

    for unit in order:
        step, judge, gate, human = flow.node_names(unit)
        g.add_node(step, _bind1(nodes.step, unit))
        g.add_node(judge, _bind1(nodes.judge, unit))
        g.add_node(gate, _bind1(nodes.gate, unit))
        g.add_node(human, _human_node(nodes, unit))
        names += [step, judge, gate, human]
        g.add_edge(step, judge)
        g.add_edge(judge, gate)
        edges += [(step, judge), (judge, gate)]
        gate_targets = flow.gate_targets(spec, unit)
        g.add_conditional_edges(gate, _router(unit, gate_targets), {t: _end(t) for t in gate_targets})
        edges += [(gate, t) for t in gate_targets]
        human_targets = flow.human_targets(spec, unit)
        g.add_conditional_edges(human, _router(unit, human_targets), {t: _end(t) for t in human_targets})
        edges += [(human, t) for t in human_targets]

    g.add_node(flow.FINALIZER, nodes.finalizer)
    names.append(flow.FINALIZER)
    g.add_edge(flow.FINALIZER, END)
    edges.append((flow.FINALIZER, flow.END))
    g.add_edge(START, flow.step_node(order[0]))
    compiled = g.compile(checkpointer=checkpointer)
    return CompiledWorkflow(graph=compiled, spec=spec, nodes=names, edges=edges)


def _bind1(fn: Callable[[str, RunState], dict[str, Any]], unit: str) -> Callable[[RunState], dict[str, Any]]:
    def node(state: RunState) -> dict[str, Any]:
        return fn(unit, state)

    node.__name__ = f"{fn.__name__}_{unit}"
    return node


def _human_node(nodes: UnitNodes, unit: str) -> Callable[[RunState], dict[str, Any]]:
    def human(state: RunState) -> dict[str, Any]:
        decision = interrupt((state.get("pause") or {}).get(unit))
        return nodes.human(unit, state, decision)

    return human


def _router(unit: str, allowed: list[str]) -> Callable[[RunState], str]:
    def route(state: RunState) -> str:
        rec = (state.get("route") or {}).get(unit) or {}
        target = rec.get("node")
        if target not in allowed:
            raise UnknownRoutingToken(f"unit {unit!r} routed to {target!r}; allowed {allowed}")
        return str(target)

    return route
