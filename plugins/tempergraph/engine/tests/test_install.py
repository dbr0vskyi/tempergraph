"""First install (UPD §2.7), engine environments and the shim (UPD §2.2), the release record (VER §2.2),
and registry reconcile from Claude Code's plugin cache (UPD §2.8, PKG-B1). No test installs from an index:
the environment builder is a stand-in that links the test interpreter."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tempergraph import constants
from tempergraph.executors.registry import default_registry
from tempergraph.install import bootstrap, shim
from tempergraph.install import environment as envmod
from tempergraph.package import registry as reg
from tempergraph.release import release

from .conftest import ENGINE_ROOT, hash_tree
from .fixtures.packages import minimal_package, write

PLUGIN_ROOT = ENGINE_ROOT.parent
LAUNCHER = PLUGIN_ROOT / "bin" / "tempergraph"


class LinkBuilder:
    """Builds an 'environment' whose interpreter is this test's interpreter (which has the engine)."""

    def __init__(self, fail: str | None = None) -> None:
        self.fail = fail
        self.calls: list[str] = []

    def create(self, python: str, env: Path) -> None:
        self.calls.append("create")
        (env / "bin").mkdir(parents=True)
        # A wrapper, not a symlink: a symlinked venv interpreter in another folder loses the venv's site-packages.
        py = env / "bin" / "python"
        py.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
        py.chmod(0o755)
        if self.fail == "create":
            raise envmod.InstallFailed("venv failed (1)")

    def install(self, env: Path, engine: Path, extras: tuple[str, ...]) -> None:
        self.calls.append(f"install:{','.join(extras)}")
        if self.fail == "install":
            raise envmod.InstallFailed("pip install failed (1)")

    def self_check(self, env: Path) -> dict[str, Any]:
        self.calls.append("self_check")
        from tempergraph.install import selfcheck

        out = io.StringIO()
        real, sys.stdout = sys.stdout, out
        try:
            selfcheck.main()
        finally:
            sys.stdout = real
        return dict(json.loads(out.getvalue()))

    def reconcile(self, env: Path) -> dict[str, Any]:
        self.calls.append("reconcile")
        r = default_registry()
        done = reg.reconcile({n: r.get(n).capabilities() for n in r.available()})
        return {"schema_version": 1, "workflows": [c.entry for c in done]}


def home(tmp_path: Path) -> Path:
    return Path(os.environ["TEMPERGRAPH_HOME"])


def run_install(tmp_path: Path, *argv: str, builder: Any = None) -> tuple[int, list[dict[str, Any]]]:
    out = io.StringIO()
    code = bootstrap.install(["--json", *argv], builder=builder or LinkBuilder(), out=out, shell="/bin/zsh",
                             user_home=tmp_path / "user")
    return code, [json.loads(line) for line in out.getvalue().splitlines()]


# -- VER §2.2 release record ---------------------------------------------------------------------------------


def test_release_record_matches_constants() -> None:
    rel = release()
    assert (rel["engine_version"], rel["workflow_api"], rel["loads_workflow_api_from"], rel["store_layout"]) == (
        constants.ENGINE_VERSION, constants.WORKFLOW_API, constants.LOADS_WORKFLOW_API_FROM, constants.STORE_LAYOUT)
    assert rel["schemas"] == constants.SCHEMA
    plugin = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["version"] == rel["engine_version"]  # VER §2.1 / UPD §2.5 version parity


