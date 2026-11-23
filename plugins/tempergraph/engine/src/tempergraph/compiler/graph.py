"""Four nodes per unit, one finalizer node, static edges for every target (CMP-B8, ADR-0004).

The node bodies come from the gate funnel through :class:`UnitNodes`; this module owns only the graph
shape and the human node's ``interrupt``, which is its first statement (HUM-AC1). LangGraph is imported
only here and in the durability package.

A contest is a unit like any other here (CMP-B16, CMP-AC6): its four nodes, and no node per slot. Its slots are the
items of its own step node, which runs them up to `concurrency` at once and writes each under its slot (`item_view`,
`slot_writes`); its judge node grades them and picks. Only a concurrent map fans out through `Send` nodes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt

from tempergraph.compiler.state import ITEM, RunState, fold, item_end, item_view, slot, slot_writes
from tempergraph.contracts import WorkflowSpec
from tempergraph.model import flow

RECURSION_LIMIT = 10_000  # a backstop only; the attempt cap stops runs first (CMP-B5)


class UnknownRoutingToken(Exception):
    pass


class UnitNodes(Protocol):
    def step(self, unit: str, state: RunState, config: Any = None) -> dict[str, Any]: ...
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
    engine: Any = None  # the node bodies' owner, for a state write deferred to the first node (`defer`)

    def config(self, thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}


def _end(name: str) -> str:
    return END if name == flow.END else name


def compile_workflow(spec: WorkflowSpec, nodes: UnitNodes, checkpointer: BaseCheckpointSaver | None) -> CompiledWorkflow:
    g: Any = StateGraph(RunState)
    order = flow.effective_order(spec)
    names: list[str] = []
    edges: list[tuple[str, str]] = []
    post: Callable[[dict[str, Any]], dict[str, Any]] = getattr(nodes, "settle", lambda w: w)

    for unit in order:
        step, judge, gate, human = flow.node_names(unit)
        fan_out = flow.concurrent_map(spec, unit)  # MAP-B9: the items of a concurrent map run at once
        item_nodes = {kind: flow.item_node(unit, kind) for kind in flow.ITEM_KINDS}
        if unit in spec.units and spec.units[unit].kind == "subworkflow":  # SWF-B8: the child is a subgraph of this node
            g.add_node(step, _subgraph_node(nodes, unit, post))
        elif unit in spec.units and spec.units[unit].kind == "council":  # CNL-B14, ADR-0062: its sessions are a subgraph
            g.add_node(step, _council_node(nodes, unit, post))
        elif fan_out:  # this node reads the list and sends the items; it names where it may send them
            g.add_node(step, _map_node(nodes, unit, post), destinations=tuple(dict.fromkeys(
                (judge, item_nodes["step"], item_nodes["human"], *_goes(spec, unit)))))
        else:
            g.add_node(step, _bind1(nodes.step, unit, post))
        g.add_node(judge, _bind1(nodes.judge, unit, post))
        g.add_node(gate, _bind1(nodes.gate, unit, post))
        g.add_node(human, _human_node(nodes, unit, post))
        names += [step, judge, gate, human]
        if fan_out:  # the unit's own step node goes to its judge by itself, once every item has passed
            for kind in flow.ITEM_KINDS:
                dest = {"step": (item_nodes["judge"],), "judge": (item_nodes["gate"],),
                        "gate": (item_nodes["step"], step), "human": (item_nodes["step"], step)}[kind]
                g.add_node(item_nodes[kind], _item_node(nodes, unit, kind, post), destinations=dest)
                names.append(item_nodes[kind])
            edges += [(step, item_nodes["step"]), (step, item_nodes["human"]), (item_nodes["step"], item_nodes["judge"]),
                      (item_nodes["judge"], item_nodes["gate"]), (item_nodes["gate"], item_nodes["step"]),
                      (item_nodes["gate"], step), (item_nodes["human"], item_nodes["step"]),
                      (item_nodes["human"], step)]
        else:
            g.add_edge(step, judge)
        g.add_edge(judge, gate)
        edges += [(step, judge), (judge, gate)]
        gate_targets = flow.gate_targets(spec, unit)
        g.add_conditional_edges(gate, _router(unit, gate_targets), {t: _end(t) for t in gate_targets})
        edges += [(gate, t) for t in gate_targets]
        human_targets = flow.human_targets(spec, unit)
        g.add_conditional_edges(human, _router(unit, human_targets), {t: _end(t) for t in human_targets})
        edges += [(human, t) for t in human_targets]

    for join in order:  # CMP-B10 to CMP-B16: a parallel block forks to every branch and joins on every pass
        u = spec.units.get(join)
        if u is None or u.kind != "parallel":
            continue
        fork = flow.fork_node(join)
        enter = getattr(nodes, "fork", None)  # WSP-B19, WSP-B11: a block with a writer branch is entered by the engine
        if enter is not None and flow.writer_branches(spec, join):
            g.add_node(fork, _bind1(enter, join, post))
        else:
            g.add_node(fork, _passthrough(fork))
        names.append(fork)
        dones = []
        for b in u.branches:
            done = flow.done_node(b)
            g.add_node(done, _passthrough(done))
            g.add_edge(fork, flow.step_node(b))
            names.append(done)
            dones.append(done)
            edges.append((fork, flow.step_node(b)))
            edges.append((done, flow.step_node(join)))
        g.add_edge(dones, flow.step_node(join))  # the engine-owned AND-join

    g.add_node(flow.FINALIZER, nodes.finalizer)
    names.append(flow.FINALIZER)
    g.add_edge(flow.FINALIZER, END)
    edges.append((flow.FINALIZER, flow.END))
    g.add_edge(START, flow.entry_node(spec, order[0]))
    compiled = g.compile(checkpointer=checkpointer)
    return CompiledWorkflow(graph=compiled, spec=spec, nodes=names, edges=edges, engine=nodes)


def _bind1(fn: Callable[[str, RunState], dict[str, Any]], unit: str,
           post: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[RunState], dict[str, Any]]:
    def node(state: RunState) -> dict[str, Any]:
        return post(fn(unit, state))

    node.__name__ = f"{fn.__name__}_{unit}"
    return node


def _subgraph_node(nodes: UnitNodes, unit: str, post: Callable[[dict[str, Any]], dict[str, Any]]
                   ) -> Callable[[RunState, RunnableConfig], dict[str, Any]]:
    """The step node of a sub-workflow unit (SWF-B8): it invokes the child's own graph with this node's config, so the
    child is a subgraph under the parent's checkpointer and thread, its checkpoint namespace nested in this node's;
    a pause inside the child is a pause of this node. It hands back only what the unit exposes."""

    def node(state: RunState, config: RunnableConfig) -> dict[str, Any]:
        return post(nodes.step(unit, state, config))

    node.__name__ = f"step_{unit}"
    return node


class _CouncilState(TypedDict, total=False):
    """The state of a council's subgraph: the attempt's run (a plain object, never checkpointed), the stage in hand and,
    on a `Send` to a member node, the member's name."""

    parent: Any
    run: Any
    stage: int
    who: str
    out: dict[str, Any]


