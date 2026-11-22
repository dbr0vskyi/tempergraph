"""Every workflow package that sits in this repository, found by its `tempergraph.json` and never by name: each
loads, passes its generated tests, covers its outcome, is in the marketplace and passes its own tests. What one
workflow does on its own paths is tested in that package's `tests/`, not here (ADR-0129)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tempergraph.package import selftest
from tempergraph.package.loader import load_package
from tempergraph.run.outcome_trust import coverage

from .conftest import REPO_ROOT, workflow_packages

PACKAGES = workflow_packages()
IDS = [p.name for p in PACKAGES]


def test_the_repository_holds_workflow_packages() -> None:
    assert PACKAGES, "no plugins/*/tempergraph.json found: the suite would check nothing"


@pytest.mark.parametrize("root", PACKAGES, ids=IDS)
def test_package_loads_and_passes_its_generated_tests(root: Path, tmp_path: Path) -> None:
    spec = load_package(root).spec
    declared = json.loads((root / "tempergraph.json").read_text())["name"]
    assert spec.name == declared and spec.outcome is not None
    record = json.loads((root / "authoring.json").read_text())
    decided = {d.get("subject") for d in record.get("decisions") or []}  # an accepted gap is a decision (AUT-B22)
    assert all(c.covered or c.criterion in decided for c in coverage(spec.outcome, spec)), "SCF rung 5"
    for test in selftest.NAMES:
        work = tmp_path / test
        work.mkdir()
        assert selftest.run(test, root, work) == [], test


@pytest.mark.parametrize("root", PACKAGES, ids=IDS)
def test_package_is_in_the_marketplace(root: Path) -> None:
    name = json.loads((root / "tempergraph.json").read_text())["name"]
    market = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
    entry = next(p for p in market["plugins"] if p["name"] == f"{name}-tgraph")  # ADR-0120
    manifest = json.loads((root / ".claude-plugin" / "plugin.json").read_text())
    assert entry["source"] == f"./plugins/{name}-tgraph" and manifest["name"] == f"{name}-tgraph"
    assert "tempergraph" in manifest["dependencies"]


@pytest.mark.parametrize("root", [p for p in PACKAGES if (p / "tests").is_dir()],
                         ids=[p.name for p in PACKAGES if (p / "tests").is_dir()])
def test_package_own_tests_pass(root: Path) -> None:
    got = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=",
                          str(root / "tests")], cwd=root, capture_output=True, text=True,
                         env={**os.environ, "PYTHONPATH": str(root / "workflow")})
    assert got.returncode == 0, got.stdout[-2000:]
