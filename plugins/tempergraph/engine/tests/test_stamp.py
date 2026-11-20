"""The changelog, compatibility, `upgrade --check --stamp` and the executor compatibility table
(VER §2.3, §2.5, §2.7, VER-B2 to B5, AC-2, AC-6; WUP §2.1, §2.6; LIF-AC-4 data)."""

from __future__ import annotations

import dataclasses
import io
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph import executor_compat
from tempergraph.catalog import from_registry
from tempergraph.cli.main import main
from tempergraph.constants import ENGINE_VERSION
from tempergraph.executors.registry import default_registry
from tempergraph.package import changelog
from tempergraph.package import registry as reg
from tempergraph.package.loader import load

from .conftest import hash_tree
from .fixtures.packages import minimal_package, write


def caps() -> dict[str, Any]:
    r = default_registry()
    return {n: r.get(n).capabilities() for n in r.available()}


def cli(cwd: Path, *argv: str) -> tuple[int, Any, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), registry=default_registry(), cwd=cwd, out=out, err=err)
    return code, json.loads(out.getvalue()) if out.getvalue().strip() else None, err.getvalue()


def entry(eid: str, *, breaking: bool, match: str = "units.*.gate.on_budget_spent == \"ask\"") -> dict[str, Any]:
    return {"id": eid, "audience": "workflow", "kind": "changed", "breaking": breaking, "surface": "spec_field",
            "subject": "on_budget_spent", "detect": [{"kind": "field", "match": match}],
            "migrate": {"action": "none", "reason": "test"}, "proof": [], "note": "test"}


def changelogs(folder: Path, files: dict[str, list[dict[str, Any]]]) -> Path:
    for version, entries in files.items():
        write(folder, f"{version}.json", {"schema_version": 1, "engine_version": version, "entries": entries})
    return folder


# -- VER §2.3, AC-2, AC-6 -------------------------------------------------------------------------------------


def test_shipped_changelog_exists_and_validates() -> None:
    files = dict((f"{v[0]}.{v[1]}.{v[2]}", p) for v, p in changelog.releases())
    assert ENGINE_VERSION in files  # VER-AC-6: a release ships its changelog file
    for p in files.values():
        for e in json.loads(p.read_text())["entries"]:
            assert changelog.entry_problems(e) == [], e["id"]


def test_renamed_entry_must_carry_its_transform() -> None:
    """VER-B4."""
    e = {**entry("E1.0.0-1", breaking=True), "kind": "renamed", "migrate": {"action": "assisted"}}
    assert any("rename_field" in p for p in changelog.entry_problems(e))
    assert changelog.entry_problems({**e, "migrate": {"action": "transform", "transform": "rename_field"}}) == []


# -- VER-B2 range selection --------------------------------------------------------------------------------------


@pytest.mark.parametrize(("stamp", "engine", "hit", "breaking", "state", "read"), [
    ("1.5.1", "1.5.1", True, False, "current", []),
    ("1.2.0", "1.5.1", False, False, "current", ["E1.2.1-1", "E1.5.1-1"]),
    ("1.2.0", "1.5.1", True, False, "stamp_behind", ["E1.2.1-1", "E1.5.1-1"]),
    ("1.2.0", "2.0.0", True, True, "needs_upgrade", ["E1.2.1-1", "E1.5.1-1", "E2.0.0-1"]),
    (None, "2.0.0", True, True, "unstamped", ["E1.2.0-1", "E1.2.1-1", "E1.5.1-1", "E2.0.0-1"]),
])
def test_range_selection(tmp_path: Path, stamp: str | None, engine: str, hit: bool, breaking: bool, state: str,
                         read: list[str]) -> None:
    match = 'units.*.gate.on_budget_spent == "ask"' if hit else 'units.*.gate.on_budget_spent == "stop"'
    folder = changelogs(tmp_path / "log", {
        "1.2.0": [entry("E1.2.0-1", breaking=False, match=match)],
        "1.2.1": [entry("E1.2.1-1", breaking=False, match=match)],
        "1.5.1": [entry("E1.5.1-1", breaking=False, match=match)],
        "2.0.0": [entry("E2.0.0-1", breaking=breaking, match=match)],
    })
    pkg = minimal_package(tmp_path / "p")
    got = changelog.compatibility(load(pkg), pkg, {"engine_version": stamp} if stamp else None, engine=engine,
                                  folder=folder)
    assert got["entries"] == read and got["state"] == state


