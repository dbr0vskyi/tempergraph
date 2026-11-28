"""A `chore` row describing a file deletion is completed by an after-script (COD-B1, COD-AC1, AC 2, AC 3)."""

from __future__ import annotations

import dataclasses
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from tempergraph.api import Gate, Judge
from tempergraph.constants import ExitCode
from tempergraph.contracts import Criterion, SessionRequest, SessionResult
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import answer, standin
from tempergraph.package.loader import load_package
from tempergraph.run.runner import RunSettings, start

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec

_TASK = "DEL-1"
_TODAY = "✓ 2026-11-28"

_TRIAGE = """\
# Triage: DEL-1

## Task

Delete an old file.

## Acceptance criteria

1. src/old.py is absent after the run

## Intent

- Goal: remove an obsolete file without a code session having to delete it
- In scope: the deletion
- Out of scope: anything else
- Assumptions: None

## Existing documents

- None

## Uncertainties

None

## Gaps

None

## Route

- Deliver: code
- Route: plan
"""

_CHORE_PLAN = """\
---
task: DEL-1
complexity: simple
status: planned
specs: []
---

# Plan: delete src/old.py

## 0. Hand-off

- Triage note: `triage_note.md`
- Why this design: a chore row handles the deletion via an after-script.

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | src/old.py is absent after the run | |

## 2. Phases

### Phase 1: Delete the file

Goal: src/old.py is absent in the committed result.
Weight: light

| Row | Kind | Req | File | Proves | Change | Completed |
|---|---|---|---|---|---|---|
| 1.1 | chore | R1 | `src/old.py` | | Delete src/old.py | |

## 3. Verification

- `git --version`

| Criterion | Test | Command |
|---|---|---|
| AC 1 | `src/old.py` | `git --version` |

## 4. Docs to update

- None
"""

# The units needed for a plan-route run, following test_code_mode.py's pattern; expand and phase are
# included so code_mode's arms are valid, though single arm is forced so they are never entered.
_UNITS = ("triage", "plan", "code_mode", "expand", "phase", "code", "regeneration", "code_join", "independent_review")

MET = ("Reviewed.\n```json\n"
       + json.dumps({"criteria": [{"n": 1, "status": "MET", "evidence": "stand-in",
                                   "defect_in": None, "no_change": False}],
                     "gap": False, "confidence": 0.9})
       + "\n```")


def _spec() -> Any:
    """Minimal workflow: selected units only; the code step keeps its after-scripts intact."""
    units: dict[str, Any] = {}
    for name in _UNITS:
        unit = SPEC.units[name]
        if unit.step is not None:
            # Keep the code step's after-scripts so delete_chore_files runs; strip all others.
            after = unit.step.after if name == "code" else ()
            step = dataclasses.replace(unit.step, prompt="Do it.", before=(), after=after, self_check=False)
            gate = Gate(judge=Judge(stance="Verify."),
                        criteria=[Criterion(id=f"c-{name}", text="ok",
                                            check_method="read", severity="blocker")])
            unit = dataclasses.replace(unit, step=step, gate=gate,
                                       route_targets=tuple(t for t in (unit.route_targets or ())
                                                           if t in _UNITS))
        units[name] = unit
    return dataclasses.replace(SPEC, order=_UNITS, units=units, flow={}, outcome=None,
                               finalizer=None, finalizer_outcomes=())


def _mark_complete(text: str) -> str:
    """Mark row 1.1 as completed and set plan status to completed."""
    marked = re.sub(r"(\| 1\.1 \|.*?)\| *\|$", r"\1| " + _TODAY + " |", text, flags=re.M)
    return re.sub(r"^status: planned$", "status: completed", marked, flags=re.M)


def _triage_reply(req: SessionRequest) -> SessionResult:
    work = Path(req.workdir)
    (work / "triage_note.md").write_text(_TRIAGE, encoding="utf-8")
    return answer("Triaged.\nARTIFACT triage_note: triage_note.md\n"
                  "ARTIFACT gaps: none\nARTIFACT route: plan")


def _plan_reply(req: SessionRequest) -> SessionResult:
    work = Path(req.workdir)
    (work / "plan.md").write_text(_CHORE_PLAN, encoding="utf-8")
    return answer("Planned.\nARTIFACT plan: plan.md\nARTIFACT complexity: simple")


_code_workdir: list[Path] = []


def _code_reply(req: SessionRequest) -> SessionResult:
    work = Path(req.workdir)
    _code_workdir.append(work)
    text = (work / "plan.md").read_text(encoding="utf-8")
    (work / "plan.md").write_text(_mark_complete(text), encoding="utf-8")
    (work / "report.md").write_text(
        "# Code report\n\n## Verification\n\n- none\n\n## Deviations\n\n- None\n", encoding="utf-8"
    )
    return answer("Coded.\nARTIFACT code_report: report.md\nARTIFACT tests_passed: yes")


def _review_reply(req: SessionRequest) -> SessionResult:
    work = Path(req.workdir)
    (work / ".tempergraph" / "review").mkdir(parents=True, exist_ok=True)
    (work / ".tempergraph" / "review" / "findings.md").write_text(
        "## Findings\n\nNone\n", encoding="utf-8"
    )
    return answer("Read.")


def test_a_chore_row_delete_causes_the_file_to_be_absent_after_the_run(tmp_path: Path) -> None:
    # COD-AC1, AC 2, AC 3
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "Test")):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("scratch\n", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / "old.py").write_text("# old file to delete\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True, capture_output=True)

    _code_workdir.clear()
    steps = [_triage_reply, _plan_reply, _code_reply, _review_reply]
    judges = [answer(MET, tools=("Read",)) for _ in steps]

    registry = Registry()
    registry.register(standin("claude", steps=steps, judges=judges))

    out = start(_spec(), _TASK, {"request": "x", "task_id": _TASK}, repo, registry,
                RunSettings(sleep=lambda s: None, flags={"code_mode.arm": "single"}))

    assert out.exit_code is ExitCode.FINISHED, out.message
    assert _code_workdir, "code session did not run"
    assert not (_code_workdir[0] / "src" / "old.py").exists(), (
        "src/old.py should be absent in the worktree after the chore row's after-script"
    )
