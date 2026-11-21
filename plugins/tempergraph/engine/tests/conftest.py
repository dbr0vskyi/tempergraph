from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SRC = ENGINE_ROOT / "src" / "tempergraph"
DOCS = ENGINE_ROOT.parent / "docs"
REPO_ROOT = ENGINE_ROOT.parents[2]


def workflow_packages() -> list[Path]:
    """The workflow packages next to the engine in this repository, found by their manifest. The engine's
    tests name none of them (WFM-AC-4, ADR-0129)."""
    return sorted(p.parent for p in (REPO_ROOT / "plugins").glob("*/tempergraph.json"))


def workflow_names() -> list[str]:
    """Each package's workflow name and plugin name, in the hyphen and underscore spellings."""
    import json

    names: set[str] = set()
    for root in workflow_packages():
        name = str(json.loads((root / "tempergraph.json").read_text(encoding="utf-8"))["name"])
        names |= {name, name.replace("-", "_"), root.name, root.name.replace("-", "_")}
    return sorted(names)


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """No test touches the real home folder or a real state root (WSP-AC-2)."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("TEMPERGRAPH_HOME", str(home / ".tempergraph"))
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "off")  # no detached loop child from a test run (SIL-B1)
    for var in ("TEMPERGRAPH_STATE_ROOT", "TEMPERGRAPH_CALLER", "TEMPERGRAPH_CALLER_APP", "TEMPERGRAPH_SUPERVISOR_TOKEN"):
        monkeypatch.delenv(var, raising=False)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A scratch git repository with one commit."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("scratch\n")
    _git(root, "add", "README.md")
    _git(root, "commit", "-q", "-m", "init")
    return root


@pytest.fixture
def real_state_root_guard() -> None:
    """Fail if the test left a state root in the engine's own repository (WSP-AC-2)."""
    before = (REPO_ROOT / ".tempergraph").exists()
    yield
    assert (REPO_ROOT / ".tempergraph").exists() == before, "a test wrote the real state root"


def hash_tree(root: Path) -> dict[str, str]:
    import hashlib

    out: dict[str, str] = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
        else:
            out[str(p.relative_to(root)) + "/"] = "dir"
    return out


os.environ.setdefault("TEMPERGRAPH_LOG_LEVEL", "WARNING")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """`live` tests spend money on a signed-in `claude`: skipped unless TEMPERGRAPH_LIVE=1 (live-checks plan)."""
    if os.environ.get("TEMPERGRAPH_LIVE") == "1":
        return
    skip = pytest.mark.skip(reason="live: set TEMPERGRAPH_LIVE=1 on a machine with a signed-in claude")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
