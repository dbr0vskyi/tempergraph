"""A map's values in the template of a unit after it: one line `<item id>: <value>` for each item, in list order, and
`none` when no item has one (VAL-AC5, VAL-B9). The fixtures are the engine's own map fixtures; they name no workflow."""

from __future__ import annotations

import dataclasses
import time
from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionRequest, SessionResult, WorkflowSpec
from tempergraph.executors.standins import answer

from .test_map import THREE, item_ok, mapped, no_phases, planner, run
from .test_map_concurrent import ByItem, concurrent, go
from .test_run import judge

NO_NOTE = answer("Did it, nothing to note.", session_id="item")


def joined(spec: WorkflowSpec) -> WorkflowSpec:
    """The same spec with an optional `note` and a join unit whose template names the map's key."""
    m = spec.units["phase"]
    assert m.step is not None
    item = dataclasses.replace(m.step, produces={"note": dataclasses.replace(m.step.produces["note"], optional=True)})
    last = spec.units["join"]
    assert last.step is not None
    join = dataclasses.replace(last, step=dataclasses.replace(last.step, prompt="Join {note}"))
    changed = dataclasses.replace(m, step=item)
    return dataclasses.replace(spec, units={**spec.units, "phase": changed, "join": join})


def body(prompt: str) -> str:
    """The template's own text: the engine adds its sections after the first blank line and a heading."""
    return prompt.split("\n\n## ")[0]


def prompt_of(ex: Any, unit: str) -> str:
    return body(next(c.request.prompt for c in ex.calls if c.kind == "step"
                     and c.request.session_key.startswith(f"{unit}.")))


def join_of(ex: ByItem) -> str:
    return body(next(r.prompt for r in ex.requests if r.session_key.startswith("join.")))


class Slow(ByItem):
    """A concurrent stand-in whose item `p1` ends after `p2` and whose items answer with a note unless named in `bare`."""

    def __init__(self, items: list[dict[str, str]], *, bare: tuple[str, ...] = ()) -> None:
        super().__init__(items)
        self.bare = bare

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        unit, item = self.whose(req)
        if unit == "phase" and item == "p1":
            time.sleep(0.2)
        if unit == "phase" and item in self.bare:
            self._enter("step", req)
            try:
                return answer(f"Did {item}.", session_id=f"s-{item}")
            finally:
                self._leave()
        return super().run_step(req, sink)


def test_a_sequential_map_renders_one_line_for_each_item_with_a_value(repo: Path) -> None:  # VAL-AC5 (VAL-B9), AC 1, AC 2
    spec = joined(mapped())
    steps = [planner(THREE), item_ok("one"), NO_NOTE, item_ok("three"), answer("Joined.")]
    out, ex = run(repo, spec, steps, [judge()] * 5)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert prompt_of(ex, "join") == "Join p1: one\np3: three"  # list order, nothing for p2


def test_a_concurrent_map_renders_the_lines_in_list_order_whichever_item_ended_first(repo: Path) -> None:
    # VAL-AC5 (VAL-B9), AC 1, AC 2
    ex = Slow(THREE[:2])
    out = go(repo, joined(concurrent(concurrency=2)), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert join_of(ex) =="Join p1: p1-done\np2: p2-done"  # p2 ended first; p1's line still comes first


def test_a_map_that_ran_no_item_renders_none_and_the_unit_runs(repo: Path) -> None:  # VAL-AC5 (VAL-B9), AC 1, AC 2
    spec = joined(mapped(extract=no_phases, on_empty="skip"))
    out, ex = run(repo, spec, [planner("x"), answer("Joined.")], [judge(), judge()])
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert prompt_of(ex, "join") == "Join none"


def test_a_map_none_of_whose_items_has_a_value_renders_none(repo: Path) -> None:  # VAL-AC5 (VAL-B9), AC 1, AC 2
    out, ex = run(repo, joined(mapped()), [planner(THREE[:2]), NO_NOTE, NO_NOTE, answer("Joined.")], [judge()] * 4)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert prompt_of(ex, "join") == "Join none"
    ex2 = Slow(THREE[:2], bare=("p1", "p2"))
    out2 = go(repo, joined(concurrent(concurrency=2)), ex2, task="M-2")
    assert out2.exit_code is ExitCode.FINISHED, out2.message
    assert join_of(ex2) == "Join none"


def test_an_item_prompt_still_renders_its_own_item_keys(repo: Path) -> None:  # VAL-AC5 (VAL-B4, VAL-B9), AC 1
    steps = [planner(THREE), item_ok("one"), item_ok("two"), item_ok("three"), answer("Joined.")]
    out, ex = run(repo, joined(mapped()), steps, [judge()] * 5)
    assert out.exit_code is ExitCode.FINISHED, out.message
    second = body([c for c in ex.calls if c.kind == "step"][2].request.prompt)
    assert second == "Do p2 (2/3): Second phase"
