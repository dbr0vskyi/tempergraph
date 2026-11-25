"""Each test keeps to its own folders, whichever worker runs it (TST-B5).

The nested runs carry the guard variable (`tests/conftest.py`); these tests return at once when it is set, so
they never nest again.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from .conftest import (
    DOCS,
    ENGINE_ROOT,
    SAMPLE_TEST_FILES,
    changed_paths,
    hash_tree,
    is_nested,
    nested_env,
    nested_pytest,
    outcome_counts,
    real_folders_snapshot,
    workflow_names,
)

PAIR = '''\
import json
import os
import time
from pathlib import Path

from tempergraph.store.layout import state_root_path


def test_record(tmp_path):
    name = os.environ["PYTEST_XDIST_WORKER"]
    shared = Path(os.environ["TEMPERGRAPH_PAIR_DIR"])
    row = {"tmp": str(tmp_path), "home": os.environ["TEMPERGRAPH_HOME"], "state": str(state_root_path(tmp_path))}
    (shared / (name + ".json")).write_text(json.dumps(row))
    deadline = time.monotonic() + 30  # both runs are in flight together, or this one fails
    while time.monotonic() < deadline:
        if all((shared / (n + ".json")).exists() for n in ("gw0", "gw1")):
            return
        time.sleep(0.05)
    raise AssertionError("the other worker did not run the test at the same time")
'''


def test_two_concurrent_tests_get_their_own_folders(tmp_path: Path) -> None:  # TST-AC6, AC 1
    if is_nested():
        return
    shared = tmp_path / "shared"
    shared.mkdir()
    module = tmp_path / "test_pair.py"
    module.write_text(PAIR, encoding="utf-8")
    # `--dist each` runs the one test once on each of the two workers, at the same time
    run = nested_pytest("-n", "2", "--dist", "each", str(module), scratch=True,
                        env={"TEMPERGRAPH_PAIR_DIR": str(shared)})
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-1000:]
    a, b = (json.loads((shared / f"{n}.json").read_text()) for n in ("gw0", "gw1"))
    for key in ("tmp", "home", "state"):
        assert a[key] != b[key], key


def test_a_run_on_workers_leaves_the_real_folders_as_they_were() -> None:  # TST-AC7, AC 1
    if is_nested():
        return
    before = real_folders_snapshot()
    run = nested_pytest(*SAMPLE_TEST_FILES)
    assert run.returncode == 0, run.stdout[-3000:]
    assert changed_paths(before, real_folders_snapshot()) == []


# --- tests of any package: the engine's pytest plugin (TST-B7, TST-B8) -----------------------------------------

PLUGIN = "tempergraph.pytest_plugin"
"""The name the entry point is registered under: what `-p no:` takes (TST-B11)."""

PLUGIN_MODULE = "tempergraph_pytest_plugin"
"""The top-level module the entry point resolves to: it imports nothing of the engine package (TST-B12)."""

HOMES = '''\
import json
import os
from pathlib import Path

from tempergraph.store.layout import home_path


def _record(name):
    Path(os.environ["TG_RECORD_DIR"], name + ".json").write_text(json.dumps({"home": str(home_path())}))


def test_first():
    _record("first")


def test_second():
    _record("second")
'''

LOOP = '''\
import os

from tempergraph.improve import child


def test_loop_is_off():
    assert os.environ["TEMPERGRAPH_LOOP"] == "off"
    assert child.mode() == "off"


def test_a_test_sets_the_loop_itself(monkeypatch):
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "inline")
    assert child.mode() == "inline"
'''

WRITES = '''\
from tempergraph.docs import append_jsonl
from tempergraph.observe import rows
from tempergraph.store.layout import ensure_home


def test_writes_the_machine_index_and_stats(tmp_path):
    assert rows.touch_index(tmp_path / "somerepo" / ".tempergraph")
    append_jsonl(rows.stats_path(ensure_home(), "2026-01"), {"row_id": "r-new", "kind": "run"})
'''


def seed_home(base: Path) -> Path:
    """A fake `HOME` with a machine index and a stats file in its `.tempergraph`; returns the `HOME`."""
    home = base / "fakehome"
    folder = home / ".tempergraph"
    (folder / "stats").mkdir(parents=True)
    (folder / "index.json").write_text(
        json.dumps({"schema_version": 1, "roots": [{"path": "/seeded/root/.tempergraph", "repository": "root"}]}),
        encoding="utf-8")
    (folder / "stats" / "2026-01.jsonl").write_text(
        json.dumps({"row_id": "r-seed", "kind": "run", "state_root": "/seeded/root/.tempergraph"}) + "\n",
        encoding="utf-8")
    return home


def install_stand_in(site_dir: Path) -> Path:
    """A stand-in for an installed engine: a folder holding only a `.dist-info` whose `entry_points.txt` is read
    from the engine's `pyproject.toml`. `importlib.metadata` finds it as it finds a pip-installed distribution, so
    the entry-point route itself is exercised with no network and no install. It does not cover the build of the
    wheel. Returns `site_dir`."""
    dist = site_dir / "tempergraph-0.0.0.dist-info"
    if dist.exists():
        return site_dir
    dist.mkdir(parents=True)
    (dist / "METADATA").write_text("Metadata-Version: 2.1\nName: tempergraph\nVersion: 0.0.0\n", encoding="utf-8")
    doc = tomllib.loads((ENGINE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pairs = doc["project"]["entry-points"]["pytest11"]
    (dist / "entry_points.txt").write_text(
        "[pytest11]\n" + "".join(f"{name} = {target}\n" for name, target in pairs.items()), encoding="utf-8")
    return site_dir


def package_command(cwd: Path, *args: str, fake_home: Path, record: Path | None = None,
                    block: bool = False) -> tuple[list[str], dict[str, str]]:
    """The command and environment of `python -m pytest` in `cwd` as a package's own run in an environment where
    the engine is installed: no home folder, loop variable or state root given, the engine's `src` and a stand-in
    install on `PYTHONPATH`, and `HOME` a seeded folder. The plugin is named nowhere: the entry point loads it;
    `block` names it with `no:`."""
    import site

    env = nested_env()
    for var in ("TEMPERGRAPH_HOME", "TEMPERGRAPH_LOOP", "TEMPERGRAPH_STATE_ROOT", "PYTEST_PLUGINS"):
        env.pop(var, None)
    env["HOME"] = str(fake_home)
    env["PYTHONUSERBASE"] = site.getuserbase()  # a changed HOME must not hide the user's installed packages
    stand_in = install_stand_in(fake_home.parent / "site")
    env["PYTHONPATH"] = os.pathsep.join([str(ENGINE_ROOT / "src"), str(stand_in)])
    if record is not None:
        env["TG_RECORD_DIR"] = str(record)
    plugin = ["-p", f"no:{PLUGIN}"] if block else []
    return [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *plugin, *args], env


def package_pytest(cwd: Path, *args: str, fake_home: Path, record: Path | None = None,
                   block: bool = False) -> subprocess.CompletedProcess[str]:
    """`python -m pytest` in `cwd` as a package's own run (`package_command`), run to its end."""
    cmd, env = package_command(cwd, *args, fake_home=fake_home, record=record, block=block)
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          timeout=300, check=False)