def test_typed_hit_wins_over_text_at_one_location(tmp_path: Path) -> None:
    """VER-B3."""
    pkg = minimal_package(tmp_path)
    e = {**entry("E1.0.0-1", breaking=True), "detect": [
        {"id": "sym", "kind": "symbol", "match": "Judge"},
        {"id": "txt", "kind": "text", "match": "Judge", "files": "workflow/*/__init__.py"}]}
    hits = changelog.detect(e, load(pkg), pkg)
    sym = [h for h in hits if h.rule == "sym"]
    assert sym and all(h.confidence == "high" for h in sym)
    assert not any(h.rule == "txt" and h.where == sym[0].where for h in hits)


def test_out_of_range_never_refuses(tmp_path: Path) -> None:
    """VER-B5: the state is a warning line; validation is unchanged."""
    pkg = minimal_package(tmp_path)
    spec = dataclasses.replace(load(pkg), requires_engine=">=9.0,<10")
    assert changelog.compatibility(spec, pkg, None)["state"] == "out_of_range"


# -- the stamp ----------------------------------------------------------------------------------------------------------


def test_upgrade_check_then_stamp(tmp_path: Path, repo: Path) -> None:
    pkg = minimal_package(tmp_path / "src")
    reg.register(pkg, caps())
    assert from_registry().compat["release-notes"] == "unstamped"
    before = hash_tree(pkg)
    code, doc, _ = cli(repo, "upgrade", "release-notes", "--check")
    assert code == 0 and doc["compatibility"]["state"] == "unstamped" and doc["pending"] == []
    assert hash_tree(pkg) == before  # --check is read-only
    code, doc, err = cli(repo, "upgrade-check", "release-notes", "--stamp")
    assert code == 0, (err, doc)
    states = {v["check"]: v["state"] for v in doc["verification"]}
    assert states["V1 load"] == states["V2 validation"] == states["V7 diagram"] == "passed"
    assert states["V4 audit"] == states["V6 suites"] == "skipped"
    stamp = json.loads((pkg / "stamp.json").read_text())
    assert stamp["engine_version"] == ENGINE_VERSION and stamp["workflow_version"].startswith("0.1.0+")
    assert stamp["tool_set"]["claude"] == ["Glob", "Grep", "Read", "Write"]
    assert json.loads((pkg / "diagram" / "model.json").read_text())["digest"] == stamp["shape_digest"]
    assert load(pkg).verified_engine == ENGINE_VERSION
    cat = from_registry()
    assert cat.compat["release-notes"] == "current"
    assert stamp["workflow_version"] == cat.packages["release-notes"].workflow_version  # stamp.json is not content


def test_stamp_refused_when_validation_fails(tmp_path: Path, repo: Path) -> None:
    pkg = minimal_package(tmp_path)
    (pkg / "prompts" / "draft.md").unlink()
    code, doc, _ = cli(repo, "upgrade-check", str(pkg), "--stamp")
    assert code == 4 and not (pkg / "stamp.json").exists()
    assert {v["check"]: v["state"] for v in doc["verification"]}["V2 validation"] == "failed"


def test_installed_copy_and_release_3_refusals(tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    cached = minimal_package(tmp_path / "claude" / "plugins" / "cache" / "acme" / "release-notes")
    code, _, err = cli(repo, "upgrade-check", str(cached), "--stamp")
    assert code == 2 and "installed copy" in err
    code, _, err = cli(repo, "upgrade", str(cached))
    assert code == 2 and "not_in_release" in err
    code, _, err = cli(repo, "upgrade-check", "nothing-here")
    assert code == 2 and "unknown workflow" in err


# -- LIF-AC-4 table data (preflight and `executors` read it through `executor_compat`) ---------------------------------


def test_executor_compatibility_table() -> None:
    assert executor_compat.row("claude", "2.1.329")["state"] == "recorded"
    assert executor_compat.row("claude", "2.3.0")["state"] == "outside"
    f = executor_compat.finding("claude", "2.3.0")
    assert f is not None and f.code == "executor-version-untested" and f.severity == "warning"
    assert executor_compat.finding("claude", "2.1.329") is None
    assert executor_compat.row("antigravity", "1.0")["state"] == "no_table"
