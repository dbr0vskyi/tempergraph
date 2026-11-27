"""What the callable of a script unit is given: the artifacts and values of the run so far and the resolved workflow
settings (SCR-B5, RST-B25). The fixture workflow names no workflow package (ADR `the-engine-names-no-workflow`)."""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import CheckResult, Gate, Judge, Routing, Script, Setting, Step, Value, Workflow
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


def _base_of(ctx: Any) -> Any:
    """The `git.base` a callable reads, or None when it has no git facts at all."""
    return getattr(ctx.git, "base", None)


def base_unit_script(ctx: Any) -> dict[str, str]:
    SEEN["base"] = {**SEEN.get("base", {}), "unit": _base_of(ctx)}
    return {}


def base_before_script(ctx: Any) -> dict[str, str]:
    SEEN["base"] = {**SEEN.get("base", {}), "before": _base_of(ctx)}
    return {}


def base_after_script(ctx: Any) -> dict[str, str]:
    SEEN["base"] = {**SEEN.get("base", {}), "after": _base_of(ctx)}
    return {}


def base_check(ctx: Any) -> CheckResult:
    # a check runs in a worker, so it reports through a file, not through SEEN
    value = _base_of(ctx) if ctx.git is not None else ""
    Path(os.environ["TEMPERGRAPH_TEST_CHECK_BASE"]).write_text(value or "", encoding="utf-8")
    return CheckResult(result="PASS", evidence="seen")


def base_spec() -> Any:
    """A script unit, a step with `before` and `after` scripts, and a check, each recording `git.base`."""
    units: dict[str, Any] = {
        "probe": Script(call=base_unit_script, produces={}, side_effects="none", gate=Gate()),
        "writer": Step(prompt="Write for {request}", tools=["read", "write"], produces={"again": "file"},
                       gate=Gate(check=base_check, judge=Judge(stance="Verify.", brief="Read first.md"),
                                 criteria=[crit("c-file")]),
                       before=[Script(call=base_before_script, produces={}, side_effects="none")],
                       after=[Script(call=base_after_script, produces={}, side_effects="none")]),
    }
    return named(Workflow(order=["probe", "writer"], units=units, issue_repository="acme/x",
                          routing=Routing(description="Context")))


def _base_run(folder: Path, report: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    SEEN.clear()
    monkeypatch.setenv("TEMPERGRAPH_TEST_CHECK_BASE", str(report))
    ex = standin("claude", steps=[answer("Wrote\nARTIFACT again: first.md", session_id="s-1")], judges=[judge()])
    out = start(base_spec(), "T-1", {"request": "notes"}, folder, registry(ex), NO_SLEEP)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert report.is_file(), "the check did not run"
    return {**SEEN["base"], "check": report.read_text(encoding="utf-8")}


def test_scr_ac6_a_script_and_a_check_of_one_run_read_the_same_base_commit(
        repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # AC 1
    got = _base_run(repo, tmp_path / "check-base.txt", monkeypatch)
    assert got["check"], got  # a run in a repository has a base commit
    assert got["unit"] == got["before"] == got["after"] == got["check"], got


def test_scr_ac6_a_run_in_place_gives_a_script_and_a_check_the_empty_base(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # AC 1
    folder = tmp_path / "plain"
    folder.mkdir()
    (folder / "first.md").write_text("no git here\n")
    got = _base_run(folder, tmp_path / "check-base.txt", monkeypatch)
    assert got == {"unit": "", "before": "", "after": "", "check": ""}, got


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
