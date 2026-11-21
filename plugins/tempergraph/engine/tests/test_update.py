"""`update`: the plan, the install beside the current engine, the switch, rollback, `--prune-engines`, and
registered workflows through an update (UPD §2.3 to §2.6, §2.8, UPD-B1 to B8, UPD-AC-1, AC-3, AC-4, AC-6, AC-7).
No test installs from an index: the builder is a stand-in."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any

import pytest

from tempergraph import constants
from tempergraph.executors.registry import default_registry
from tempergraph.install import environment as envmod
from tempergraph.install import update as upd
from tempergraph.package import registry as reg
from tempergraph.release import release
from tempergraph.store import migrate

from .conftest import ENGINE_ROOT, hash_tree
from .fixtures.packages import minimal_package, write
from .test_install import LinkBuilder, run_install

KEYS = {
    "engine": {"kind", "says", "decision", "state", "current", "target", "digest"},
    "extras": {"kind", "says", "name", "range", "state"},
    "live": {"kind", "says", "thread_id", "pid", "engine", "state_root"},
    "threads": {"kind", "says", "state_root", "pinned", "reasons"},
    "store": {"kind", "says", "path", "from_layout", "backup"},
    "workflow": {"kind", "says", "name", "version", "source", "state", "dependencies", "engine_pin", "findings",
                 "remedy"},
    "plugin": {"kind", "says", "plugin", "engine", "match"},
    "summary": {"kind", "says"},
}


def caps() -> dict[str, Any]:
    r = default_registry()
    return {n: r.get(n).capabilities() for n in r.available()}


class UpdateBuilder(LinkBuilder):
    """Reports the staged release's version, and reconciles in-process with a scripted installer."""

    def __init__(self, version: str, fail: str | None = None, broken: tuple[str, ...] = (),
                 conflicts: tuple[str, ...] = ()) -> None:
        super().__init__(fail)
        self.version, self.broken, self.conflicts = version, broken, conflicts
        self.installed: list[tuple[str, list[str]]] = []

    def self_check(self, env: Path) -> dict[str, Any]:
        self.calls.append("self_check")
        if self.fail == "self_check":
            raise envmod.InstallFailed("self-check failed (1)")
        return {"schema_version": 1, "engine_version": self.version, "executors": {"claude": "ok"}}

    def reconcile(self, env: Path, previous: str | None = None) -> dict[str, Any]:
        self.calls.append(f"reconcile:{previous}")
        if self.fail == "reconcile":
            return {"error": "reconcile failed (1)"}

        def installer(name: str, lines: list[str]) -> str | None:
            self.installed.append((name, lines))
            return "pip install failed (1): conflict" if name in self.conflicts else None

        for name in self.broken:  # the new release tightens validation for these
            e = next(e for e in reg.read_entries() if e["name"] == name)
            (Path(e["path"]) / "prompts" / "draft.md").unlink()
        done = reg.after_update(caps(), previous=previous, engine=env.name, installer=installer)
        return {"schema_version": 1, "workflows": [
            {**{k: c.entry.get(k) for k in ("name", "kind", "state", "version", "engine_pin", "dependencies")},
             "findings": [f.code for f in c.findings]} for c in done]}


def home() -> Path:
    return Path(os.environ["TEMPERGRAPH_HOME"])


def staged(tmp: Path, version: str, body: str = "x = 1\n", **rel: Any) -> Path:
    """A staged engine of another release: a release record and a source file, enough for the plan."""
    engine = tmp / f"plugin-{version}-{abs(hash(body)) % 9999}" / "engine"
    write(engine, "pyproject.toml", f'[project]\nname = "tempergraph"\nversion = "{version}"\n')
    write(engine, "src/tempergraph/__init__.py", body)
    write(engine, "src/tempergraph/data/release.json", {**release(), "engine_version": version, **rel})
    return engine


