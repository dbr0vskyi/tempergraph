"""How the engine's own suite is spread over processes (TST-B1, TST-B2, TST-B3, TST-B6).

Each test starts a nested `python -m pytest` with the engine folder as working directory and the project's own
configuration over a small generated module of twelve trivial tests. The nested runs carry the guard variable
(`tests/conftest.py`), and these tests return at once when it is set, so they never nest again.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

import pytest

from .conftest import ENGINE_ROOT, is_nested, nested_pytest, outcome_counts

TWELVE = 12
# `-vv`: the project's addopts carry `-q`, so a single `-v` would still print dots, not one line per test.
VERBOSE = "-vv"


@pytest.fixture(scope="module")
def twelve(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("twelve") / "test_twelve.py"
    path.write_text(
        "import time\n\n" + "".join(f"def test_t{i}():\n    time.sleep(0.2)\n\n" for i in range(TWELVE)),
        encoding="utf-8",
    )
    return path


def _prefixes(output: str) -> set[str]:
    return set(re.findall(r"\[(gw\d+)\]", output))


def test_default_run_spreads_the_tests_over_workers(twelve: Path) -> None:  # TST-AC1, AC 1
    if is_nested():
        return
    expected = min(os.cpu_count() or 1, 4)
    run = nested_pytest(VERBOSE, str(twelve), scratch=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert outcome_counts(run.stdout) == {"passed": TWELVE}
    prefixes = _prefixes(run.stdout)
    if expected < 2:  # one processor: one process, no worker prefix
        assert not prefixes
    else:
        assert 2 <= len(prefixes) <= expected, run.stdout
    assert len(prefixes) <= 4


def test_n_zero_runs_every_test_in_one_process(twelve: Path) -> None:  # TST-AC2, AC 1
    if is_nested():
        return
    run = nested_pytest("-n", "0", VERBOSE, str(twelve), scratch=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert not _prefixes(run.stdout)
    assert outcome_counts(run.stdout) == {"passed": TWELVE}


def test_a_missing_runner_runs_one_process_and_names_the_extra(twelve: Path) -> None:  # TST-AC3, AC 1
    if is_nested():
        return
    run = nested_pytest("-p", "no:xdist", "--collect-only", "-q", str(twelve), scratch=True)
    out = run.stdout + run.stderr
    assert run.returncode == 0, out
    assert "unrecognized arguments" not in out and "no such option" not in out
    assert "pytest-xdist" in out and "dev" in out
    assert not _prefixes(out)
    # and the tests do run, in one process, with the runner switched off
    ran = nested_pytest("-p", "no:xdist", VERBOSE, str(twelve), scratch=True)
    assert ran.returncode == 0 and not _prefixes(ran.stdout) and outcome_counts(ran.stdout) == {"passed": TWELVE}


def test_the_dev_extra_lists_the_runner() -> None:  # TST-AC8, AC 1
    if is_nested():
        return
    data = tomllib.loads((ENGINE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev = data["project"]["optional-dependencies"]["dev"]
    assert any(re.match(r"pytest-xdist\b", dep) for dep in dev), dev
