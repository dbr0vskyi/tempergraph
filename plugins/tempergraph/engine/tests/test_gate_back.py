"""A gate with no judge and `on_fail: back` sends a failing check back to its one back target (HUM-B15 to HUM-B17).

The fixture names no workflow package: a step `a`, then a script unit `s` whose callable returns a mapping and whose
gate has a check and no judge.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import CheckResult, Gate, Judge, Routing, Script, Step, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import CheckFinding, WorkflowSpec
from tempergraph.executors.standins import answer, standin

from .fixtures.workflows import crit, named
from .test_run import go, judge, records

A_DONE = answer("Done", session_id="s-a")

# The engine imports the callables by their reference, so a module-level list is not the test's list: the state of the
# fixture is a JSON file whose path the environment holds.
STATE_ENV = "GATE_BACK_STATE"


def _state() -> Path:
    return Path(os.environ[STATE_ENV])


def _load() -> dict[str, Any]:
    return json.loads(_state().read_text())  # type: ignore[no-any-return]


@pytest.fixture(autouse=True)
def _state_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STATE_ENV, str(tmp_path / "gate-back-state.json"))
    _state().write_text(json.dumps({"plan": [], "ran": [], "checked": 0}))


def plan(*results: dict[str, Any]) -> None:
    """The check's result for its first, second ... run; the last one repeats."""
    state = _load()
    state["plan"] = list(results)
    _state().write_text(json.dumps(state))


def ran() -> list[str]:
    return _load()["ran"]  # type: ignore[no-any-return]


def checked() -> int:
    return _load()["checked"]  # type: ignore[no-any-return]


def script_call(ctx: Any) -> dict[str, str]:
    state = _load()
    state["ran"].append(ctx.unit)
    _state().write_text(json.dumps(state))
    return {}


def planned_check(ctx: Any) -> CheckResult:
    state = _load()
    state["checked"] += 1
    _state().write_text(json.dumps(state))
    got = state["plan"][min(state["checked"], len(state["plan"])) - 1]
    return CheckResult(result=got["result"], evidence="evidence", environmental=got.get("environmental", False),
                       findings=[CheckFinding(**f) for f in got["findings"]])


def fail(*findings: dict[str, Any], environmental: bool = False) -> dict[str, Any]:
    return {"result": "FAIL", "environmental": environmental, "findings": list(findings)}


PASS = {"result": "PASS", "findings": [{"status": "pass", "criterion": "c-ok"}]}


def finding(criterion: str, message: str, place: str | None = None, fix: str | None = None,
            status: str = "fail") -> dict[str, Any]:
    return {"status": status, "criterion": criterion, "message": message, "place": place, "fix": fix}


def fixture(**gate: Any) -> WorkflowSpec:
    fields: dict[str, Any] = {"check": planned_check, "on_fail": "back", "back_targets": ["a"]}
    fields.update(gate)
    units = {
        "a": Step(prompt="Do {request}", tools=["read"],
                  gate=Gate(judge=Judge(stance="V."), criteria=[crit("c-a")])),
        "s": Script(call=script_call, summary="A script unit", gate=Gate(**fields)),
    }
    return named(Workflow(order=["a", "s"], units=units, issue_repository="acme/x",
                          routing=Routing(description="A step and a script unit that goes back")))


def sessions(ex: Any) -> list[str]:
    return [c.kind for c in ex.calls]


def test_a_failing_check_goes_back_with_numbered_findings(repo: Path) -> None:  # HUM-AC11 (HUM-B15, HUM-B16), AC 9
    plan(fail(finding("c-a", "first problem", "notes.md", "do it"), finding("c-b", "second problem"),
              finding("c-ok", "fine", status="pass")), PASS)
    ex = standin("claude", steps=[A_DONE, A_DONE], judges=[judge(), judge()])
    out = go(repo, ex, fixture())
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert sessions(ex) == ["step", "judge", "step", "judge"]  # the unit `a` ran again, once
    assert ran() == ["s", "s"] and checked() == 2  # no retry of the script within a pass
    revisit = ex.calls[2].request.prompt
    assert "Why this unit runs again" in revisit and "sent back by `s`" in revisit
    assert "1. [c-a] notes.md: first problem (fix: do it)" in revisit
    assert "2. [c-b]: second problem" in revisit and "\n3. " not in revisit
    assert "fine" not in revisit  # a passing finding is left out
    entered = [(r["unit"], r["visit"], r["entered_from"]) for r in records(repo) if r["kind"] == "unit_entered"]
    assert [e for e in entered if e[0] == "a"] == [("a", 1, "start"), ("a", 2, "back:s")]


def test_an_environmental_failure_pauses_with_no_trip_back(repo: Path) -> None:  # HUM-AC11 (HUM-B17)
    plan(fail(finding("c-a", "no git"), environmental=True))
    ex = standin("claude", steps=[A_DONE], judges=[judge()])
    out = go(repo, ex, fixture())
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "escalation"
    assert sessions(ex) == ["step", "judge"] and ran() == ["s"]


def test_a_failure_with_no_finding_retries_the_script_unit(repo: Path) -> None:  # HUM-AC11 (HUM-B16)
    plan(fail(), PASS)
    ex = standin("claude", steps=[A_DONE], judges=[judge()])
    out = go(repo, ex, fixture())
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert sessions(ex) == ["step", "judge"] and ran() == ["s", "s"]  # a retry, not a trip back


def test_a_second_failure_pauses_with_kind_budget_and_the_findings(repo: Path) -> None:  # HUM-AC12 (HUM-B17)
    plan(fail(finding("c-a", "first failure")), fail(finding("c-a", "second failure", "x.md", "fix x")))
    ex = standin("claude", steps=[A_DONE, A_DONE], judges=[judge(), judge()])
    out = go(repo, ex, fixture())
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget"
    text = json.dumps(out.payload)
    assert "second failure" in text and "first failure" not in text
    assert sessions(ex) == ["step", "judge", "step", "judge"]  # the loop budget of 1 allowed one trip


def test_a_second_failure_under_stop_exits_5(repo: Path) -> None:  # HUM-AC12 (HUM-B17, BUD)
    plan(fail(finding("c-a", "first failure")), fail(finding("c-a", "second failure")))
    ex = standin("claude", steps=[A_DONE, A_DONE], judges=[judge(), judge()])
    out = go(repo, ex, fixture(on_budget_spent="stop"))
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA and int(out.exit_code) == 5


def test_a_failure_then_a_pass_after_the_trip_back_finishes_with_no_pause(repo: Path) -> None:  # HUM-AC12
    plan(fail(finding("c-a", "first failure")), PASS)
    ex = standin("claude", steps=[A_DONE, A_DONE], judges=[judge(), judge()])
    out = go(repo, ex, fixture())
    assert out.exit_code is ExitCode.FINISHED and int(out.exit_code) == 0
    assert not [r for r in records(repo) if r["kind"] == "pause"]
