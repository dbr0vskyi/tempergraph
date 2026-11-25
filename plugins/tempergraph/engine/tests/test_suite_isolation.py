"""Each test keeps to its own folders, whichever worker runs it (TST-B5).

The nested runs carry the guard variable (`tests/conftest.py`); these tests return at once when it is set, so
they never nest again.
"""

from __future__ import annotations

import json
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


def package_pytest(cwd: Path, *args: str, fake_home: Path, record: Path | None = None,
                   block: bool = False) -> subprocess.CompletedProcess[str]:
    """`python -m pytest` in `cwd` as a package's own run: no home folder, loop variable or state root given, the
    engine's `src` on `PYTHONPATH`, and `HOME` a seeded folder. The plugin is named with `-p` (an environment
    installed before it existed has no entry point); `block` names it with `no:` instead."""
    import site

    env = nested_env()
    for var in ("TEMPERGRAPH_HOME", "TEMPERGRAPH_LOOP", "TEMPERGRAPH_STATE_ROOT", "PYTEST_PLUGINS"):
        env.pop(var, None)
    env["HOME"] = str(fake_home)
    env["PYTHONUSERBASE"] = site.getuserbase()  # a changed HOME must not hide the user's installed packages
    env["PYTHONPATH"] = str(ENGINE_ROOT / "src")
    if record is not None:
        env["TG_RECORD_DIR"] = str(record)
    plugin = ["-p", f"no:{PLUGIN}"] if block else ["-p", PLUGIN]
    return subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *plugin, *args], cwd=cwd,
                          env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=300,
                          check=False)


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


def test_the_install_declares_the_plugin_under_the_pytest_entry_point() -> None:  # TST-AC9, TST-AC10
    doc = tomllib.loads((ENGINE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert doc["project"]["entry-points"]["pytest11"] == {PLUGIN: PLUGIN}
    assert (ENGINE_ROOT / "src" / "tempergraph" / "pytest_plugin.py").is_file()


def test_the_specs_state_the_isolation_and_the_verb_without_naming_a_workflow() -> None:  # AC 4
    specs = DOCS / "specs"
    suite = (specs / "test-suite.spec.md").read_text(encoding="utf-8")
    stats = (specs / "central-run-stats.spec.md").read_text(encoding="utf-8")
    cli = (specs / "engine-cli.spec.md").read_text(encoding="utf-8")
    for ident in ("TST-B7", "TST-B8"):
        assert f"### {ident} " in suite
    for n in range(17, 22):
        assert f"### CST-B{n} " in stats
    assert "`stats flush`, `stats sync` and `stats forget`" in cli
    names = workflow_names()
    assert names
    for name in names:
        for text in (suite, stats):
            assert name not in text, name