def _council_node(nodes: Any, unit: str, post: Callable[[dict[str, Any]], dict[str, Any]]
                  ) -> Callable[[RunState], dict[str, Any]]:
    """The step node of a council unit (CNL-B14, ADR-0062): a subgraph of one member node per round and member (a `Send`
    each), the engine-owned barrier that waits for every member's answer, failure or spoil before the next round, a pure
    tally node and the chair node. The unit's usual judge, gate and human nodes follow in the parent graph. Each member
    session is kept on its own as it ends (`run.council_run`), so the subgraph itself takes no checkpointer: a rerun of
    the attempt finds the sessions that ended and runs only the others."""

    def fan(s: _CouncilState) -> Any:
        names = s["run"].dispatch(int(s["stage"]))
        if not names:
            return "tally"
        return [Send("member", {"run": s["run"], "stage": s["stage"], "who": n}) for n in names]

    def member(s: _CouncilState) -> dict[str, Any]:
        nodes.council_member(s["run"], s["who"], int(s["stage"]))
        return {}

    def barrier(s: _CouncilState) -> dict[str, Any]:
        return {"stage": nodes.council_close(s["run"], int(s["stage"]))}

    def tally(s: _CouncilState) -> dict[str, Any]:
        nodes.council_tally(s["run"])
        return {}

    def chair(s: _CouncilState) -> dict[str, Any]:
        nodes.council_chair(s["run"])
        return {"out": nodes.council_finish(s["run"])}

    sub: Any = StateGraph(_CouncilState)
    sub.add_node("open", lambda s: {"run": nodes.council_open(unit, s["parent"]), "stage": 0})
    sub.add_node("member", member)
    sub.add_node("barrier", barrier)
    sub.add_node("tally", tally)
    sub.add_node("chair", chair)
    sub.add_edge(START, "open")
    sub.add_conditional_edges("open", fan, ["member", "tally"])
    sub.add_edge("member", "barrier")
    sub.add_conditional_edges("barrier", fan, ["member", "tally"])
    sub.add_edge("tally", "chair")
    sub.add_edge("chair", END)
    graph = sub.compile(checkpointer=False)

    def node(state: RunState) -> dict[str, Any]:
        got = graph.invoke({"parent": state}, {"recursion_limit": 100})
        return post(got["out"])

    node.__name__ = f"step_{unit}"
    return node


