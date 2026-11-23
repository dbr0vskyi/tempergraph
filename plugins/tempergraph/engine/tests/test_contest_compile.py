"""A contest compiles to the unit's four nodes and no more (CMP-AC6; CMP-B16)."""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver

from tempergraph.compiler import compile_workflow
from tempergraph.model import flow

from .test_compiler import Scripted
from .test_contest_run import contest_spec


def test_a_contest_compiles_to_the_units_four_nodes_and_no_more() -> None:  # CMP-AC6 (CMP-B16)
    spec = contest_spec(slots=4, then=False)
    cw = compile_workflow(spec, Scripted(spec, {}), InMemorySaver())
    mine = sorted(n for n in cw.nodes if n.startswith("pick"))
    assert mine == sorted(flow.node_names("pick"))  # `pick.step`, `.judge`, `.gate`, `.human`: none per slot
    assert sorted(cw.nodes) == sorted([*flow.node_names("pick"), flow.FINALIZER])
    assert {(a, b) for a, b in cw.edges if a == "pick.step"} == {("pick.step", "pick.judge")}  # the usual step edge


def test_a_contest_among_other_units_adds_no_nodes_beyond_the_four() -> None:  # CMP-AC6 (CMP-B16)
    spec = contest_spec(slots=2, then=True)
    cw = compile_workflow(spec, Scripted(spec, {}), InMemorySaver())
    assert len([n for n in cw.nodes if n.startswith("pick")]) == 4 and len([n for n in cw.nodes if n.startswith("after")]) == 4