def test_a_package_without_a_conftest_gets_a_home_folder_of_its_own(tmp_path: Path) -> None:  # TST-AC9, AC 1
    if is_nested():
        return
    package = tmp_path / "package"
    package.mkdir()
    (package / "test_homes.py").write_text(HOMES, encoding="utf-8")
    fake = seed_home(tmp_path)
    real = (fake / ".tempergraph").resolve()
    temp = Path(tempfile.gettempdir()).resolve()

    here = tmp_path / "records-here"
    here.mkdir()
    run = package_pytest(package, fake_home=fake, record=here)
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-1000:]
    first, second = (Path(json.loads((here / f"{n}.json").read_text())["home"]) for n in ("first", "second"))
    assert first != second
    for home in (first, second):
        assert home.resolve() != real
        assert home.resolve().is_relative_to(temp) and not home.resolve().is_relative_to(fake.resolve())

    # started in another folder, naming the test's path
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    there = tmp_path / "records-there"
    there.mkdir()
    run = package_pytest(elsewhere, str(package / "test_homes.py"), fake_home=fake, record=there)
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-1000:]
    home = Path(json.loads((there / "first.json").read_text())["home"]).resolve()
    assert home != real and home.is_relative_to(temp) and not home.is_relative_to(fake.resolve())


def test_a_package_without_a_conftest_runs_with_the_loop_off(tmp_path: Path) -> None:  # TST-AC10, AC 1
    if is_nested():
        return
    package = tmp_path / "package"
    package.mkdir()
    (package / "test_loop.py").write_text(LOOP, encoding="utf-8")
    run = package_pytest(package, fake_home=seed_home(tmp_path))
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-1000:]
    assert "2 passed" in run.stdout, run.stdout[-1500:]  # the test that sets `inline` itself keeps its value