def run_update(*argv: str, engine: Path | None, builder: Any = None, **kw: Any) -> tuple[int, list[dict[str, Any]]]:
    out = io.StringIO()
    code = upd.update(["--json", *argv], builder=builder, out=out, engine=engine, **kw)
    return code, [json.loads(line) for line in out.getvalue().splitlines()]


@pytest.fixture
def installed(tmp_path: Path) -> Path:
    code, _ = run_install(tmp_path)
    assert code == 0
    return home()


def pointer(name: str = "current") -> dict[str, Any]:
    return json.loads((home() / "engines" / f"{name}.json").read_text())


# -- the plan and the report (UPD §2.3 step 2, §2.4) ----------------------------------------------------------


def test_plan_decisions(installed: Path, tmp_path: Path) -> None:
    cur = pointer()
    assert upd.plan(installed, ENGINE_ROOT)["decision"] == "up_to_date"
    assert upd.plan(installed, staged(tmp_path, "9.0.0"))["decision"] == "install"
    assert upd.plan(installed, staged(tmp_path, cur["engine_version"], "other = 2\n"))["decision"] == "reinstall"
    assert upd.plan(installed, staged(tmp_path, "0.0.0"))["decision"] == "refused_downgrade"
    assert upd.plan(installed, None)["decision"] == "no_source"
    assert upd.plan(tmp_path / "empty-home", ENGINE_ROOT)["decision"] == "no_engine"


def test_check_is_read_only(installed: Path, tmp_path: Path) -> None:
    """UPD-B6, UPD-AC-3."""
    engine = staged(tmp_path, "9.0.0")
    before = hash_tree(installed)
    b = UpdateBuilder("9.0.0")
    for flag in ("--check", "--dry-run"):
        code, lines = run_update(flag, engine=engine, builder=b)
        assert code == 0 and lines[0]["decision"] == "install" and lines[-1]["kind"] == "summary"
    assert hash_tree(installed) == before and b.calls == []
    code, lines = run_update("--check", engine=ENGINE_ROOT, builder=b)
    assert code == 0 and "nothing to do" in lines[-1]["says"]


def test_downgrade_and_no_engine_are_refused(installed: Path, tmp_path: Path) -> None:
    code, lines = run_update(engine=staged(tmp_path, "0.0.0"), builder=UpdateBuilder("0.0.0"))
    assert code == 2 and lines[0]["decision"] == "refused_downgrade" and "PATH" in lines[0]["says"]
    assert pointer()["engine_version"] == constants.ENGINE_VERSION


def test_every_line_kind_has_a_fixed_key_set(installed: Path, tmp_path: Path) -> None:
    """UPD-AC-4."""
    pkg = minimal_package(tmp_path / "src")
    reg.register(pkg, caps())
    root = tmp_path / "repo" / ".tempergraph"
    write(root, "manifest.json", {"schema_version": 1, "kind": "state_root", "layout": 1})
    write(root, "locks/demo/t1.holder.json", {"pid": os.getpid(), "engine_version": "0.0.1", "engine": "0.0.1-abc"})
    write(root, "runs/demo/t2/engine.json", {"pinned": {"engine": "0.0.1-abc", "reason": "checkpoint_format"}})
    write(installed, "index.json", {"schema_version": 1, "roots": [{"path": str(root)}]})
    engine = staged(tmp_path, "9.0.0", store_layout=2)
    code, lines = run_update(engine=engine, builder=UpdateBuilder("9.0.0"), plugin_version="9.0.0",
                             )
    assert code == 1  # no migration step ships for layout 1 → 2, so nothing is switched
    code, lines = run_update("--check", engine=engine)
    seen = {ln["kind"] for ln in lines}
    assert seen >= {"engine", "extras", "live", "threads", "store", "summary"}
    code, more = run_update(engine=staged(tmp_path, "9.0.1"), builder=UpdateBuilder("9.0.1"), plugin_version="9.0.1")
    assert code == 0
    for ln in [*lines, *more]:
        assert set(ln) == KEYS[ln["kind"]], ln
    assert {ln["kind"] for ln in more} >= {"engine", "workflow", "plugin", "summary"}


