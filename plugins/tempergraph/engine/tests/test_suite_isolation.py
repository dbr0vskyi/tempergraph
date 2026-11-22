"""Each test keeps to its own folders, whichever worker runs it (TST-B5).

The nested runs carry the guard variable (`tests/conftest.py`); these tests return at once when it is set, so
they never nest again.
"""

from __future__ import annotations

import json
from pathlib import Path

from .conftest import SAMPLE_TEST_FILES, changed_paths, is_nested, nested_pytest, real_folders_snapshot

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
