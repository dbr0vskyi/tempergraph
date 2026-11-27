"""This repository's own declaration of regenerations (AC 3, RGN-B9): its entries for the workflow packages under
`plugins/`, and a fixture run in a linked worktree that regenerates a package's stamp, authoring record and diagram
with the engine's own command while the main checkout and the registry stay as they were."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import tempergraph
from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
load_package(ROOT)  # makes the package's module importable as `tgwf_temperspec`
regeneration = importlib.import_module("tgwf_temperspec.regeneration")
ENGINE_SRC = Path(tempergraph.__file__).resolve().parents[1]
TASK = "T"
OUTPUTS = ("stamp.json", "authoring.json", "diagram/model.json", "diagram/workflow.md")


def test_ac3_this_repositorys_declaration_holds_the_stamp_diagram_and_record_of_each_package() -> None:
    # AC 3, RGN-AC9 (RGN-B9)
    got = {r.command: r for r in regeneration.load_declaration(REPO)}
    packages = sorted(p.parent.relative_to(REPO).as_posix() for p in (REPO / "plugins").glob("*/tempergraph.json"))
    assert packages
    for folder in packages:
        entry = got.get(f"tempergraph author verify {folder} --json")  # --json: a failure comes back as findings
        assert entry is not None, folder
        assert folder in entry.inputs and "plugins/tempergraph/engine/src" in entry.inputs
        assert set(entry.outputs) == {f"{folder}/{name}" for name in OUTPUTS}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout


def _digest(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and ".git" not in p.relative_to(root).parts):
        h.update(path.relative_to(root).as_posix().encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def _commit(repo: Path, subject: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", subject)


def test_ac3_a_run_in_a_linked_worktree_regenerates_the_package_files_and_leaves_the_main_checkout(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AC 3, RGN-AC9 (RGN-B9)
    home = tmp_path / "home" / ".tempergraph"
    monkeypatch.setenv("TEMPERGRAPH_HOME", str(home))
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(ENGINE_SRC), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep))
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q", "-b", "main")
    folder = "plugins/release-notes-tgraph"  # a path, as the repository's own declaration names a package
    shutil.copytree(REPO / folder, main / folder,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".ruff_cache", ".mypy_cache"))
    (main / "tempergraph.regenerations.json").write_text(json.dumps({"schema_version": 1, "regenerations": [{
        "name": "release-notes", "command": f"python -m tempergraph author verify {folder} --json",
        "inputs": [folder], "outputs": [f"{folder}/{name}" for name in OUTPUTS]}]}), encoding="utf-8")
    _commit(main, "start")
    _git(main, "commit", "-q", "--allow-empty", "-m", f"docs(temperspec): prepare for {TASK}")
    registered = subprocess.run([sys.executable, "-m", "tempergraph", "workflows", "register", str(main / folder)],
                                capture_output=True, text=True, cwd=main)
    assert registered.returncode == 0, registered.stdout + registered.stderr
    work = tmp_path / "work"
    _git(main, "worktree", "add", "-q", "-b", "tg/run", str(work))
    # the run's code step changed a unit's summary and a prompt
    init = work / folder / "workflow" / "release_notes" / "__init__.py"
    init.write_text(init.read_text().replace('summary="Write the release notes"',
                                             'summary="Write the release notes for one release"'), encoding="utf-8")
    blueprint = work / folder / "blueprint.json"
    blueprint.write_text(blueprint.read_text().replace('"Write the release notes"',
                                                       '"Write the release notes for one release"'), encoding="utf-8")
    prompt = work / folder / "prompts" / "draft.md"
    prompt.write_text(prompt.read_text() + "\nName each change once.\n", encoding="utf-8")
    diagram = (work / folder / "diagram" / "workflow.md").read_text()
    (work / folder / "diagram" / "workflow.md").write_text("stale\n", encoding="utf-8")  # a diagram the change left stale
    _commit(work, f"feat(temperspec): code for {TASK}")
    before_main, before_registry = _digest(main), (home / "registry.json").read_bytes() if (
        home / "registry.json").exists() else b""
    old_stamp = (work / folder / "stamp.json").read_bytes()

    ctx = CheckContext(unit="regeneration", workdir=work, request={"task_id": TASK})
    regeneration.regenerate(ctx)
    result: Any = regeneration.regeneration_check(ctx)
    assert result.result == "PASS", result.evidence + "\n" + (work / ".tempergraph/regeneration/report.json").read_text()

    assert _digest(main) == before_main  # the main checkout holds what it held
    written = (work / folder / "diagram" / "workflow.md").read_text()  # what the command writes
    assert "Write the release notes for one release" in written and written != diagram
    assert (work / folder / "stamp.json").read_bytes() != old_stamp and (work / folder / "authoring.json").is_file()
    assert _git(work, "status", "--porcelain") == ""
    assert _git(work, "log", "-1", "--format=%s").strip() == f"docs(temperspec): regeneration for {TASK}"
    assert _digest(main) == before_main
    assert ((home / "registry.json").read_bytes() if (home / "registry.json").exists() else b"") == before_registry
