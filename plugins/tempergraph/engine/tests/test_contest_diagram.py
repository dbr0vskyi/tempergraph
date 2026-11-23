"""A contest is drawn as one unit with its slot count (CMP-AC6; CMP-B16)."""

from __future__ import annotations

from tempergraph.model.diagram import diagram_model, to_mermaid

from .fixtures.workflows import two_step
from .test_contest_validate import contest_unit, workflow


def test_the_diagram_model_carries_one_unit_with_its_slot_count() -> None:  # CMP-AC6 (CMP-B16)
    model = diagram_model(workflow(contest_unit()))
    pick = [u for u in model["units"] if u["name"] == "pick"]
    assert len(pick) == 1 and pick[0]["kind"] == "contest" and pick[0]["slots"] == 3
    names = {n for n in model["nodes"] if n.startswith("pick.")}
    assert names == {"pick.step", "pick.judge", "pick.gate", "pick.human"}  # the unit's four nodes, no node per slot


def test_the_mermaid_text_shows_the_slot_count() -> None:  # CMP-AC6 (CMP-B16)
    text = to_mermaid(diagram_model(workflow(contest_unit(slots=4))))
    assert "4 slots" in text
    assert sum(1 for line in text.splitlines() if line.lstrip().startswith("u0[")) == 1  # one box for the unit
    assert "slots" not in to_mermaid(diagram_model(two_step()))  # a step carries no count