# -- install, switch, failure (UPD-B1, B3, AC-1) -----------------------------------------------------------------


def test_update_installs_beside_and_switches(installed: Path, tmp_path: Path) -> None:
    old = pointer()
    b = UpdateBuilder("9.0.0")
    code, lines = run_update("--with", "agent-sdk", engine=staged(tmp_path, "9.0.0"), builder=b)
    assert code == 0, lines
    cur = pointer()
    assert cur["engine_version"] == "9.0.0" and cur["extras"] == ["agent-sdk"] and pointer("previous") == old
    assert Path(old["path"]).is_dir() and (Path(cur["path"]) / ".complete").is_file()
    assert b.calls == ["create", "install:agent-sdk", "self_check", f"reconcile:{Path(old['path']).name}"]
    assert lines[0]["state"] == "installed" and "you are on engine 9.0.0" in lines[-1]["says"]
    # UPD-B3: the same version with other content is a reinstall into a folder of its own
    b2 = UpdateBuilder("9.0.0")
    code, lines = run_update(engine=staged(tmp_path, "9.0.0", "other = 2\n"), builder=b2)
    assert code == 0 and lines[0]["decision"] == "reinstall"
    assert pointer()["path"] != cur["path"] and pointer("previous")["path"] == cur["path"]
    assert b2.calls[1] == "install:agent-sdk"  # the extras the current environment has are kept


@pytest.mark.parametrize("fail", ["create", "install", "self_check"])
def test_a_failed_install_changes_nothing(installed: Path, tmp_path: Path, fail: str) -> None:
    """UPD-B1, UPD-AC-1."""
    before = hash_tree(installed)
    code, lines = run_update(engine=staged(tmp_path, "9.0.0"), builder=UpdateBuilder("9.0.0", fail=fail))
    assert code == 1 and lines[0]["state"] == "failed" and "nothing was switched" in lines[0]["says"]
    assert hash_tree(installed) == before  # the half folder is gone, the pointer and the old engine untouched


def test_a_failed_home_migration_switches_nothing(installed: Path, tmp_path: Path) -> None:
    old = pointer()
    code, lines = run_update(engine=staged(tmp_path, "9.0.0", store_layout=2), builder=UpdateBuilder("9.0.0"))
    assert code == 1 and pointer() == old and not (installed / "engines" / "previous.json").exists()
    assert json.loads((installed / "manifest.json").read_text())["layout"] == 1


def test_a_failed_reconcile_is_reported_and_the_switch_stands(installed: Path, tmp_path: Path) -> None:
    code, lines = run_update(engine=staged(tmp_path, "9.0.0"), builder=UpdateBuilder("9.0.0", fail="reconcile"))
    assert code == 0 and pointer()["engine_version"] == "9.0.0"
    assert any(ln["kind"] == "workflow" and ln["state"] == "error" for ln in lines)


# -- registered workflows (UPD-B7, B8, AC-7) ---------------------------------------------------------------------


def with_dependency(pkg: Path) -> None:
    f = pkg / "workflow" / "pyproject.toml"
    f.write_text(f.read_text().replace("dependencies = []", 'dependencies = ["requests>=2"]'))


