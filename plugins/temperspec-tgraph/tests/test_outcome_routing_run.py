"""A stand-in run of the package after a failing outcome judgement (spec outcome-gate, OGT-B6 to OGT-B8 and OGT-B11):
the outcome judge grades `ts-spec-sync` PARTIAL once and names no earlier step's output as the place of the defect; the
run shows which step is entered next and what that step is told. The routing is the engine's own, run on the loaded
package and its `outcome.json`; only the sessions and the checks of the units are stand-ins."""

from __future__ import annotations

import dataclasses
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import CheckResult
from tempergraph.constants import ExitCode
from tempergraph.contracts import CallableRef, SessionRequest, SessionResult
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import answer, standin
from tempergraph.package.loader import load_package
from tempergraph.run.runner import RunSettings, start
from tempergraph.store.layout import run_dir, state_root_path

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
TASK = "O-1"
PLACE = "docs/specs/session.spec.md, SES-B2 against SES-B4"
FIX = "reword SES-B2 so that it holds with the idle limit of SES-B4"
EVIDENCE = f"SES-B2 and SES-B4 cannot both hold. Place: {PLACE}. Fix: {FIX}."
NOTE = ("# Triage: O-1\n\n## Task\n\nA task.\n\n## Acceptance criteria\n\n1. A thing\n\n## Existing documents\n\n- None\n\n"
        "## Gaps\n\n- G1 spec gap: idle expiry. Searched `docs/specs/` for \"idle\": nothing. Findable\n\n"
        "## Owner decisions\n\nNone\n\n## Route\n\n- Deliver: code\n- Route: {route}\n")
REASON = "Why this unit runs again"


def passes(ctx: Any) -> CheckResult:
    return CheckResult(result="PASS", evidence="stand-in")


def ready(ctx: Any) -> dict[str, str]:
    return {"setup_ready": "yes"}


