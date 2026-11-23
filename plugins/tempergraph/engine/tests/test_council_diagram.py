"""A council compiles to the unit's usual nodes, its step node a subgraph, and draws as one box with no member count
(CMP-B16, CNL-B14, CNL-AC4; task AC 4)."""

from __future__ import annotations

from tempergraph.compiler import compile_workflow
from tempergraph.model import flow
from tempergraph.model.diagram import diagram_model, edge_set, to_mermaid

from .test_compiler import Scripted
from .test_council_run import UNIT, council_wf


def test_a_council_compiles_to_the_units_four_nodes_and_no_node_of_its_members() -> None:  # CNL-AC4 (CNL-B14, CMP-B16)
    spec = council_wf(rounds=2)
    cw = compile_workflow(spec, Scripted(spec, {}), None)
    assert sorted(cw.nodes) == sorted([*flow.node_names(UNIT), flow.FINALIZER])  # members and barrier live in the subgraph
    assert {(UNIT + ".step", UNIT + ".judge"), (UNIT + ".judge", UNIT + ".gate")} <= set(cw.edges)


def test_the_diagram_draws_a_council_as_one_box_with_no_member_count() -> None:  # CNL-AC4 (CMP-B16)
    few, many = council_wf(("a", "b")), council_wf(("a", "b", "c", "d", "e", "f", "g"))
    m_few, m_many = diagram_model(few), diagram_model(many)
    (box,) = [u for u in m_many["units"] if u["name"] == UNIT]
    assert box["kind"] == "council" and box["summary"] == "synthesize council"
    assert m_few["digest"] == m_many["digest"]  # the shape does not depend on how many members there are
    text = to_mermaid(m_many)
    assert text.count(f"{UNIT}<br/>") == 1 and "7" not in text.split(UNIT, 1)[1].split("\n", 1)[0]
    compiled = compile_workflow(many, Scripted(many, {}), None)
    assert edge_set(m_many) <= set(compiled.edges) | {("__start__", flow.entry_node(many, UNIT))}
