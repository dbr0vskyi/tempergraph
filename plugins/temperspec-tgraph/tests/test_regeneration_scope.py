"""What the gates and the quick lane's guard do with a file only the regeneration unit's commits changed (spec
regeneration, RGN-B13). The file builds its own scratch repositories, so it passes alone."""

from __future__ import annotations

import importlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts, git_facts

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
checks = importlib.import_module("tgwf_temperspec.checks")
QUICK = ROOT / "evals" / "checks" / "code" / "must-pass" / "3-quick"
OUTPUT = "stamp.json"
LINE = "Written by the regeneration"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout


def _put(repo: Path, path: str, text: str) -> None:
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(text, encoding="utf-8")


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    """A base, a code commit changing `src/a.py`, and a regeneration commit changing the declared output."""
    work = tmp_path / "repo"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    declaration = {"schema_version": 1, "regenerations": [
        {"name": "stamp", "command": "make stamp", "inputs": ["src"], "outputs": [OUTPUT]}]}
    _put(work, "tempergraph.regenerations.json", json.dumps(declaration))
    _put(work, OUTPUT, "{}\n")
    _commit(work, "base")
    base = _git(work, "rev-parse", "HEAD").strip()
    _put(work, "src/a.py", "a = 1\n")
    _commit(work, "feat(temperspec): code for T")
    _put(work, OUTPUT, '{"digest": 1}\n')
    _commit(work, "docs(temperspec): regeneration for T")
    return work, base


def _ctx(work: Path, git: GitFacts, values: dict[str, Any] | None = None) -> CheckContext:
    return CheckContext(unit="code", workdir=work, request={}, artifacts={}, values=values or {}, git=git,
                        allow=SPEC.allow_commands, out_dir=work.parent / f"{work.name}.out",
                        deadline_at=time.monotonic() + 60)


def _lines(ctx: CheckContext, step: str | None = None) -> list[str]:
    return str(checks._result(ctx, [], None, None, reading=checks._reading_lines(ctx), step=step).evidence).splitlines()


def test_rgn_ac13_the_code_gate_lists_the_regenerated_file_apart(repo: tuple[Path, str]) -> None:
    # RGN-AC13 (RGN-B13), AC 8
    work, base = repo
    ctx = _ctx(work, git_facts(work, base))
    lines = _lines(ctx)
    assert "Changed paths since the run's base: src/a.py" in lines, lines
    assert any(ln.startswith(LINE) and OUTPUT in ln for ln in lines), lines
    listed = next(ln for ln in lines if ln.startswith("Changed source files"))
    assert OUTPUT not in listed and "src/a.py 1" in listed, listed
    assert any(ln.startswith("Changed source lines: 1.") for ln in lines), lines


def test_rgn_ac13_the_phase_gate_lists_the_regenerated_file_apart(repo: tuple[Path, str]) -> None:
    # RGN-AC13 (RGN-B13), AC 8
    work, base = repo
    lines = _lines(_ctx(work, git_facts(work, base)), step="phase")
    assert any(ln.startswith(LINE) and OUTPUT in ln for ln in lines), lines
    for ln in lines:
        if ln.startswith(("Changed since the phase", "Changed only by earlier")):
            assert OUTPUT not in ln, ln


def test_rgn_ac13_a_later_edit_of_the_file_puts_it_back_among_the_changes(repo: tuple[Path, str]) -> None:
    # RGN-AC13 (RGN-B13), AC 8
    work, base = repo
    _put(work, OUTPUT, '{"digest": 2}\n')
    _commit(work, "docs(temperspec): code for T")
    lines = _lines(_ctx(work, git_facts(work, base)))
    assert any(ln.startswith("Changed paths") and OUTPUT in ln for ln in lines), lines
    assert not any(ln.startswith(LINE) for ln in lines), lines


def test_rgn_ac13_the_quick_lane_passes_for_the_two_files_beside_a_regenerated_file(repo: tuple[Path, str]) -> None:
    # RGN-AC13 (RGN-B13), AC 8
    work, base = repo
    for f in sorted(p for p in QUICK.rglob("*") if p.is_file()):
        _put(work, f.relative_to(QUICK).as_posix(), f.read_text())
    git = GitFacts(base=base, changed_paths=("src/tool/config.py", "tests/test_config.py", OUTPUT))
    ctx = _ctx(work, git, {"triage": {"route": "quick", "gaps": "none"}})
    ctx.artifacts = {"triage": {"triage_note": "triage_note.md"}}
    assert [f.status for f in checks._lane(ctx, "ts-code-lane")] == ["pass"]
