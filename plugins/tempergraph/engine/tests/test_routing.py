"""Routes and switches pick their target in the gate node (CMP-B10 to CMP-B16, CMP-B3; OBS `route` records)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from tempergraph.api import Gate, Judge, Route, Routing, Step, Switch, Value, Workflow
from tempergraph.constants import ExitCode
from tempergraph.executors.standins import answer, standin
from tempergraph.run.runner import RunSettings, start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.workflows import crit, named, routed, single_route, switched
from .test_run import MET, judge, registry

NO_SLEEP = RunSettings(sleep=lambda s: None)


def mode(value: str, sid: str = "s-1") -> Any:
    return answer(f"Done.\nARTIFACT mode: {value}", session_id=sid)


PLAIN = answer("Done.", session_id="s-2")


def go(repo: Path, spec: Any, steps: list[Any], judges: list[Any], task: str = "R-1") -> Any:
    return start(spec, task, {"request": "x"}, repo, registry(standin("claude", steps=steps, judges=judges)),
                 NO_SLEEP)


def recs(repo: Path, kind: str, task: str = "R-1") -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", task) / "run.jsonl"
    return [r for r in map(json.loads, p.read_text().splitlines()) if r["kind"] == kind]


def units_entered(repo: Path, task: str = "R-1") -> list[str]:
    return [r["unit"] for r in recs(repo, "unit_entered", task)]


def test_a_step_route_picks_its_target(repo: Path) -> None:
    out = go(repo, routed(), [mode("light")], [judge()])
    assert out.exit_code is ExitCode.FINISHED and units_entered(repo) == ["draft"]  # light goes to the finalizer
    (r,) = recs(repo, "route")
    assert (r["unit"], r["arm"], r["target"], r["chosen_by"]) == ("draft", "finalizer", "finalizer", "predicate")
    assert r["signals"] == {"mode": "light"}  # the value the route read is in the record (L-25)
    out = go(repo, routed(), [mode("full"), PLAIN], [judge(), judge()], task="R-2")
    assert out.exit_code is ExitCode.FINISHED and units_entered(repo, "R-2") == ["draft", "review"]


def boom(view: Any) -> str:
    raise RuntimeError("no")


def nowhere(view: Any) -> str:
    return "deep"


def test_a_route_fault_stops_and_never_falls_back(repo: Path) -> None:  # CMP-B3
    for i, fn in enumerate((boom, nowhere)):
        spec = routed()
        d = spec.units["draft"]
        spec = dataclasses.replace(spec, units={**spec.units, "draft": dataclasses.replace(
            d, route=Route(select=fn, targets=["review"]).route)})
        out = go(repo, spec, [mode("full")], [judge()], task=f"F-{i}")
        assert out.exit_code is ExitCode.STOPPED and out.reason == "route", out.message
        assert "review" not in units_entered(repo, f"F-{i}")


def test_a_route_unit_runs_no_session(repo: Path) -> None:
    ex = standin("claude", steps=[PLAIN], judges=[judge()])
    out = start(single_route(), "U-1", {"request": "x"}, repo, registry(ex), NO_SLEEP)
    assert out.exit_code is ExitCode.FINISHED, out.message  # `r` picks the finalizer: `b` never starts
    assert [c.kind for c in ex.calls] == ["step", "judge"]
    assert recs(repo, "route", "U-1")[0]["unit"] == "r"


def test_a_switch_takes_its_arm_or_the_default(repo: Path) -> None:
    out = go(repo, switched(), [mode("light")], [judge()])
    assert out.exit_code is ExitCode.FINISHED and units_entered(repo) == ["triage"]
    assert recs(repo, "route")[0]["chosen_by"] == "predicate"
    spec = switched()
    sw = spec.units["mode"]
    spec = dataclasses.replace(spec, units={**spec.units, "mode": Switch(
        predicate=boom, arms=dict(sw.switch.arms), default="full")})
    out = go(repo, spec, [mode("light"), PLAIN], [judge(), judge()], task="R-2")
    assert out.exit_code is ExitCode.FINISHED and units_entered(repo, "R-2") == ["triage", "deep"]
    (r,) = recs(repo, "route", "R-2")
    assert (r["arm"], r["chosen_by"]) == ("full", "default")


def light(view: Any) -> str:
    return "finalizer" if view.values.get("mode") == "light" else "review"


def test_the_route_is_picked_before_an_approval_pause(repo: Path) -> None:
    from tempergraph.run.runner import resume

    units = {"draft": Step(prompt="Draft {request}", tools=["read"], produces={"mode": Value(choices=["full", "light"])},
                           gate=Gate(judge=Judge(stance="V."), criteria=[crit("c1")], approval=True),
                           route=light, route_targets=["review", "finalizer"]),
             "review": Step(prompt="Review", tools=["read"], gate=Gate(judge=Judge(stance="V."), criteria=[crit("c2")]))}
    spec = named(Workflow(order=["draft", "review"], units=units, issue_repository="acme/x",
                          routing=Routing(description="Approve a routed draft")))
    ex = standin("claude", steps=[mode("light")], judges=[answer(MET, tools=("Read",), session_id="j")])
    out = start(spec, "A-1", {"request": "x"}, repo, registry(ex), NO_SLEEP)
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "approval"
    assert recs(repo, "route", "A-1")[0]["target"] == "finalizer"
    done = resume(spec, "A-1", repo, registry(ex), decision="proceed", settings=NO_SLEEP)
    assert done.exit_code is ExitCode.FINISHED and units_entered(repo, "A-1") == ["draft"]