def test_bootstrap_loads_no_compiled_library() -> None:
    """UPD §2.7: the bootstrap imports the standard library and stdlib-only engine modules only."""
    code = ("import sys; import tempergraph.install.bootstrap; "
            "std = set(sys.stdlib_module_names) | {'tempergraph', '__main__', '_virtualenv', 'sitecustomize', 'usercustomize'}; "
            "print(sorted({m.split('.')[0] for m in sys.modules} - std))")
    got = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    extra = [m for m in eval(got.stdout) if not m.startswith(("_", "__editable"))]  # noqa: S307
    assert extra == [], extra
    names = subprocess.run([sys.executable, "-c", "import sys, tempergraph.install.bootstrap; "
                            "print([m for m in sys.modules if m.startswith('tempergraph.')])"],
                           capture_output=True, text=True, check=True).stdout
    from tempergraph.install import BOOTSTRAP_IMPORTS

    loaded = {m for m in eval(names)}  # noqa: S307
    def allowed(m: str) -> bool:  # an allowed module, one of its submodules, or a parent package of one
        return any(m == b or m.startswith(b + ".") or b.startswith(m + ".") for b in BOOTSTRAP_IMPORTS)

    assert [m for m in loaded if not allowed(m)] == []


# -- UPD §2.7 first install -------------------------------------------------------------------------------------


def test_first_install_then_already_current(tmp_path: Path) -> None:
    b = LinkBuilder()
    code, lines = run_install(tmp_path, "--with", "agent-sdk", builder=b)
    assert code == 0, lines
    h = home(tmp_path)
    cur = envmod.current(h)
    assert cur is not None and cur["engine_version"] == constants.ENGINE_VERSION
    env = Path(cur["path"])
    assert env.parent == h / "engines" and env.name.startswith(f"{constants.ENGINE_VERSION}-")
    assert (env / ".complete").is_file() and not (h / "engines" / "previous.json").exists()
    assert b.calls == ["create", "install:agent-sdk", "self_check", "reconcile"]
    assert {ln["kind"] for ln in lines} >= {"engine", "extras", "shim", "workflow", "summary"}
    assert (h / "manifest.json").is_file() and (h / "machine.json").is_file() and (h / "registry.json").is_file()
    assert os.access(shim.shim_path(h), os.X_OK)
    code, lines = run_install(tmp_path)
    assert code == 0 and lines[0]["state"] == "current"


@pytest.mark.parametrize("step", ["create", "install"])
def test_failed_install_changes_nothing(tmp_path: Path, step: str) -> None:
    code, lines = run_install(tmp_path, builder=LinkBuilder(fail=step))
    h = home(tmp_path)
    assert code == 1 and lines[-1]["state"] == "failed"
    assert envmod.current(h) is None and list((h / "engines").iterdir()) == []


def test_check_is_read_only(tmp_path: Path) -> None:
    h = home(tmp_path)
    code, lines = run_install(tmp_path, "--check")
    assert code == 0 and lines[0]["state"] == "would_install" and not h.exists()
    run_install(tmp_path)
    before = hash_tree(h)
    code, lines = run_install(tmp_path, "--check")
    assert lines[0]["state"] == "current" and hash_tree(h) == before


def test_no_python_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap, "find_python", lambda: None)
    code, lines = run_install(tmp_path)
    assert code == 2 and lines[0]["state"] == "no_python"


def test_add_to_path_once(tmp_path: Path) -> None:
    run_install(tmp_path, "--add-to-path")
    rc = tmp_path / "user" / ".zshrc"
    first = rc.read_text()
    assert shim.MARKER in first and str(home(tmp_path) / "bin") in first
    code, lines = run_install(tmp_path, "--add-to-path")
    assert rc.read_text() == first and next(ln for ln in lines if ln["kind"] == "shim")["path_state"] == "already_added"


def test_repair_rewrites_shim_and_current(tmp_path: Path) -> None:
    run_install(tmp_path)
    h = home(tmp_path)
    (h / "engines" / "current.json").unlink()
    shim.shim_path(h).unlink()
    code, lines = run_install(tmp_path, "--repair")
    assert code == 0 and lines[0]["state"] == "repaired"
    assert envmod.current(h) is not None and shim.shim_path(h).is_file()