def test_a_package_run_leaves_the_real_home_folder_as_it_was(tmp_path: Path) -> None:  # TST-AC11, AC 2
    if is_nested():
        return
    package = tmp_path / "package"
    package.mkdir()
    (package / "test_writes.py").write_text(WRITES, encoding="utf-8")
    fake = seed_home(tmp_path)
    home = fake / ".tempergraph"

    before = hash_tree(home)
    run = package_pytest(package, fake_home=fake)
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-1000:]
    assert hash_tree(home) == before

    # the control: with the plugin blocked the same tests write the real home folder, so the check can fail
    run = package_pytest(package, fake_home=fake, block=True)
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-1000:]
    assert hash_tree(home) != before


ROUTE = '''\
import json
import os
from pathlib import Path

from tempergraph.store.layout import home_path


def test_record():
    row = {"home": str(home_path()), "loop": os.environ.get("TEMPERGRAPH_LOOP")}
    Path(os.environ["TG_RECORD_DIR"], "route.json").write_text(json.dumps(row))
'''


def _route(package: Path, fake: Path, record: Path, *, block: bool = False) -> dict[str, str | None]:
    run = package_pytest(package, fake_home=fake, record=record, block=block)
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-1000:]
    return json.loads((record / "route.json").read_text())  # type: ignore[no-any-return]


def test_the_entry_point_route_loads_the_plugin_in_an_installed_environment(tmp_path: Path) -> None:
    # TST-AC15, AC 5, AC 2: no `-p` names the plugin; the entry point of the stand-in install loads it
    if is_nested():
        return
    package = tmp_path / "package"
    package.mkdir()
    (package / "test_route.py").write_text(ROUTE, encoding="utf-8")
    fake = seed_home(tmp_path)
    record = tmp_path / "records"
    record.mkdir()
    seen = _route(package, fake, record)
    home = Path(str(seen["home"])).resolve()
    assert home != (fake / ".tempergraph").resolve()
    assert home.is_relative_to(Path(tempfile.gettempdir()).resolve()) and not home.is_relative_to(fake.resolve())
    assert seen["loop"] == "off"


def test_blocking_the_plugin_switches_the_isolation_off(tmp_path: Path) -> None:  # TST-AC16, AC 5
    if is_nested():
        return
    package = tmp_path / "package"
    package.mkdir()
    (package / "test_route.py").write_text(ROUTE, encoding="utf-8")
    fake = seed_home(tmp_path)
    blocked = tmp_path / "records-blocked"
    blocked.mkdir()
    seen = _route(package, fake, blocked, block=True)
    assert Path(str(seen["home"])).resolve() == (fake / ".tempergraph").resolve()
    assert seen["loop"] is None
    again = tmp_path / "records-again"
    again.mkdir()
    seen = _route(package, fake, again)  # the same folder with no option is isolated again
    assert Path(str(seen["home"])).resolve() != (fake / ".tempergraph").resolve()
    assert seen["loop"] == "off"


SCOPES = '''\
import json
import os
from pathlib import Path

import pytest

from tempergraph.store.layout import home_path


def _record(name):
    row = {"home": str(home_path()), "loop": os.environ.get("TEMPERGRAPH_LOOP")}
    Path(os.environ["TG_RECORD_DIR"], name + ".json").write_text(json.dumps(row))


_record("import")


@pytest.fixture(scope="session", autouse=True)
def _session_scope():
    _record("session")


@pytest.fixture(scope="module", autouse=True)
def _module_scope():
    _record("module")


class TestScopes:
    @pytest.fixture(scope="class", autouse=True)
    def _class_scope(self):
        _record("class")

    def test_reads_its_own_home(self):
        _record("test")
'''


def test_code_outside_the_tests_gets_a_session_home_and_the_loop_off(tmp_path: Path) -> None:
    # TST-AC12, TST-AC14, AC 2
    if is_nested():
        return
    package = tmp_path / "package"
    package.mkdir()
    (package / "test_scopes.py").write_text(SCOPES, encoding="utf-8")
    fake = seed_home(tmp_path)
    record = tmp_path / "records"
    record.mkdir()
    run = package_pytest(package, fake_home=fake, record=record)
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-1000:]
    seen = {n: json.loads((record / f"{n}.json").read_text()) for n in ("import", "session", "module", "class", "test")}
    real = (fake / ".tempergraph").resolve()
    temp = Path(tempfile.gettempdir()).resolve()
    for name, row in seen.items():
        home = Path(row["home"]).resolve()
        assert home != real and home.is_relative_to(temp) and not home.is_relative_to(fake.resolve()), name
        assert row["loop"] == "off", name
    for name in ("import", "session", "module", "class"):
        assert seen["test"]["home"] != seen[name]["home"], name