def test_registered_workflows_survive_an_update(installed: Path, tmp_path: Path) -> None:
    """UPD-B7 and its table."""
    plain = minimal_package(tmp_path / "src", "plain")
    deps = minimal_package(tmp_path / "src", "with-deps")
    with_dependency(deps)
    tight = minimal_package(tmp_path / "src", "tightened")
    clash = minimal_package(tmp_path / "src", "clashing")
    with_dependency(clash)
    never = minimal_package(tmp_path / "src", "never-worked")
    for pkg in (plain, deps, tight, clash, never):
        reg.register(pkg, caps())
    (never / "prompts" / "draft.md").unlink()  # it is broken before the update
    reg.reinstall(["never-worked"], caps())
    assert {e["name"]: e["state"] for e in reg.read_entries()}["never-worked"] == "not_loaded"
    old = Path(pointer()["path"]).name

    b = UpdateBuilder("9.0.0", broken=("tightened",), conflicts=("clashing",))
    code, lines = run_update(engine=staged(tmp_path, "9.0.0"), builder=b)
    assert code == 0, lines
    entries = {e["name"]: e for e in reg.read_entries()}
    assert set(entries) == {"plain", "with-deps", "tightened", "clashing", "never-worked"}  # none is lost
    new = Path(pointer()["path"]).name
    assert entries["plain"]["state"] == "ok" and entries["plain"]["engine_pin"] is None
    assert entries["with-deps"]["state"] == "ok" and entries["with-deps"]["installed_into"] == [new]
    assert ("with-deps", ["requests>=2"]) in b.installed
    assert entries["tightened"]["state"] == "pinned" and entries["tightened"]["engine_pin"]["engine"] == old
    assert entries["clashing"]["engine_pin"]["reason"] == "dependency_conflict"
    assert entries["never-worked"]["state"] == "not_loaded" and entries["never-worked"]["engine_pin"] is None
    by = {ln["name"]: ln for ln in lines if ln["kind"] == "workflow"}
    assert by["tightened"]["remedy"] == "tempergraph upgrade tightened" and "keeps working" in by["tightened"]["says"]
    assert "2 workflow(s) stay on the previous engine" in lines[-1]["says"]

    # UPD-B8: the pin clears itself at the next reinstall after the workflow validates again
    (tight / "prompts" / "draft.md").write_text("Write release notes for {request} into notes.md.\n")
    reg.reinstall(["tightened"], caps())
    fixed = {e["name"]: e for e in reg.read_entries()}["tightened"]
    assert fixed["state"] == "ok" and fixed["engine_pin"] is None


def test_a_bad_requirement_never_reaches_the_installer(installed: Path, tmp_path: Path) -> None:
    pkg = minimal_package(tmp_path / "src", "odd")
    reg.register(pkg, caps())
    f = pkg / "workflow" / "pyproject.toml"
    f.write_text(f.read_text().replace("dependencies = []", 'dependencies = ["requests; rm -rf /"]'))
    b = UpdateBuilder("9.0.0")
    run_update(engine=staged(tmp_path, "9.0.0"), builder=b)
    assert b.installed == []
    assert {e["name"]: e for e in reg.read_entries()}["odd"]["state"] in ("pinned", "not_loaded")


# -- rollback and prune (UPD-B5, UPD §2.6, AC-6) ------------------------------------------------------------------


def test_rollback_swaps_the_pointers(installed: Path, tmp_path: Path) -> None:
    old = pointer()
    assert run_update("--rollback", engine=None)[0] == 2  # nothing to roll back to yet
    run_update(engine=staged(tmp_path, "9.0.0"), builder=UpdateBuilder("9.0.0"))
    new = pointer()
    code, lines = run_update("--rollback", engine=None)
    assert code == 0 and lines[-1]["state"] == "rolled_back"
    assert pointer()["path"] == old["path"] and pointer("previous")["path"] == new["path"]