def _passthrough(name: str) -> Callable[[RunState], dict[str, Any]]:
    def node(state: RunState) -> dict[str, Any]:
        return {}

    node.__name__ = name.replace(".", "_")
    return node


def _goes(spec: WorkflowSpec, unit: str) -> tuple[str, ...]:
    """Where a concurrent map can go once an item has stopped it: where a gate or a person's decision can send a unit."""
    return tuple(_end(t) for t in flow.gate_targets(spec, unit) + flow.human_targets(spec, unit))


def _map_node(nodes: Any, unit: str, post: Callable[[dict[str, Any]], dict[str, Any]]
              ) -> Callable[[RunState], Command[Any]]:
    """The step node of a concurrent map (MAP-B9, MAP-B10): the node's own body says what the map does next (its `Move`),
    and this node sends the items it names, each with a state of its own, or goes where it says, or waits."""

    def node(state: RunState) -> Command[Any]:
        move = nodes.map_move(unit, state)
        writes = post(move.writes)
        goto: list[Any] = []
        if move.items:
            after = fold(state, writes)
            target = flow.item_node(unit, move.kind)
            goto = [Send(target, {**after, ITEM: {"unit": unit, "id": i, "slot": slot(unit, i)}}) for i in move.items]
        elif move.goto:
            goto = [_end(move.goto)]
        return Command(update=writes, goto=goto)

    node.__name__ = f"step_{unit}"
    return node


def _item_node(nodes: Any, unit: str, kind: str, post: Callable[[dict[str, Any]], dict[str, Any]]
               ) -> Callable[[dict[str, Any]], Command[Any]]:
    """One node of an item of a concurrent map (MAP-B9, CMP-B14): the unit's own step, judge, gate or human body runs on
    the item's view of the state, its writes are kept under the item's slot, and the next node of the same item is sent
    the state as it reads after them. An item that has passed, waits for a person or has stopped the map goes back to the
    unit's step node, which decides what the map does next."""

    def node(sent: dict[str, Any]) -> Command[Any]:
        held = sent[ITEM]
        decision = interrupt((sent.get("pause") or {}).get(held["slot"])) if kind == "human" else None  # HUM-AC1
        iid = held["id"]
        view = item_view(sent, unit, iid)
        if kind == "step":
            body = nodes.step(unit, view)
        elif kind == "judge":
            body = nodes.judge(unit, view)
        elif kind == "gate":
            body = nodes.gate(unit, view)
        else:
            body = nodes.human(unit, view, decision)
        writes = slot_writes(post(body), unit, iid)
        if kind in ("step", "judge"):
            after = {**fold(sent, writes), ITEM: held}
            return Command(update=writes, goto=Send(flow.item_node(unit, "judge" if kind == "step" else "gate"), after))
        route = (writes.get("route") or {}).get(slot(unit, iid)) or {}
        token = str(route.get("token"))
        writes = fold(writes, item_end(unit, iid, token, str(route.get("node"))))  # the two writes, composed
        if token == "RETRY":  # a retry reruns this item alone
            return Command(update=writes, goto=Send(flow.item_node(unit, "step"), {**fold(sent, writes), ITEM: held}))
        return Command(update=writes, goto=flow.step_node(unit))

    node.__name__ = f"item_{kind}_{unit}"
    return node


def _human_node(nodes: UnitNodes, unit: str,
                post: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[RunState], dict[str, Any]]:
    def human(state: RunState) -> dict[str, Any]:
        decision = interrupt((state.get("pause") or {}).get(unit))
        return post(nodes.human(unit, state, decision))

    return human


def _router(unit: str, allowed: list[str]) -> Callable[[RunState], str]:
    def route(state: RunState) -> str:
        rec = (state.get("route") or {}).get(unit) or {}
        target = rec.get("node")
        if target not in allowed:
            raise UnknownRoutingToken(f"unit {unit!r} routed to {target!r}; allowed {allowed}")
        return str(target)

    return route
