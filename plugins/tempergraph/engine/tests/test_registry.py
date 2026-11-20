"""The home workflow registry and `workflows list|register|unregister|reinstall` (UPD §2.8, PKG-B1)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.catalog import from_registry
from tempergraph.cli.main import main
from tempergraph.constants import ExitCode
from tempergraph.durability.lock import RunLock
from tempergraph.executors.registry import default_registry
from tempergraph.package import registry as reg
from tempergraph.store.layout import home_path, lock_path, state_root_path

from .conftest import hash_tree
from .fixtures.packages import minimal_package, write


def caps() -> dict[str, Any]:
    r = default_registry()
    return {n: r.get(n).capabilities() for n in r.available()}


def cli(cwd: Path, *argv: str) -> tuple[int, Any, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), registry=default_registry(), cwd=cwd, out=out, err=err)
    text = out.getvalue()
    return code, json.loads(text) if text.strip() else None, err.getvalue()


@pytest.fixture
def pkg(tmp_path: Path) -> Path:
    return minimal_package(tmp_path / "src")


def test_register_list_and_catalog(pkg: Path, repo: Path) -> None:
    code, doc, err = cli(repo, "workflows", "register", str(pkg))
    assert code == 0, err
    assert doc["entry"]["state"] == "ok" and doc["entry"]["kind"] == "local"
    assert doc["entry"]["workflow_version"].startswith("0.1.0+")
    code, doc, _ = cli(repo, "workflows", "list", "--json")
    assert [(r["name"], r["state"]) for r in doc["workflows"]] == [("release-notes", "ok")]
    cat = from_registry()
    assert cat.specs["release-notes"].package_root == pkg.resolve()
    code, doc, _ = cli(repo, "list")
    row = doc["workflows"][0]
    assert row["state"] == "ok" and row["workflow_version"] == cat.packages["release-notes"].workflow_version


def test_register_check_writes_nothing(pkg: Path, repo: Path) -> None:
    home = home_path()
    before = hash_tree(home) if home.exists() else None
    code, doc, _ = cli(repo, "workflows", "register", str(pkg), "--check")
    assert code == 0 and doc["registered"] is False
    assert (hash_tree(home) if home.exists() else None) == before


def test_register_refusals(pkg: Path, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    code, _, err = cli(repo, "workflows", "register", str(plain))
    assert code == ExitCode.USAGE and "not-a-package" in err
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    cached = minimal_package(tmp_path / "claude" / "plugins" / "cache" / "mk" / "release-notes", "release-notes")
    code, _, err = cli(repo, "workflows", "register", str(cached))
    assert code == ExitCode.USAGE and "plugin-cache-path" in err
    (pkg / "prompts/draft.md").unlink()
    code, doc, err = cli(repo, "workflows", "register", str(pkg))
    assert code == ExitCode.USAGE and "not-valid" in err
    assert "text-ref" in {f["code"] for f in doc["findings"]}
    assert not reg.registry_path().exists()


def test_name_taken_by_another_path(pkg: Path, repo: Path, tmp_path: Path) -> None:
    assert cli(repo, "workflows", "register", str(pkg))[0] == 0
    other = minimal_package(tmp_path / "other")
    code, _, err = cli(repo, "workflows", "register", str(other))
    assert code == ExitCode.USAGE and "name-taken" in err
    assert cli(repo, "workflows", "register", str(pkg))[0] == 0  # same path again: refreshed in place


def test_unregister_keeps_files_and_refuses_live_threads(pkg: Path, repo: Path) -> None:
    assert cli(repo, "workflows", "register", str(pkg))[0] == 0
    lock = RunLock(lock_path(state_root_path(repo), "release-notes", "R-9"))
    lock.acquire()
    try:
        code, _, err = cli(repo, "workflows", "unregister", "release-notes")
        assert code == ExitCode.USAGE and "release-notes:R-9" in err
    finally:
        lock.release()
    code, doc, _ = cli(repo, "workflows", "unregister", "release-notes")
    assert code == 0 and doc["unregistered"] == "release-notes"
    assert (pkg / "tempergraph.json").exists() and reg.read_entries() == []
    code, _, err = cli(repo, "workflows", "unregister", "release-notes")
    assert code == ExitCode.USAGE and "unknown-workflow" in err


def test_missing_path_keeps_its_entry(pkg: Path, repo: Path, tmp_path: Path) -> None:
    assert cli(repo, "workflows", "register", str(pkg))[0] == 0
    pkg.rename(tmp_path / "moved")
    code, doc, _ = cli(repo, "workflows", "reinstall", "--all")
    assert code == ExitCode.USAGE and doc["workflows"][0]["entry"]["state"] == "missing"
    assert [e["name"] for e in reg.read_entries()] == ["release-notes"]  # never lost (ADR-0060)


def test_reinstall_clears_a_pin_that_no_longer_applies(pkg: Path, repo: Path) -> None:
    assert cli(repo, "workflows", "register", str(pkg))[0] == 0
    entries = reg.read_entries()
    entries[0]["engine_pin"] = {"engine": "0.0.0", "reason": "workflow_api", "since": "2026-11-01"}
    entries[0]["state"] = "pinned"
    reg.write_entries(entries)
    code, doc, _ = cli(repo, "workflows", "reinstall", "release-notes")
    assert code == 0
    assert doc["workflows"][0]["entry"]["engine_pin"] is None and doc["workflows"][0]["entry"]["state"] == "ok"


def test_reinstall_reports_broken_and_pending_dependencies(pkg: Path, repo: Path) -> None:
    assert cli(repo, "workflows", "register", str(pkg))[0] == 0
    write(pkg, "workflow/pyproject.toml", '[project]\nname = "tgwf-release-notes"\ndependencies = ["rich>=13"]\n')
    code, doc, _ = cli(repo, "workflows", "reinstall", "release-notes")
    entry = doc["workflows"][0]["entry"]
    assert code == 0 and entry["dependencies"] == "pending"  # no managed environment before T8.2
    write(pkg, "tempergraph.json", {"schema_version": 1, "name": "release-notes", "entry": "release_notes:workflow",
                                    "workflow_api": 99})
    code, doc, _ = cli(repo, "workflows", "reinstall", "release-notes")
    row = doc["workflows"][0]
    assert code == ExitCode.USAGE and row["entry"]["reason"] == "workflow_api_newer" and "update" in row["remedy"]
    code, _, err = cli(repo, "workflows", "reinstall")
    assert code == ExitCode.USAGE and "a name or --all" in err


def test_version_not_bumped_for_a_plugin_entry(pkg: Path) -> None:
    first = reg.check_package(pkg, caps(), {"kind": "plugin", "name": "release-notes"})
    write(pkg, "prompts/draft.md", "A changed prompt for {request}.\n")
    again = reg.check_package(pkg, caps(), first.entry)
    assert "version-not-bumped" in {f.code for f in again.findings if f.severity == "warning"}
    local = reg.check_package(pkg, caps(), {**first.entry, "kind": "local"})
    assert "version-not-bumped" not in {f.code for f in local.findings}