class Stand:
    """A stand-in executor that answers by the unit of the session key and records each session with its prompt. The
    outcome judge grades `ts-spec-sync` PARTIAL on its first session, with the place and the fix in its evidence and
    in its own fields and no earlier artifact as the place of the defect, and every criterion MET after that."""

    def __init__(self, route: str) -> None:
        self.inner = standin("claude")
        self.name = self.inner.name
        self.route = route
        self.sessions: list[dict[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def _enter(self, kind: str, req: SessionRequest) -> dict[str, Any]:
        row = {"kind": kind, "unit": req.session_key.split(".")[0], "prompt": req.prompt}
        self.sessions.append(row)
        return row

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        unit = str(self._enter("step", req)["unit"])
        work = Path(req.workdir)
        if unit == "triage":
            (work / "triage_note.md").write_text(NOTE.replace("{route}", self.route), encoding="utf-8")
            return answer("Triaged.\nARTIFACT triage_note: triage_note.md\n"
                          f"ARTIFACT gaps: {'none' if self.route == 'quick' else 'some'}\n"
                          f"ARTIFACT route: {self.route}", session_id="s-triage")
        if unit == "discovery":
            (work / "handoff.md").write_text("# Hand-off: O-1\n", encoding="utf-8")
            return answer("Closed.\nARTIFACT handoff: handoff.md", session_id=f"s-discovery-{len(self.sessions)}")
        if unit == "plan":
            (work / "plan.md").write_text("# Plan: a goal\n", encoding="utf-8")
            return answer("Planned.\nARTIFACT plan: plan.md\nARTIFACT complexity: simple",
                          session_id=f"s-plan-{len(self.sessions)}")
        if unit == "code":
            (work / "report.md").write_text(f"# Code report\n\n<!-- code session {len(self.sessions)} -->\n",
                                            encoding="utf-8")
            return answer("Coded.\nARTIFACT code_report: report.md\nARTIFACT tests_passed: yes",
                          session_id=f"s-code-{len(self.sessions)}")
        if unit == "independent_review":  # the reader after `code_join`: a clean change, so no trip back
            (work / ".tempergraph" / "review").mkdir(parents=True, exist_ok=True)
            (work / ".tempergraph" / "review" / "findings.md").write_text("## Findings\n\nNone\n", encoding="utf-8")
            return answer("Read.", session_id=f"s-review-{len(self.sessions)}")
        raise AssertionError(f"a session of {unit} that the stand-in does not answer")

    def run_judge(self, req: SessionRequest, views: Any, sink: Any) -> SessionResult:
        unit = str(self._enter("judge", req)["unit"])
        if unit == "outcome":
            count = len(re.findall(r"^\d+\. \[", req.prompt, re.M))
            first = sum(1 for s in self.sessions if s["kind"] == "judge" and s["unit"] == "outcome") == 1
            sync = re.search(r"^(\d+)\. \[ts-spec-sync\]", req.prompt, re.M)
            assert sync is not None, "the outcome judge is asked to grade ts-spec-sync"
        else:
            count, first, sync = max(len(SPEC.units[unit].gate.criteria), 1), False, None
        rows: list[dict[str, Any]] = []
        for i in range(1, count + 1):
            if first and sync is not None and i == int(sync.group(1)):
                rows.append({"n": i, "id": "ts-spec-sync", "status": "PARTIAL", "evidence": EVIDENCE, "place": PLACE,
                             "fix": FIX, "defect_in": None, "no_change": False})
            else:
                rows.append({"n": i, "status": "MET", "evidence": "stand-in", "defect_in": None, "no_change": False})
        text = "Reviewed.\n```json\n" + json.dumps({"criteria": rows, "gap": False, "confidence": 0.9}) + "\n```"
        return answer(text, tools=("Read",), session_id=f"j-{unit}-{len(self.sessions)}")


def _spec() -> Any:
    """The package's spec with the checks of its units replaced by one that passes, `prepare` answered by a callable,
    the code step not asked for its own check run, no last stage, and the outcome kept with its own check left out:
    the engine's check of the deliverables stays."""
    units = {}
    for name, u in SPEC.units.items():
        gate = u.gate
        if gate.check is not None:
            gate = dataclasses.replace(gate, check=CallableRef(module=__name__, qualname="passes", func=passes))
        step = dataclasses.replace(u.step, self_check=False) if u.step is not None and name == "code" else u.step
        units[name] = dataclasses.replace(u, gate=gate, step=step)
    script = dataclasses.replace(SPEC.units["prepare"].script, run=None,
                                 call=CallableRef(module=__name__, qualname="ready", func=ready))
    units["prepare"] = dataclasses.replace(units["prepare"], script=script)
    assert SPEC.outcome is not None
    return dataclasses.replace(SPEC, units=units, outcome=dataclasses.replace(SPEC.outcome, check=None),
                               finalizer=None, finalizer_outcomes=())


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "Test")):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    (root / "README.md").write_text("scratch\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True, capture_output=True)
    return root


def _go(repo: Path, stand: Stand) -> Any:
    registry = Registry()
    registry.register(stand)
    return start(_spec(), TASK, {"request": "x"}, repo, registry,
                 RunSettings(sleep=lambda s: None, flags={"code_mode.arm": "single"}))


def _after_the_first_outcome_judgement(stand: Stand) -> list[dict[str, Any]]:
    at = next(i for i, s in enumerate(stand.sessions) if s["kind"] == "judge" and s["unit"] == "outcome")
    return [s for s in stand.sessions[at + 1:] if s["kind"] == "step"]


def _outcome_gates(repo: Path) -> list[dict[str, Any]]:
    path = run_dir(state_root_path(repo), SPEC.name, TASK) / "run.jsonl"
    rows = map(json.loads, path.read_text(encoding="utf-8").splitlines())
    return [r for r in rows if r["kind"] == "gate" and r.get("unit") == "outcome"]


@pytest.mark.parametrize(("route", "back"), [("discovery", "discovery"), ("quick", "code")])
def test_ogt_ac21_a_failing_spec_sync_goes_back_to_the_step_that_owns_the_specs_and_tells_it_the_place_and_the_fix(
        repo: Path, route: str, back: str) -> None:  # OGT-AC21, AC 3, AC 4
    stand = Stand(route)
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    entered = _after_the_first_outcome_judgement(stand)
    assert entered and entered[0]["unit"] == back, [s["unit"] for s in entered]
    assert not {s["unit"] for s in entered} & {"triage", "setup", "list_components", "read_component", "read_gap"}
    prompt = str(entered[0]["prompt"])
    assert REASON in prompt, prompt
    reason = prompt.split(REASON, 1)[1]
    assert PLACE in reason and FIX in reason, reason
    gates = _outcome_gates(repo)
    assert [g["token"] for g in gates] == ["BACK", "PROCEED"], gates
    assert gates[0]["route_target"] == f"{back}.step", gates[0]
