"""What the callable of a script unit is given: the artifacts and values of the run so far and the resolved workflow
settings (SCR-B5, RST-B25). The fixture workflow names no workflow package (ADR-0129)."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from tempergraph.api import Gate, Judge, Routing, Script, Setting, Step, Value, Workflow
from tempergraph.constants import ExitCode
from tempergraph.executors.standins import answer, standin
from tempergraph.run.runner import start

from .fixtures.workflows import crit, named
from .test_run import NO_SLEEP, judge, registry

SEEN: dict[str, dict[str, Any]] = {}


def first_script(ctx: Any) -> dict[str, str]:
    (ctx.workdir / "first.md").write_text("first\n", encoding="utf-8")
    return {"first_file": "first.md"}


def later_script(ctx: Any) -> dict[str, str]:
    SEEN["unit"] = {"artifacts": dict(ctx.artifacts), "values": dict(ctx.values), "settings": dict(ctx.settings)}
    return {}


def before_script(ctx: Any) -> dict[str, str]:
    SEEN["before"] = {"artifacts": dict(ctx.artifacts), "values": dict(ctx.values), "settings": dict(ctx.settings)}
    return {}


def after_script(ctx: Any) -> dict[str, str]:
    SEEN["after"] = {"artifacts": dict(ctx.artifacts), "values": dict(ctx.values), "settings": dict(ctx.settings)}
    return {}


def spec(hybrid: bool = False) -> Any:
    units: dict[str, Any] = {
        "first": Script(call=first_script, produces={"first_file": "file"}, side_effects="workspace", gate=Gate()),
        "marker": Step(prompt="Mark the run for {request}", tools=["read"], produces={"mark": Value(choices=["no", "yes"])},
                       gate=Gate(judge=Judge(stance="Verify.", brief="Read the mark"), criteria=[crit("c-mark")])),
    }
    order = ["first", "marker"]
    if hybrid:
        units["writer"] = Step(prompt="Write {first_file} again for {request}", tools=["read", "write"],
                               produces={"again": "file"},
                               gate=Gate(judge=Judge(stance="Verify.", brief="Read first.md"), criteria=[crit("c-file")]),
                               before=[Script(call=before_script, produces={}, side_effects="none")],
                               after=[Script(call=after_script, produces={}, side_effects="none")])
        order.append("writer")
    else:
        units["later"] = Script(call=later_script, produces={}, side_effects="none", gate=Gate())
        order.append("later")
    return named(Workflow(order=order, units=units, issue_repository="acme/x", routing=Routing(description="Context"),
                          settings={"depth": Setting(kind="int", default=2, min=1, max=9, meaning="How deep")},
                          allow_commands=["git status"]))


def _marking() -> Any:
    """A stand-in executor for the step `marker`, which produces the value `mark`."""
    return standin("claude", steps=[answer("Marked\nARTIFACT mark: yes", session_id="s-0")], judges=[judge()])


def test_scr_b5_a_script_callable_is_given_the_artifacts_values_and_settings(repo: Path) -> None:  # AC 2
    SEEN.clear()
    settings = dataclasses.replace(NO_SLEEP, flags={"settings.depth": 7})
    out = start(spec(), "T-1", {"request": "notes"}, repo, registry(_marking()), settings)
    assert out.exit_code is ExitCode.FINISHED, out.message
    seen = SEEN["unit"]
    assert seen["artifacts"]["first"]["first_file"] == "first.md"  # the earlier unit's file, by unit name
    assert seen["values"]["marker"]["mark"] == "yes"  # and a later step's value
    assert seen["settings"]["depth"] == 7  # RST-B25: the resolved setting, not the default 2


def test_rst_b25_the_default_of_a_setting_reaches_a_script_callable(repo: Path) -> None:  # AC 2
    SEEN.clear()
    out = start(spec(), "T-1", {"request": "notes"}, repo, registry(_marking()), NO_SLEEP)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert SEEN["unit"]["settings"]["depth"] == 2


def test_scr_b5_a_hybrid_before_and_after_script_gets_the_same(repo: Path) -> None:  # AC 2
    SEEN.clear()
    ex = standin("claude", steps=[answer("Marked\nARTIFACT mark: yes", session_id="s-0"),
                                  answer("Wrote\nARTIFACT again: first.md", session_id="s-1")],
                 judges=[judge(), judge()])
    settings = dataclasses.replace(NO_SLEEP, flags={"settings.depth": 5})
    out = start(spec(hybrid=True), "T-1", {"request": "notes"}, repo, registry(ex), settings)
    assert out.exit_code is ExitCode.FINISHED, out.message
    for phase in ("before", "after"):
        seen = SEEN[phase]
        assert seen["artifacts"]["first"]["first_file"] == "first.md", phase
        assert seen["values"]["marker"]["mark"] == "yes", phase
        assert seen["settings"]["depth"] == 5, phase