def test_shim_runs_the_current_engine_or_exits_127(tmp_path: Path) -> None:
    h = home(tmp_path)
    shim.write_shim(h)
    env = {k: v for k, v in os.environ.items() if k != "TEMPERGRAPH_PYTHON"}
    got = subprocess.run(["sh", str(shim.shim_path(h)), "list"], capture_output=True, text=True, env=env)
    assert got.returncode == 127 and "launcher" in got.stderr
    run_install(tmp_path)
    got = subprocess.run(["sh", str(shim.shim_path(h)), "list"], capture_output=True, text=True, env=env,
                         cwd=tmp_path)
    assert got.returncode == 0, got.stderr
    assert json.loads(got.stdout)["schema_version"] == 1


def test_launcher_accepts_only_install_and_update(tmp_path: Path) -> None:
    got = subprocess.run(["sh", str(LAUNCHER), "run", "x"], capture_output=True, text=True)
    assert got.returncode == 127 and "bin/tempergraph install" in got.stderr
    got = subprocess.run(["sh", str(LAUNCHER), "update"], capture_output=True, text=True,
                         env={**os.environ, "TEMPERGRAPH_PYTHON": sys.executable})
    assert got.returncode == 2 and "no engine is installed" in got.stdout  # update needs a first install
    got = subprocess.run(["sh", str(LAUNCHER), "install", "--check", "--json"], capture_output=True, text=True,
                         env={**os.environ, "TEMPERGRAPH_PYTHON": sys.executable})
    assert got.returncode == 0, got.stderr
    assert json.loads(got.stdout.splitlines()[0])["state"] == "would_install"
    assert not home(tmp_path).exists()


def test_install_through_the_cli(tmp_path: Path, repo: Path) -> None:
    from tempergraph.cli.main import main

    out = io.StringIO()
    assert main(["install", "--check", "--json"], cwd=repo, out=out, err=io.StringIO()) == 0
    assert json.loads(out.getvalue().splitlines()[0])["kind"] == "engine"


# -- UPD §2.8 reconcile, PKG-B1 ---------------------------------------------------------------------------------------


def caps() -> dict[str, Any]:
    r = default_registry()
    return {n: r.get(n).capabilities() for n in r.available()}


def test_reconcile_registers_repoints_and_keeps_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    plugin_dir = tmp_path / "claude" / "plugins" / "cache" / "acme" / "release-notes"
    plugin_dir.mkdir(parents=True)
    minimal_package(tmp_path / "v1", "release-notes", "0.1.0").rename(plugin_dir / "0.1.0")
    write(plugin_dir / "other", "README.md", "not a package\n")
    done = reg.reconcile(caps())
    [e] = reg.read_entries()
    assert (e["name"], e["kind"], e["plugin"], e["state"]) == ("release-notes", "plugin", "release-notes@acme", "ok")
    assert e["path"] == str(plugin_dir / "0.1.0") and done[0].ok
    tmp_v2 = minimal_package(tmp_path / "v2", "release-notes", "0.2.0")
    tmp_v2.rename(plugin_dir / "0.2.0")
    (plugin_dir / "0.1.0" / ".orphaned_at").write_text("1\n")
    reg.reconcile(caps())
    [e] = reg.read_entries()
    assert e["path"] == str(plugin_dir / "0.2.0") and e["version"] == "0.2.0"
    assert e["registered_at"]
    import shutil

    shutil.rmtree(plugin_dir)
    reg.reconcile(caps())
    [e] = reg.read_entries()
    assert e["state"] == "missing"  # never lost


def test_reconcile_skips_a_name_already_registered_locally(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    local = minimal_package(tmp_path / "src")
    reg.register(local, caps())
    cached = tmp_path / "claude" / "plugins" / "cache" / "acme" / "release-notes"
    cached.mkdir(parents=True)
    minimal_package(tmp_path / "c").rename(cached / "0.1.0")
    done = reg.reconcile(caps())
    assert [e["kind"] for e in reg.read_entries()] == ["local"]
    assert any("name-taken" in {f.code for f in c.findings} for c in done)
