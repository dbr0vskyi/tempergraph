"""Fixture runs of the regeneration unit on the loaded workflow (RGN-B1, RGN-B2, RGN-B8). The sessions are the
stand-ins of the independent review's tests; the unit itself is the package's own."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from tempergraph.constants import ExitCode

ROOT = Path(__file__).resolve().parents[1]
TASK = "I-1"
GEN = "import pathlib\npathlib.Path('generated.txt').write_text('generated\\n')\n"
MARKER = "import pathlib\npathlib.Path('ran.txt').write_text('x')\n"


def _load(name: str) -> Any:
    here = str(ROOT / "tests")
    if here not in sys.path:
        sys.path.insert(0, here)  # the engine imports the module's check functions by name
    return importlib.import_module(name)


irv = _load("test_independent_review")
modes = _load("test_code_mode")


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


def _declare(repo: Path, *entries: dict[str, Any], tools: dict[str, str] | None = None) -> None:
    for rel, text in {"tools/gen.py": GEN, "tools/marker.py": MARKER, **(tools or {})}.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    (repo / "tempergraph.regenerations.json").write_text(
        json.dumps({"schema_version": 1, "regenerations": list(entries)}), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "declare"], cwd=repo, check=True, capture_output=True)


def _entry(command: str = "python3 tools/gen.py", inputs: list[str] | None = None,
           outputs: list[str] | None = None) -> dict[str, Any]:
    return {"name": "gen", "command": command, "inputs": inputs or ["src"], "outputs": outputs or ["generated.txt"]}


def _work(repo: Path) -> Path:
    """The run's own worktree."""
    return repo.parent / "repo.worktrees" / f"temperspec--{TASK}"


def _subjects(repo: Path) -> list[str]:
    return irv._git_out(repo, "log", "--format=%s").splitlines()


def _gate_units(repo: Path) -> list[str]:
    return [r["unit"] for r in irv._records(repo, "gate")]


def test_rgn_ac1_the_unit_is_entered_after_the_code_step_on_each_arm(repo: Path) -> None:
    # RGN-AC1, AC 1
    for steps, task in ((modes.SINGLE, "S-1"), (modes.PHASES, "P-1")):
        out = modes._run(repo, steps, task=task)
        assert out.exit_code is ExitCode.FINISHED, json.dumps(out.payload, default=str)[:1500]
        assert modes._entered(repo, task)[-4:] == ["code", "regeneration", "code_join", "independent_review"], task


def test_rgn_ac1_the_quick_lane_enters_the_unit_before_the_outcome_gate_and_no_review(repo: Path) -> None:
    # RGN-AC1, AC 1
    stand = irv.Stand(route="quick")
    out = irv._go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    gates = _gate_units(repo)
    assert gates.index("code") < gates.index("regeneration") < gates.index("outcome")
    assert "independent_review" not in gates and "independent_review" not in stand.units()


def test_rgn_ac2_a_due_regeneration_starts_no_session_and_its_files_are_committed(repo: Path) -> None:
    # RGN-AC2, AC 1, RGN-B2, RGN-B11
    _declare(repo, _entry())
    stand = irv.Stand()
    out = irv._go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert "regeneration" not in stand.units() and "regeneration" not in stand.units("judge")
    assert stand.units()[-2:] == ["code", "independent_review"]  # nothing between them: no session for the unit
    assert (_work(repo) / "generated.txt").read_text() == "generated\n"
    assert f"docs(temperspec): regeneration for {TASK}" in _subjects(_work(repo))
    gates = _gate_units(repo)
    assert gates.index("code") < gates.index("regeneration") < gates.index("independent_review")


@pytest.mark.parametrize("entries", [[], [_entry(inputs=["other"])]])
def test_rgn_ac2_nothing_declared_or_no_input_changed_starts_no_command_and_adds_no_commit(
        repo: Path, entries: list[dict[str, Any]]) -> None:
    # AC 1, RGN-AC8 (RGN-B8): an empty list, and a declaration whose input the run did not change
    _declare(repo, *[{**e, "command": "python3 tools/marker.py"} for e in entries])
    stand = irv.Stand()
    out = irv._go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert not (_work(repo) / "ran.txt").exists() and not (_work(repo) / "generated.txt").exists()
    assert not any("regeneration for" in s for s in _subjects(_work(repo)))


def test_rgn_ac2_a_repository_with_no_declaration_passes_the_unit_with_nothing_run(repo: Path) -> None:
    # AC 1, RGN-AC8 (RGN-B8)
    out = irv._go(repo, irv.Stand())
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert "regeneration" in _gate_units(repo)
    assert not any("regeneration for" in s for s in _subjects(_work(repo)))
