"""A `chore` row describing a file deletion is completed by an after-script (COD-B1, COD-AC1, AC 2, AC 3)."""

from __future__ import annotations

import dataclasses
import importlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode
from tempergraph.contracts import CallableRef, SessionRequest, SessionResult
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


def _mark_complete(text: str) -> str:
    """Mark row 1.1 as completed and set plan status to completed."""
    marked = re.sub(r"(\| 1\.1 \|.*?)\| *\|$", r"\1| " + _TODAY + " |", text, flags=re.M)
    return re.sub(r"^status: planned$", "status: completed", marked, flags=re.M)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                   cwd=cwd, check=True, capture_output=True)


def passes(ctx: Any) -> Any:
    from tempergraph.api import CheckResult
    return CheckResult(result="PASS", evidence="stand-in")


def ready(ctx: Any) -> dict[str, str]:
    return {"setup_ready": "yes"}


def _spec() -> Any:
    """The package spec with all checks replaced by passing stand-ins and no outcome or finalizer."""
    units = {}
    for name, u in SPEC.units.items():
        gate = u.gate
        if gate.check is not None:
            gate = dataclasses.replace(gate, check=CallableRef(module=__name__, qualname="passes", func=passes))
        step = u.step
        if step is not None and name == "code":
            step = dataclasses.replace(step, self_check=False)
        units[name] = dataclasses.replace(u, gate=gate, step=step)
    script = dataclasses.replace(SPEC.units["prepare"].script, run=None,
                                 call=CallableRef(module=__name__, qualname="ready", func=ready))
    units["prepare"] = dataclasses.replace(units["prepare"], script=script)
    return dataclasses.replace(SPEC, units=units, outcome=None, finalizer=None, finalizer_outcomes=())


class _DeletionStand:
    """A scripted Stand that creates a chore plan and marks it in the code session without deleting the file."""

    def __init__(self) -> None:
        self._inner = standin("claude")
        self.name = self._inner.name
        self.workdir: Path | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        unit = req.session_key.split(".")[0]
        work = Path(req.workdir)
        self.workdir = work
        if unit == "triage":
            (work / "triage_note.md").write_text(_TRIAGE, encoding="utf-8")
            return answer("Triaged.\nARTIFACT triage_note: triage_note.md\nARTIFACT gaps: none\n"
                          "ARTIFACT route: plan")
        if unit == "plan":
            (work / "plan.md").write_text(_CHORE_PLAN, encoding="utf-8")
            return answer("Planned.\nARTIFACT plan: plan.md\nARTIFACT complexity: simple")
        if unit == "code":
            # Mark the chore row and set plan status to completed; do NOT delete src/old.py here
            text = (work / "plan.md").read_text(encoding="utf-8")
            (work / "plan.md").write_text(_mark_complete(text), encoding="utf-8")
            (work / "report.md").write_text(
                "# Code report\n\n## Verification\n\n- none\n\n## Deviations\n\n- None\n", encoding="utf-8"
            )
            return answer("Coded.\nARTIFACT code_report: report.md\nARTIFACT tests_passed: yes")
        if unit == "independent_review":
            (work / ".tempergraph" / "review").mkdir(parents=True, exist_ok=True)
            (work / ".tempergraph" / "review" / "findings.md").write_text(
                "## Findings\n\nNone\n", encoding="utf-8"
            )
            return answer("Read.")
        raise AssertionError(f"unexpected session unit {unit!r}")

    def run_judge(self, req: SessionRequest, views: Any, sink: Any) -> SessionResult:
        rows = [{"n": 1, "status": "MET", "evidence": "stand-in", "defect_in": None, "no_change": False}]
        return answer("OK.\n```json\n" + json.dumps({"criteria": rows, "gap": False, "confidence": 0.9}) + "\n```",
                      tools=("Read",))


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

    stand = _DeletionStand()
    registry = Registry()
    registry.register(stand)
    out = start(_spec(), _TASK, {"request": "x", "task_id": _TASK}, repo, registry,
                RunSettings(sleep=lambda s: None, flags={"code_mode.arm": "single"}))

    assert out.exit_code is ExitCode.FINISHED, out.message
    assert not (repo / "src" / "old.py").exists(), "src/old.py should be absent after the chore row's after-script"
