"""The findings a failed regeneration gives (spec regeneration-failures, RGF-B3, RGF-B4): one for each thing the
command reported, read from the JSON report of the engine's two commands, otherwise one for the command."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from tempergraph.api import CheckFinding
from tempergraph.package.loader import load_package

load_package(Path(__file__).resolve().parents[1])  # puts the package's module on the path
regeneration = importlib.import_module("tgwf_temperspec.regeneration")


def _row(command: str, tail: str, exit_code: int = 2) -> dict[str, Any]:
    return {"name": "n", "command": command, "state": "failed", "exit_code": exit_code, "tail": tail}


def _rung(n: int, name: str, state: str, *findings: dict[str, Any]) -> dict[str, Any]:
    return {"rung": n, "name": name, "state": state, "note": "", "findings": list(findings)}


def _f(code: str, unit: str | None, message: str, remedy: str) -> dict[str, Any]:
    return {"code": code, "unit": unit, "message": message, "remedy": remedy}


def _verify(*rungs: dict[str, Any]) -> str:
    return "verifying\n" + json.dumps({"schema_version": 1, "workflow": "w", "ok": False, "refused": "",
                                       "rungs": list(rungs)}, indent=2)


def _lines(found: list[CheckFinding]) -> list[tuple[str | None, str, str, str]]:
    return [(f.criterion, f.place, f.message, f.fix) for f in found]


def test_rgf_ac3_an_author_verify_report_gives_one_finding_for_each_finding_of_a_failed_rung() -> None:
    # RGF-AC3 (RGF-B3)
    one = _verify(_rung(1, "load", "passed"), _rung(2, "model", "failed", _f("summary-long", "code", "summary over 60", "shorten it")))
    assert _lines(regeneration.findings_of(_row("tempergraph author verify p", one))) == [
        ("model", "code", "summary-long: summary over 60", "shorten it")]
    two = _verify(_rung(3, "criteria", "failed", _f("no-pass-case", "plan", "no pass case", "add one"),
                        _f("blocker-unverified", "plan", "no case verifies it", "add a case")))
    found = regeneration.findings_of(_row("tempergraph author verify p", two))
    assert _lines(found) == [("criteria", "plan", "no-pass-case: no pass case", "add one"),
                             ("criteria", "plan", "blocker-unverified: no case verifies it", "add a case")]
    assert all(f.status == "fail" for f in found)


def test_rgf_ac3_an_upgrade_check_report_gives_one_finding_for_each_failed_check_and_each_error() -> None:
    # RGF-AC3 (RGF-B3)
    def report(checks: list[dict[str, str]], findings: list[dict[str, str]]) -> str:
        return json.dumps({"schema_version": 1, "workflow": "w", "verification": checks, "findings": findings}, indent=2)

    one = report([{"check": "diagram", "state": "passed", "evidence": ""},
                  {"check": "blueprint", "state": "failed", "evidence": "blueprint differs from the model"}], [])
    assert _lines(regeneration.findings_of(_row("tempergraph upgrade-check p --stamp", one))) == [
        ("blueprint", "", "blueprint differs from the model", "")]
    two = report([{"check": "a", "state": "failed", "evidence": "ea"}, {"check": "b", "state": "failed", "evidence": "eb"}],
                 [{"severity": "error", "code": "x", "unit": "u", "message": "boom"},
                  {"severity": "warning", "code": "y", "unit": "u", "message": "quiet"}])
    found = regeneration.findings_of(_row("tempergraph upgrade-check p --stamp", two, exit_code=1))
    assert [f.criterion for f in found] == ["a", "b", "x"] and "boom" in found[2].message
    assert not any("quiet" in f.message for f in found)


def test_rgf_ac4_any_other_failure_gives_one_finding_with_the_command_the_exit_code_and_the_last_lines() -> None:
    # RGF-AC4 (RGF-B4)
    three = "error one\nerror two\nerror three"
    (a,) = regeneration.findings_of(_row("python3 tools/gen.py", three))
    assert a.criterion == "python3 tools/gen.py" and "exit code 2" in a.message and "error three" in a.message
    (b,) = regeneration.findings_of(_row("python3 tools/gen.py", json.dumps({"something": "else"}), exit_code=1))
    assert "exit code 1" in b.message and "something" in b.message
    empty = json.dumps({"verification": [{"check": "a", "state": "passed", "evidence": ""}], "findings": []})
    (c,) = regeneration.findings_of(_row("tempergraph upgrade-check p --stamp", empty))
    assert "exit code 2" in c.message and c.place == "tempergraph upgrade-check p --stamp"
    long = "\n".join(f"line {i}" for i in range(100))
    (d,) = regeneration.findings_of(_row("python3 x.py", long))
    assert "line 99" in d.message and "line 59" not in d.message and "line 60" in d.message