def test_rollback_across_a_layout_change(installed: Path, tmp_path: Path) -> None:
    """UPD-B5."""
    run_update(engine=staged(tmp_path, "9.0.0"), builder=UpdateBuilder("9.0.0"))
    root = tmp_path / "repo" / ".tempergraph"
    write(root, "manifest.json", {"schema_version": 1, "kind": "state_root", "layout": 1})
    write(root, "config/settings.json", {"old": True})
    write(installed, "index.json", {"schema_version": 1, "roots": [{"path": str(root)}]})

    def step(r: Path) -> None:
        (r / "config" / "settings.json").write_text('{"new": true}')

    steps = {1: migrate.Step(from_layout=1, kind="breaking", apply=step, touches=lambda r: ["config/settings.json"])}
    assert migrate.migrate(root, target=2, engine="9.0.0", steps=steps) == [1]
    code, lines = run_update("--rollback", engine=None)
    assert code == 2 and str(root) in lines[0]["says"] and "--restore-backups" in lines[-1]["says"]
    assert pointer()["engine_version"] == "9.0.0"
    code, lines = run_update("--rollback", "--restore-backups", engine=None)
    assert code == 0 and pointer()["engine_version"] == constants.ENGINE_VERSION
    assert json.loads((root / "config" / "settings.json").read_text()) == {"old": True}
    assert json.loads((root / "manifest.json").read_text())["layout"] == 1


def test_rollback_is_refused_once_a_run_wrote_to_the_migrated_store(installed: Path, tmp_path: Path) -> None:
    run_update(engine=staged(tmp_path, "9.0.0"), builder=UpdateBuilder("9.0.0"))
    root = tmp_path / "repo" / ".tempergraph"
    write(root, "manifest.json", {"schema_version": 1, "kind": "state_root", "layout": 1})
    write(installed, "index.json", {"schema_version": 1, "roots": [{"path": str(root)}]})
    steps = {1: migrate.Step(from_layout=1, kind="breaking", apply=lambda r: None)}
    migrate.migrate(root, target=2, engine="9.0.0", steps=steps)
    log = write(root, "runs/demo/t1/run.jsonl", "{}\n")
    os.utime(log, (log.stat().st_atime, log.stat().st_mtime + 60))
    code, lines = run_update("--rollback", "--restore-backups", engine=None)
    assert code == 2 and "written to since" in lines[-1]["says"] and pointer()["engine_version"] == "9.0.0"


def test_prune_never_removes_a_kept_engine(installed: Path, tmp_path: Path) -> None:
    """UPD-AC-6."""
    eng = installed / "engines"
    for name in ("1.0.0-aaaaaaaaaaaa", "1.1.0-bbbbbbbbbbbb", "1.2.0-cccccccccccc", "1.3.0-dddddddddddd"):
        write(eng / name, ".complete", "x\n")
    run_update(engine=staged(tmp_path, "9.0.0"), builder=UpdateBuilder("9.0.0"))
    root = tmp_path / "repo" / ".tempergraph"
    write(root, "manifest.json", {"schema_version": 1, "layout": 1})
    write(root, "locks/demo/t1.holder.json", {"pid": os.getpid(), "engine": "1.0.0-aaaaaaaaaaaa"})
    write(root, "runs/demo/t2/engine.json", {"pinned": {"engine": "1.1.0-bbbbbbbbbbbb", "reason": "checkpoint_format"}})
    write(installed, "index.json", {"schema_version": 1, "roots": [{"path": str(root)}]})
    pkg = minimal_package(tmp_path / "src")
    reg.register(pkg, caps())
    entries = reg.read_entries()
    entries[0]["engine_pin"] = {"engine": "1.2.0-cccccccccccc", "reason": "invalid", "since": "x"}
    reg.write_entries(entries)
    code, lines = run_update("--prune-engines", "--dry-run", engine=None)
    assert code == 0 and (eng / "1.3.0-dddddddddddd").is_dir()
    code, lines = run_update("--prune-engines", engine=None)
    left = sorted(p.name for p in eng.iterdir() if p.is_dir())
    assert left == sorted(["1.0.0-aaaaaaaaaaaa", "1.1.0-bbbbbbbbbbbb", "1.2.0-cccccccccccc",
                           Path(pointer()["path"]).name, Path(pointer("previous")["path"]).name])
    removed = [ln["engine"] for ln in lines if ln["state"] == "removed"]
    assert removed == ["1.3.0-dddddddddddd"]
    assert {ln["engine"]: ln["reason"] for ln in lines if ln["state"] == "kept"}["1.0.0-aaaaaaaaaaaa"].startswith("live run")
