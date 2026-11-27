"""Task i58, RCM-B5 to RCM-B9: prepare writes `tempergraph.commands.json` for a Python repository that has none,
leaves an existing file alone, and the code gate does not count the file it wrote as a change of the run. The file
builds its own scratch repositories, so it passes alone."""

from __future__ import annotations

import importlib
import json
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts
from tempergraph.run.commands import expand

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
routing = importlib.import_module("tgwf_temperspec.routing")
checks = importlib.import_module("tgwf_temperspec.checks")
fmt = importlib.import_module("tgwf_temperspec.specfmt")
FILE = "tempergraph.commands.json"
PYTHON = ["pytest", "python -m pytest", "python3 -m pytest", "ruff check", "ruff format --check", "mypy"]
GIT_COMMANDS = ("git --version", "git status", "git diff", "git log", "git show")
QUICK = ROOT / "evals" / "checks" / "code" / "must-pass" / "3-quick"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A scratch git repository with one commit; the machine holds no rule files."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    return _new(tmp_path / "repo")


def _new(root: Path) -> Path:
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "commit", "-q", "--allow-empty", "-m", "start")
    return root


def _put(repo: Path, *paths: str, text: str = "# x\n") -> None:
    for path in paths:
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text, encoding="utf-8")


def _commit(repo: Path, message: str = "files") -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD").strip()


def _prepare(repo: Path) -> None:
    routing.prepare(SimpleNamespace(workdir=repo, unit="prepare", request={"task_id": "T"}))


def _ctx(repo: Path, git: GitFacts | None = None, values: dict[str, Any] | None = None) -> CheckContext:
    return CheckContext(unit="code", workdir=repo, request={}, artifacts={}, values=values or {},
                        git=git or GitFacts(), allow=SPEC.allow_commands, out_dir=repo.parent / f"{repo.name}.out",
                        deadline_at=time.monotonic() + 60)


def _file(repo: Path) -> dict[str, Any]:
    got: dict[str, Any] = json.loads((repo / FILE).read_text(encoding="utf-8"))
    return got


def _accepts(repo: Path, *commands: str) -> bool:
    return all(checks._commands(_ctx(repo), fmt.Plan(commands=[c]), "ts-plan-form") == [] for c in commands)


def test_rcm_ac6_prepare_writes_the_python_commands(repo: Path, tmp_path: Path) -> None:
    """RCM-AC6 (RCM-B6): a root `pyproject.toml`, a nested one and a root `requirements.txt` each count."""
    _put(repo, "pyproject.toml")
    second = _new(tmp_path / "nested")
    _put(second, "plugins/a/engine/pyproject.toml")
    third = _new(tmp_path / "reqs")
    _put(third, "requirements.txt")
    for work in (repo, second, third):
        _commit(work, "base")
        _prepare(work)
        assert _file(work) == {"schema_version": 1, "commands": PYTHON}, work.name
        assert _git(work, "log", "--format=%s", "--", FILE).count("\n") == 1, work.name  # one commit holds it
        assert _git(work, "status", "--porcelain").strip() == "", work.name  # and it is committed
        assert _accepts(work, "python3 -m pytest tests -q", "ruff format --check src", "mypy"), work.name
    assert not (second / "plugins" / "a" / "engine" / FILE).exists()
    assert (repo / FILE).read_bytes() == (second / FILE).read_bytes() == (third / FILE).read_bytes()


def test_rcm_ac7_an_existing_file_is_left_as_it_is(repo: Path, tmp_path: Path) -> None:
    """RCM-AC7 (RCM-B7): a file with other commands, one that is not JSON, and one of a repository that is not Python."""
    cases = [(repo, "pyproject.toml", json.dumps({"schema_version": 1, "commands": ["make check"]})),
             (_new(tmp_path / "broken"), "pyproject.toml", "{not json"),
             (_new(tmp_path / "web"), "package.json", json.dumps({"schema_version": 1, "commands": ["npm test"]}))]
    for work, marker, text in cases:
        _put(work, marker)
        _put(work, FILE, text=text)
        _commit(work, f"add {FILE}")
        _prepare(work)
        assert (work / FILE).read_bytes() == text.encode(), work.name
        assert _git(work, "log", "--format=%s", "--", FILE).split("\n")[:-1] == [f"add {FILE}"], work.name


def test_rcm_ac8_a_repository_that_is_not_python_gets_no_file(repo: Path, tmp_path: Path) -> None:
    """RCM-AC8 (RCM-B8): a `package.json`, a `pyproject.toml` in a folder of fixtures and a `setup.py` in
    `node_modules`."""
    _put(repo, "package.json")
    fixtures = _new(tmp_path / "fixtures")
    _put(fixtures, "evals/case/pyproject.toml")
    vendored = _new(tmp_path / "vendored")
    _put(vendored, "node_modules/pkg/setup.py")
    for work in (repo, fixtures, vendored):
        _prepare(work)
        assert not (work / FILE).exists(), work.name