def test_two_runs_started_together_read_two_import_time_homes(tmp_path: Path) -> None:  # TST-AC13, AC 2
    if is_nested():
        return
    package = tmp_path / "package"
    package.mkdir()
    (package / "test_scopes.py").write_text(SCOPES, encoding="utf-8")
    fake = seed_home(tmp_path)
    records = []
    procs = []
    for n in range(2):  # both start before either is waited for
        record = tmp_path / f"records-{n}"
        record.mkdir()
        records.append(record)
        cmd, env = package_command(package, fake_home=fake, record=record)
        procs.append(subprocess.Popen(cmd, cwd=package, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, stdin=subprocess.DEVNULL))
    outputs = [p.communicate(timeout=300)[0] for p in procs]
    for p, out in zip(procs, outputs):
        assert p.returncode == 0, out[-3000:]
    first, second = (json.loads((r / "import.json").read_text())["home"] for r in records)
    assert first != second


def other_copy(base: Path) -> Path:
    """A folder standing for another installed copy of the engine: a `tempergraph` package that is not the
    checkout's, its own copy of the plugin module, and the stand-in install that registers the entry point."""
    folder = base / "other-copy"
    (folder / "tempergraph").mkdir(parents=True)
    (folder / "tempergraph" / "__init__.py").write_text("OTHER_COPY = True\n", encoding="utf-8")
    shutil.copy(ENGINE_ROOT / "src" / f"{PLUGIN_MODULE}.py", folder / f"{PLUGIN_MODULE}.py")
    return install_stand_in(folder)


PROBE = "tests/test_suite_isolation.py::test_the_engine_comes_from_this_checkout"


def test_the_engine_comes_from_this_checkout() -> None:  # TST-AC17, TST-AC18, AC 1 (the probe of the nested runs)
    if not is_nested():
        return
    import tempergraph

    assert Path(tempergraph.__file__).resolve().is_relative_to((ENGINE_ROOT / "src").resolve()), tempergraph.__file__
    assert not hasattr(tempergraph, "OTHER_COPY")


def test_a_run_in_one_process_tests_the_checkout_beside_another_installed_copy(tmp_path: Path) -> None:
    # TST-AC17, AC 1
    if is_nested():
        return
    copy = other_copy(tmp_path)
    run = nested_pytest("-n", "0", "--trace-config", PROBE, env={"PYTHONPATH": str(copy)})
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-1000:]
    assert outcome_counts(run.stdout) == {"passed": 1}, run.stdout[-1500:]
    registered = [ln for ln in run.stdout.splitlines() if PLUGIN_MODULE in ln and "registered" in ln]
    assert any(copy.name in ln for ln in registered), run.stdout[-3000:]  # the entry point was registered


def test_a_run_on_workers_tests_the_checkout_beside_another_installed_copy(tmp_path: Path) -> None:
    # TST-AC18, AC 1
    if is_nested():
        return
    copy = other_copy(tmp_path)
    run = nested_pytest("-n", "2", "--dist", "each", PROBE, env={"PYTHONPATH": str(copy)})
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-1000:]
    assert outcome_counts(run.stdout) == {"passed": 2}, run.stdout[-1500:]


def test_the_install_declares_the_plugin_under_the_pytest_entry_point() -> None:  # TST-AC15, AC 5
    doc = tomllib.loads((ENGINE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert doc["project"]["entry-points"]["pytest11"] == {PLUGIN: PLUGIN_MODULE}
    src = ENGINE_ROOT / "src"
    module = src / f"{PLUGIN_MODULE}.py"
    assert module.is_file()
    assert not (src / "tempergraph" / "pytest_plugin.py").exists()
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):  # loading it imports no engine code (TST-B12)
        names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
            [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
        for name in names:
            assert not name.startswith("tempergraph"), name


def test_the_specs_state_the_isolation_and_the_verb_without_naming_a_workflow() -> None:  # AC 4
    specs = DOCS / "specs"
    suite = (specs / "test-suite.spec.md").read_text(encoding="utf-8")
    stats = (specs / "central-run-stats.spec.md").read_text(encoding="utf-8")
    cli = (specs / "engine-cli.spec.md").read_text(encoding="utf-8")
    for n in range(7, 13):
        assert f"### TST-B{n} " in suite
    for n in range(17, 25):
        assert f"### CST-B{n} " in stats
    assert "`-p no:tempergraph.pytest_plugin`" in suite
    assert "where the engine is installed" in suite
    assert "the entry stays until `stats forget` removes it (CST-B17)" in stats
    assert "`stats flush`, `stats sync` and `stats forget`" in cli
    names = workflow_names()
    assert names
    for name in names:
        for text in (suite, stats):
            assert name not in text, name