REGENERATIONS = "tempergraph.regenerations.json"


def test_rgn_ac5_prepare_declares_no_regeneration(repo: Path, tmp_path: Path) -> None:
    """RGN-AC5 (RGN-B5): none for a Python repository, none for a stamp and a diagram, an existing one left as it was."""
    _put(repo, "pyproject.toml")
    generated = _new(tmp_path / "generated")
    _put(generated, "stamp.json", "diagram/model.json", "diagram/workflow.md")
    declared = _new(tmp_path / "declared")
    text = json.dumps({"schema_version": 1, "regenerations": [
        {"name": "a", "command": "make a", "inputs": ["src"], "outputs": ["a.md"]}]}, indent=1) + "\n"
    _put(declared, "pyproject.toml")
    _put(declared, REGENERATIONS, text=text)
    for work in (repo, generated, declared):
        _commit(work, "base")
        _prepare(work)
    assert not (repo / REGENERATIONS).exists() and not (generated / REGENERATIONS).exists()
    assert (declared / REGENERATIONS).read_bytes() == text.encode()


def _prepared_run(repo: Path) -> str:
    """A Python repository whose prepare wrote the file; the commit before prepare."""
    _put(repo, "pyproject.toml", "src/a.py")
    base = _commit(repo, "base")
    _prepare(repo)
    assert (repo / FILE).is_file()
    return base


def test_rcm_ac9_the_file_prepare_wrote_is_listed_apart(repo: Path) -> None:
    """RCM-AC9 (RCM-B9): written by prepare, not among the changed paths or the changed source files."""
    base = _prepared_run(repo)
    git = GitFacts(base=base, changed_paths=(FILE, "src/a.py"))
    res = checks._result(_ctx(repo, git), [])
    lines = res.evidence.splitlines()
    assert any(ln.startswith("Written by prepare") and FILE in ln for ln in lines), res.evidence
    assert "Changed paths since the run's base: src/a.py" in lines
    sources = checks._reading_lines(_ctx(repo, git))
    assert FILE not in " ".join(sources) and "src/a.py" in " ".join(sources)


def test_rcm_ac9_the_quick_lane_passes_when_only_the_file_prepare_wrote_is_extra(repo: Path) -> None:
    """RCM-AC9 (RCM-B9): `ts-code-lane` passes for the two files the note names and the file prepare wrote."""
    base = _prepared_run(repo)
    for f in sorted(p for p in QUICK.rglob("*") if p.is_file()):
        _put(repo, f.relative_to(QUICK).as_posix(), text=f.read_text())
    git = GitFacts(base=base, changed_paths=("src/tool/config.py", "tests/test_config.py", FILE))
    values = {"triage": {"route": "quick", "gaps": "none"}}
    ctx = _ctx(repo, git, values)
    ctx.artifacts = {"triage": {"triage_note": "triage_note.md"}}
    assert [f.status for f in checks._lane(ctx, "ts-code-lane")] == ["pass"]


def test_rcm_ac9_a_step_that_edits_the_file_puts_it_back_among_the_changes(repo: Path) -> None:
    """RCM-AC9 (RCM-B9): after a later edit the file is a changed path, and in the quick lane the lane fails."""
    base = _prepared_run(repo)
    for f in sorted(p for p in QUICK.rglob("*") if p.is_file()):
        _put(repo, f.relative_to(QUICK).as_posix(), text=f.read_text())
    doc = _file(repo)
    (repo / FILE).write_text(json.dumps({**doc, "commands": [*doc["commands"], "make check"]}))
    git = GitFacts(base=base, changed_paths=("src/tool/config.py", "tests/test_config.py", FILE))
    ctx = _ctx(repo, git, {"triage": {"route": "quick", "gaps": "none"}})
    ctx.artifacts = {"triage": {"triage_note": "triage_note.md"}}
    found = checks._lane(ctx, "ts-code-lane")
    assert [f.status for f in found] == ["fail"] and found[0].place == FILE
    res = checks._result(_ctx(repo, git), [])
    assert any(ln.startswith("Changed paths") and FILE in ln for ln in res.evidence.splitlines()), res.evidence
    assert not any(ln.startswith("Written by prepare") and FILE in ln for ln in res.evidence.splitlines())


def test_rcm_ac5_the_code_step_of_a_python_repository_runs_the_python_commands(repo: Path) -> None:
    """RCM-AC5 (RCM-B5): after prepare, the session may run the six Python commands and the read-only git commands."""
    _prepared_run(repo)
    step = SPEC.units["code"].step
    assert step is not None
    assert set(expand(step.commands, repo)) == {*PYTHON, *GIT_COMMANDS}
